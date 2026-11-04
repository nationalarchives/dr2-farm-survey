import os
import unittest
from pathlib import PosixPath
from unittest.mock import patch, MagicMock

import validate_farm_survey_jsons
from jsonschema import ValidationError


class TestLambdaFunction(unittest.TestCase):
    def test_load_json_returns_json_as_a_dict(self):
        json = validate_farm_survey_jsons.load_json("test_jsons/test_json.json")

        self.assertEqual({"test_field": "test"}, json)

    def test_load_json_should_throw_an_exception(self):
        with self.assertRaises(Exception) as context:
            validate_farm_survey_jsons.load_json("test_jsons/test_json_incorrect.json")

        self.assertEqual("Illegal trailing comma before end of object: line 1 column 32 (char 31)", str(context.exception))


    @patch("validate_farm_survey_jsons.validate")
    def test_validate_json_should_call_validate_with_the_correct_args(self, validate):
        json_schema_data = "{'schema': 'data'}"

        validate_farm_survey_jsons.validate_json(
            "test_jsons/test_json.json",
            {"test_field": "test"},
            json_schema_data
        )

        self.assertEqual( {"instance": {"test_field": "test"}, "schema": "{'schema': 'data'}"},
                         validate.call_args_list[0].kwargs)


    @patch("validate_farm_survey_jsons.validate")
    def test_validate_json_should_throw_an_exception_if_validate_call_throws_a_validation_error(self, validate):
        validate.side_effect = ValidationError("An error message")

        json_schema_data = "{'schema': 'data'}"

        error_message = validate_farm_survey_jsons.validate_json(
            "test_jsons/test_json.json",
            {"test_field": "test"},
            json_schema_data
        )

        self.assertEqual( {"instance": {"test_field": "test"}, "schema": "{'schema': 'data'}"},
                          validate.call_args_list[0].kwargs)

        self.assertEqual("\nJSON validation returned an error for file 'test_jsons/test_json.json' at path: :\n - An error "
                         "message", error_message)

    def test_print_errors_should_throw_an_exception(self):
        with self.assertRaises(Exception) as context:
            validate_farm_survey_jsons.print_errors(["Error message1", "Error message2"])

        self.assertEqual("\n2 validation error(s) occurred:", str(context.exception))

    @patch("validate_farm_survey_jsons.load_json")
    @patch("validate_farm_survey_jsons.validate_json")
    def test_validate_local_jsons_should_validate_only_jsons(self, validate_json, load_json):
        load_json.side_effect = ["{'schema': 'data'}", {"test_field": "test"}, {"test_field": "test2"}]
        validate_json.side_effect = [None, None]

        validate_farm_survey_jsons.validate_local_jsons(
            "test_jsons",
            "preliminary_json_schema_validation.json"
        )

        load_json_jsons = [load_json.call_args_list[1].args[0], load_json.call_args_list[2].args[0]]

        self.assertEqual("preliminary_json_schema_validation.json", load_json.call_args_list[0].args[0])
        self.assertCountEqual(
            [PosixPath("test_jsons/test_json.json"), PosixPath("test_jsons/test_json_incorrect.json")], load_json_jsons
        )

        json_names = [validate_json.call_args_list[0].args[0], validate_json.call_args_list[1].args[0]]
        json_data = [validate_json.call_args_list[0].args[1], validate_json.call_args_list[1].args[1]]
        json_schema = [validate_json.call_args_list[0].args[2], validate_json.call_args_list[1].args[2]]

        self.assertCountEqual(["test_json.json", "test_json_incorrect.json"], json_names)
        self.assertCountEqual([{"test_field": "test"}, {"test_field": "test2"}], json_data)
        self.assertCountEqual(["{'schema': 'data'}", "{'schema': 'data'}"], json_schema)

    @patch("validate_farm_survey_jsons.load_json")
    @patch("validate_farm_survey_jsons.validate_json")
    @patch("validate_farm_survey_jsons.print_errors")
    def test_validate_local_jsons_should_validate_only_jsons_and_print_error_messages(self, print_errors,
                                                                                      validate_json, load_json):
        load_json.side_effect = ["{'schema': 'data'}", {"test_field": "test"}, {"test_field": "test2"}]
        validate_json.side_effect = ["error message1", "error message2"]

        validate_farm_survey_jsons.validate_local_jsons(
            "test_jsons",
            "preliminary_json_schema_validation.json"
        )

        jsons = [load_json.call_args_list[1].args[0], load_json.call_args_list[2].args[0]]

        self.assertEqual("preliminary_json_schema_validation.json", load_json.call_args_list[0].args[0])
        self.assertCountEqual(
            [PosixPath("test_jsons/test_json.json"), PosixPath("test_jsons/test_json_incorrect.json")], jsons
        )
        self.assertEqual(("test_json.json", {"test_field": "test"}, "{'schema': 'data'}"), validate_json.call_args_list[0].args)
        self.assertEqual(("test_json_incorrect.json", {"test_field": 'test2'}, "{'schema': 'data'}"),
                         validate_json.call_args_list[1].args)
        self.assertEqual((['error message1', 'error message2'],), print_errors.call_args_list[0].args)

if __name__ == '__main__':
    unittest.main()
