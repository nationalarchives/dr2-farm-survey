import json
import os

import boto3


def s3_setup():
    s3_client = boto3.client("s3")
    aws_files_bucket = os.environ["AWS_FILES_BUCKET"]

    def list_jsons_in_bucket(prefix):
        response = s3_client.list_objects_v2(
            Bucket=aws_files_bucket,
            Prefix=f"{prefix}/"
        )
        return response["Contents"]

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
    bucket, list_jsons_in_bucket = s3_setup()
    send_to_sqs = sqs_setup()

    for object_info in list_jsons_in_bucket(prefix="original_replica_jsons"):
        key = object_info["Key"]
        if not key.endswith("/"):
            uri = f"s3://{bucket}/{object_info["Key"]}"
            message_body: str = json.dumps({"metadataLocation": uri})
            send_to_sqs(message_body)
