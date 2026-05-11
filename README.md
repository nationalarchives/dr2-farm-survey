# DR2 Farm Survey

This code is written for 2 Lambdas. The purpose of the 1st is to get metadata JSONs from an S3 bucket and send them to 
an SQS queue. The 2nd is to take files from an Azure container, convert it from TIFF to JPG and upload them to an 
AWS bucket along with metadata.


## Send to SQS

### Input

The lambda is triggered manually with a body that contains the batch name; this batch name is also the name of the  
S3 prefix where the JSONs are held and the database and table used in the 2nd lambda.

```json
{
  "batchName": "name"
}
```

### Output

The lambda doesn't return anything as it sends messages to SQS

### Steps

1. Gets the "batchName" from the event
2. Gets the JSON file names from the specified bucket via a paginator
3. Sends the S3 location of each JSON to SQS along with the `batchName`


## Convert Images from TIFF to JPEG

### Input

The lambda is triggered from an SQS message (sent by the "send to sqs lambda") with a body that contains a location
 to a JSON metadata file of the images

```json
{
  "metadataLocation":"s3://farm-survey/image_map.json"
}
```

### Output

The lambda doesn't return anything as it uploads the files to an S3 bucket

### Steps

1. Gets the batchName in the input JSON
2. Gets the URL from the metadataLocation in the input JSON
3. Downloads a JSON image metadata file from this location, which has this format:
   a. ```{
             "record": {
                 "iaid": "c4abac9e-5f39-4b4b-aef8-af54ccecc0d8"
                 "replicaId": "cdbda02f-f9b1-4690-bf3c-70ac8acaf87a",
                 ... 
             },
             "updateScope": "RecordAndReplica", # or "RecordOnly"
             "replica": {
                 "files": [
                     {
                         "originalName": "file-name.tif",
                         "format": "jpg",
                         "name": "path/e5299c0d-0df6-4785-b43e-4bd381e371fe.jpg",
                         "size": 90
                     }
                     ...
                ]
            }```
4. Validates that all ids in the JSON image metadata file's objects have unique file_ids and file_names and throws
   exceptions if they aren't
5. if `updateScope` in the JSON is "RecordAndReplica"
   1. For each file object, it will, using the file_name, retrieve the Azure Blob path for each from a SQLite database
      (which contains information on all files in an Azure container) make note of the ones that are missing from the Azure container
   2. If there are any files missing, it will throw an exception
   3. Iterate threw the image metadata objects and call Azure, using the file path and retrieve the bytes
      of the TIFF file
   4. Use the TIFF file bytes to convert it into JPEG bytes
   5. Send the bytes to a file in S3 with this path `"{files_prefix}/{iaid}/{name}"`
   6. Calculates the file size in KB
   7. Generates and SHA256 checksum
   8. Updates the `replica` section of the JSON with the file size and checksum for each file
   9. Totals the file sizes and updates `totalSize` key of `replica` object
6. Upload the final metadata JSON object's bytes to a file in a different bucket in S3 with this path `"
{metadata_prefix}/{iaid}.json"`
