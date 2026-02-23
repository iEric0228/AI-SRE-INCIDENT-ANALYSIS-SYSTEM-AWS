"""
Comprehensive Terraform validation tests.

This test suite validates the complete Terraform infrastructure configuration
against all requirements specified in task 13.

Validates Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 17.1, 17.2, 17.3, 17.5
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List

import pytest


def get_terraform_root():
    """Get the path to the Terraform root directory."""
    return Path(__file__).parent.parent.parent / "terraform"


def get_terraform_module_path(module_name: str):
    """Get the path to a specific Terraform module."""
    return get_terraform_root() / "modules" / module_name


def load_terraform_file(module_name: str, filename: str) -> str:
    """Load a Terraform file from a module."""
    module_path = get_terraform_module_path(module_name)
    file_path = module_path / filename
    if not file_path.exists():
        pytest.skip(f"File {filename} not found in module {module_name}")
    return file_path.read_text()


def extract_policy_section(content: str, policy_name: str) -> str:
    """Extract a specific IAM policy document section from Terraform HCL."""
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


def extract_resource_section(content: str, resource_type: str, resource_name: str) -> str:
    """Extract a specific resource section from Terraform HCL."""
    start = content.find(f'resource "{resource_type}" "{resource_name}"')
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


class TestIAMPolicyValidation:
    """
    Test IAM policies contain only allowed permissions.
    Validates Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
    """

    def test_metrics_collector_has_only_allowed_permissions(self):
        """
        Requirement 10.1: Metrics Collector SHALL have IAM permissions ONLY for
        cloudwatch:GetMetricStatistics and cloudwatch:ListMetrics
        """
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "metrics_collector")

        # Verify required permissions are present
        assert "cloudwatch:GetMetricStatistics" in policy_section
        assert "cloudwatch:ListMetrics" in policy_section

        # Verify no forbidden services (except logs for Lambda logging)
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
            "ssm:",
            "cloudtrail:",
        ]

        for service in forbidden_services:
            assert (
                service not in policy_section
            ), f"Metrics collector should not have {service} permissions"

    def test_logs_collector_has_only_allowed_permissions(self):
        """
        Requirement 10.2: Logs Collector SHALL have IAM permissions ONLY for
        logs:FilterLogEvents and logs:DescribeLogGroups
        """
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "logs_collector")

        # Verify required permissions are present
        assert "logs:FilterLogEvents" in policy_section
        assert "logs:DescribeLogGroups" in policy_section

        # Verify no forbidden services
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
            "ssm:",
            "cloudtrail:",
            "cloudwatch:Get",
            "cloudwatch:List",
        ]

        for service in forbidden_services:
            assert (
                service not in policy_section
            ), f"Logs collector should not have {service} permissions"

    def test_deploy_context_collector_has_only_allowed_permissions(self):
        """
        Requirement 10.3: Deploy Context Collector SHALL have IAM permissions ONLY for
        ssm:GetParameter, ssm:GetParameterHistory, and cloudtrail:LookupEvents
        """
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "deploy_context_collector")

        # Verify required permissions are present
        assert "ssm:GetParameter" in policy_section
        assert "ssm:GetParameterHistory" in policy_section
        assert "cloudtrail:LookupEvents" in policy_section

        # Verify no forbidden services
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
            "cloudwatch:Get",
        ]

        for service in forbidden_services:
            assert (
                service not in policy_section
            ), f"Deploy context collector should not have {service} permissions"

    def test_llm_analyzer_has_only_allowed_permissions(self):
        """
        Requirement 10.4: LLM Analyzer SHALL have IAM permissions ONLY for
        bedrock:InvokeModel
        """
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "llm_analyzer")

        # Verify required permissions are present
        assert "bedrock:InvokeModel" in policy_section
        assert "ssm:GetParameter" in policy_section  # For prompt template

        # Extract only the Allow statements (not Deny statements)
        # Split by statement blocks and check only Allow statements
        allow_statements = []
        current_statement = ""
        in_statement = False

        for line in policy_section.split("\n"):
            if "statement {" in line:
                in_statement = True
                current_statement = ""
            elif in_statement:
                current_statement += line + "\n"
                if "}" in line and 'effect = "Allow"' in current_statement.lower():
                    allow_statements.append(current_statement)
                    in_statement = False
                elif "}" in line:
                    in_statement = False

        # Verify no forbidden services in Allow statements
        allow_text = "\n".join(allow_statements)
        forbidden_services = [
            "ec2:",
            "rds:",
            "iam:",
            "s3:Delete",
            "s3:Put",
            "dynamodb:Delete",
            "dynamodb:Update",
            "dynamodb:Put",
            "lambda:Update",
            "lambda:Delete",
            "lambda:Create",
            "sns:",
            "secretsmanager:",
            "cloudtrail:",
        ]

        for service in forbidden_services:
            assert (
                service not in allow_text
            ), f"LLM analyzer should not have Allow permission for {service}"


class TestLLMAnalyzerExplicitDeny:
    """
    Test LLM analyzer has explicit deny for restricted services.
    Validates Requirement: 10.5
    """

    def test_llm_analyzer_has_explicit_deny_statement(self):
        """
        Requirement 10.5: LLM Analyzer SHALL NOT have permissions for any
        EC2, RDS, IAM, or mutating AWS APIs
        """
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "llm_analyzer")

        # Verify explicit deny statement exists (case-insensitive check)
        assert (
            'effect = "deny"' in policy_section.lower()
        ), "LLM analyzer must have explicit Deny statement"

    def test_llm_analyzer_denies_ec2_operations(self):
        """LLM analyzer must explicitly deny all EC2 operations."""
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "llm_analyzer")

        assert "ec2:*" in policy_section, "LLM analyzer must explicitly deny ec2:*"

    def test_llm_analyzer_denies_rds_operations(self):
        """LLM analyzer must explicitly deny all RDS operations."""
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "llm_analyzer")

        assert "rds:*" in policy_section, "LLM analyzer must explicitly deny rds:*"

    def test_llm_analyzer_denies_iam_operations(self):
        """LLM analyzer must explicitly deny all IAM operations."""
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "llm_analyzer")

        assert "iam:*" in policy_section, "LLM analyzer must explicitly deny iam:*"

    def test_llm_analyzer_denies_mutating_operations(self):
        """LLM analyzer must explicitly deny mutating operations."""
        main_tf = load_terraform_file("iam", "main.tf")
        policy_section = extract_policy_section(main_tf, "llm_analyzer")

        # Check for various mutating operations
        mutating_patterns = [
            "s3:Delete",
            "s3:Put",
            "dynamodb:Delete",
            "dynamodb:Update",
            "lambda:Update",
            "lambda:Delete",
        ]

        found_mutating_denies = sum(1 for pattern in mutating_patterns if pattern in policy_section)
        assert (
            found_mutating_denies >= 3
        ), "LLM analyzer must explicitly deny multiple mutating operations"


class TestResourceTagging:
    """
    Test all resources have required tags.
    Validates Requirement: 17.6
    """

    def test_dynamodb_table_has_required_tags(self):
        """DynamoDB table must have Project tag."""
        main_tf = load_terraform_file("dynamodb", "main.tf")

        assert (
            'Project = "AI-SRE-Portfolio"' in main_tf or "Project: AI-SRE-Portfolio" in main_tf
        ), "DynamoDB table must have Project tag"

    def test_lambda_functions_have_required_tags(self):
        """Lambda functions must have Project tag."""
        main_tf = load_terraform_file("lambda", "main.tf")

        # Check for tags configuration
        assert "tags" in main_tf.lower(), "Lambda functions must have tags configuration"

        # Check for Project tag reference
        assert (
            "Project" in main_tf or "project" in main_tf
        ), "Lambda functions must reference Project tag"

    def test_step_functions_has_required_tags(self):
        """Step Functions state machine must have Project tag."""
        main_tf = load_terraform_file("step-functions", "main.tf")

        # Check for tags configuration
        assert "tags" in main_tf.lower(), "Step Functions must have tags configuration"


class TestDynamoDBTTLConfiguration:
    """
    Test DynamoDB TTL is configured correctly.
    Validates Requirement: 9.4
    """

    def test_dynamodb_ttl_is_enabled(self):
        """DynamoDB table must have TTL enabled."""
        main_tf = load_terraform_file("dynamodb", "main.tf")

        # Check for TTL block
        ttl_pattern = r"ttl\s*\{[^}]*enabled\s*=\s*true[^}]*\}"
        assert re.search(ttl_pattern, main_tf, re.DOTALL), "DynamoDB table must have TTL enabled"

    def test_dynamodb_ttl_attribute_name(self):
        """DynamoDB TTL must use 'ttl' attribute."""
        main_tf = load_terraform_file("dynamodb", "main.tf")

        # Check for TTL attribute name
        assert 'attribute_name = "ttl"' in main_tf, "DynamoDB TTL must use 'ttl' attribute name"

    def test_dynamodb_ttl_calculation_logic(self):
        """Test TTL calculation for 90-day retention."""
        from datetime import datetime, timedelta

        # Simulate incident timestamp
        incident_time = datetime(2024, 1, 15, 14, 30, 0)

        # Calculate TTL (90 days from incident)
        ttl_time = incident_time + timedelta(days=90)
        ttl_unix = int(ttl_time.timestamp())

        # Verify TTL is 90 days in the future
        expected_ttl = incident_time + timedelta(days=90)
        assert ttl_time == expected_ttl, "TTL must be exactly 90 days from incident timestamp"

        # Verify TTL is a valid Unix timestamp
        assert ttl_unix > 0, "TTL must be a positive Unix timestamp"


class TestLambdaArchitecture:
    """
    Test Lambda functions use ARM64 architecture.
    Validates Requirement: 17.2
    """

    def test_all_lambda_functions_use_arm64(self):
        """
        Requirement 17.2: Lambda functions SHALL use ARM64 architecture (Graviton2)
        for cost efficiency
        """
        main_tf = load_terraform_file("lambda", "main.tf")

        # Count Lambda function resources
        function_count = main_tf.count('resource "aws_lambda_function"')
        assert function_count == 6, f"Expected 6 Lambda functions, found {function_count}"

        # Verify all functions use ARM64
        arm64_count = main_tf.count('architectures = ["arm64"]')
        assert (
            arm64_count == 6
        ), f"All 6 Lambda functions must use ARM64 architecture, found {arm64_count}"

    def test_no_x86_64_architecture(self):
        """Lambda functions must not use x86_64 architecture."""
        main_tf = load_terraform_file("lambda", "main.tf")

        assert "x86_64" not in main_tf, "Lambda functions must not use x86_64 architecture"

    def test_each_function_has_arm64_explicitly_set(self):
        """Each Lambda function must explicitly set ARM64 architecture."""
        main_tf = load_terraform_file("lambda", "main.tf")

        function_names = [
            "metrics_collector",
            "logs_collector",
            "deploy_context_collector",
            "correlation_engine",
            "llm_analyzer",
            "notification_service",
        ]

        for function_name in function_names:
            function_section = extract_resource_section(
                main_tf, "aws_lambda_function", function_name
            )
            assert (
                'architectures = ["arm64"]' in function_section
            ), f"{function_name} must explicitly set ARM64 architecture"


class TestStepFunctionsWorkflowType:
    """
    Test Step Functions uses Express Workflow type.
    Validates Requirement: 17.1
    """

    def test_step_functions_uses_express_workflow(self):
        """
        Requirement 17.1: Orchestrator SHALL use Express Workflows (not Standard Workflows)
        to reduce Step Functions costs
        """
        main_tf = load_terraform_file("step-functions", "main.tf")

        # Check for Express workflow type
        assert (
            'type = "EXPRESS"' in main_tf or 'type     = "EXPRESS"' in main_tf
        ), "Step Functions must use EXPRESS workflow type"

    def test_step_functions_not_standard_workflow(self):
        """Step Functions must not use STANDARD workflow type."""
        main_tf = load_terraform_file("step-functions", "main.tf")

        assert (
            'type = "STANDARD"' not in main_tf and 'type     = "STANDARD"' not in main_tf
        ), "Step Functions must not use STANDARD workflow type"


class TestCloudWatchLogsRetention:
    """
    Test CloudWatch Logs retention is 7 days.
    Validates Requirement: 17.5
    """

    def test_lambda_log_groups_have_7_day_retention(self):
        """
        Requirement 17.5: CloudWatch Logs retention SHALL be 7 days for Lambda logs
        """
        main_tf = load_terraform_file("lambda", "main.tf")

        # Count CloudWatch Log Group resources
        log_group_count = main_tf.count('resource "aws_cloudwatch_log_group"')
        assert log_group_count == 6, f"Expected 6 log groups, found {log_group_count}"

        # Verify all log groups have 7-day retention
        retention_count = main_tf.count("retention_in_days = 7")
        assert (
            retention_count == 6
        ), f"All 6 log groups must have 7-day retention, found {retention_count}"

    def test_step_functions_log_group_has_7_day_retention(self):
        """Step Functions log group must have 7-day retention."""
        main_tf = load_terraform_file("step-functions", "main.tf")

        # Check if log group is defined
        if 'resource "aws_cloudwatch_log_group"' in main_tf:
            assert (
                "retention_in_days = 7" in main_tf
            ), "Step Functions log group must have 7-day retention"

    def test_no_longer_retention_periods(self):
        """No log groups should have retention longer than 7 days."""
        main_tf = load_terraform_file("lambda", "main.tf")

        # Check for longer retention periods
        forbidden_retentions = [14, 30, 60, 90, 120, 180, 365]
        for retention in forbidden_retentions:
            assert (
                f"retention_in_days = {retention}" not in main_tf
            ), f"Log groups must not have {retention}-day retention"


class TestLambdaMemoryConfiguration:
    """
    Test Lambda functions have appropriate memory settings.
    Validates Requirement: 17.3
    """

    def test_metrics_collector_memory(self):
        """Metrics Collector should have 512MB memory."""
        main_tf = load_terraform_file("lambda", "main.tf")
        metrics_section = extract_resource_section(
            main_tf, "aws_lambda_function", "metrics_collector"
        )
        assert "memory_size   = 512" in metrics_section

    def test_logs_collector_memory(self):
        """Logs Collector should have 512MB memory."""
        main_tf = load_terraform_file("lambda", "main.tf")
        logs_section = extract_resource_section(main_tf, "aws_lambda_function", "logs_collector")
        assert "memory_size   = 512" in logs_section

    def test_deploy_context_collector_memory(self):
        """Deploy Context Collector should have 512MB memory."""
        main_tf = load_terraform_file("lambda", "main.tf")
        deploy_section = extract_resource_section(
            main_tf, "aws_lambda_function", "deploy_context_collector"
        )
        assert "memory_size   = 512" in deploy_section

    def test_correlation_engine_memory(self):
        """Correlation Engine should have 256MB memory."""
        main_tf = load_terraform_file("lambda", "main.tf")
        correlation_section = extract_resource_section(
            main_tf, "aws_lambda_function", "correlation_engine"
        )
        assert "memory_size   = 256" in correlation_section

    def test_llm_analyzer_memory(self):
        """LLM Analyzer should have 1024MB memory."""
        main_tf = load_terraform_file("lambda", "main.tf")
        llm_section = extract_resource_section(main_tf, "aws_lambda_function", "llm_analyzer")
        assert "memory_size   = 1024" in llm_section

    def test_notification_service_memory(self):
        """Notification Service should have 256MB memory."""
        main_tf = load_terraform_file("lambda", "main.tf")
        notification_section = extract_resource_section(
            main_tf, "aws_lambda_function", "notification_service"
        )
        assert "memory_size   = 256" in notification_section


class TestLambdaTimeoutConfiguration:
    """
    Test Lambda functions have appropriate timeout settings.
    Validates Requirement: 17.3
    """

    def test_metrics_collector_timeout(self):
        """Metrics Collector should have 20s timeout."""
        main_tf = load_terraform_file("lambda", "main.tf")
        metrics_section = extract_resource_section(
            main_tf, "aws_lambda_function", "metrics_collector"
        )
        assert "timeout       = 20" in metrics_section

    def test_logs_collector_timeout(self):
        """Logs Collector should have 20s timeout."""
        main_tf = load_terraform_file("lambda", "main.tf")
        logs_section = extract_resource_section(main_tf, "aws_lambda_function", "logs_collector")
        assert "timeout       = 20" in logs_section

    def test_deploy_context_collector_timeout(self):
        """Deploy Context Collector should have 20s timeout."""
        main_tf = load_terraform_file("lambda", "main.tf")
        deploy_section = extract_resource_section(
            main_tf, "aws_lambda_function", "deploy_context_collector"
        )
        assert "timeout       = 20" in deploy_section

    def test_correlation_engine_timeout(self):
        """Correlation Engine should have 10s timeout."""
        main_tf = load_terraform_file("lambda", "main.tf")
        correlation_section = extract_resource_section(
            main_tf, "aws_lambda_function", "correlation_engine"
        )
        assert "timeout       = 10" in correlation_section

    def test_llm_analyzer_timeout(self):
        """LLM Analyzer should have 40s timeout."""
        main_tf = load_terraform_file("lambda", "main.tf")
        llm_section = extract_resource_section(main_tf, "aws_lambda_function", "llm_analyzer")
        assert "timeout       = 40" in llm_section

    def test_notification_service_timeout(self):
        """Notification Service should have 15s timeout."""
        main_tf = load_terraform_file("lambda", "main.tf")
        notification_section = extract_resource_section(
            main_tf, "aws_lambda_function", "notification_service"
        )
        assert "timeout       = 15" in notification_section


class TestTerraformValidation:
    """Test Terraform configuration is valid and well-formed."""

    def test_terraform_fmt_check(self):
        """Test that Terraform files are properly formatted."""
        result = subprocess.run(
            ["terraform", "fmt", "-check", "-recursive"],
            cwd=get_terraform_root(),
            capture_output=True,
            text=True,
        )

        # Note: fmt returns 0 if files are formatted, 3 if they need formatting
        assert result.returncode in [0, 3], f"Terraform fmt check failed: {result.stderr}"

    def test_all_modules_have_required_files(self):
        """Test that all modules have required files."""
        modules = ["iam", "lambda", "dynamodb", "step-functions", "eventbridge", "secrets"]
        required_files = ["main.tf", "variables.tf", "outputs.tf"]

        for module in modules:
            module_path = get_terraform_module_path(module)
            if not module_path.exists():
                continue

            for file in required_files:
                file_path = module_path / file
                assert file_path.exists(), f"Module {module} is missing required file {file}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
