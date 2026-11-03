import os
import unittest
from sqlite3 import Cursor, Connection
from unittest.mock import patch, MagicMock
import datetime

import lambda_function_create_azure_blob_paths_db

db_name = lambda _: "farm_survey_test.db"


class BlobProperties:
    def __init__(self, name, container):
        self.name = name
        self.container = container


def call_kwarg(mock: MagicMock, param, count=0):
    return mock.call_args_list[count].kwargs[param]


class StorageStreamDownloader:
    def __init__(self, name):
        self.name = name


class TestLambdaFunction(unittest.TestCase):
    @patch("lambda_function_create_azure_blob_paths_db.boto3")
    def test_token_callback_should_call_the_correct_sts_endpoint(self, boto3):
        boto3.return_value = MagicMock()
        sts_client = MagicMock()
        sts_client.get_web_identity_token.return_value = {"WebIdentityToken": "test_token"}
        boto3.client.return_value = sts_client

        web_identity_token = lambda_function_create_azure_blob_paths_db.token_callback()

        self.assertEqual("test_token", web_identity_token)
        self.assertEqual("sts", boto3.client.call_args.args[0])

        self.assertEqual({
            "Audience": ["api://AzureADTokenExchange"],
            "DurationSeconds": 300,
            "SigningAlgorithm": "RS256"
        }, sts_client.get_web_identity_token.call_args.kwargs)


    @patch.dict(os.environ, {
        "AZURE_ACCOUNT_URL": "test_account_url",
        "AZURE_TENANT_ID": "test_tenant_id",
        "AZURE_CLIENT_ID": "test_client_id",
        "AZURE_FS_CONTAINER": "azure_container1"
    }, clear=True)
    @patch("lambda_function_create_azure_blob_paths_db.ClientAssertionCredential")
    @patch("lambda_function_create_azure_blob_paths_db.BlobServiceClient")
    def test_get_container_client_should_upload_file_bytes_to_correct_s3_bucket(self, blob_service_client,
                                                                                client_assertion_credential):
        client = MagicMock()
        client.get_container_client.return_value = "container_client_response"
        blob_service_client.return_value = client

        container_client = lambda_function_create_azure_blob_paths_db.get_container_client()

        self.assertEqual("container_client_response", container_client)
        self.assertEqual("test_client_id", call_kwarg(client_assertion_credential, "client_id"))
        self.assertEqual("token_callback", call_kwarg(client_assertion_credential, "func").__name__)
        self.assertEqual("test_tenant_id", call_kwarg(client_assertion_credential, "tenant_id"))

        self.assertEqual("test_account_url", call_kwarg(blob_service_client, "account_url"))
        self.assertEqual("ClientAssertionCredential()",
                         call_kwarg(blob_service_client, "credential")._extract_mock_name())

    @patch("lambda_function.db_name", new=db_name)
    def test_download_blob_paths_and_names_should_write_only_tiffs_to_db(self):
        cursor = MagicMock()
        conn = MagicMock()

        pages = [["prefix/blob_path1.tif", "prefix/blob_path2.tif"], ["prefix/blob_path3.tif", "prefix/blob_path4.jpg"]]
        total_files_retrieved = \
            lambda_function_create_azure_blob_paths_db.download_blob_paths_and_names(pages, cursor, conn)

        self.assertEqual(3, total_files_retrieved)
        self.assertEqual(("INSERT INTO farm_survey_paths (blobPath, originalName) VALUES (?, ?)",
                          [("prefix/blob_path1.tif", "blob_path1.tif"), ("prefix/blob_path2.tif", "blob_path2.tif")]),
                         cursor.executemany.call_args_list[0].args)

        self.assertEqual(("INSERT INTO farm_survey_paths (blobPath, originalName) VALUES (?, ?)",
                          [("prefix/blob_path3.tif", "blob_path3.tif")]),
                         cursor.executemany.call_args_list[1].args)

        self.assertEqual(2, conn.commit.call_count)

    @patch.dict(os.environ, { "SOURCE_BUCKET": "dest_bucket", "BLOB_PATHS_PREFIX": "prefix" }, clear=True)
    @patch("lambda_function_create_azure_blob_paths_db.boto3")
    def test_upload_to_s3_should_upload_file_bytes_to_correct_s3_bucket(self, boto3):
        boto3.return_value = MagicMock()
        s3_client = MagicMock()
        boto3.client.return_value = s3_client

        lambda_function_create_azure_blob_paths_db.upload_to_s3("db_path", "db_name")

        self.assertEqual("s3", boto3.client.call_args.args[0])
        self.assertEqual(("db_path", "dest_bucket", "prefix/db_name"), s3_client.upload_file.call_args.args)


    @patch.dict(os.environ, { "SOURCE_BUCKET": "dest_bucket", "BLOB_PATHS_PREFIX": "prefix" }, clear=True)
    @patch("lambda_function_create_azure_blob_paths_db.boto3")
    def test_upload_to_s3_should_raise_an_error_if_an_error_occurs_whilst_uploading(self, boto3):
        boto3.return_value = MagicMock()
        s3_client = MagicMock()
        boto3.client.return_value = s3_client

        s3_client.upload_file.side_effect = Exception("Upload Error")

        with self.assertRaises(Exception) as context:
            lambda_function_create_azure_blob_paths_db.upload_to_s3("db_path", "db_name")

        self.assertEqual("Upload Error", context.exception.args[0])
        self.assertEqual("s3", boto3.client.call_args.args[0])
        self.assertEqual(("db_path", "dest_bucket", "prefix/db_name"), s3_client.upload_file.call_args.args)


    @patch("lambda_function_create_azure_blob_paths_db.datetime")
    @patch("lambda_function_create_azure_blob_paths_db.download_blob_paths_and_names")
    @patch("lambda_function_create_azure_blob_paths_db.get_container_client")
    @patch("lambda_function_create_azure_blob_paths_db.upload_to_s3")
    def test_lambda_handler_should_write_blob_paths_to_a_db_and_upload_it_to_s3(
        self, upload_to_s3, get_container_client, download_blob_paths_and_names, date_and_time):

        container_client = MagicMock()
        blob_names_list_obj = MagicMock()
        blob_names_list_obj.by_page.return_value = ["pages"]
        container_client.list_blob_names.return_value = blob_names_list_obj
        get_container_client.return_value = container_client
        download_blob_paths_and_names.return_value = 3

        date_and_time.datetime.now.return_value = datetime.datetime(2026, 1, 1, 15, 30, 0)

        lambda_function_create_azure_blob_paths_db.lambda_handler(None, None)

        upload_calls = upload_to_s3.call_args_list

        self.assertEqual(1, get_container_client.call_count)
        self.assertEqual(["pages"], download_blob_paths_and_names.call_args_list[0].args[0])
        self.assertEqual(True, isinstance(download_blob_paths_and_names.call_args_list[0].args[1], Cursor))
        self.assertEqual(True, isinstance(download_blob_paths_and_names.call_args_list[0].args[2], Connection))
        self.assertEqual("/tmp/farm-survey-2026-01-01 15:30:00.db", upload_calls[0].args[0])
        self.assertEqual(True, upload_calls[0].args[1].startswith("farm-survey-2026-01-01 15:30:00.db"))


    @patch("lambda_function_create_azure_blob_paths_db.datetime")
    @patch("lambda_function_create_azure_blob_paths_db.download_blob_paths_and_names")
    @patch("lambda_function_create_azure_blob_paths_db.get_container_client")
    @patch("lambda_function_create_azure_blob_paths_db.upload_to_s3")
    def test_lambda_handler_should_throw_ane_exception_if_one_was_thrown_when_uploading_to_s3(
        self, upload_to_s3, get_container_client, download_blob_paths_and_names, date_and_time):

        container_client = MagicMock()
        blob_names_list_obj = MagicMock()
        blob_names_list_obj.by_page.return_value = ["pages"]
        container_client.list_blob_names.return_value = blob_names_list_obj

        upload_to_s3.side_effect = Exception("Upload Error")
        get_container_client.return_value = container_client
        download_blob_paths_and_names.return_value = 3
        date_and_time.datetime.now.return_value = datetime.datetime(2026, 1, 1, 15, 30, 0)

        upload_calls = upload_to_s3.call_args_list

        with self.assertRaises(Exception) as context:
            lambda_function_create_azure_blob_paths_db.lambda_handler(None, None)

        self.assertEqual("Upload Error", context.exception.args[0])
        self.assertEqual(1, get_container_client.call_count)
        self.assertEqual(["pages"], download_blob_paths_and_names.call_args_list[0][0][0])
        self.assertEqual(True, isinstance(download_blob_paths_and_names.call_args_list[0].args[1], Cursor))
        self.assertEqual("/tmp/farm-survey-2026-01-01 15:30:00.db", upload_calls[0].args[0])
        self.assertEqual(True, upload_calls[0].args[1].startswith("farm-survey-2026-01-01 15:30:00.db"))


if __name__ == '__main__':
    unittest.main()
