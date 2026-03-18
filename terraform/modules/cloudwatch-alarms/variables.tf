# CloudWatch Alarms Module Variables

variable "project_name" {
  description = "Name of the project, used for resource naming"
  type        = string
}

variable "aws_region" {
  description = "AWS region for CloudWatch dashboard"
  type        = string
}

variable "state_machine_arn" {
  description = "ARN of the Step Functions state machine to monitor"
  type        = string
}

variable "state_machine_log_group_name" {
  description = "CloudWatch log group name for Step Functions state machine"
  type        = string
}

variable "llm_analyzer_function_name" {
  description = "Name of the LLM analyzer Lambda function"
  type        = string
}

variable "notification_service_function_name" {
  description = "Name of the notification service Lambda function"
  type        = string
}

variable "notification_service_log_group_name" {
  description = "CloudWatch log group name for notification service Lambda"
  type        = string
}

variable "correlation_engine_function_name" {
  description = "Name of the correlation engine Lambda function"
  type        = string
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB incident store table"
  type        = string
}

variable "kms_key_id" {
  description = "KMS key ID for encrypting SNS topic"
  type        = string
}

variable "metric_namespace" {
  description = "CloudWatch metric namespace used by Lambda functions for custom put_metric calls (must match METRIC_NAMESPACE in src/shared/metrics.py)"
  type        = string
  default     = "AI-SRE-IncidentAnalysis"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
