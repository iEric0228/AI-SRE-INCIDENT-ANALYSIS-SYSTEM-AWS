# Variables for AI-Assisted SRE Incident Analysis System
# This file defines all configurable parameters for the infrastructure

# ============================================================================
# Core Configuration
# ============================================================================

variable "aws_region" {
  description = "AWS region where resources will be deployed"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]{1}$", var.aws_region))
    error_message = "AWS region must be a valid region identifier (e.g., us-east-1, eu-west-1)."
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "ai-sre-incident-analysis"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must contain only lowercase letters, numbers, and hyphens."
  }
}

# ============================================================================
# CloudWatch Alarm Configuration
# ============================================================================

variable "alarm_evaluation_periods" {
  description = "Number of periods over which data is compared to the threshold"
  type        = number
  default     = 2

  validation {
    condition     = var.alarm_evaluation_periods >= 1 && var.alarm_evaluation_periods <= 5
    error_message = "Evaluation periods must be between 1 and 5."
  }
}

variable "alarm_period" {
  description = "Period (in seconds) over which the alarm statistic is applied"
  type        = number
  default     = 60

  validation {
    condition     = contains([60, 300, 900, 3600], var.alarm_period)
    error_message = "Alarm period must be 60, 300, 900, or 3600 seconds."
  }
}

variable "cpu_threshold" {
  description = "CPU utilization threshold (%) that triggers high CPU alarm"
  type        = number
  default     = 80

  validation {
    condition     = var.cpu_threshold > 0 && var.cpu_threshold <= 100
    error_message = "CPU threshold must be between 1 and 100."
  }
}

variable "error_rate_threshold" {
  description = "Error rate threshold that triggers high error rate alarm"
  type        = number
  default     = 10

  validation {
    condition     = var.error_rate_threshold > 0
    error_message = "Error rate threshold must be greater than 0."
  }
}

variable "memory_threshold" {
  description = "Memory utilization threshold (%) that triggers high memory alarm"
  type        = number
  default     = 85

  validation {
    condition     = var.memory_threshold > 0 && var.memory_threshold <= 100
    error_message = "Memory threshold must be between 1 and 100."
  }
}

# ============================================================================
# Notification Configuration
# ============================================================================

variable "slack_webhook_secret_name" {
  description = "Name of the Secrets Manager secret containing Slack webhook URL"
  type        = string
  default     = ""

  validation {
    condition     = var.slack_webhook_secret_name == "" || can(regex("^[a-zA-Z0-9/_+=.@-]+$", var.slack_webhook_secret_name))
    error_message = "Secret name must contain only alphanumeric characters and /_+=.@- symbols."
  }
}

variable "email_notification_endpoints" {
  description = "List of email addresses to receive incident notifications"
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for email in var.email_notification_endpoints :
      can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email))
    ])
    error_message = "All email addresses must be valid email format."
  }
}

variable "notification_topic_name" {
  description = "Name of the SNS topic for incident notifications"
  type        = string
  default     = "incident-notifications"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+$", var.notification_topic_name))
    error_message = "Topic name must contain only alphanumeric characters, hyphens, and underscores."
  }
}

# ============================================================================
# Lambda Configuration
# ============================================================================

variable "lambda_log_level" {
  description = "Log level for Lambda functions (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], var.lambda_log_level)
    error_message = "Log level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL."
  }
}

variable "lambda_memory_sizes" {
  description = "Memory allocation (MB) for each Lambda function"
  type = object({
    metrics_collector        = number
    logs_collector           = number
    deploy_context_collector = number
    correlation_engine       = number
    llm_analyzer             = number
    notification_service     = number
  })
  default = {
    metrics_collector        = 512
    logs_collector           = 512
    deploy_context_collector = 512
    correlation_engine       = 256
    llm_analyzer             = 1024
    notification_service     = 256
  }

  validation {
    condition = alltrue([
      for k, v in var.lambda_memory_sizes :
      v >= 128 && v <= 10240
    ])
    error_message = "Lambda memory must be between 128 MB and 10240 MB."
  }
}

variable "lambda_timeout_seconds" {
  description = "Timeout (seconds) for each Lambda function"
  type = object({
    metrics_collector        = number
    logs_collector           = number
    deploy_context_collector = number
    correlation_engine       = number
    llm_analyzer             = number
    notification_service     = number
  })
  default = {
    metrics_collector        = 20
    logs_collector           = 20
    deploy_context_collector = 20
    correlation_engine       = 10
    llm_analyzer             = 40
    notification_service     = 15
  }

  validation {
    condition = alltrue([
      for k, v in var.lambda_timeout_seconds :
      v >= 3 && v <= 900
    ])
    error_message = "Lambda timeout must be between 3 and 900 seconds."
  }
}

variable "lambda_architecture" {
  description = "Instruction set architecture for Lambda functions (x86_64 or arm64)"
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "Lambda architecture must be either x86_64 or arm64."
  }
}

# ============================================================================
# DynamoDB Configuration
# ============================================================================

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB table for incident storage"
  type        = string
  default     = "incident-analysis-store"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_.-]+$", var.dynamodb_table_name))
    error_message = "Table name must contain only alphanumeric characters, hyphens, underscores, and periods."
  }
}

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode (PROVISIONED or PAY_PER_REQUEST)"
  type        = string
  default     = "PAY_PER_REQUEST"

  validation {
    condition     = contains(["PROVISIONED", "PAY_PER_REQUEST"], var.dynamodb_billing_mode)
    error_message = "Billing mode must be either PROVISIONED or PAY_PER_REQUEST."
  }
}

variable "incident_retention_days" {
  description = "Number of days to retain incident records (TTL)"
  type        = number
  default     = 90

  validation {
    condition     = var.incident_retention_days >= 1 && var.incident_retention_days <= 365
    error_message = "Retention days must be between 1 and 365."
  }
}

variable "enable_point_in_time_recovery" {
  description = "Enable point-in-time recovery for DynamoDB table"
  type        = bool
  default     = true
}

# ============================================================================
# Step Functions Configuration
# ============================================================================

variable "workflow_timeout_seconds" {
  description = "Maximum execution time for the Step Functions workflow"
  type        = number
  default     = 120

  validation {
    condition     = var.workflow_timeout_seconds >= 60 && var.workflow_timeout_seconds <= 300
    error_message = "Workflow timeout must be between 60 and 300 seconds."
  }
}

variable "enable_xray_tracing" {
  description = "Enable AWS X-Ray tracing for Step Functions"
  type        = bool
  default     = true
}

# ============================================================================
# LLM Configuration
# ============================================================================

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID for LLM analysis"
  type        = string
  default     = "anthropic.claude-v2"

  validation {
    condition     = can(regex("^anthropic\\.claude-", var.bedrock_model_id))
    error_message = "Model ID must be a valid Anthropic Claude model (e.g., anthropic.claude-v2)."
  }
}

variable "bedrock_model_temperature" {
  description = "Temperature parameter for LLM inference (0.0 to 1.0)"
  type        = number
  default     = 0.3

  validation {
    condition     = var.bedrock_model_temperature >= 0.0 && var.bedrock_model_temperature <= 1.0
    error_message = "Temperature must be between 0.0 and 1.0."
  }
}

variable "bedrock_max_tokens" {
  description = "Maximum tokens for LLM response"
  type        = number
  default     = 1000

  validation {
    condition     = var.bedrock_max_tokens >= 100 && var.bedrock_max_tokens <= 4096
    error_message = "Max tokens must be between 100 and 4096."
  }
}

variable "prompt_template_parameter_name" {
  description = "SSM Parameter Store name for LLM prompt template"
  type        = string
  default     = "/ai-sre-incident-analysis/prompt-template"

  validation {
    condition     = can(regex("^/[a-zA-Z0-9/_.-]+$", var.prompt_template_parameter_name))
    error_message = "Parameter name must start with / and contain only alphanumeric characters and /_.- symbols."
  }
}

# ============================================================================
# Observability Configuration
# ============================================================================

variable "cloudwatch_log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.cloudwatch_log_retention_days)
    error_message = "Log retention must be a valid CloudWatch Logs retention period."
  }
}

variable "enable_detailed_monitoring" {
  description = "Enable detailed CloudWatch monitoring for all resources"
  type        = bool
  default     = true
}

variable "create_cloudwatch_alarms" {
  description = "Create CloudWatch alarms for the incident analysis system itself"
  type        = bool
  default     = true
}

# ============================================================================
# Security Configuration
# ============================================================================

variable "kms_key_deletion_window" {
  description = "Number of days before KMS key deletion (7-30)"
  type        = number
  default     = 30

  validation {
    condition     = var.kms_key_deletion_window >= 7 && var.kms_key_deletion_window <= 30
    error_message = "KMS key deletion window must be between 7 and 30 days."
  }
}

variable "enable_kms_key_rotation" {
  description = "Enable automatic rotation for KMS keys"
  type        = bool
  default     = true
}

variable "secrets_rotation_days" {
  description = "Number of days between automatic secret rotation"
  type        = number
  default     = 90

  validation {
    condition     = var.secrets_rotation_days >= 30 && var.secrets_rotation_days <= 365
    error_message = "Secrets rotation must be between 30 and 365 days."
  }
}

# ============================================================================
# Data Collection Configuration
# ============================================================================

variable "metrics_lookback_minutes" {
  description = "Number of minutes to look back for metrics collection"
  type        = number
  default     = 60

  validation {
    condition     = var.metrics_lookback_minutes >= 5 && var.metrics_lookback_minutes <= 1440
    error_message = "Metrics lookback must be between 5 and 1440 minutes (24 hours)."
  }
}

variable "logs_lookback_minutes" {
  description = "Number of minutes to look back for logs collection"
  type        = number
  default     = 30

  validation {
    condition     = var.logs_lookback_minutes >= 5 && var.logs_lookback_minutes <= 1440
    error_message = "Logs lookback must be between 5 and 1440 minutes (24 hours)."
  }
}

variable "changes_lookback_hours" {
  description = "Number of hours to look back for deployment/configuration changes"
  type        = number
  default     = 24

  validation {
    condition     = var.changes_lookback_hours >= 1 && var.changes_lookback_hours <= 168
    error_message = "Changes lookback must be between 1 and 168 hours (7 days)."
  }
}

variable "max_log_entries" {
  description = "Maximum number of log entries to collect per incident"
  type        = number
  default     = 100

  validation {
    condition     = var.max_log_entries >= 10 && var.max_log_entries <= 1000
    error_message = "Max log entries must be between 10 and 1000."
  }
}

variable "max_context_size_bytes" {
  description = "Maximum size (bytes) of structured context for LLM"
  type        = number
  default     = 51200

  validation {
    condition     = var.max_context_size_bytes >= 10240 && var.max_context_size_bytes <= 102400
    error_message = "Max context size must be between 10KB and 100KB."
  }
}

# ============================================================================
# Resource Tags
# ============================================================================

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project   = "AI-SRE-Portfolio"
    ManagedBy = "Terraform"
    Purpose   = "Incident-Analysis"
  }
}

variable "additional_tags" {
  description = "Additional tags to merge with default tags"
  type        = map(string)
  default     = {}
}
