# Variables for IAM module

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "ai-sre-incident-analysis"
}

variable "aws_region" {
  description = "AWS region where resources are deployed"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB table for incident storage"
  type        = string
  default     = "incident-analysis-store"
}

variable "enable_lambda_insights" {
  description = "Enable CloudWatch Lambda Insights for all functions"
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "ARN of the KMS key used for encrypting DynamoDB, SNS, and Secrets Manager"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all IAM resources"
  type        = map(string)
  default = {
    Project = "AI-SRE-Portfolio"
  }
}
