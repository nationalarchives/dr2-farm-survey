locals {
  environment                    = "sbox"
  tif_to_jpg_lambda_name         = "${local.environment}-dr2-farm-survey-tif-to-jpg"
  invocation_event_rule_name     = "${local.environment}-dr2-farm-survey-invocation-rule"
  cloudwatch_event_target_lambda = "${local.environment}-dr2-farm-survey-lambda-target"
  replica_jsons_prefix           = "${local.environment}-dr2-farm-survey-replica-jsons"
  send_to_sqs_lambda_name        = "${local.environment}-dr2-farm-survey-send_to_sqs"
  farm_survey_bucket_name        = "${local.environment}-dr2-farm-survey"
  farm_survey_queue              = "${local.environment}-dr2-farm-survey_replica_jsons"
  farm_survey_role_name          = "${local.environment}-dr2-farm-survey-role"
}

data "aws_ssm_parameter" "azure_account_url" {
  name = "/${local.environment}/farm-survey/azure-account-url"
}

data "aws_ssm_parameter" "azure_client_id" {
  name = "/${local.environment}/farm-survey/azure_client_id"
}

data "aws_ssm_parameter" "azure_tenant_id" {
  name = "/${local.environment}/farm-survey/azure-tenant-id"
}

data "aws_ssm_parameter" "dest_account_id" {
  name = "/${local.environment}/farm-survey/dest-account-id"
}

data "aws_ssm_parameter" "dest_bucket_alias" {
  name = "/${local.environment}/farm-survey/dest_bucket_alias"
}

module "dr2_farm_survey_bucket" {
  source      = "git::https://github.com/nationalarchives/da-terraform-modules//s3"
  bucket_name = local.farm_survey_bucket_name
}

resource "aws_s3_object" "image_magick_lambda_layer" {
  bucket = module.dr2_farm_survey_bucket.s3_bucket_name
  key    = "layers/dr2-farm-survey-image_magick.zip"
  source = "../dr2-farm-survey-image_magick.zip"

  source_hash = filebase64sha256("../dr2-farm-survey-image_magick.zip")
}

resource "aws_s3_object" "python_deps_lambda_layer" {
  bucket = module.dr2_farm_survey_bucket.s3_bucket_name
  key    = "layers/dr2-farm-survey-python_deps.zip"
  source = "../dr2-farm-survey-python_deps.zip"

  source_hash = filebase64sha256("../dr2-farm-survey-python_deps.zip")
}

resource "aws_lambda_layer_version" "image_magick" {
  s3_bucket = aws_s3_object.image_magick_lambda_layer.bucket
  s3_key    = aws_s3_object.image_magick_lambda_layer.key

  layer_name = "farm_survey_image_magick_layer"

  compatible_runtimes      = ["nodejs10.x", "python3.14"]
  compatible_architectures = ["x86_64"]
}

resource "aws_lambda_layer_version" "python_deps" {
  s3_bucket = aws_s3_object.python_deps_lambda_layer.bucket
  s3_key    = aws_s3_object.python_deps_lambda_layer.key

  layer_name = "farm_survey_python_deps"

  compatible_runtimes      = ["python3.14"]
  compatible_architectures = ["x86_64"]
}

data "archive_file" "tif_to_jpg_lambda_code" {
  type        = "zip"
  source_dir  = "${path.module}/src/convert-tif-to-jpg"
  output_path = "${path.module}/lambda_function_payload.zip"
}

module "dr2_convert_tif_to_jpg_lambda" {
  source          = "git::https://github.com/nationalarchives/da-terraform-modules//lambda"
  description     = "A lambda function to retrieve .tif files, convert them to .jpg and upload them to bucket"
  filename        = data.archive_file.tif_to_jpg_lambda_code.output_path
  function_name   = local.tif_to_jpg_lambda_name
  handler         = "lambda_function.lambda_handler"
  timeout_seconds = 60
  runtime         = "python3.14"
  memory_size     = 256
  layers          = [aws_lambda_layer_version.image_magick.arn, aws_lambda_layer_version.python_deps.arn]
  policies = {
    "${local.tif_to_jpg_lambda_name}-policy" = templatefile("./templates/iam_policy/farm_survey_lambda_policy.json.tpl", {
      dest_account_id             = data.aws_ssm_parameter.dest_account_id.value
      dr2_farm_survey_dest_bucket = "ds-dev-publication-service-data-imports"
      files_prefix                = "tna-digital-files-to-process"
      records_prefix              = "tna-records-to-process"
      account_id                  = data.aws_caller_identity.current.account_id
      lambda_name                 = local.tif_to_jpg_lambda_name
      queue_name                  = local.farm_survey_queue
    })
  }

  plaintext_env_vars = {
    DEST_FILES_BUCKET          = "ds-dev-publication-service-data-imports"
    DEST_BUCKET_FILES_PREFIX   = "tna-digital-files-to-process"
    DEST_BUCKET_RECORDS_PREFIX = "tna-records-to-process"
    AZURE_ACCOUNT_URL          = data.aws_ssm_parameter.azure_account_url.value
    AZURE_CLIENT_ID            = data.aws_ssm_parameter.azure_client_id.value
    AZURE_FS_CONTAINER         = "farms"
    AZURE_TENANT_ID            = data.aws_ssm_parameter.azure_tenant_id.value
  }

  tags = {
    Name = local.tif_to_jpg_lambda_name
  }
}

data "archive_file" "send_to_queue_lambda_code" {
  type        = "zip"
  source_file  = "${path.module}/src/send-to-sqs/lambda_function_send_to_sqs.py"
  output_path = "${path.module}/sqs_lambda_function_payload.zip"
}

module "dr2_send_to_farm_survey_queue_lambda" {
  filename        = data.archive_file.send_to_queue_lambda_code.output_path
  source          = "git::https://github.com/nationalarchives/da-terraform-modules//lambda"
  description     = "A lambda function to retrieve json file names from S3 and send them to SQS"
  function_name   = local.send_to_sqs_lambda_name
  handler         = "lambda_function_send_to_sqs.py.lambda_handler"
  timeout_seconds = 60
  runtime         = "python3.14"
  memory_size     = 256
  layers          = [aws_lambda_layer_version.python_deps.arn]
  policies = {
    "${local.send_to_sqs_lambda_name}-policy" = templatefile("./templates/iam_policy/send_to_farm_survey_queue_lambda_policy.json.tpl", {
      replica_jsons_bucket_name = local.replica_jsons_prefix
      account_id                = data.aws_caller_identity.current.account_id
      queue_name                = local.farm_survey_queue
    })
  }

  plaintext_env_vars = {
    FS_BUCKET            = local.farm_survey_bucket_name
    QUEUE_URL            = module.farm_survey_queue.sqs_queue_url
    REPLICA_JSONS_PREFIX = local.replica_jsons_prefix
  }
  tags = {
    Name = local.send_to_sqs_lambda_name
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

  depends_on = [
    module.dr2_convert_tif_to_jpg_lambda
  ]
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