# Secrets Manager module for storing notification service credentials
# Validates Requirements: 14.1, 14.2, 14.5

data "aws_caller_identity" "current" {}

# KMS key for encrypting secrets
resource "aws_kms_key" "secrets" {
  description             = "KMS key for encrypting Secrets Manager secrets"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-secrets-key"
      Project = "AI-SRE-Portfolio"
    }
  )
}

resource "aws_kms_key_policy" "secrets" {
  key_id = aws_kms_key.secrets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "key-default-1"
    Statement = [
      {
        Sid    = "EnableIAMUserPermissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowEventBridgeToEncrypt"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.project_name}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# Slack webhook URL secret
resource "aws_secretsmanager_secret" "slack_webhook" {
  name                    = "${var.project_name}/slack-webhook"
  description             = "Slack webhook URL for incident notifications"
  kms_key_id              = aws_kms_key.secrets.arn
  recovery_window_in_days = 7

  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-slack-webhook"
      Project = "AI-SRE-Portfolio"
    }
  )
}

# Slack webhook secret version (placeholder - must be updated manually or via CI/CD)
resource "aws_secretsmanager_secret_version" "slack_webhook" {
  secret_id = aws_secretsmanager_secret.slack_webhook.id
  secret_string = jsonencode({
    webhook_url = var.slack_webhook_url
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Automatic rotation configuration for Slack webhook
resource "aws_secretsmanager_secret_rotation" "slack_webhook" {
  count = var.enable_rotation ? 1 : 0

  secret_id           = aws_secretsmanager_secret.slack_webhook.id
  rotation_lambda_arn = var.rotation_lambda_arn

  rotation_rules {
    automatically_after_days = var.rotation_days
  }
}

# Email configuration secret
resource "aws_secretsmanager_secret" "email_config" {
  name                    = "${var.project_name}/email-config"
  description             = "Email configuration for incident notifications"
  kms_key_id              = aws_kms_key.secrets.arn
  recovery_window_in_days = 7

  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-email-config"
      Project = "AI-SRE-Portfolio"
    }
  )
}

# Email configuration secret version (placeholder - must be updated manually or via CI/CD)
resource "aws_secretsmanager_secret_version" "email_config" {
  secret_id = aws_secretsmanager_secret.email_config.id
  secret_string = jsonencode({
    sns_topic_arn    = var.email_sns_topic_arn
    from_address     = var.email_from_address
    recipient_emails = var.email_recipients
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Automatic rotation configuration for email config
resource "aws_secretsmanager_secret_rotation" "email_config" {
  count = var.enable_rotation ? 1 : 0

  secret_id           = aws_secretsmanager_secret.email_config.id
  rotation_lambda_arn = var.rotation_lambda_arn

  rotation_rules {
    automatically_after_days = var.rotation_days
  }
}
