import os

import sqlite3
import boto3
from azure.identity import ClientAssertionCredential
from azure.storage.blob import BlobServiceClient

account_url = os.environ["AZURE_ACCOUNT_URL"]
tenant_id = os.environ["AZURE_TENANT_ID"]
client_id = os.environ["AZURE_CLIENT_ID"]


def assertion_callback():
    sts = boto3.client("sts")
    res = sts.get_web_identity_token(Audience=["api://AzureADTokenExchange"], DurationSeconds=300, SigningAlgorithm="RS256")
    return res["WebIdentityToken"]


credential = ClientAssertionCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    func=assertion_callback
)

blob_service_client = BlobServiceClient(account_url=account_url, credential=credential)
container_client = blob_service_client.get_container_client("farms")
pages = container_client.list_blob_names().by_page()

conn = sqlite3.connect("farm-survey.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS farm_survey_paths (filePath, originalName)")

total_files_retrieved = 0
for page_no, page in enumerate(pages):
    file_paths_and_names = []
    for file_path in page:
        if file_path.endswith(".tif"):
            file_paths_and_names.append((file_path, file_path.split("/")[-1]))

    cursor.executemany("INSERT INTO farm_survey_paths (filePath, originalName) VALUES (?, ?)",
                       file_paths_and_names)
    conn.commit()
    file_paths_and_names_retrieved = len(file_paths_and_names)
    total_files_retrieved += file_paths_and_names_retrieved
    print(f"Page {page_no + 1} - {total_files_retrieved} file paths and names written so far")
conn.close()
