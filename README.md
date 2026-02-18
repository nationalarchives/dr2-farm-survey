# DR2 Farm Survey

This code is written for a Lambda. The purpose is to take files from an Azure container, convert it from TIFF to JPG and
upload them to an AWS bucket along with metadata. The steps are

## Input

The lambda is triggered from an SQS message with a body that contains a location to a JSON metadata file of the 
images

```json
{
  "metadataLocation":"s3://farm-survey/image_map.json"
}
```

## Output

The lambda doesn't return anything as it uploads the files to an S3 bucket


## Steps

1. Gets the url from the metadataLocation in the input JSON
2. Downloads a JSON image metadata file from this location, which has this format:
   a. ```{
             "IAID": "c4abac9e-5f39-4b4b-aef8-af54ccecc0d8",
             "replicaId": "61668524-a170-4488-beb4-10d54af1c531",
             "images": [
                 {
                     "file_name": "file-name.tif",
                     "sequence_no": 1,
                     "file_id": "ae0afc95-4ff8-4388-8706-a5523a7a83bb"
                }
                ...
             ]
        }```
3. Validates that all ids in the JSON image metadata file's objects have unique file_ids and file_names and throws 
   exceptions if they aren't
4. For each file object, it will, using the file_name, retrieve the Azure Blob path for each from a SQLite database 
   (which contains information on all files in an Azure container) make note of the ones that are missing from the Azure container
5. If there are any files missing, it will throw an exception
6. Iterate threw the image metadata objects and call Azure, using the file path and retrieve the bytes 
   of the TIFF file
7. Use the TIFF file bytes to convert it into JPEG bytes
8. Send the bytes to a file in S3 with this path `"files/{iaid}/66/MAF/32/{file_id}.jpg"`
9. Calculates the file size in KB
10. Generates and SHA256 checksum
11. Generates a "replica" metadata object for each file
    a. ```{
                "checkSum": {sha256 checksum},
                "format": "jpg",
                "name": "{new file name}",
                "originalName": "{file name}",
                "size": {file size in KB}
         }```
12. Sort these objects by their `originalName`
13. Generate a final metadata JSON object with this format
    a.  ```{
            "files": [{sorted_replica_files}],
            "replicaId": {replicaId},
            "origination": "DigitalSurrogate",
            "totalSize": {all file sizes totalled}
        }```
14. Upload the final metadata JSON object's bytes to a file in S3 with this path `"metadata/{iaid}.json"`