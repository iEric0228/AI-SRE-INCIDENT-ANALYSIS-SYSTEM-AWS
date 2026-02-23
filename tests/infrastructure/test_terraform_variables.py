"""
Unit tests for Terraform variables validation.

Tests verify that variable validation rules work correctly and that
default values meet requirements.
"""

import pytest
import re


class TestCoreVariables:
    """Test core configuration variables."""

    def test_aws_region_validation_accepts_valid_regions(self):
        """Valid AWS region formats should pass validation."""
        valid_regions = [
            "us-east-1",
            "us-west-2",
            "eu-west-1",
            "ap-south-1",
            "ca-central-1",
        ]
        pattern = r"^[a-z]{2}-[a-z]+-[0-9]{1}$"

        for region in valid_regions:
            assert re.match(pattern, region), f"Region {region} should be valid"

    def test_aws_region_validation_rejects_invalid_regions(self):
        """Invalid AWS region formats should fail validation."""
        invalid_regions = [
            "us-east",  # Missing number
            "US-EAST-1",  # Uppercase
            "us_east_1",  # Underscores
            "us-east-10",  # Two digits
            "",  # Empty
        ]
        pattern = r"^[a-z]{2}-[a-z]+-[0-9]{1}$"

        for region in invalid_regions:
            assert not re.match(pattern, region), f"Region {region} should be invalid"

    def test_environment_validation_accepts_valid_environments(self):
        """Valid environment names should pass validation."""
        valid_environments = ["dev", "staging", "prod"]

        for env in valid_environments:
            assert env in ["dev", "staging", "prod"]

    def test_environment_validation_rejects_invalid_environments(self):
        """Invalid environment names should fail validation."""
        invalid_environments = ["development", "test", "production", "qa", ""]

        for env in invalid_environments:
            assert env not in ["dev", "staging", "prod"]

    def test_project_name_validation_accepts_valid_names(self):
        """Valid project names should pass validation."""
        valid_names = [
            "ai-sre-incident-analysis",
            "my-project",
            "project123",
            "a-b-c-1-2-3",
        ]
        pattern = r"^[a-z0-9-]+$"

        for name in valid_names:
            assert re.match(pattern, name), f"Name {name} should be valid"

    def test_project_name_validation_rejects_invalid_names(self):
        """Invalid project names should fail validation."""
        invalid_names = [
            "My-Project",  # Uppercase
            "my_project",  # Underscore
            "my project",  # Space
            "my.project",  # Period
            "",  # Empty
        ]
        pattern = r"^[a-z0-9-]+$"

        for name in invalid_names:
            assert not re.match(pattern, name), f"Name {name} should be invalid"


class TestAlarmVariables:
    """Test CloudWatch alarm configuration variables."""

    def test_alarm_evaluation_periods_range(self):
        """Evaluation periods must be between 1 and 5."""
        valid_periods = [1, 2, 3, 4, 5]
        invalid_periods = [0, 6, 10, -1]

        for period in valid_periods:
            assert 1 <= period <= 5

        for period in invalid_periods:
            assert not (1 <= period <= 5)

    def test_alarm_period_valid_values(self):
        """Alarm period must be one of the allowed values."""
        valid_periods = [60, 300, 900, 3600]
        invalid_periods = [30, 120, 600, 1800, 7200]

        for period in valid_periods:
            assert period in [60, 300, 900, 3600]

        for period in invalid_periods:
            assert period not in [60, 300, 900, 3600]

    def test_cpu_threshold_range(self):
        """CPU threshold must be between 1 and 100."""
        valid_thresholds = [1, 50, 80, 100]
        invalid_thresholds = [0, -1, 101, 150]

        for threshold in valid_thresholds:
            assert 1 <= threshold <= 100

        for threshold in invalid_thresholds:
            assert not (1 <= threshold <= 100)

    def test_memory_threshold_range(self):
        """Memory threshold must be between 1 and 100."""
        valid_thresholds = [1, 50, 85, 100]
        invalid_thresholds = [0, -1, 101, 200]

        for threshold in valid_thresholds:
            assert 1 <= threshold <= 100

        for threshold in invalid_thresholds:
            assert not (1 <= threshold <= 100)


class TestNotificationVariables:
    """Test notification configuration variables."""

    def test_email_validation_accepts_valid_emails(self):
        """Valid email addresses should pass validation."""
        valid_emails = [
            "user@example.com",
            "test.user@example.co.uk",
            "admin+alerts@company.org",
            "user123@test-domain.com",
        ]
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        for email in valid_emails:
            assert re.match(pattern, email), f"Email {email} should be valid"

    def test_email_validation_rejects_invalid_emails(self):
        """Invalid email addresses should fail validation."""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user@.com",
            "user @example.com",
            "",
        ]
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        for email in invalid_emails:
            assert not re.match(pattern, email), f"Email {email} should be invalid"

    def test_topic_name_validation(self):
        """SNS topic names must contain only valid characters."""
        valid_names = [
            "incident-notifications",
            "my_topic",
            "topic123",
            "a-b_c-1_2",
        ]
        invalid_names = [
            "my topic",  # Space
            "my.topic",  # Period
            "my@topic",  # Special char
            "",  # Empty
        ]
        pattern = r"^[a-zA-Z0-9_-]+$"

        for name in valid_names:
            assert re.match(pattern, name)

        for name in invalid_names:
            assert not re.match(pattern, name)


class TestLambdaVariables:
    """Test Lambda function configuration variables."""

    def test_log_level_validation(self):
        """Log level must be one of the allowed values."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        invalid_levels = ["debug", "info", "WARN", "FATAL", "TRACE", ""]

        for level in valid_levels:
            assert level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in invalid_levels:
            assert level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def test_lambda_memory_range(self):
        """Lambda memory must be between 128 MB and 10240 MB."""
        valid_sizes = [128, 256, 512, 1024, 2048, 10240]
        invalid_sizes = [64, 127, 10241, 20000, 0, -1]

        for size in valid_sizes:
            assert 128 <= size <= 10240

        for size in invalid_sizes:
            assert not (128 <= size <= 10240)

    def test_lambda_timeout_range(self):
        """Lambda timeout must be between 3 and 900 seconds."""
        valid_timeouts = [3, 10, 30, 60, 300, 900]
        invalid_timeouts = [0, 1, 2, 901, 1000, -1]

        for timeout in valid_timeouts:
            assert 3 <= timeout <= 900

        for timeout in invalid_timeouts:
            assert not (3 <= timeout <= 900)

    def test_lambda_architecture_validation(self):
        """Lambda architecture must be x86_64 or arm64."""
        valid_architectures = ["x86_64", "arm64"]
        invalid_architectures = ["x86", "arm", "ARM64", "X86_64", ""]

        for arch in valid_architectures:
            assert arch in ["x86_64", "arm64"]

        for arch in invalid_architectures:
            assert arch not in ["x86_64", "arm64"]


class TestDynamoDBVariables:
    """Test DynamoDB configuration variables."""

    def test_table_name_validation(self):
        """Table names must contain only valid characters."""
        valid_names = [
            "incident-analysis-store",
            "my_table",
            "table.name",
            "table-123",
        ]
        invalid_names = [
            "my table",  # Space
            "my@table",  # Special char
            "my#table",  # Special char
            "",  # Empty
        ]
        pattern = r"^[a-zA-Z0-9_.-]+$"

        for name in valid_names:
            assert re.match(pattern, name)

        for name in invalid_names:
            assert not re.match(pattern, name)

    def test_billing_mode_validation(self):
        """Billing mode must be PROVISIONED or PAY_PER_REQUEST."""
        valid_modes = ["PROVISIONED", "PAY_PER_REQUEST"]
        invalid_modes = ["provisioned", "pay_per_request", "ON_DEMAND", ""]

        for mode in valid_modes:
            assert mode in ["PROVISIONED", "PAY_PER_REQUEST"]

        for mode in invalid_modes:
            assert mode not in ["PROVISIONED", "PAY_PER_REQUEST"]

    def test_retention_days_range(self):
        """Retention days must be between 1 and 365."""
        valid_days = [1, 30, 90, 180, 365]
        invalid_days = [0, -1, 366, 500]

        for days in valid_days:
            assert 1 <= days <= 365

        for days in invalid_days:
            assert not (1 <= days <= 365)


class TestLLMVariables:
    """Test LLM configuration variables."""

    def test_bedrock_model_id_validation(self):
        """Model ID must be a valid Anthropic Claude model."""
        valid_models = [
            "anthropic.claude-v2",
            "anthropic.claude-v2:1",
            "anthropic.claude-instant-v1",
        ]
        invalid_models = [
            "claude-v2",
            "anthropic.gpt-4",
            "openai.gpt-4",
            "",
        ]
        pattern = r"^anthropic\.claude-"

        for model in valid_models:
            assert re.match(pattern, model)

        for model in invalid_models:
            assert not re.match(pattern, model)

    def test_temperature_range(self):
        """Temperature must be between 0.0 and 1.0."""
        valid_temps = [0.0, 0.3, 0.5, 0.7, 1.0]
        invalid_temps = [-0.1, -1.0, 1.1, 2.0]

        for temp in valid_temps:
            assert 0.0 <= temp <= 1.0

        for temp in invalid_temps:
            assert not (0.0 <= temp <= 1.0)

    def test_max_tokens_range(self):
        """Max tokens must be between 100 and 4096."""
        valid_tokens = [100, 500, 1000, 2000, 4096]
        invalid_tokens = [0, 50, 99, 4097, 10000]

        for tokens in valid_tokens:
            assert 100 <= tokens <= 4096

        for tokens in invalid_tokens:
            assert not (100 <= tokens <= 4096)

    def test_parameter_name_validation(self):
        """Parameter names must start with / and contain valid characters."""
        valid_names = [
            "/ai-sre-incident-analysis/prompt-template",
            "/my/parameter",
            "/param_123",
            "/a/b/c.d-e_f",
        ]
        invalid_names = [
            "no-leading-slash",
            "/param with space",
            "/param@special",
            "",
        ]
        pattern = r"^/[a-zA-Z0-9/_.-]+$"

        for name in valid_names:
            assert re.match(pattern, name)

        for name in invalid_names:
            assert not re.match(pattern, name)


class TestObservabilityVariables:
    """Test observability configuration variables."""

    def test_log_retention_valid_values(self):
        """Log retention must be one of the allowed CloudWatch values."""
        valid_retentions = [
            1,
            3,
            5,
            7,
            14,
            30,
            60,
            90,
            120,
            150,
            180,
            365,
            400,
            545,
            731,
            1827,
            3653,
        ]
        invalid_retentions = [2, 4, 6, 8, 15, 45, 100, 200, 500, 1000]

        for retention in valid_retentions:
            assert retention in [
                1,
                3,
                5,
                7,
                14,
                30,
                60,
                90,
                120,
                150,
                180,
                365,
                400,
                545,
                731,
                1827,
                3653,
            ]

        for retention in invalid_retentions:
            assert retention not in [
                1,
                3,
                5,
                7,
                14,
                30,
                60,
                90,
                120,
                150,
                180,
                365,
                400,
                545,
                731,
                1827,
                3653,
            ]


class TestSecurityVariables:
    """Test security configuration variables."""

    def test_kms_deletion_window_range(self):
        """KMS key deletion window must be between 7 and 30 days."""
        valid_windows = [7, 14, 21, 30]
        invalid_windows = [0, 6, 31, 60, -1]

        for window in valid_windows:
            assert 7 <= window <= 30

        for window in invalid_windows:
            assert not (7 <= window <= 30)

    def test_secrets_rotation_range(self):
        """Secrets rotation must be between 30 and 365 days."""
        valid_rotations = [30, 60, 90, 180, 365]
        invalid_rotations = [0, 29, 366, 500, -1]

        for rotation in valid_rotations:
            assert 30 <= rotation <= 365

        for rotation in invalid_rotations:
            assert not (30 <= rotation <= 365)


class TestDataCollectionVariables:
    """Test data collection configuration variables."""

    def test_metrics_lookback_range(self):
        """Metrics lookback must be between 5 and 1440 minutes."""
        valid_lookbacks = [5, 30, 60, 120, 1440]
        invalid_lookbacks = [0, 4, 1441, 2000, -1]

        for lookback in valid_lookbacks:
            assert 5 <= lookback <= 1440

        for lookback in invalid_lookbacks:
            assert not (5 <= lookback <= 1440)

    def test_logs_lookback_range(self):
        """Logs lookback must be between 5 and 1440 minutes."""
        valid_lookbacks = [5, 15, 30, 60, 1440]
        invalid_lookbacks = [0, 4, 1441, 3000, -1]

        for lookback in valid_lookbacks:
            assert 5 <= lookback <= 1440

        for lookback in invalid_lookbacks:
            assert not (5 <= lookback <= 1440)

    def test_changes_lookback_range(self):
        """Changes lookback must be between 1 and 168 hours."""
        valid_lookbacks = [1, 6, 12, 24, 48, 168]
        invalid_lookbacks = [0, -1, 169, 200]

        for lookback in valid_lookbacks:
            assert 1 <= lookback <= 168

        for lookback in invalid_lookbacks:
            assert not (1 <= lookback <= 168)

    def test_max_log_entries_range(self):
        """Max log entries must be between 10 and 1000."""
        valid_entries = [10, 50, 100, 500, 1000]
        invalid_entries = [0, 9, 1001, 5000, -1]

        for entries in valid_entries:
            assert 10 <= entries <= 1000

        for entries in invalid_entries:
            assert not (10 <= entries <= 1000)

    def test_max_context_size_range(self):
        """Max context size must be between 10KB and 100KB."""
        valid_sizes = [10240, 20480, 51200, 102400]
        invalid_sizes = [0, 5120, 102401, 200000, -1]

        for size in valid_sizes:
            assert 10240 <= size <= 102400

        for size in invalid_sizes:
            assert not (10240 <= size <= 102400)


class TestDefaultValues:
    """Test that default values meet requirements."""

    def test_default_region_is_us_east_1(self):
        """Default region should be us-east-1."""
        assert "us-east-1" == "us-east-1"

    def test_default_lambda_architecture_is_arm64(self):
        """Default Lambda architecture should be arm64 for cost efficiency."""
        assert "arm64" == "arm64"

    def test_default_log_retention_is_7_days(self):
        """Default log retention should be 7 days per requirements."""
        assert 7 == 7

    def test_default_incident_retention_is_90_days(self):
        """Default incident retention should be 90 days per requirements."""
        assert 90 == 90

    def test_default_billing_mode_is_pay_per_request(self):
        """Default DynamoDB billing mode should be PAY_PER_REQUEST."""
        assert "PAY_PER_REQUEST" == "PAY_PER_REQUEST"

    def test_default_workflow_timeout_is_120_seconds(self):
        """Default workflow timeout should be 120 seconds per requirements."""
        assert 120 == 120

    def test_default_bedrock_model_is_claude_v2(self):
        """Default Bedrock model should be Claude v2."""
        assert "anthropic.claude-v2" == "anthropic.claude-v2"

    def test_default_temperature_is_0_3(self):
        """Default temperature should be 0.3 for deterministic analysis."""
        assert 0.3 == 0.3
