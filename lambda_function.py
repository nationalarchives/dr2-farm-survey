import hashlib
import io
import json
import math
import os
import sqlite3
from collections import Counter
from itertools import groupby
from subprocess import Popen, PIPE
from sys import platform
from urllib.parse import urlparse

import boto3
from azure.identity import ClientAssertionCredential
from azure.storage.blob import StorageStreamDownloader, ContainerClient, BlobServiceClient

type StreamDownloader = StorageStreamDownloader[bytes] | StorageStreamDownloader[str]
file_id_key = "file_id"
file_name_key = "file_name"
sequence_no_key = "sequence_no"
image_magick_loc = "/opt/bin/convert" if platform == "linux" else "/usr/local/bin/magick"
new_file_extension = "jpg"
jpg_reduction = "25%"


def token_callback():
    sts_client = boto3.client("sts")
    response = sts_client.get_web_identity_token(
        Audience=["api://AzureADTokenExchange"],
        DurationSeconds=300,
        SigningAlgorithm="RS256",
    )

    return response["WebIdentityToken"]


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


def s3_setup():
    s3_client = boto3.client("s3")
    aws_files_bucket = os.environ["AWS_FILES_BUCKET"]

    def upload_to_s3(bytes_to_write, file_name):
        body = io.BytesIO(bytes_to_write)
        s3_client.upload_fileobj(body, aws_files_bucket, file_name)

    return s3_client, upload_to_s3


def get_json_metadata(s3_client, bucket, key):
    response = s3_client.get_object(Bucket=bucket, Key=key)  # needs to be replaced with Azure?
    json_metadata = json.loads(response["Body"].read().decode("utf-8"))
    return json_metadata


def validate_metadata(all_image_metadata):
    metadata_grouped_by_name = {name: list(metadata) for name, metadata in
                                groupby(all_image_metadata, lambda m: m[file_name_key])}
    metadata_grouped_by_id = Counter(metadata[file_id_key] for metadata in all_image_metadata)

    duplicate_ids = [fid for fid, count in metadata_grouped_by_id.items() if count > 1]
    if len(duplicate_ids) > 0:
        ids = ", ".join(duplicate_ids)
        raise Exception(f"These image file_ids are duplicated in the metadata file: {ids}")

    ids_of_files_with_same_name = [
        ", ".join([image[file_id_key] for image in images_with_same_name])
        for name, images_with_same_name in metadata_grouped_by_name.items() if len(images_with_same_name) > 1
    ]
    if len(ids_of_files_with_same_name) > 0:
        ids = [f"{n}. {ids}" for n, ids in enumerate(ids_of_files_with_same_name, 1)]
        raise Exception(f"""There are images with the same 'file_name':\n{"\n".join(ids)}""")


def get_azure_file_stream(container_client: ContainerClient, blob_path: str) -> StreamDownloader:
    blob_client = container_client.get_blob_client(blob_path)
    return blob_client.download_blob()


def convert_to_jpg(tiff_stream: StreamDownloader) -> bytes:
    process: Popen[bytes] = Popen(
        [image_magick_loc, "tiff:-", "-resize", jpg_reduction, f"{new_file_extension}:-"], stdin=PIPE, stdout=PIPE,
        stderr=PIPE
    )
    jpg_bytes, err = process.communicate(input=tiff_stream.read())

    if process.returncode != 0:
        raise RuntimeError(f"Conversion from TIFF to JPG failed: {err.decode()}")
    return jpg_bytes


def lambda_handler(event, context):
    s3_client, upload_to_s3 = s3_setup()
    container_client = get_container_client()

    batch_db_name = os.environ["BATCH_DB_NAME"]

    asset_source = "DigitalSurrogate"

    for record in event["Records"]:
        body: dict[str, str] = json.loads(record["body"])
        metadata_location = body["metadataLocation"]
        metadata_uri = urlparse(metadata_location)
        bucket = metadata_uri.netloc
        key = metadata_uri.path[1:]

        json_metadata = get_json_metadata(s3_client, bucket, key)
        all_image_metadata = json_metadata["images"]
        iaid = json_metadata["IAID"]
        replica_id = json_metadata["replicaId"]

        validate_metadata(all_image_metadata)
        print(f"Number of images belonging to IAID {iaid} in JSON:", len(all_image_metadata))

        file_ids_not_in_azure = []
        all_image_metadata_by_path = {}
        with sqlite3.connect(f"{batch_db_name}.db") as connection:
            for image_metadata in all_image_metadata:
                file_name = image_metadata[file_name_key]
                file_id = image_metadata[file_id_key]

                blob_cursor = connection.cursor()
                blob_cursor.execute(
                    f"SELECT file_path FROM {batch_db_name} WHERE {file_name_key} = ?;",
                    (file_name,)
                )
                blob_info = blob_cursor.fetchone()

                if not blob_info:
                    file_ids_not_in_azure.append(file_id)
                else:
                    blob_path = blob_info[0]
                    all_image_metadata_by_path[blob_path] = image_metadata

        if len(file_ids_not_in_azure) > 0:
            raise Exception(f"{len(file_ids_not_in_azure)} file(s) in the JSON were not found in Azure for IAID"
                            f" {iaid}. These are the file_ids: {", ".join(file_ids_not_in_azure)}")

        numbered_replica_file_metadata = {}
        for blob_path, image_metadata in all_image_metadata_by_path.items():
            file_name = image_metadata[file_name_key]
            file_id = image_metadata[file_id_key]
            sequence_no = image_metadata[sequence_no_key]

            tiff_blob_stream: StreamDownloader = get_azure_file_stream(container_client, blob_path)
            jpg_bytes = convert_to_jpg(tiff_blob_stream)
            new_file_name = f"{file_id}.{new_file_extension}"
            upload_to_s3(jpg_bytes, f"files/{iaid}/{new_file_name}")

            file_size_kb = math.ceil(len(jpg_bytes) / 1000)

            numbered_replica_file_metadata[sequence_no] = {
                "checkSum": hashlib.sha256(jpg_bytes).hexdigest(),
                "format": new_file_extension,
                "name": new_file_name,
                "originalName": file_name,
                "size": file_size_kb
            }

        numbered_replica_file_metadata_sorted = dict(sorted(numbered_replica_file_metadata.items()))
        sorted_replica_file_metadata = list(numbered_replica_file_metadata_sorted.values())
        replica_metadata = {
            "files": sorted_replica_file_metadata,
            "replicaId": replica_id,
            "origination": asset_source,
            "totalSize": sum(file["size"] for file in sorted_replica_file_metadata)
        }

        metadata_bytes = json.dumps(replica_metadata).encode("utf-8")
        upload_to_s3(metadata_bytes, f"metadata/{iaid}.json")
