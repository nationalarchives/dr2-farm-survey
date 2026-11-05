import os

import sqlite3
import boto3
from azure.identity import ClientAssertionCredential
from azure.storage.blob import BlobServiceClient
import datetime


db_name = lambda start_date: f"farm-survey-{start_date}.db"

def token_callback():
    sts = boto3.client("sts")
    res = sts.get_web_identity_token(
        Audience=["api://AzureADTokenExchange"],
        DurationSeconds=300,
        SigningAlgorithm="RS256"
    )

    return res["WebIdentityToken"]

def get_container_client():
    account_url = os.environ["AZURE_ACCOUNT_URL"]
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    azure_fs_container = os.environ["AZURE_FS_CONTAINER"]

    credential = ClientAssertionCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        func=token_callback,
    )

    blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)

    return blob_service_client.get_container_client(azure_fs_container)

def download_blob_paths_and_names(pages, cursor, conn):
    total_files_retrieved = 0
    for page_no, page in enumerate(pages):
        blob_paths_and_names = []
        for blob_path in page:
            if blob_path.endswith(".tif"):
                blob_paths_and_names.append((blob_path, blob_path.split("/")[-1]))

        cursor.executemany("INSERT INTO farm_survey_paths (blobPath, originalName) VALUES (?, ?)",
                           blob_paths_and_names)
        conn.commit()
        blob_paths_and_names_retrieved = len(blob_paths_and_names)
        total_files_retrieved += blob_paths_and_names_retrieved
        print(f"Page {page_no + 1} - {total_files_retrieved:,} blob paths and names written so far")
    return total_files_retrieved

def upload_to_s3(db_path, db_name):
    s3_client = boto3.client("s3")
    s3_bucket = os.environ["SOURCE_BUCKET"]
    s3_key = f"{os.environ["BLOB_PATHS_PREFIX"]}/{db_name}"
    

    try:
        s3_client.upload_file(db_path, s3_bucket, s3_key)
        print(f"Database successfully updated in s3, here: {s3_bucket}/{s3_key}")
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        raise e

def lambda_handler(event, context):
    start_date = datetime.datetime.now()
    container_client = get_container_client()
    pages = container_client.list_blob_names().by_page()

    database_name = db_name(start_date)
    ephemeral_storage_db_path = f"/tmp/{database_name}"

    conn = sqlite3.connect(ephemeral_storage_db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = OFF;")
    cursor.execute("PRAGMA temp_store = MEMORY;")
    cursor.execute("PRAGMA cache_size = -524288;")
    cursor.execute("CREATE TABLE IF NOT EXISTS farm_survey_paths (blobPath, originalName)")
    cursor.execute("BEGIN TRANSACTION;")

    total_files_retrieved = download_blob_paths_and_names(pages, cursor, conn)

    time_taken = datetime.datetime.now() - start_date
    mins, seconds = divmod(int(time_taken.total_seconds()), 60)
    print(f"\nDatabase populated in {int(mins)} mins {seconds} seconds - {total_files_retrieved} rows written")
    conn.close()

    upload_to_s3(ephemeral_storage_db_path, database_name)
