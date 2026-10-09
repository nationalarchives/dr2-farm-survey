{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3Send",
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:eu-west-2:${account_id}:${queue_name}",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "${bucket_arn}"
        }
      }
    },
    {
      "Sid": "AllowLambdaGetAndReceive",
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:eu-west-2:${account_id}:${queue_name}",
      "Condition": {
        "ArnEquals": {
          "aws:PrincipalArn": "${lambda_role_arn}"
        }
      }
    }
  ]
}
