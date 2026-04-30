# Variables for Lambda module

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "ai-sre-incident-analysis"
}

variable "aws_region" {
  description = "AWS region where resources are deployed"
  type        = string
}

variable "iam_role_arns" {
  description = "Map of IAM role ARNs for Lambda functions"
  type = object({
    metrics_collector        = string
    logs_collector           = string
    deploy_context_collector = string
    correlation_engine       = string
    llm_analyzer             = string
    notification_service     = string
    event_transformer        = string
  })
}

variable "lambda_packages" {
  description = "Map of Lambda deployment package file paths"
  type = object({
    metrics_collector        = string
    logs_collector           = string
    deploy_context_collector = string
    correlation_engine       = string
    llm_analyzer             = string
    notification_service     = string
    event_transformer        = string
  })
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB incident store table"
  type        = string
}

variable "sns_topic_arn" {
  description = "ARN of the SNS topic for incident notifications"
  type        = string
}

variable "state_machine_arn" {
  description = "ARN of the Step Functions state machine for the event transformer to start"
  type        = string
}

variable "lambda_concurrency_limit" {
  description = "Maximum concurrent executions per Lambda function (prevents runaway costs)"
  type        = number
  default     = 100
}

variable "log_level" {
  description = "Log level for Lambda functions (DEBUG, INFO, WARNING, ERROR)"
  type        = string
  default     = "INFO"
}

variable "enable_lambda_insights" {
  description = "Enable CloudWatch Lambda Insights for all functions"
  type        = bool
  default     = true
}

variable "lambda_insights_layer_version" {
  description = "Version of the Lambda Insights extension layer"
  type        = number
  default     = 21
}

variable "log_group_mapping_parameter_name" {
  description = "SSM parameter name for custom log group mappings"
  type        = string
  default     = "/ai-sre-incident-analysis/log-group-mappings"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days for Lambda function logs (7 for dev, 30 for prod)"
  type        = number
  default     = 7
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID for LLM analysis"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "max_context_size_bytes" {
  description = "Maximum context size in bytes for LLM input"
  type        = number
  default     = 51200
}

variable "tags" {
  description = "Tags to apply to all Lambda resources"
  type        = map(string)
  default = {
    Project = "AI-SRE-Portfolio"
  }
}
