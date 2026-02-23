# Outputs for AI-Assisted SRE Incident Analysis System
# These outputs expose key resource identifiers for integration and reference

# ============================================================================
# Step Functions Orchestrator Outputs
# ============================================================================

output "orchestrator_arn" {
  description = "ARN of the Step Functions state machine orchestrator"
  value       = module.step_functions.state_machine_arn
}

output "orchestrator_name" {
  description = "Name of the Step Functions state machine"
  value       = module.step_functions.state_machine_name
}

output "orchestrator_role_arn" {
  description = "ARN of the IAM role used by the orchestrator"
  value       = module.iam.orchestrator_role_arn
}

# ============================================================================
# DynamoDB Incident Store Outputs
# ============================================================================

output "incident_table_name" {
  description = "Name of the DynamoDB table storing incident records"
  value       = module.dynamodb.table_name
}

output "incident_table_arn" {
  description = "ARN of the DynamoDB incident store table"
  value       = module.dynamodb.table_arn
}

output "incident_table_stream_arn" {
  description = "ARN of the DynamoDB table stream (if enabled)"
  value       = try(module.dynamodb.table_stream_arn, null)
}

# ============================================================================
# SNS Topic Outputs
# ============================================================================

output "notification_topic_arn" {
  description = "ARN of the SNS topic for incident notifications"
  value       = module.eventbridge.sns_topic_arn
}

output "notification_topic_name" {
  description = "Name of the SNS topic for notifications"
  value       = module.eventbridge.sns_topic_name
}

# ============================================================================
# Lambda Function Outputs
# ============================================================================

output "lambda_function_arns" {
  description = "ARNs of all Lambda functions in the workflow"
  value = {
    metrics_collector        = module.lambda.metrics_collector_arn
    logs_collector           = module.lambda.logs_collector_arn
    deploy_context_collector = module.lambda.deploy_context_collector_arn
    correlation_engine       = module.lambda.correlation_engine_arn
    llm_analyzer             = module.lambda.llm_analyzer_arn
    notification_service     = module.lambda.notification_service_arn
  }
}

output "lambda_function_names" {
  description = "Names of all Lambda functions in the workflow"
  value = {
    metrics_collector        = module.lambda.metrics_collector_name
    logs_collector           = module.lambda.logs_collector_name
    deploy_context_collector = module.lambda.deploy_context_collector_name
    correlation_engine       = module.lambda.correlation_engine_name
    llm_analyzer             = module.lambda.llm_analyzer_name
    notification_service     = module.lambda.notification_service_name
  }
}

output "lambda_log_group_names" {
  description = "CloudWatch Log Group names for all Lambda functions"
  value = {
    metrics_collector        = "/aws/lambda/${module.lambda.metrics_collector_name}"
    logs_collector           = "/aws/lambda/${module.lambda.logs_collector_name}"
    deploy_context_collector = "/aws/lambda/${module.lambda.deploy_context_collector_name}"
    correlation_engine       = "/aws/lambda/${module.lambda.correlation_engine_name}"
    llm_analyzer             = "/aws/lambda/${module.lambda.llm_analyzer_name}"
    notification_service     = "/aws/lambda/${module.lambda.notification_service_name}"
  }
}

# ============================================================================
# EventBridge Outputs
# ============================================================================

output "eventbridge_rule_arn" {
  description = "ARN of the EventBridge rule for CloudWatch Alarm events"
  value       = module.eventbridge.eventbridge_rule_arn
}

output "eventbridge_rule_name" {
  description = "Name of the EventBridge rule"
  value       = module.eventbridge.eventbridge_rule_name
}

# ============================================================================
# IAM Role Outputs
# ============================================================================

output "iam_role_arns" {
  description = "ARNs of all IAM roles created for the system"
  value = {
    metrics_collector        = module.iam.metrics_collector_role_arn
    logs_collector           = module.iam.logs_collector_role_arn
    deploy_context_collector = module.iam.deploy_context_collector_role_arn
    correlation_engine       = module.iam.correlation_engine_role_arn
    llm_analyzer             = module.iam.llm_analyzer_role_arn
    notification_service     = module.iam.notification_service_role_arn
    orchestrator             = module.iam.orchestrator_role_arn
  }
}

# ============================================================================
# Security Outputs
# ============================================================================

output "kms_key_id" {
  description = "ID of the KMS key used for encryption"
  value       = module.secrets.kms_key_id
  sensitive   = true
}

output "kms_key_arn" {
  description = "ARN of the KMS key used for encryption"
  value       = module.secrets.kms_key_arn
}

output "slack_secret_arn" {
  description = "ARN of the Secrets Manager secret for Slack webhook"
  value       = module.secrets.slack_webhook_secret_arn
  sensitive   = true
}

# ============================================================================
# CloudWatch Alarms Outputs
# ============================================================================

output "system_alarm_arns" {
  description = "ARNs of CloudWatch alarms monitoring the incident analysis system"
  value = var.create_cloudwatch_alarms ? {
    workflow_failures              = module.cloudwatch_alarms[0].workflow_failures_alarm_arn
    workflow_timeouts              = module.cloudwatch_alarms[0].workflow_timeouts_alarm_arn
    llm_analyzer_errors            = module.cloudwatch_alarms[0].llm_analyzer_errors_alarm_arn
    llm_analyzer_timeouts          = module.cloudwatch_alarms[0].llm_analyzer_timeouts_alarm_arn
    notification_errors            = module.cloudwatch_alarms[0].notification_errors_alarm_arn
    notification_delivery_failures = module.cloudwatch_alarms[0].notification_delivery_failures_alarm_arn
    collector_failures             = module.cloudwatch_alarms[0].collector_failures_alarm_arn
    dynamodb_throttles             = module.cloudwatch_alarms[0].dynamodb_throttles_alarm_arn
    correlation_engine_errors      = module.cloudwatch_alarms[0].correlation_engine_errors_alarm_arn
  } : {}
}

# ============================================================================
# Configuration Outputs
# ============================================================================

output "prompt_template_parameter_name" {
  description = "SSM Parameter Store name for the LLM prompt template"
  value       = var.prompt_template_parameter_name
}

output "bedrock_model_id" {
  description = "Amazon Bedrock model ID used for analysis"
  value       = var.bedrock_model_id
}

# ============================================================================
# Console URLs
# ============================================================================

output "console_urls" {
  description = "AWS Console URLs for key resources"
  value = {
    state_machine = "https://console.aws.amazon.com/states/home?region=${var.aws_region}#/statemachines/view/${module.step_functions.state_machine_arn}"
    dynamodb      = "https://console.aws.amazon.com/dynamodbv2/home?region=${var.aws_region}#table?name=${module.dynamodb.table_name}"
    cloudwatch    = "https://console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:"
    xray          = "https://console.aws.amazon.com/xray/home?region=${var.aws_region}#/service-map"
  }
}

# ============================================================================
# Integration Outputs
# ============================================================================

output "integration_config" {
  description = "Configuration values for external integrations"
  value = {
    region             = var.aws_region
    environment        = var.environment
    orchestrator_arn   = module.step_functions.state_machine_arn
    notification_topic = module.eventbridge.sns_topic_arn
    incident_table     = module.dynamodb.table_name
    log_level          = var.lambda_log_level
  }
}

# ============================================================================
# Deployment Information
# ============================================================================

output "deployment_info" {
  description = "Information about the deployed infrastructure"
  value = {
    project_name        = var.project_name
    environment         = var.environment
    region              = var.aws_region
    terraform_workspace = terraform.workspace
    lambda_architecture = var.lambda_architecture
    workflow_timeout    = var.workflow_timeout_seconds
    incident_retention  = var.incident_retention_days
  }
}

# ============================================================================
# Testing Outputs
# ============================================================================

output "test_configuration" {
  description = "Configuration values for testing the system"
  value = {
    orchestrator_arn          = module.step_functions.state_machine_arn
    test_alarm_topic          = module.eventbridge.sns_topic_arn
    incident_table            = module.dynamodb.table_name
    metrics_collector_name    = module.lambda.metrics_collector_name
    logs_collector_name       = module.lambda.logs_collector_name
    correlation_engine_name   = module.lambda.correlation_engine_name
    llm_analyzer_name         = module.lambda.llm_analyzer_name
    notification_service_name = module.lambda.notification_service_name
  }
}
