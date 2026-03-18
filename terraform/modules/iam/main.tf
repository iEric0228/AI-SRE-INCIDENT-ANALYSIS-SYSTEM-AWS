# IAM Roles and Policies Module
# This module creates least-privilege IAM roles for all Lambda functions and Step Functions orchestrator

# Metrics Collector Lambda Role
resource "aws_iam_role" "metrics_collector" {
  name               = "${var.project_name}-metrics-collector-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "metrics_collector" {
  name   = "${var.project_name}-metrics-collector-policy"
  role   = aws_iam_role.metrics_collector.id
  policy = data.aws_iam_policy_document.metrics_collector.json
}

data "aws_iam_policy_document" "metrics_collector" {
  # CloudWatch Metrics read permissions
  statement {
    sid    = "CloudWatchMetricsRead"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics"
    ]
    resources = ["*"]
  }

  # CloudWatch Logs permissions for Lambda function logs
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-metrics-collector*"
    ]
  }

  # CloudWatch Metrics permissions for custom metrics
  statement {
    sid    = "CloudWatchMetricsWrite"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["AI-SRE-IncidentAnalysis"]
    }
  }
}

# Logs Collector Lambda Role
resource "aws_iam_role" "logs_collector" {
  name               = "${var.project_name}-logs-collector-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "logs_collector" {
  name   = "${var.project_name}-logs-collector-policy"
  role   = aws_iam_role.logs_collector.id
  policy = data.aws_iam_policy_document.logs_collector.json
}

data "aws_iam_policy_document" "logs_collector" {
  # CloudWatch Logs read permissions
  statement {
    sid    = "CloudWatchLogsRead"
    effect = "Allow"
    actions = [
      "logs:FilterLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ]
    resources = ["*"]
  }

  # CloudWatch Logs permissions for Lambda function logs
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-logs-collector*"
    ]
  }

  # CloudWatch Metrics permissions for custom metrics
  statement {
    sid    = "CloudWatchMetricsWrite"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["AI-SRE-IncidentAnalysis"]
    }
  }
}

# Deploy Context Collector Lambda Role
resource "aws_iam_role" "deploy_context_collector" {
  name               = "${var.project_name}-deploy-context-collector-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "deploy_context_collector" {
  name   = "${var.project_name}-deploy-context-collector-policy"
  role   = aws_iam_role.deploy_context_collector.id
  policy = data.aws_iam_policy_document.deploy_context_collector.json
}

data "aws_iam_policy_document" "deploy_context_collector" {
  # SSM Parameter Store read permissions
  statement {
    sid    = "SSMParameterRead"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameterHistory"
    ]
    resources = ["arn:aws:ssm:${var.aws_region}:${var.aws_account_id}:parameter/*"]
  }

  # CloudTrail read permissions
  statement {
    sid       = "CloudTrailRead"
    effect    = "Allow"
    actions   = ["cloudtrail:LookupEvents"]
    resources = ["*"]
  }

  # CloudWatch Logs permissions for Lambda function logs
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-deploy-context-collector*"
    ]
  }

  # CloudWatch Metrics permissions for custom metrics
  statement {
    sid    = "CloudWatchMetricsWrite"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["AI-SRE-IncidentAnalysis"]
    }
  }
}

# Correlation Engine Lambda Role
resource "aws_iam_role" "correlation_engine" {
  name               = "${var.project_name}-correlation-engine-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "correlation_engine" {
  name   = "${var.project_name}-correlation-engine-policy"
  role   = aws_iam_role.correlation_engine.id
  policy = data.aws_iam_policy_document.correlation_engine.json
}

data "aws_iam_policy_document" "correlation_engine" {
  # CloudWatch Logs permissions for Lambda function logs
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-correlation-engine*"
    ]
  }

  # CloudWatch Metrics permissions for custom metrics
  statement {
    sid    = "CloudWatchMetricsWrite"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["AI-SRE-IncidentAnalysis"]
    }
  }
}

# LLM Analyzer Lambda Role (MOST RESTRICTIVE)
resource "aws_iam_role" "llm_analyzer" {
  name               = "${var.project_name}-llm-analyzer-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "llm_analyzer" {
  name   = "${var.project_name}-llm-analyzer-policy"
  role   = aws_iam_role.llm_analyzer.id
  policy = data.aws_iam_policy_document.llm_analyzer.json
}

data "aws_iam_policy_document" "llm_analyzer" {
  # Bedrock InvokeModel permission
  statement {
    sid    = "BedrockInvokeModel"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel"
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
      "arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:inference-profile/us.anthropic.claude-*"
    ]
  }

  # SSM Parameter Store read for prompt template
  statement {
    sid    = "SSMPromptTemplateRead"
    effect = "Allow"
    actions = [
      "ssm:GetParameter"
    ]
    resources = [
      "arn:aws:ssm:${var.aws_region}:${var.aws_account_id}:parameter/${var.project_name}/prompt-template"
    ]
  }

  # CloudWatch Logs permissions for Lambda function logs
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-llm-analyzer*"
    ]
  }

  # CloudWatch Metrics permissions for custom metrics
  statement {
    sid    = "CloudWatchMetricsWrite"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["AI-SRE-IncidentAnalysis"]
    }
  }

  # EXPLICIT DENY for mutating AWS APIs
  statement {
    sid    = "ExplicitDenyMutatingAPIs"
    effect = "Deny"
    actions = [
      "ec2:*",
      "rds:*",
      "iam:*",
      "s3:Delete*",
      "s3:Put*",
      "dynamodb:Delete*",
      "dynamodb:Update*",
      "dynamodb:Put*",
      "lambda:Update*",
      "lambda:Delete*",
      "lambda:Create*",
      "lambda:Put*",
      "cloudformation:*",
      "sts:AssumeRole"
    ]
    resources = ["*"]
  }
}

# Notification Service Lambda Role
resource "aws_iam_role" "notification_service" {
  name               = "${var.project_name}-notification-service-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "notification_service" {
  name   = "${var.project_name}-notification-service-policy"
  role   = aws_iam_role.notification_service.id
  policy = data.aws_iam_policy_document.notification_service.json
}

data "aws_iam_policy_document" "notification_service" {
  # Secrets Manager read permission for Slack webhook
  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:${var.project_name}/slack-webhook*"
    ]
  }

  # SNS publish permission for email notifications
  statement {
    sid    = "SNSPublish"
    effect = "Allow"
    actions = [
      "sns:Publish"
    ]
    resources = [
      "arn:aws:sns:${var.aws_region}:${var.aws_account_id}:${var.project_name}-incident-notifications"
    ]
  }

  # KMS permissions for encrypted SNS topic and Secrets Manager
  statement {
    sid    = "KMSAccess"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]
    resources = ["*"]
  }

  # CloudWatch Logs permissions for Lambda function logs
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-notification-service*"
    ]
  }

  # CloudWatch Metrics permissions for custom metrics
  statement {
    sid    = "CloudWatchMetricsWrite"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["AI-SRE-IncidentAnalysis"]
    }
  }
}

# Event Transformer Lambda Role
resource "aws_iam_role" "event_transformer" {
  name               = "${var.project_name}-event-transformer-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "event_transformer" {
  name   = "${var.project_name}-event-transformer-policy"
  role   = aws_iam_role.event_transformer.id
  policy = data.aws_iam_policy_document.event_transformer.json
}

data "aws_iam_policy_document" "event_transformer" {
  statement {
    sid     = "StepFunctionsStart"
    effect  = "Allow"
    actions = ["states:StartExecution"]
    resources = [
      "arn:aws:states:${var.aws_region}:${var.aws_account_id}:stateMachine:${var.project_name}-orchestrator"
    ]
  }

  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/lambda/${var.project_name}-event-transformer*"
    ]
  }

  statement {
    sid     = "CloudWatchMetricsWrite"
    effect  = "Allow"
    actions = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["AI-SRE-IncidentAnalysis"]
    }
  }
}

# Step Functions Orchestrator Role
resource "aws_iam_role" "orchestrator" {
  name               = "${var.project_name}-orchestrator-role"
  assume_role_policy = data.aws_iam_policy_document.states_assume_role.json

  tags = var.tags
}

resource "aws_iam_role_policy" "orchestrator" {
  name   = "${var.project_name}-orchestrator-policy"
  role   = aws_iam_role.orchestrator.id
  policy = data.aws_iam_policy_document.orchestrator.json
}

data "aws_iam_policy_document" "orchestrator" {
  # Lambda invoke permissions for specific functions only
  statement {
    sid    = "LambdaInvoke"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction"
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-metrics-collector",
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-logs-collector",
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-deploy-context-collector",
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-correlation-engine",
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-llm-analyzer",
      "arn:aws:lambda:${var.aws_region}:${var.aws_account_id}:function:${var.project_name}-notification-service"
    ]
  }

  # DynamoDB write permission for incident storage
  statement {
    sid    = "DynamoDBWrite"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem"
    ]
    resources = [
      "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.dynamodb_table_name}"
    ]
  }

  # KMS permissions for encrypted DynamoDB table
  statement {
    sid    = "KMSDecrypt"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]
    resources = ["*"]
  }

  # X-Ray tracing permissions
  statement {
    sid    = "XRayTracing"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords"
    ]
    resources = ["*"]
  }

  # CloudWatch Logs permissions for Step Functions logs
  statement {
    sid    = "CloudWatchLogsWrite"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${var.aws_account_id}:log-group:/aws/vendedlogs/states/${var.project_name}-orchestrator*"
    ]
  }

  # Log delivery permissions required for Step Functions Express workflow logging
  statement {
    sid    = "CloudWatchLogsDelivery"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:DescribeLogGroups",
      "logs:DescribeResourcePolicies",
      "logs:GetLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:UpdateLogDelivery"
    ]
    resources = ["*"]
  }
}

# Lambda assume role policy (shared by all Lambda functions)
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# Step Functions assume role policy
data "aws_iam_policy_document" "states_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}
