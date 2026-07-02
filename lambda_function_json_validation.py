import json
import os

import boto3
from botocore.paginate import PageIterator
from validate_farm_survey_jsons import validate_json, load_json, print_errors


def s3_setup():
    s3_client = boto3.client("s3")
    aws_jsons_bucket = os.environ["SOURCE_JSONS_BUCKET"]
    aws_jsons_bucket_prefix = os.environ["SOURCE_JSONS_BUCKET_PREFIX"]

    def list_jsons_in_bucket() -> PageIterator:
        paginator = s3_client.get_paginator("list_objects_v2")
        return paginator.paginate(Bucket=aws_jsons_bucket, Prefix=f"{aws_jsons_bucket_prefix}/")

    return s3_client, aws_jsons_bucket, list_jsons_in_bucket, aws_jsons_bucket_prefix


def get_and_validate_jsons(s3_client, bucket_name, aws_jsons_bucket_prefix, json_schema_data, json_names: list[str]):
    error_messages = []
    for json_name in json_names:
        if not json_name.endswith("/"):
            response = s3_client.get_object(Bucket=bucket_name, Key=json_name)
            json_metadata = json.loads(response["Body"].read().decode("utf-8"))
            error_message = validate_json(json_name, json_metadata, json_schema_data)
            if error_message is not None:
                error_messages.append(error_message)

    return error_messages


def lambda_handler(event, context):
    s3_client, bucket, list_jsons_in_bucket, aws_jsons_bucket_prefix = s3_setup()
    json_schema_data = load_json("preliminary_json_schema_validation.json")

    for page in list_jsons_in_bucket():
        page_results: list[dict] = page["Contents"]
        json_names = [result["Key"] for result in page_results]
        error_messages = get_and_validate_jsons(s3_client, bucket, aws_jsons_bucket_prefix, json_schema_data,
                                                json_names)
        if error_messages:
            print_errors(error_messages)
        else:
            print(f"\nJSON files validated successfully")
