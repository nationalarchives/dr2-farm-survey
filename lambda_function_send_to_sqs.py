import json
import os

import boto3
from botocore.paginate import PageIterator
from validate_farm_survey_jsons import validate_json, load_json


def s3_setup(batch_name):
    s3_client = boto3.client("s3")
    aws_files_bucket = os.environ["AWS_FILES_BUCKET"]
    replica_jsons_prefix = batch_name

    def list_jsons_in_bucket() -> PageIterator:
        paginator = s3_client.get_paginator("list_objects_v2")
        return paginator.paginate(Bucket=aws_files_bucket, Prefix=f"{replica_jsons_prefix}/")

    return s3_client, aws_files_bucket, list_jsons_in_bucket


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

def get_and_validate_jsons(s3_client, bucket_name, json_schema_data, json_names: list[str]):
    name_and_json_metadata = []
    for json_name in json_names:
        if not json_name.endswith("/"):
            uri = f"s3://{bucket_name}/{json_name}"
            response = s3_client.get_object(Bucket=bucket_name, Key=uri)
            json_metadata = json.loads(response["Body"].read().decode("utf-8"))
            validate_json(uri, json_metadata, json_schema_data)
            name_and_json_metadata.append((json_name, json_metadata))

    return name_and_json_metadata

def lambda_handler(event, context):
    batch_name_key = "batchName"
    batch_name = event[batch_name_key]
    s3_client, bucket, list_jsons_in_bucket = s3_setup(batch_name)
    send_to_sqs = sqs_setup()
    json_schema_data = load_json("preliminary_json_schema_validation.json")
    all_json_metadata = []

    for page in list_jsons_in_bucket():
        page_results: list[dict] = page["Contents"]
        json_names = [result["Key"] for result in page_results]
        json_metadata = get_and_validate_jsons(s3_client, bucket, json_schema_data, json_names)
        all_json_metadata.extend(json_metadata)

    for (name, json_metadata) in all_json_metadata:
        message_body: str = json.dumps({batch_name_key: batch_name, "jsonName": name, "jsonMetadata": json_metadata})
        send_to_sqs(message_body)
