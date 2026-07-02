import os
import unittest
from unittest.mock import patch, MagicMock

import lambda_function_json_validation


class TestLambdaFunction(unittest.TestCase):
    @patch.dict(os.environ, {"SOURCE_JSONS_BUCKET": "bucket1", "SOURCE_JSONS_BUCKET_PREFIX": "test_batch1"},
                clear=True)
    @patch("lambda_function_json_validation.boto3")
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

        client, aws_files_bucket, list_jsons_in_bucket, prefix = lambda_function_json_validation.s3_setup()
        response_iter = list_jsons_in_bucket()

        self.assertEqual(s3_client, client)
        self.assertEqual("bucket1", aws_files_bucket)
        self.assertEqual([
            {"Contents": [{"Key": "folder_name/s3_object_1.json"}, {"Key": "folder_name/s3_object_2.json"}]},
            {"Contents": [{"Key": "folder_name/s3_object_3.json"}, {"Key": "folder_name/s3_object_4.json"}]}
        ], list(response_iter))
        self.assertEqual("s3", boto3.client.call_args.args[0])
        self.assertEqual("list_objects_v2", s3_client.get_paginator.call_args.args[0])
        self.assertEqual({"Bucket": "bucket1", "Prefix": "test_batch1/"}, paginator.paginate.call_args.kwargs)

    @patch("lambda_function_json_validation.validate_json")
    def test_get_and_validate_jsons_should_retrieve_the_files_in_bucket_and_call_validate_json(self, validate_json):
        validate_json.side_effect = ["An error message", None, None]

        s3_client = MagicMock()
        streaming_body = MagicMock()
        reader = MagicMock()

        reader.decode.return_value = """{"Key": "folder_name/s3_object_1.json"}"""
        streaming_body.read.return_value = reader
        s3_client.get_object.return_value = {
            "Body": streaming_body
        }
        bucket_name = "bucket1"
        prefix = "prefix1"
        json_schema_data = "{'schema': 'data'}"
        json_names = ["name_without_slash.json", "name_without_slash2.json", "name_without_slash3.json",
                      "name_with_slash/"]

        error_messages = lambda_function_json_validation.get_and_validate_jsons(
            s3_client,
            bucket_name,
            prefix,
            json_schema_data,
            json_names
        )

        self.assertEqual(["An error message"], error_messages)
        client_call_kwargs = [call.kwargs for call in s3_client.get_object.call_args_list]
        self.assertEqual([{"Bucket": "bucket1", "Key": "name_without_slash.json"},
                          {"Bucket": "bucket1", "Key": "name_without_slash2.json"},
                          {"Bucket": "bucket1", "Key": "name_without_slash3.json"}],
                         client_call_kwargs)

        validate_json_call_args = [call.args for call in validate_json.call_args_list]
        self.assertEqual([("name_without_slash.json", {"Key": "folder_name/s3_object_1.json"}, "{'schema': 'data'}"),
                          ("name_without_slash2.json", {"Key": "folder_name/s3_object_1.json"}, "{'schema': 'data'}"),
                          ("name_without_slash3.json", {"Key": "folder_name/s3_object_1.json"}, "{'schema': 'data'}")],
                         validate_json_call_args)

    @patch("lambda_function_json_validation.s3_setup")
    @patch("lambda_function_json_validation.load_json")
    @patch("lambda_function_json_validation.get_and_validate_jsons")
    @patch("lambda_function_json_validation.print_errors")
    def test_lambda_handler_should_get_the_file_objects_and_call_get_and_validate_jsons(self, print_errors,
                                                                                        get_and_validate_jsons,
                                                                                        load_json, s3_setup):
        list_jsons_in_bucket = MagicMock()
        list_jsons_in_bucket.return_value = iter([
            {"Contents": [{"Key": "folder_name/s3_object_1.json"}, {"Key": "folder_name/s3_object_2.json"}]},
            {"Contents": [{"Key": "folder_name/s3_object_3.json"}, {"Key": "folder_name/s3_object_4.json"}]}
        ])
        s3_setup.return_value = ("s3_client", "bucket1", list_jsons_in_bucket, "prefix1")
        load_json.return_value = "json_schema_data"

        get_and_validate_jsons.return_value = []
        print_errors.return_value = None

        lambda_function_json_validation.lambda_handler(None, None)

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, load_json.call_count)
        self.assertEqual(2, get_and_validate_jsons.call_count)
        self.assertEqual(0, print_errors.call_count)
        self.assertEqual("preliminary_json_schema_validation.json", load_json.call_args.args[0])
        call_args = [call.args for call in get_and_validate_jsons.call_args_list]
        self.assertEqual(
            [
                ("s3_client", "bucket1", "prefix1", "json_schema_data",
                 ["folder_name/s3_object_1.json", "folder_name/s3_object_2.json"]),
                ("s3_client", "bucket1", "prefix1", "json_schema_data",
                 ["folder_name/s3_object_3.json", "folder_name/s3_object_4.json"])
            ],
            call_args
        )

    @patch("lambda_function_json_validation.s3_setup")
    @patch("lambda_function_json_validation.load_json")
    @patch("lambda_function_json_validation.get_and_validate_jsons")
    @patch("lambda_function_json_validation.print_errors")
    def test_lambda_handler_should_get_the_file_objects_call_get_and_validate_jsons_and_print_errors(self,
                                                                                                     print_errors,
                                                                                                     get_and_validate_jsons,
                                                                                                     load_json,
                                                                                                     s3_setup):
        list_jsons_in_bucket = MagicMock()
        list_jsons_in_bucket.return_value = iter([
            {"Contents": [{"Key": "folder_name/s3_object_1.json"}, {"Key": "folder_name/s3_object_2.json"}]},
            {"Contents": [{"Key": "folder_name/s3_object_3.json"}, {"Key": "folder_name/s3_object_4.json"}]}
        ])
        s3_setup.return_value = ("s3_client", "bucket1", list_jsons_in_bucket, "prefix1")
        load_json.return_value = "json_schema_data"

        get_and_validate_jsons.return_value = ["An error message"]
        print_errors.return_value = None

        lambda_function_json_validation.lambda_handler(None, None)

        self.assertEqual(1, s3_setup.call_count)
        self.assertEqual(1, load_json.call_count)
        self.assertEqual(2, get_and_validate_jsons.call_count)
        self.assertEqual(2, print_errors.call_count)
        self.assertEqual("preliminary_json_schema_validation.json", load_json.call_args.args[0])
        call_args = [call.args for call in get_and_validate_jsons.call_args_list]
        self.assertEqual(
            [
                ("s3_client", "bucket1", "prefix1", "json_schema_data",
                 ["folder_name/s3_object_1.json", "folder_name/s3_object_2.json"]),
                ("s3_client", "bucket1", "prefix1", "json_schema_data",
                 ["folder_name/s3_object_3.json", "folder_name/s3_object_4.json"])
            ],
            call_args
        )
        self.assertEqual(["An error message"], print_errors.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
