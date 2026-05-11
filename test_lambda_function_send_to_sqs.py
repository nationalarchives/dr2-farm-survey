import os
import unittest
from unittest.mock import patch, MagicMock

import lambda_function_send_to_sqs


class TestLambdaFunction(unittest.TestCase):
    @patch.dict(os.environ, {"AWS_FILES_BUCKET": "bucket1"}, clear=True)
    @patch("lambda_function_send_to_sqs.boto3")
    def test_list_jsons_in_bucket_should_retrieve_the_files_in_bucket(self, boto3):
        boto3.return_value = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = iter([
            {"Contents": [{"Key": "folder_name/s3_object_1.json"}, {"Key": "folder_name/s3_object_2.json"}]},
            {"Contents": [{"Key": "folder_name/s3_object_3.json"}, {"Key": "folder_name/s3_object_4.json"}]}
        ])
        s3_client = MagicMock()
        s3_client.get_paginator.return_value = paginator
        boto3.client.return_value = s3_client

        aws_files_bucket, list_jsons_in_bucket = lambda_function_send_to_sqs.s3_setup("test_batch1")
        response_iter = list_jsons_in_bucket()

        self.assertEqual("bucket1", aws_files_bucket)
        self.assertEqual([
            {"Contents": [{"Key": "folder_name/s3_object_1.json"}, {"Key": "folder_name/s3_object_2.json"}]},
            {"Contents": [{"Key": "folder_name/s3_object_3.json"}, {"Key": "folder_name/s3_object_4.json"}]}
        ], list(response_iter))
        self.assertEqual("s3", boto3.client.call_args.args[0])
        self.assertEqual("list_objects_v2", s3_client.get_paginator.call_args.args[0])
        self.assertEqual({"Bucket": "bucket1", "Prefix": "test_batch1/"}, paginator.paginate.call_args.kwargs)

    @patch.dict(os.environ, {"QUEUE_URL": "https://sqs.queueurl.com"}, clear=True)
    @patch("lambda_function_send_to_sqs.boto3")
    def test_send_to_sqs_should_upload_file_bytes_to_correct_s3_bucket(self, boto3):
        boto3.return_value = MagicMock()
        sqs_client = MagicMock()
        sqs_client.send_message.return_value = {"Messages": []}
        boto3.client.return_value = sqs_client

        send_to_sqs = lambda_function_send_to_sqs.sqs_setup()
        response = send_to_sqs({"batchName": "test_batch1", "metadataLocation":
            "https://folder_name/an_s3_object.json"})

        self.assertEqual({"Messages": []}, response)
        self.assertEqual("sqs", boto3.client.call_args.args[0])
        self.assertEqual({"MessageBody": {"batchName": "test_batch1", "metadataLocation":
            "https://folder_name/an_s3_object.json"}, "QueueUrl": "https://sqs.queueurl.com"},
                         sqs_client.send_message.call_args.kwargs)

    @patch("lambda_function_send_to_sqs.s3_setup")
    @patch("lambda_function_send_to_sqs.sqs_setup")
    def test_lambda_handler_should_get_the_file_objects_from_the_s3_bucket_and_send_them_to_sqs(self, sqs_setup,
                                                                                                s3_setup):
        list_jsons_in_bucket = MagicMock()
        list_jsons_in_bucket.return_value = iter([
            {"Contents": [{"Key": "folder_name/s3_object_1.json"}, {"Key": "folder_name/s3_object_2.json"}]},
            {"Contents": [{"Key": "folder_name/s3_object_3.json"}, {"Key": "folder_name/s3_object_4.json"}]}
        ])
        s3_setup.return_value = ("bucket1", list_jsons_in_bucket)

        send_to_sqs = MagicMock()
        sqs_setup.return_value = send_to_sqs

        lambda_function_send_to_sqs.lambda_handler({"batchName": "test_batch1"}, None)

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, sqs_setup.call_count)
        self.assertEqual(4, send_to_sqs.call_count)
        call_args = [call.args[0] for call in send_to_sqs.call_args_list]
        self.assertEqual([
            """{"batchName": "test_batch1", "metadataLocation": "s3://bucket1/folder_name/s3_object_1.json"}""",
            """{"batchName": "test_batch1", "metadataLocation": "s3://bucket1/folder_name/s3_object_2.json"}""",
            """{"batchName": "test_batch1", "metadataLocation": "s3://bucket1/folder_name/s3_object_3.json"}""",
            """{"batchName": "test_batch1", "metadataLocation": "s3://bucket1/folder_name/s3_object_4.json"}"""],
            call_args
        )

    @patch("lambda_function_send_to_sqs.s3_setup")
    @patch("lambda_function_send_to_sqs.sqs_setup")
    def test_lambda_handler_should_get_the_objects_from_the_s3_but_not_send_them_to_sqs_if_there_are_no_files(
        self, sqs_setup, s3_setup):
        list_jsons_in_bucket = MagicMock()
        list_jsons_in_bucket.return_value = [{"Key": "folder_name/"}, {"Key": "another_folder_name/"}]
        list_jsons_in_bucket.return_value = iter([
            {"Contents": [{"Key": "folder_name/"}]}, {"Contents": [{"Key": "another_folder_name/"}]}
        ])
        s3_setup.return_value = ("bucket1", list_jsons_in_bucket)

        send_to_sqs = MagicMock()
        sqs_setup.return_value = send_to_sqs

        lambda_function_send_to_sqs.lambda_handler({"batchName": "test_batch1"}, None)

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, sqs_setup.call_count)
        self.assertEqual(0, send_to_sqs.call_count)


if __name__ == '__main__':
    unittest.main()
