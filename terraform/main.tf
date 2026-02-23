# AI-Assisted SRE Incident Analysis System - Root Terraform Configuration
# This file instantiates all infrastructure modules and wires them together

# ============================================================================
# Terraform and Provider Configuration
# ============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # S3 backend for remote state storage
  # Supports multiple environments via workspaces
  backend "s3" {
    bucket         = "ai-sre-incident-analysis-terraform-state"
    key            = "incident-analysis/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"

    # Workspace-specific state files
    workspace_key_prefix = "env"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      var.tags,
      var.additional_tags,
      {
        Environment = var.environment
        Workspace   = terraform.workspace
      }
    )
  }
}

# ============================================================================
# Data Sources
# ============================================================================

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# ============================================================================
# Local Values
# ============================================================================

locals {
  # Combine default and additional tags
  common_tags = merge(
    var.tags,
    var.additional_tags,
    {
      Environment = var.environment
      Workspace   = terraform.workspace
    }
  )

  # Account and region information
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name

  # Lambda deployment package paths
  lambda_packages = {
    metrics_collector        = "${path.module}/../src/metrics_collector/deployment.zip"
    logs_collector           = "${path.module}/../src/logs_collector/deployment.zip"
    deploy_context_collector = "${path.module}/../src/deploy_context_collector/deployment.zip"
    correlation_engine       = "${path.module}/../src/correlation_engine/deployment.zip"
    llm_analyzer             = "${path.module}/../src/llm_analyzer/deployment.zip"
    notification_service     = "${path.module}/../src/notification_service/deployment.zip"
  }
}

# ============================================================================
# Module: Secrets Manager (KMS Key)
# Must be created first as other modules depend on it
# ============================================================================

module "secrets" {
  source = "./modules/secrets"

  project_name        = var.project_name
  email_sns_topic_arn = ""    # Will be updated after EventBridge module creates SNS topic
  enable_rotation     = false # Rotation requires Lambda function (future enhancement)
  rotation_days       = var.secrets_rotation_days

  tags = local.common_tags
}

# ============================================================================
# Module: IAM Roles and Policies
# Must be created before Lambda and Step Functions
# ============================================================================

module "iam" {
  source = "./modules/iam"

  project_name   = var.project_name
  aws_region     = local.region
  aws_account_id = local.account_id

  tags = local.common_tags
}

# ============================================================================
# Module: DynamoDB Incident Store
# ============================================================================

module "dynamodb" {
  source = "./modules/dynamodb"

  table_name  = var.dynamodb_table_name
  kms_key_arn = module.secrets.kms_key_arn

  tags = local.common_tags
}

# ============================================================================
# Module: EventBridge and SNS
# Note: event_transformer_lambda_arn is placeholder - will be created in future task
# ============================================================================

module "eventbridge" {
  source = "./modules/eventbridge"

  project_name                 = var.project_name
  event_transformer_lambda_arn = "arn:aws:lambda:${local.region}:${local.account_id}:function:${var.project_name}-event-transformer"
  kms_key_id                   = module.secrets.kms_key_id
  alarm_notification_topic_arn = "" # Will be populated by cloudwatch_alarms module

  tags = local.common_tags

  depends_on = [module.secrets]
}

# ============================================================================
# Module: Lambda Functions
# ============================================================================

module "lambda" {
  source = "./modules/lambda"

  project_name        = var.project_name
  aws_region          = local.region
  iam_role_arns       = module.iam.lambda_role_arns
  lambda_packages     = local.lambda_packages
  dynamodb_table_name = module.dynamodb.table_name
  sns_topic_arn       = module.eventbridge.sns_topic_arn
  log_level           = var.lambda_log_level

  tags = local.common_tags

  depends_on = [
    module.iam,
    module.dynamodb,
    module.eventbridge
  ]
}

# ============================================================================
# Module: Step Functions Orchestrator
# ============================================================================

module "step_functions" {
  source = "./modules/step-functions"

  project_name           = var.project_name
  state_machine_role_arn = module.iam.orchestrator_role_arn
  lambda_function_arns   = module.lambda.lambda_function_arns
  dynamodb_table_name    = module.dynamodb.table_name

  tags = local.common_tags

  depends_on = [
    module.iam,
    module.lambda,
    module.dynamodb
  ]
}

# ============================================================================
# Module: CloudWatch Alarms and Dashboard
# ============================================================================

module "cloudwatch_alarms" {
  source = "./modules/cloudwatch-alarms"
  count  = var.create_cloudwatch_alarms ? 1 : 0

  project_name                        = var.project_name
  aws_region                          = local.region
  state_machine_arn                   = module.step_functions.state_machine_arn
  state_machine_log_group_name        = module.step_functions.log_group_name
  llm_analyzer_function_name          = module.lambda.llm_analyzer_name
  notification_service_function_name  = module.lambda.notification_service_name
  notification_service_log_group_name = "/aws/lambda/${module.lambda.notification_service_name}"
  correlation_engine_function_name    = module.lambda.correlation_engine_name
  dynamodb_table_name                 = module.dynamodb.table_name
  kms_key_id                          = module.secrets.kms_key_id
  ops_email                           = length(var.email_notification_endpoints) > 0 ? var.email_notification_endpoints[0] : ""

  tags = local.common_tags

  depends_on = [
    module.step_functions,
    module.lambda,
    module.dynamodb,
    module.secrets
  ]
}

# ============================================================================
# Outputs
# Note: All outputs are defined in outputs.tf
# ============================================================================
