# Lambda Functions Module
# This module creates all 6 Lambda functions with ARM64 architecture and appropriate configurations

# Metrics Collector Lambda Function
resource "aws_lambda_function" "metrics_collector" {
  function_name = "${var.project_name}-metrics-collector"
  role          = var.iam_role_arns.metrics_collector
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 20

  filename         = var.lambda_packages.metrics_collector
  source_code_hash = filebase64sha256(var.lambda_packages.metrics_collector)

  environment {
    variables = {
      DYNAMODB_TABLE     = var.dynamodb_table_name
      LOG_LEVEL          = var.log_level
      INCIDENT_TOPIC_ARN = var.sns_topic_arn
    }
  }

  tags = var.tags
}

# CloudWatch Log Group for Metrics Collector
resource "aws_cloudwatch_log_group" "metrics_collector" {
  name              = "/aws/lambda/${aws_lambda_function.metrics_collector.function_name}"
  retention_in_days = 7

  tags = var.tags
}

# Logs Collector Lambda Function
resource "aws_lambda_function" "logs_collector" {
  function_name = "${var.project_name}-logs-collector"
  role          = var.iam_role_arns.logs_collector
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 20

  filename         = var.lambda_packages.logs_collector
  source_code_hash = filebase64sha256(var.lambda_packages.logs_collector)

  environment {
    variables = {
      DYNAMODB_TABLE     = var.dynamodb_table_name
      LOG_LEVEL          = var.log_level
      INCIDENT_TOPIC_ARN = var.sns_topic_arn
    }
  }

  tags = var.tags
}

# CloudWatch Log Group for Logs Collector
resource "aws_cloudwatch_log_group" "logs_collector" {
  name              = "/aws/lambda/${aws_lambda_function.logs_collector.function_name}"
  retention_in_days = 7

  tags = var.tags
}

# Deploy Context Collector Lambda Function
resource "aws_lambda_function" "deploy_context_collector" {
  function_name = "${var.project_name}-deploy-context-collector"
  role          = var.iam_role_arns.deploy_context_collector
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 20

  filename         = var.lambda_packages.deploy_context_collector
  source_code_hash = filebase64sha256(var.lambda_packages.deploy_context_collector)

  environment {
    variables = {
      DYNAMODB_TABLE     = var.dynamodb_table_name
      LOG_LEVEL          = var.log_level
      INCIDENT_TOPIC_ARN = var.sns_topic_arn
    }
  }

  tags = var.tags
}

# CloudWatch Log Group for Deploy Context Collector
resource "aws_cloudwatch_log_group" "deploy_context_collector" {
  name              = "/aws/lambda/${aws_lambda_function.deploy_context_collector.function_name}"
  retention_in_days = 7

  tags = var.tags
}

# Correlation Engine Lambda Function
resource "aws_lambda_function" "correlation_engine" {
  function_name = "${var.project_name}-correlation-engine"
  role          = var.iam_role_arns.correlation_engine
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 10

  filename         = var.lambda_packages.correlation_engine
  source_code_hash = filebase64sha256(var.lambda_packages.correlation_engine)

  environment {
    variables = {
      DYNAMODB_TABLE     = var.dynamodb_table_name
      LOG_LEVEL          = var.log_level
      MAX_CONTEXT_SIZE   = "51200" # 50KB in bytes
      INCIDENT_TOPIC_ARN = var.sns_topic_arn
    }
  }

  tags = var.tags
}

# CloudWatch Log Group for Correlation Engine
resource "aws_cloudwatch_log_group" "correlation_engine" {
  name              = "/aws/lambda/${aws_lambda_function.correlation_engine.function_name}"
  retention_in_days = 7

  tags = var.tags
}

# LLM Analyzer Lambda Function
resource "aws_lambda_function" "llm_analyzer" {
  function_name = "${var.project_name}-llm-analyzer"
  role          = var.iam_role_arns.llm_analyzer
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  memory_size   = 1024
  timeout       = 40

  filename         = var.lambda_packages.llm_analyzer
  source_code_hash = filebase64sha256(var.lambda_packages.llm_analyzer)

  environment {
    variables = {
      DYNAMODB_TABLE        = var.dynamodb_table_name
      LOG_LEVEL             = var.log_level
      BEDROCK_MODEL_ID      = "anthropic.claude-v2"
      PROMPT_TEMPLATE_PARAM = "${var.project_name}/prompt-template"
      INCIDENT_TOPIC_ARN    = var.sns_topic_arn
    }
  }

  tags = var.tags
}

# CloudWatch Log Group for LLM Analyzer
resource "aws_cloudwatch_log_group" "llm_analyzer" {
  name              = "/aws/lambda/${aws_lambda_function.llm_analyzer.function_name}"
  retention_in_days = 7

  tags = var.tags
}

# Notification Service Lambda Function
resource "aws_lambda_function" "notification_service" {
  function_name = "${var.project_name}-notification-service"
  role          = var.iam_role_arns.notification_service
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 15

  filename         = var.lambda_packages.notification_service
  source_code_hash = filebase64sha256(var.lambda_packages.notification_service)

  environment {
    variables = {
      DYNAMODB_TABLE     = var.dynamodb_table_name
      LOG_LEVEL          = var.log_level
      SLACK_SECRET_NAME  = "${var.project_name}/slack-webhook"
      SNS_TOPIC_ARN      = var.sns_topic_arn
      INCIDENT_STORE_URL = "https://console.aws.amazon.com/dynamodbv2/home?region=${var.aws_region}#item-explorer?table=${var.dynamodb_table_name}"
    }
  }

  tags = var.tags
}

# CloudWatch Log Group for Notification Service
resource "aws_cloudwatch_log_group" "notification_service" {
  name              = "/aws/lambda/${aws_lambda_function.notification_service.function_name}"
  retention_in_days = 7

  tags = var.tags
}
