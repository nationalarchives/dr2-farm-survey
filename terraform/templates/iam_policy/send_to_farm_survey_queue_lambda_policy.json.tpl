{
  "Statement": [
    {
      "Sid": "listBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::${dr2_farm_survey_dest_bucket}"
    },
    {
      "Action": "sqs:SendMessage",
      "Effect": "Allow",
      "Resource": "arn:aws:sqs:eu-west-2:${account_id}:${queue_name}",
      "Sid": "sendMessage"
    }
  ],
  "Version": "2012-10-17"
}