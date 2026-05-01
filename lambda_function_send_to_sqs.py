import json
import os

import boto3
from botocore.paginate import PageIterator


def s3_setup(batch_name):
    s3_client = boto3.client("s3")
    aws_files_bucket = os.environ["AWS_FILES_BUCKET"]
    replica_jsons_prefix = batch_name

    def list_jsons_in_bucket() -> PageIterator:
        paginator = s3_client.get_paginator("list_objects_v2")
        iterator: PageIterator = paginator.paginate(Bucket=aws_files_bucket, Prefix=f"{replica_jsons_prefix}/")
        return iterator

    return aws_files_bucket, list_jsons_in_bucket


def sqs_setup():
    sqs_client = boto3.client("sqs")
    queue_url = os.environ["QUEUE_URL"]

    def send_to_sqs(message_body: str):
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=message_body
        )
        return response

    return send_to_sqs


def lambda_handler(event, context):
    batch_name_key = "batchName"
    batch_name = event[batch_name_key]
    bucket, list_jsons_in_bucket = s3_setup(batch_name)
    send_to_sqs = sqs_setup()

    for page in list_jsons_in_bucket():
        page_results: list[dict] = page["Contents"]
        json_names = [result["Key"] for result in page_results]

        for json_name in json_names:
            if not json_name.endswith("/"):
                uri = f"s3://{bucket}/{json_name}"
                message_body: str = json.dumps({batch_name_key: batch_name, "metadataLocation": uri})
                send_to_sqs(message_body)
