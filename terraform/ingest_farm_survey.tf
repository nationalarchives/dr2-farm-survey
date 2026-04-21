locals {
  environment                    = "sbox"
  tif_to_jpg_lambda_name         = "${local.environment}-dr2-farm-survey-tif-to-jpg"
  invocation_event_rule_name     = "${local.environment}-dr2-farm-survey-invocation-rule"
  cloudwatch_event_target_lambda = "${local.environment}-dr2-farm-survey-lambda-target"
  replica_jsons_prefix      = "${local.environment}-dr2-farm-survey-replica-jsons"
  farm_survey_bucket_name       = "${local.environment}-dr2-farm-survey"
  farm_survey_queue              = "${local.environment}-dr2-farm-survey_replica_jsons"
  farm_survey_role_name          = "${local.environment}-dr2-farm-survey-role"
}

resource "aws_secretsmanager_secret" "azure_account_url" {
  name = "${local.environment}-farm-survey-azure-account-url"
}

resource "aws_secretsmanager_secret" "azure_client_id" {
  name = "${local.environment}-farm_survey-azure_client_id"
}

resource "aws_secretsmanager_secret" "azure_tenant_id" {
  name = "${local.environment}-farm-survey-azure-tenant-id"
}

resource "aws_secretsmanager_secret" "dest_account_id" {
  name = "${local.environment}-farm-survey-dest-account-id"
}


resource "aws_secretsmanager_secret" "dest_bucket_name" {
  name = "${local.environment}-farm-survey-dest-bucket-name"
}

resource "aws_secretsmanager_secret" "dest_bucket_records_prefix" {
  name = "${local.environment}-farm-survey-dest-bucket-records-prefix"
}

resource "aws_secretsmanager_secret" "dest_bucket_files_prefix" {
  name = "${local.environment}-farm-survey-dest-bucket-files-prefix"
}


module "dr2_farm_survey_bucket" {
  source      = "git::https://github.com/nationalarchives/da-terraform-modules//s3"
  bucket_name = local.farm_survey_bucket_name
}

module "dr2_convert_tif_to_jpg_lambda" {
  source          = "git::https://github.com/nationalarchives/da-terraform-modules//lambda"
  description     = "A lambda function to retrieve .tif files, convert them to .jpg and upload them to bucket"
  function_name   = local.tif_to_jpg_lambda_name
  handler         = "farm_survey.lambda_handler"
  timeout_seconds = 60
  runtime         = "python3.14"
  memory_size     = 256
  policies = {
    "${local.tif_to_jpg_lambda_name}-policy" = templatefile("./templates/iam_policy/farm_survey_lambda_policy.json.tpl", {
      dest_account_id = aws_secretsmanager_secret.dest_account_id
      dr2_farm_survey_dest_bucket = aws_secretsmanager_secret.dest_bucket_name
      files_prefix = aws_secretsmanager_secret.dest_bucket_files_prefix
      records_prefix = aws_secretsmanager_secret.dest_bucket_records_prefix
      account_id                  = data.aws_caller_identity.current.account_id
      lambda_name                 = local.tif_to_jpg_lambda_name
      queue_name                  = local.farm_survey_queue
    })
  }

  plaintext_env_vars = {
    DEST_BUCKET     = aws_secretsmanager_secret.dest_bucket_name
    DEST_BUCKET_FILES_PREFIX = aws_secretsmanager_secret.dest_bucket_files_prefix
    DEST_BUCKET_RECORDS_PREFIX = aws_secretsmanager_secret.dest_bucket_records_prefix
    AZURE_ACCOUNT_URL    = aws_secretsmanager_secret.azure_account_url
    AZURE_CLIENT_ID      = aws_secretsmanager_secret.azure_client_id
    AZURE_FS_CONTAINER   = "farms"
    AZURE_TENANT_ID      = aws_secretsmanager_secret.azure_tenant_id
    BATCH_DB_NAME        = "farm_survey_batch001"
  }

  tags = {
    Name = local.tif_to_jpg_lambda_name
  }
}

module "dr2_send_to_farm_survey_queue_lambda" {
  source          = "git::https://github.com/nationalarchives/da-terraform-modules//lambda"
  description     = "A lambda function to retrieve json file names from S3 and send them to SQS"
  function_name   = local.tif_to_jpg_lambda_name
  handler         = "farm_survey.lambda_handler"
  timeout_seconds = 60
  runtime         = "python3.14"
  memory_size     = 256
  policies = {
    "${local.tif_to_jpg_lambda_name}-policy" = templatefile("./templates/iam_policy/send_to_farm_survey_queue_lambda_policy.json.tpl", {
      replica_jsons_bucket_name = local.replica_jsons_prefix
      account_id                = data.aws_caller_identity.current.account_id
      lambda_name               = local.tif_to_jpg_lambda_name
      queue_name                = local.farm_survey_queue
    })
  }

  plaintext_env_vars = {
    FS_BUCKET = local.farm_survey_bucket_name
    QUEUE_URL        = farm_survey_queue
    REPLICA_JSONS_PREFIX = local.replica_jsons_prefix
  }
  tags = {
    Name = local.tif_to_jpg_lambda_name
  }
}

module "farm_survey_queue" {
  source     = "git::https://github.com/nationalarchives/da-terraform-modules//sqs"
  queue_name = local.farm_survey_queue
  sqs_policy = templatefile("./templates/sqs/sqs_access_policy.json.tpl", {
    account_id = data.aws_caller_identity.current.account_id,
    queue_name = local.farm_survey_queue
  })
  queue_cloudwatch_alarm_visible_messages_threshold = 60
  visibility_timeout                                = 60
  encryption_type                                   = "sse"
}

resource "aws_lambda_event_source_mapping" "lambda_trigger" {
  event_source_arn = module.farm_survey_queue.sqs_arn
  function_name    = module.dr2_convert_tif_to_jpg_lambda.lambda_arn
}

resource "aws_cloudwatch_event_rule" "fire_event_every_minute" {
  name                = local.invocation_event_rule_name
  description         = "triggers the lambda every minute"
  schedule_expression = "rate(1 minute)"
}

resource "aws_cloudwatch_event_target" "lambda_trigger" {
  rule      = aws_cloudwatch_event_rule.fire_event_every_minute.name
  target_id = local.cloudwatch_event_target_lambda
  arn       = module.dr2_convert_tif_to_jpg_lambda.lambda_arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = local.tif_to_jpg_lambda_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.fire_event_every_minute.arn
}