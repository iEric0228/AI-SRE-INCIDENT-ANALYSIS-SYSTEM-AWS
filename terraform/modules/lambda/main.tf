# Lambda Functions Module
# This module creates all 6 Lambda functions with ARM64 architecture and appropriate configurations

# Metrics Collector Lambda Function
resource "aws_lambda_function" "metrics_collector" {
  function_name                  = "${var.project_name}-metrics-collector"
  role                           = var.iam_role_arns.metrics_collector
  handler                        = "lambda_function.lambda_handler"
  runtime                        = "python3.11"
  architectures                  = ["arm64"]
  memory_size                    = 512
  timeout                        = 20
  reserved_concurrent_executions = var.lambda_concurrency_limit

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
  function_name                  = "${var.project_name}-logs-collector"
  role                           = var.iam_role_arns.logs_collector
  handler                        = "lambda_function.lambda_handler"
  runtime                        = "python3.11"
  architectures                  = ["arm64"]
  memory_size                    = 512
  timeout                        = 20
  reserved_concurrent_executions = var.lambda_concurrency_limit

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
  function_name                  = "${var.project_name}-deploy-context-collector"
  role                           = var.iam_role_arns.deploy_context_collector
  handler                        = "lambda_function.lambda_handler"
  runtime                        = "python3.11"
  architectures                  = ["arm64"]
  memory_size                    = 512
  timeout                        = 20
  reserved_concurrent_executions = var.lambda_concurrency_limit

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
  function_name                  = "${var.project_name}-correlation-engine"
  role                           = var.iam_role_arns.correlation_engine
  handler                        = "lambda_function.lambda_handler"
  runtime                        = "python3.11"
  architectures                  = ["arm64"]
  memory_size                    = 256
  timeout                        = 10
  reserved_concurrent_executions = var.lambda_concurrency_limit

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
  function_name                  = "${var.project_name}-llm-analyzer"
  role                           = var.iam_role_arns.llm_analyzer
  handler                        = "lambda_function.lambda_handler"
  runtime                        = "python3.11"
  architectures                  = ["arm64"]
  memory_size                    = 1024
  timeout                        = 40
  reserved_concurrent_executions = var.lambda_concurrency_limit

  filename         = var.lambda_packages.llm_analyzer
  source_code_hash = filebase64sha256(var.lambda_packages.llm_analyzer)

  environment {
    variables = {
      DYNAMODB_TABLE        = var.dynamodb_table_name
      LOG_LEVEL             = var.log_level
      BEDROCK_MODEL_ID      = "anthropic.claude-3-haiku-20240307-v1:0"
      PROMPT_TEMPLATE_PARAM = "/${var.project_name}/prompt-template"
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
  function_name                  = "${var.project_name}-notification-service"
  role                           = var.iam_role_arns.notification_service
  handler                        = "lambda_function.lambda_handler"
  runtime                        = "python3.11"
  architectures                  = ["arm64"]
  memory_size                    = 256
  timeout                        = 15
  reserved_concurrent_executions = var.lambda_concurrency_limit

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

# Event Transformer Lambda Function
# Receives CloudWatch Alarm state-change events from SNS and starts the Step Functions workflow.
resource "aws_lambda_function" "event_transformer" {
  function_name                  = "${var.project_name}-event-transformer"
  role                           = var.iam_role_arns.event_transformer
  handler                        = "lambda_function.lambda_handler"
  runtime                        = "python3.11"
  architectures                  = ["arm64"]
  memory_size                    = 256
  timeout                        = 15
  reserved_concurrent_executions = var.lambda_concurrency_limit

  filename         = var.lambda_packages.event_transformer
  source_code_hash = filebase64sha256(var.lambda_packages.event_transformer)

  environment {
    variables = {
      LOG_LEVEL         = var.log_level
      SNS_TOPIC_ARN     = var.sns_topic_arn
      STATE_MACHINE_ARN = var.state_machine_arn
    }
  }

  tags = var.tags
}

# CloudWatch Log Group for Event Transformer
resource "aws_cloudwatch_log_group" "event_transformer" {
  name              = "/aws/lambda/${aws_lambda_function.event_transformer.function_name}"
  retention_in_days = 7

  tags = var.tags
}

# Allow SNS to invoke the Event Transformer Lambda
resource "aws_lambda_permission" "sns_invoke_event_transformer" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.event_transformer.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = var.sns_topic_arn
}
