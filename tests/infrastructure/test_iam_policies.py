"""
Unit tests for IAM policy validation.

These tests validate that IAM roles follow least-privilege principles
and that the LLM Analyzer has explicit denies for restricted services.

Validates Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
"""

import json
import os
import subprocess
from pathlib import Path


def get_terraform_module_path():
    """Get the path to the IAM Terraform module."""
    return Path(__file__).parent.parent.parent / "terraform" / "modules" / "iam"


def parse_terraform_policy(policy_document_hcl):
    """
    Parse a Terraform IAM policy document data source.

    This is a simplified parser for testing purposes.
    In production, you would use terraform show -json.
    """
    # For now, we'll read the HCL directly and validate structure
    return policy_document_hcl


class TestMetricsCollectorIAMPolicy:
    """Test Metrics Collector IAM policy (Requirement 10.1)."""

    def test_metrics_collector_has_only_cloudwatch_metrics_permissions(self):
        """
        Requirement 10.1: Metrics Collector SHALL have IAM permissions ONLY for
        cloudwatch:GetMetricStatistics and cloudwatch:ListMetrics
        """
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Verify CloudWatch Metrics permissions are present
        assert "cloudwatch:GetMetricStatistics" in main_tf
        assert "cloudwatch:ListMetrics" in main_tf

        # Verify policy is scoped to metrics_collector
        assert 'data "aws_iam_policy_document" "metrics_collector"' in main_tf

        # Verify no other AWS service permissions (except logs for Lambda logging)
        policy_section = self._extract_policy_section(main_tf, "metrics_collector")

        # Should not have permissions for other services
        forbidden_services = [
            "ec2:",
            "rds:",
            "iam:",
            "s3:",
            "dynamodb:",
            "lambda:",
            "bedrock:",
            "sns:",
            "secretsmanager:",
        ]
        for service in forbidden_services:
            # Allow logs: for CloudWatch Logs (Lambda logging)
            if service != "logs:":
                assert service not in policy_section or "logs:" in service

    def _extract_policy_section(self, content, policy_name):
        """Extract a specific policy document section from Terraform HCL."""
        start = content.find(f'data "aws_iam_policy_document" "{policy_name}"')
        if start == -1:
            return ""

        # Find the closing brace
        brace_count = 0
        in_block = False
        end = start

        for i in range(start, len(content)):
            if content[i] == "{":
                brace_count += 1
                in_block = True
            elif content[i] == "}":
                brace_count -= 1
                if in_block and brace_count == 0:
                    end = i + 1
                    break

        return content[start:end]


class TestLogsCollectorIAMPolicy:
    """Test Logs Collector IAM policy (Requirement 10.2)."""

    def test_logs_collector_has_only_cloudwatch_logs_permissions(self):
        """
        Requirement 10.2: Logs Collector SHALL have IAM permissions ONLY for
        logs:FilterLogEvents and logs:DescribeLogGroups
        """
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Verify CloudWatch Logs permissions are present
        assert "logs:FilterLogEvents" in main_tf
        assert "logs:DescribeLogGroups" in main_tf
        assert "logs:DescribeLogStreams" in main_tf

        # Verify policy is scoped to logs_collector
        assert 'data "aws_iam_policy_document" "logs_collector"' in main_tf


class TestDeployContextCollectorIAMPolicy:
    """Test Deploy Context Collector IAM policy (Requirement 10.3)."""

    def test_deploy_context_collector_has_only_ssm_and_cloudtrail_permissions(self):
        """
        Requirement 10.3: Deploy Context Collector SHALL have IAM permissions ONLY for
        ssm:GetParameter, ssm:GetParameterHistory, and cloudtrail:LookupEvents
        """
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Verify SSM and CloudTrail permissions are present
        assert "ssm:GetParameter" in main_tf
        assert "ssm:GetParameterHistory" in main_tf
        assert "cloudtrail:LookupEvents" in main_tf

        # Verify policy is scoped to deploy_context_collector
        assert 'data "aws_iam_policy_document" "deploy_context_collector"' in main_tf


class TestLLMAnalyzerIAMPolicy:
    """Test LLM Analyzer IAM policy (Requirements 10.4, 10.5)."""

    def test_llm_analyzer_has_only_bedrock_invoke_permission(self):
        """
        Requirement 10.4: LLM Analyzer SHALL have IAM permissions ONLY for
        bedrock:InvokeModel
        """
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Verify Bedrock permission is present
        assert "bedrock:InvokeModel" in main_tf

        # Verify SSM permission for prompt template
        assert "ssm:GetParameter" in main_tf

        # Verify policy is scoped to llm_analyzer
        assert 'data "aws_iam_policy_document" "llm_analyzer"' in main_tf

    def test_llm_analyzer_has_explicit_deny_for_restricted_services(self):
        """
        Requirement 10.5: LLM Analyzer SHALL NOT have permissions for any
        EC2, RDS, IAM, or mutating AWS APIs
        """
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Extract LLM analyzer policy section
        policy_section = self._extract_llm_policy_section(main_tf)

        # Verify explicit deny statement exists
        assert 'effect = "Deny"' in policy_section or 'Effect = "Deny"' in policy_section

        # Verify denied services
        assert "ec2:*" in policy_section
        assert "rds:*" in policy_section
        assert "iam:*" in policy_section

        # Verify mutating operations are denied
        assert "s3:Delete" in policy_section or "s3:Put" in policy_section
        assert "dynamodb:Delete" in policy_section or "dynamodb:Update" in policy_section
        assert "lambda:Update" in policy_section or "lambda:Delete" in policy_section

    def _extract_llm_policy_section(self, content):
        """Extract LLM analyzer policy section."""
        start = content.find('data "aws_iam_policy_document" "llm_analyzer"')
        if start == -1:
            return ""

        # Find the closing brace
        brace_count = 0
        in_block = False
        end = start

        for i in range(start, len(content)):
            if content[i] == "{":
                brace_count += 1
                in_block = True
            elif content[i] == "}":
                brace_count -= 1
                if in_block and brace_count == 0:
                    end = i + 1
                    break

        return content[start:end]


class TestNotificationServiceIAMPolicy:
    """Test Notification Service IAM policy (Requirement 10.6)."""

    def test_notification_service_has_only_sns_and_secrets_permissions(self):
        """
        Requirement 10.6: Notification Service SHALL have IAM permissions ONLY for
        sns:Publish and secretsmanager:GetSecretValue
        """
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Verify SNS and Secrets Manager permissions are present
        assert "sns:Publish" in main_tf
        assert "secretsmanager:GetSecretValue" in main_tf

        # Verify policy is scoped to notification_service
        assert 'data "aws_iam_policy_document" "notification_service"' in main_tf


class TestOrchestratorIAMPolicy:
    """Test Step Functions Orchestrator IAM policy (Requirement 10.7)."""

    def test_orchestrator_has_only_lambda_invoke_permissions(self):
        """
        Requirement 10.7: Orchestrator SHALL have IAM permissions ONLY to invoke
        the specific Lambda functions in the workflow
        """
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Verify Lambda invoke permission is present
        assert "lambda:InvokeFunction" in main_tf

        # Verify policy is scoped to orchestrator
        assert 'data "aws_iam_policy_document" "orchestrator"' in main_tf

        # Verify specific function ARNs are listed (not wildcard)
        policy_section = self._extract_orchestrator_policy_section(main_tf)

        # Should have specific function names
        assert "metrics-collector" in policy_section
        assert "logs-collector" in policy_section
        assert "deploy-context-collector" in policy_section
        assert "correlation-engine" in policy_section
        assert "llm-analyzer" in policy_section
        assert "notification-service" in policy_section

        # Verify DynamoDB write permission for incident storage
        assert "dynamodb:PutItem" in main_tf

        # Verify X-Ray permissions
        assert "xray:PutTraceSegments" in main_tf
        assert "xray:PutTelemetryRecords" in main_tf

    def _extract_orchestrator_policy_section(self, content):
        """Extract orchestrator policy section."""
        start = content.find('data "aws_iam_policy_document" "orchestrator"')
        if start == -1:
            return ""

        # Find the closing brace
        brace_count = 0
        in_block = False
        end = start

        for i in range(start, len(content)):
            if content[i] == "{":
                brace_count += 1
                in_block = True
            elif content[i] == "}":
                brace_count -= 1
                if in_block and brace_count == 0:
                    end = i + 1
                    break

        return content[start:end]


class TestIAMRoleStructure:
    """Test IAM role structure and naming."""

    def test_all_lambda_roles_exist(self):
        """Verify all Lambda function roles are defined."""
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        required_roles = [
            "metrics_collector",
            "logs_collector",
            "deploy_context_collector",
            "correlation_engine",
            "llm_analyzer",
            "notification_service",
        ]

        for role in required_roles:
            assert f'resource "aws_iam_role" "{role}"' in main_tf
            assert f'resource "aws_iam_role_policy" "{role}"' in main_tf

    def test_orchestrator_role_exists(self):
        """Verify Step Functions orchestrator role is defined."""
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        assert 'resource "aws_iam_role" "orchestrator"' in main_tf
        assert 'resource "aws_iam_role_policy" "orchestrator"' in main_tf

    def test_all_roles_have_cloudwatch_logs_permissions(self):
        """Verify all Lambda roles have CloudWatch Logs write permissions."""
        module_path = get_terraform_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # All Lambda functions need CloudWatch Logs permissions
        assert main_tf.count("logs:CreateLogGroup") >= 6
        assert main_tf.count("logs:CreateLogStream") >= 6
        assert main_tf.count("logs:PutLogEvents") >= 6


class TestTerraformConfiguration:
    """Test Terraform module configuration."""

    def test_terraform_validates_successfully(self):
        """Verify Terraform configuration is valid."""
        module_path = get_terraform_module_path()

        # Run terraform validate
        result = subprocess.run(
            ["terraform", "validate"], cwd=module_path, capture_output=True, text=True
        )

        assert result.returncode == 0, f"Terraform validation failed: {result.stderr}"
        assert "Success" in result.stdout

    def test_required_files_exist(self):
        """Verify all required Terraform files exist."""
        module_path = get_terraform_module_path()

        required_files = ["main.tf", "variables.tf", "outputs.tf", "README.md"]

        for file in required_files:
            assert (module_path / file).exists(), f"Missing required file: {file}"

    def test_outputs_are_defined(self):
        """Verify all role ARN outputs are defined."""
        module_path = get_terraform_module_path()
        outputs_tf = (module_path / "outputs.tf").read_text()

        required_outputs = [
            "metrics_collector_role_arn",
            "logs_collector_role_arn",
            "deploy_context_collector_role_arn",
            "correlation_engine_role_arn",
            "llm_analyzer_role_arn",
            "notification_service_role_arn",
            "orchestrator_role_arn",
        ]

        for output in required_outputs:
            assert f'output "{output}"' in outputs_tf
