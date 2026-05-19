locals {
  environment                    = "sbox"
  tif_to_jpg_lambda_name         = "${local.environment}-dr2-farm-survey-tif-to-jpg"
  replica_jsons_bucket           = "${local.environment}-dr2-farm-survey-replica-jsons"
  send_to_sqs_lambda_name        = "${local.environment}-dr2-farm-survey-send_to_sqs"
  farm_survey_queue              = "${local.environment}-dr2-farm-survey_replica_jsons"
  farm_survey_role_name          = "${local.environment}-dr2-farm-survey-role"
  dest_bucket                    = "ds-dev-publication-service-data-imports"
  dest_bucket_files_prefix       = "tna-digital-files-to-process"
  dest_records_prefix            = "tna-records-to-process"
  azure_container                = "farms"
  tif_to_jpg_lambda_timeout      = 60
  tif_to_jpg_deps_loc            = "src/convert-tif-to-jpg"
  send_to_sqs_deps_loc           = "src/send-to-sqs"
}

module "dr2_farm_survey_bucket" {
  source      = "git::https://github.com/nationalarchives/da-terraform-modules//s3"
  bucket_name = local.replica_jsons_bucket
}


resource "aws_lambda_layer_version" "image_magick" {
  filename  = "${local.tif_to_jpg_deps_loc}/dr2-farm-survey-image_magick.zip"

  layer_name = "farm_survey_image_magick_layer"

  compatible_runtimes      = ["nodejs10.x", "python3.14"]
  compatible_architectures = ["x86_64"]
}

resource "aws_lambda_layer_version" "python_deps" {
  filename  = "${local.tif_to_jpg_deps_loc}/dr2-farm-survey-python_deps.zip"

  layer_name = "farm_survey_python_deps"

  compatible_runtimes      = ["python3.14"]
  compatible_architectures = ["x86_64"]
}

module "dr2_convert_tif_to_jpg_lambda" {
  source          = "git::https://github.com/nationalarchives/da-terraform-modules//lambda"
  description     = "A lambda function to retrieve .tif files, convert them to .jpg and upload them to bucket"
  filename        = "${local.tif_to_jpg_deps_loc}/lambda_function_payload.zip"
  function_name   = local.tif_to_jpg_lambda_name
  handler         = "lambda_function.lambda_handler"
  timeout_seconds = local.tif_to_jpg_lambda_timeout
  runtime         = "python3.14"
  memory_size     = 256
  layers          = [aws_lambda_layer_version.image_magick.arn, aws_lambda_layer_version.python_deps.arn]
  policies = {
    "${local.tif_to_jpg_lambda_name}-policy" = templatefile("./templates/iam_policy/farm_survey_lambda_policy.json.tpl", {
      dest_account_id = var.dest_account_id
      dest_bucket     = local.dest_bucket
      files_prefix    = local.dest_bucket_files_prefix
      records_prefix  = local.dest_records_prefix
      account_id      = data.aws_caller_identity.current.account_id
      lambda_name     = local.tif_to_jpg_lambda_name
      queue_name      = local.farm_survey_queue
    })
  }

  plaintext_env_vars = {
    AZURE_ACCOUNT_URL          = var.azure_account_url
    AZURE_CLIENT_ID            = var.azure_client_id
    AZURE_FS_CONTAINER         = local.azure_container
    AZURE_TENANT_ID            = var.azure_tenant_id
    DEST_BUCKET                = local.dest_bucket
    DEST_BUCKET_FILES_PREFIX   = local.dest_bucket_files_prefix
    DEST_BUCKET_RECORDS_PREFIX = local.dest_records_prefix
  }

  tags = {
    Name = local.tif_to_jpg_lambda_name
  }
}


module "dr2_send_to_farm_survey_queue_lambda" {
  filename        = "${local.send_to_sqs_deps_loc}/sqs_lambda_function_payload.zip"
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
      replica_jsons_bucket_name = local.replica_jsons_bucket
      account_id                = data.aws_caller_identity.current.account_id
      queue_name                = local.farm_survey_queue
    })
  }

  plaintext_env_vars = {
    AWS_FILES_BUCKET     = local.replica_jsons_bucket
    QUEUE_URL            = module.farm_survey_queue.sqs_queue_url
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
  visibility_timeout                                = local.tif_to_jpg_lambda_timeout * 6
  encryption_type                                   = "sse"
}

resource "aws_lambda_event_source_mapping" "lambda_trigger" {
  event_source_arn = module.farm_survey_queue.sqs_arn
  function_name    = module.dr2_convert_tif_to_jpg_lambda.lambda_arn
}
