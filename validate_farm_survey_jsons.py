import json
import os
import sys
from pathlib import Path

from jsonschema import validate, ValidationError, SchemaError


def load_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON file '{file_path}': {e}")
        sys.exit(1)


def validate_json(json_file_name, json_data, schema_data):
    try:
        validate(instance=json_data, schema=schema_data)
    except ValidationError as e:
        return (f"\nJSON validation returned an error for file '{json_file_name}' at path: {'/'.join(map(str, e.path))}:\n" +
                f"  - {e.message}")


def validate_local_jsons(jsons_folder, schema_file):
    error_messages = []
    print(f"Validating JSON files in folder '{jsons_folder}' ...\n")
    for direct_dir, _, files_in_dir in Path(jsons_folder).walk():
        if files_in_dir:  # for each directory, there could be just directories inside
            for n, json_file_name in enumerate(files_in_dir):
                if n % 100 == 0:
                    print(f"{n} files processed")
                json_data = load_json(direct_dir / json_file_name)
                schema_data = load_json(schema_file)

                error_message = validate_json(json_file_name, json_data, schema_data)
                if error_message:
                    error_messages.append(error_message)

    if error_messages:
        print(f"\n{len(error_messages)} validation error(s) occurred:")
        for n, error_message in enumerate(error_messages):
            print(f"{n + 1}. {error_message}")
        sys.exit(1)

def main():
    if len(sys.argv) != 3:
        print("Not enough arguments passed in. Run the script like this: python validate_farm_survey_jsons.py {"
              "jsons_folder} {schema_file}")
        sys.exit(1)

    jsons_folder = sys.argv[1]
    schema_file = sys.argv[2]

    validate_local_jsons(jsons_folder, schema_file)


if __name__ == "__main__":
    main()