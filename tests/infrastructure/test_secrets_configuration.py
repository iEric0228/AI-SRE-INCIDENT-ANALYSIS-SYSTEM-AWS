"""
Infrastructure tests for Secrets Manager module configuration.

Validates Requirements: 14.1, 14.2, 14.4, 14.5
"""

import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def secrets_module_path():
    """Path to the Secrets Manager Terraform module"""
    return Path(__file__).parent.parent.parent / "terraform" / "modules" / "secrets"


@pytest.fixture
def secrets_main_tf(secrets_module_path):
    """Load main.tf configuration"""
    main_tf_path = secrets_module_path / "main.tf"
    with open(main_tf_path, "r") as f:
        return f.read()


@pytest.fixture
def secrets_variables_tf(secrets_module_path):
    """Load variables.tf configuration"""
    variables_tf_path = secrets_module_path / "variables.tf"
    with open(variables_tf_path, "r") as f:
        return f.read()


class TestSecretsManagerConfiguration:
    """Test Secrets Manager module configuration"""

    def test_slack_webhook_secret_exists(self, secrets_main_tf):
        """
        Validates Requirement 14.1: Store Slack webhook URLs in AWS Secrets Manager
        """
        assert (
            'resource "aws_secretsmanager_secret" "slack_webhook"' in secrets_main_tf
        ), "Slack webhook secret not defined"
        assert "slack-webhook" in secrets_main_tf, "Secret name should contain 'slack-webhook'"
        assert (
            "Slack webhook URL for incident notifications" in secrets_main_tf
        ), "Secret description mismatch"

    def test_email_config_secret_exists(self, secrets_main_tf):
        """
        Validates Requirement 14.2: Store email configuration in AWS Secrets Manager
        """
        assert (
            'resource "aws_secretsmanager_secret" "email_config"' in secrets_main_tf
        ), "Email config secret not defined"
        assert "email-config" in secrets_main_tf, "Secret name should contain 'email-config'"
        assert (
            "Email configuration for incident notifications" in secrets_main_tf
        ), "Secret description mismatch"

    def test_secrets_use_kms_encryption(self, secrets_main_tf):
        """
        Validates Requirement 14.4: All secrets encrypted with KMS
        """
        # Check KMS key exists
        assert (
            'resource "aws_kms_key" "secrets"' in secrets_main_tf
        ), "KMS key not defined for secret encryption"
        assert (
            "enable_key_rotation     = true" in secrets_main_tf
        ), "KMS key rotation should be enabled"

        # Check secrets reference KMS key
        assert (
            "kms_key_id              = aws_kms_key.secrets.arn" in secrets_main_tf
        ), "Secrets should use KMS encryption"

    def test_automatic_rotation_configuration(self, secrets_main_tf):
        """
        Validates Requirement 14.5: Rotate secrets automatically every 90 days
        """
        assert (
            'resource "aws_secretsmanager_secret_rotation" "slack_webhook"' in secrets_main_tf
        ), "Slack webhook rotation configuration missing"
        assert (
            'resource "aws_secretsmanager_secret_rotation" "email_config"' in secrets_main_tf
        ), "Email config rotation configuration missing"

        # Check rotation is conditional
        assert (
            "count = var.enable_rotation ? 1 : 0" in secrets_main_tf
        ), "Rotation should be conditional"

        # Check rotation rules
        assert (
            "automatically_after_days = var.rotation_days" in secrets_main_tf
        ), "Rotation should use rotation_days variable"

    def test_secret_recovery_window(self, secrets_main_tf):
        """
        Test that secrets have a recovery window configured
        """
        assert (
            "recovery_window_in_days = 7" in secrets_main_tf
        ), "Secrets should have 7-day recovery window"

    def test_secret_versions_ignore_changes(self, secrets_main_tf):
        """
        Validates Requirement 14.4: Secrets not managed in Terraform state after initial creation
        """
        assert (
            'resource "aws_secretsmanager_secret_version" "slack_webhook"' in secrets_main_tf
        ), "Slack webhook secret version not defined"
        assert (
            'resource "aws_secretsmanager_secret_version" "email_config"' in secrets_main_tf
        ), "Email config secret version not defined"

        # Check lifecycle ignore_changes
        assert (
            "ignore_changes = [secret_string]" in secrets_main_tf
        ), "Secret versions should ignore secret_string changes"

    def test_rotation_days_default_value(self, secrets_variables_tf):
        """
        Validates Requirement 14.5: Default rotation period is 90 days
        """
        assert (
            'variable "rotation_days"' in secrets_variables_tf
        ), "rotation_days variable not defined"
        assert "type        = number" in secrets_variables_tf, "rotation_days should be a number"
        assert (
            "default     = 90" in secrets_variables_tf
        ), "Default rotation period should be 90 days"

    def test_sensitive_variables_marked(self, secrets_variables_tf):
        """
        Test that sensitive variables are marked as sensitive
        """
        assert (
            'variable "slack_webhook_url"' in secrets_variables_tf
        ), "slack_webhook_url variable not defined"
        assert (
            "sensitive   = true" in secrets_variables_tf
        ), "slack_webhook_url should be marked as sensitive"

    def test_kms_key_alias_configured(self, secrets_main_tf):
        """
        Test that KMS key has an alias for easier reference
        """
        assert 'resource "aws_kms_alias" "secrets"' in secrets_main_tf, "KMS key alias not defined"
        assert "secrets" in secrets_main_tf, "KMS alias should contain 'secrets'"
        assert (
            "target_key_id = aws_kms_key.secrets.key_id" in secrets_main_tf
        ), "KMS alias should reference the secrets KMS key"

    def test_project_tagging(self, secrets_main_tf):
        """
        Validates Requirement 17.6: Tag all resources for cost tracking
        """
        # Check for Project tag
        assert "AI-SRE-Portfolio" in secrets_main_tf, "Resources missing Project tag"


class TestSecretsManagerOutputs:
    """Test Secrets Manager module outputs"""

    def test_required_outputs_defined(self, secrets_module_path):
        """
        Test that all required outputs are defined
        """
        outputs_tf_path = secrets_module_path / "outputs.tf"
        with open(outputs_tf_path, "r") as f:
            outputs_tf = f.read()

        required_outputs = [
            "slack_webhook_secret_arn",
            "slack_webhook_secret_name",
            "email_config_secret_arn",
            "email_config_secret_name",
            "kms_key_arn",
            "kms_key_id",
        ]

        for required_output in required_outputs:
            assert (
                f'output "{required_output}"' in outputs_tf
            ), f"Required output {required_output} not defined"

    def test_output_descriptions(self, secrets_module_path):
        """
        Test that all outputs have descriptions
        """
        outputs_tf_path = secrets_module_path / "outputs.tf"
        with open(outputs_tf_path, "r") as f:
            outputs_tf = f.read()

        # Count output blocks
        output_count = outputs_tf.count('output "')
        description_count = outputs_tf.count("description =")

        assert output_count == description_count, "All outputs should have descriptions"


class TestSecretsManagerDocumentation:
    """Test Secrets Manager module documentation"""

    def test_readme_exists(self, secrets_module_path):
        """
        Test that README.md exists
        """
        readme_path = secrets_module_path / "README.md"
        assert readme_path.exists(), "README.md not found"

    def test_readme_contains_usage_examples(self, secrets_module_path):
        """
        Test that README contains usage examples
        """
        readme_path = secrets_module_path / "README.md"
        with open(readme_path, "r") as f:
            readme_content = f.read()

        assert "## Usage" in readme_content, "README missing Usage section"
        assert 'module "secrets"' in readme_content, "README missing module usage example"

    def test_readme_contains_iam_permissions(self, secrets_module_path):
        """
        Test that README documents required IAM permissions
        """
        readme_path = secrets_module_path / "README.md"
        with open(readme_path, "r") as f:
            readme_content = f.read()

        assert "## IAM Permissions" in readme_content, "README missing IAM Permissions section"
        assert (
            "secretsmanager:GetSecretValue" in readme_content
        ), "README missing GetSecretValue permission"
        assert "kms:Decrypt" in readme_content, "README missing KMS Decrypt permission"

    def test_readme_contains_rotation_instructions(self, secrets_module_path):
        """
        Validates Requirement 14.5: Documentation for secret rotation
        """
        readme_path = secrets_module_path / "README.md"
        with open(readme_path, "r") as f:
            readme_content = f.read()

        assert (
            "## Automatic Rotation" in readme_content
        ), "README missing Automatic Rotation section"
        assert "rotation_days" in readme_content, "README missing rotation_days documentation"
        assert "90" in readme_content, "README should mention 90-day rotation period"

    def test_readme_contains_compliance_section(self, secrets_module_path):
        """
        Test that README documents compliance with requirements
        """
        readme_path = secrets_module_path / "README.md"
        with open(readme_path, "r") as f:
            readme_content = f.read()

        assert "## Compliance" in readme_content, "README missing Compliance section"
        assert "14.1" in readme_content, "README missing requirement 14.1"
        assert "14.2" in readme_content, "README missing requirement 14.2"
        assert "14.5" in readme_content, "README missing requirement 14.5"
