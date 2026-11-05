{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "crossAccountBucketAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::${source_jsons_bucket_name}"
    },
    {
      "Sid": "crossAccountObjectAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::${source_jsons_bucket_name}/*"
    },
    {
      "Sid": "invokeValidateJsonsAndAzureBlobPathsLambda",
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": [
        "arn:aws:lambda:eu-west-2:${account_id}:function:${json_validation_lambda_name}:*",
        "arn:aws:lambda:eu-west-2:${account_id}:function:${azure_blob_paths_db_lambda_name}:*"
      ]
    }
  ]
}
