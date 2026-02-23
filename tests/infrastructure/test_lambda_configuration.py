"""
Unit tests for Lambda function configuration validation.

These tests validate that Lambda functions are configured with:
- ARM64 architecture (Graviton2)
- Appropriate memory settings
- Appropriate timeout settings
- CloudWatch Logs retention (7 days)
- Required environment variables

Validates Requirements: 17.2, 17.3, 17.5
"""

from pathlib import Path


def get_terraform_lambda_module_path():
    """Get the path to the Lambda Terraform module."""
    return Path(__file__).parent.parent.parent / "terraform" / "modules" / "lambda"


class TestLambdaArchitecture:
    """Test Lambda functions use ARM64 architecture (Requirement 17.2)."""

    def test_all_functions_use_arm64_architecture(self):
        """
        Requirement 17.2: Lambda functions SHALL use ARM64 architecture (Graviton2)
        for cost efficiency
        """
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Count Lambda function resources
        function_count = main_tf.count('resource "aws_lambda_function"')
        assert function_count == 6, f"Expected 6 Lambda functions, found {function_count}"

        # Verify all functions use ARM64
        arm64_count = main_tf.count('architectures = ["arm64"]')
        assert arm64_count == 6, f"Expected 6 ARM64 configurations, found {arm64_count}"

        # Verify no x86_64 architecture
        assert "x86_64" not in main_tf


class TestLambdaMemoryConfiguration:
    """Test Lambda functions have appropriate memory settings (Requirement 17.3)."""

    def test_metrics_collector_memory(self):
        """Metrics Collector should have 512MB memory."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        metrics_section = self._extract_function_section(main_tf, "metrics_collector")
        assert "memory_size   = 512" in metrics_section

    def test_logs_collector_memory(self):
        """Logs Collector should have 512MB memory."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        logs_section = self._extract_function_section(main_tf, "logs_collector")
        assert "memory_size   = 512" in logs_section

    def test_deploy_context_collector_memory(self):
        """Deploy Context Collector should have 512MB memory."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        deploy_section = self._extract_function_section(main_tf, "deploy_context_collector")
        assert "memory_size   = 512" in deploy_section

    def test_correlation_engine_memory(self):
        """Correlation Engine should have 256MB memory."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        correlation_section = self._extract_function_section(main_tf, "correlation_engine")
        assert "memory_size   = 256" in correlation_section

    def test_llm_analyzer_memory(self):
        """LLM Analyzer should have 1024MB memory."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        llm_section = self._extract_function_section(main_tf, "llm_analyzer")
        assert "memory_size   = 1024" in llm_section

    def test_notification_service_memory(self):
        """Notification Service should have 256MB memory."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        notification_section = self._extract_function_section(main_tf, "notification_service")
        assert "memory_size   = 256" in notification_section

    def _extract_function_section(self, content, function_name):
        """Extract a specific Lambda function section from Terraform HCL."""
        start = content.find(f'resource "aws_lambda_function" "{function_name}"')
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


class TestLambdaTimeoutConfiguration:
    """Test Lambda functions have appropriate timeout settings (Requirement 17.3)."""

    def test_metrics_collector_timeout(self):
        """Metrics Collector should have 20s timeout."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        metrics_section = self._extract_function_section(main_tf, "metrics_collector")
        assert "timeout       = 20" in metrics_section

    def test_logs_collector_timeout(self):
        """Logs Collector should have 20s timeout."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        logs_section = self._extract_function_section(main_tf, "logs_collector")
        assert "timeout       = 20" in logs_section

    def test_deploy_context_collector_timeout(self):
        """Deploy Context Collector should have 20s timeout."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        deploy_section = self._extract_function_section(main_tf, "deploy_context_collector")
        assert "timeout       = 20" in deploy_section

    def test_correlation_engine_timeout(self):
        """Correlation Engine should have 10s timeout."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        correlation_section = self._extract_function_section(main_tf, "correlation_engine")
        assert "timeout       = 10" in correlation_section

    def test_llm_analyzer_timeout(self):
        """LLM Analyzer should have 40s timeout."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        llm_section = self._extract_function_section(main_tf, "llm_analyzer")
        assert "timeout       = 40" in llm_section

    def test_notification_service_timeout(self):
        """Notification Service should have 15s timeout."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        notification_section = self._extract_function_section(main_tf, "notification_service")
        assert "timeout       = 15" in notification_section

    def _extract_function_section(self, content, function_name):
        """Extract a specific Lambda function section from Terraform HCL."""
        start = content.find(f'resource "aws_lambda_function" "{function_name}"')
        if start == -1:
            return ""

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


class TestCloudWatchLogsRetention:
    """Test CloudWatch Logs retention is 7 days (Requirement 17.5)."""

    def test_all_log_groups_have_7_day_retention(self):
        """
        Requirement 17.5: CloudWatch Logs retention SHALL be 7 days for Lambda logs
        """
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Count CloudWatch Log Group resources
        log_group_count = main_tf.count('resource "aws_cloudwatch_log_group"')
        assert log_group_count == 6, f"Expected 6 log groups, found {log_group_count}"

        # Verify all log groups have 7-day retention
        retention_count = main_tf.count("retention_in_days = 7")
        assert retention_count == 6, f"Expected 6 retention configurations, found {retention_count}"


class TestLambdaEnvironmentVariables:
    """Test Lambda functions have required environment variables."""

    def test_all_functions_have_common_environment_variables(self):
        """All functions should have AWS_REGION, DYNAMODB_TABLE, LOG_LEVEL."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Each function should have environment block
        env_block_count = main_tf.count("environment {")
        assert env_block_count == 6, f"Expected 6 environment blocks, found {env_block_count}"

        # Common variables should appear in all functions
        assert main_tf.count("AWS_REGION") >= 6
        assert main_tf.count("DYNAMODB_TABLE") >= 6
        assert main_tf.count("LOG_LEVEL") >= 6

    def test_llm_analyzer_has_bedrock_configuration(self):
        """LLM Analyzer should have Bedrock-specific environment variables."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        llm_section = self._extract_function_section(main_tf, "llm_analyzer")
        assert "BEDROCK_MODEL_ID" in llm_section
        assert "PROMPT_TEMPLATE_PARAM" in llm_section
        assert "anthropic.claude-v2" in llm_section

    def test_notification_service_has_notification_configuration(self):
        """Notification Service should have notification-specific environment variables."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        notification_section = self._extract_function_section(main_tf, "notification_service")
        assert "SLACK_SECRET_NAME" in notification_section
        assert "EMAIL_TOPIC_ARN" in notification_section
        assert "INCIDENT_STORE_URL" in notification_section

    def test_correlation_engine_has_size_constraint(self):
        """Correlation Engine should have MAX_CONTEXT_SIZE environment variable."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        correlation_section = self._extract_function_section(main_tf, "correlation_engine")
        assert "MAX_CONTEXT_SIZE" in correlation_section
        assert "51200" in correlation_section  # 50KB in bytes

    def _extract_function_section(self, content, function_name):
        """Extract a specific Lambda function section from Terraform HCL."""
        start = content.find(f'resource "aws_lambda_function" "{function_name}"')
        if start == -1:
            return ""

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


class TestLambdaRuntimeConfiguration:
    """Test Lambda functions use Python 3.11 runtime."""

    def test_all_functions_use_python311(self):
        """All Lambda functions should use Python 3.11 runtime."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Count Python 3.11 runtime configurations
        python311_count = main_tf.count('runtime       = "python3.11"')
        assert python311_count == 6, f"Expected 6 Python 3.11 runtimes, found {python311_count}"

        # Verify no other Python versions
        assert "python3.9" not in main_tf
        assert "python3.10" not in main_tf
        assert "python3.12" not in main_tf


class TestLambdaIAMRoleAttachment:
    """Test Lambda functions have IAM roles attached."""

    def test_all_functions_have_iam_roles(self):
        """All Lambda functions should have IAM roles attached."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        # Each function should reference an IAM role
        assert main_tf.count("role          = var.iam_role_arns.") == 6

        # Verify specific role references
        assert "var.iam_role_arns.metrics_collector" in main_tf
        assert "var.iam_role_arns.logs_collector" in main_tf
        assert "var.iam_role_arns.deploy_context_collector" in main_tf
        assert "var.iam_role_arns.correlation_engine" in main_tf
        assert "var.iam_role_arns.llm_analyzer" in main_tf
        assert "var.iam_role_arns.notification_service" in main_tf


class TestTerraformModuleStructure:
    """Test Terraform module structure and files."""

    def test_required_files_exist(self):
        """Verify all required Terraform files exist."""
        module_path = get_terraform_lambda_module_path()

        required_files = ["main.tf", "variables.tf", "outputs.tf", "README.md"]

        for file in required_files:
            assert (module_path / file).exists(), f"Missing required file: {file}"

    def test_outputs_are_defined(self):
        """Verify all Lambda function ARN outputs are defined."""
        module_path = get_terraform_lambda_module_path()
        outputs_tf = (module_path / "outputs.tf").read_text()

        required_outputs = [
            "metrics_collector_arn",
            "logs_collector_arn",
            "deploy_context_collector_arn",
            "correlation_engine_arn",
            "llm_analyzer_arn",
            "notification_service_arn",
            "lambda_function_arns",
            "lambda_function_names",
            "log_group_arns",
        ]

        for output in required_outputs:
            assert f'output "{output}"' in outputs_tf

    def test_variables_are_defined(self):
        """Verify all required variables are defined."""
        module_path = get_terraform_lambda_module_path()
        variables_tf = (module_path / "variables.tf").read_text()

        required_variables = [
            "project_name",
            "aws_region",
            "iam_role_arns",
            "lambda_packages",
            "dynamodb_table_name",
            "sns_topic_arn",
            "log_level",
            "tags",
        ]

        for variable in required_variables:
            assert f'variable "{variable}"' in variables_tf


class TestLambdaFunctionNaming:
    """Test Lambda function naming conventions."""

    def test_function_names_follow_convention(self):
        """Function names should follow project_name-function_name pattern."""
        module_path = get_terraform_lambda_module_path()
        main_tf = (module_path / "main.tf").read_text()

        expected_functions = [
            "metrics-collector",
            "logs-collector",
            "deploy-context-collector",
            "correlation-engine",
            "llm-analyzer",
            "notification-service",
        ]

        for function in expected_functions:
            assert f'"{function}"' in main_tf or f"-{function}" in main_tf
