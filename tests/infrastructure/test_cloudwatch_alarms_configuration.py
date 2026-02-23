"""
Infrastructure tests for CloudWatch Alarms module configuration.

These tests validate that the CloudWatch alarms module is correctly configured
with appropriate thresholds, SNS topics, and monitoring coverage.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def cloudwatch_alarms_module_path():
    """Path to the CloudWatch alarms Terraform module."""
    return Path(__file__).parent.parent.parent / "terraform" / "modules" / "cloudwatch-alarms"


@pytest.fixture
def cloudwatch_alarms_main_tf(cloudwatch_alarms_module_path):
    """Load the main.tf file for CloudWatch alarms module."""
    main_tf_path = cloudwatch_alarms_module_path / "main.tf"
    assert main_tf_path.exists(), "CloudWatch alarms main.tf not found"
    return main_tf_path.read_text()


@pytest.fixture
def cloudwatch_alarms_variables_tf(cloudwatch_alarms_module_path):
    """Load the variables.tf file for CloudWatch alarms module."""
    variables_tf_path = cloudwatch_alarms_module_path / "variables.tf"
    assert variables_tf_path.exists(), "CloudWatch alarms variables.tf not found"
    return variables_tf_path.read_text()


@pytest.fixture
def cloudwatch_alarms_outputs_tf(cloudwatch_alarms_module_path):
    """Load the outputs.tf file for CloudWatch alarms module."""
    outputs_tf_path = cloudwatch_alarms_module_path / "outputs.tf"
    assert outputs_tf_path.exists(), "CloudWatch alarms outputs.tf not found"
    return outputs_tf_path.read_text()


class TestCloudWatchAlarmsModuleStructure:
    """Test CloudWatch alarms module file structure and organization."""

    def test_module_files_exist(self, cloudwatch_alarms_module_path):
        """Test that all required module files exist."""
        required_files = ["main.tf", "variables.tf", "outputs.tf", "README.md"]

        for filename in required_files:
            file_path = cloudwatch_alarms_module_path / filename
            assert file_path.exists(), f"Required file {filename} not found"

    def test_readme_exists_and_not_empty(self, cloudwatch_alarms_module_path):
        """Test that README.md exists and contains documentation."""
        readme_path = cloudwatch_alarms_module_path / "README.md"
        assert readme_path.exists(), "README.md not found"

        content = readme_path.read_text()
        assert len(content) > 100, "README.md is too short"
        assert "CloudWatch Alarms Module" in content, "README missing module title"


class TestSNSTopicConfiguration:
    """Test SNS topic configuration for operational alerts."""

    def test_ops_alerts_topic_exists(self, cloudwatch_alarms_main_tf):
        """Test that ops alerts SNS topic is defined."""
        assert 'resource "aws_sns_topic" "ops_alerts"' in cloudwatch_alarms_main_tf
        assert "ops-alerts" in cloudwatch_alarms_main_tf

    def test_ops_alerts_topic_encrypted(self, cloudwatch_alarms_main_tf):
        """Test that ops alerts topic is encrypted with KMS."""
        assert "kms_master_key_id" in cloudwatch_alarms_main_tf
        assert "var.kms_key_id" in cloudwatch_alarms_main_tf

    def test_ops_alerts_topic_policy_exists(self, cloudwatch_alarms_main_tf):
        """Test that SNS topic policy allows CloudWatch to publish."""
        assert 'resource "aws_sns_topic_policy" "ops_alerts"' in cloudwatch_alarms_main_tf
        assert "cloudwatch.amazonaws.com" in cloudwatch_alarms_main_tf
        assert "SNS:Publish" in cloudwatch_alarms_main_tf

    def test_email_subscription_optional(self, cloudwatch_alarms_main_tf):
        """Test that email subscription is optional based on variable."""
        assert 'resource "aws_sns_topic_subscription" "ops_email"' in cloudwatch_alarms_main_tf
        assert 'count     = var.ops_email != "" ? 1 : 0' in cloudwatch_alarms_main_tf


class TestWorkflowAlarms:
    """Test Step Functions workflow monitoring alarms."""

    def test_workflow_failures_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that workflow failures alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "workflow_failures"'
            in cloudwatch_alarms_main_tf
        )
        assert "ExecutionsFailed" in cloudwatch_alarms_main_tf
        assert "AWS/States" in cloudwatch_alarms_main_tf

    def test_workflow_failures_alarm_threshold(self, cloudwatch_alarms_main_tf):
        """Test that workflow failures alarm has zero-tolerance threshold."""
        # Extract the workflow_failures alarm block
        assert "workflow_failures" in cloudwatch_alarms_main_tf
        assert "threshold           = 0" in cloudwatch_alarms_main_tf

    def test_workflow_timeouts_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that workflow timeouts alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "workflow_timeouts"'
            in cloudwatch_alarms_main_tf
        )
        assert "ExecutionsTimedOut" in cloudwatch_alarms_main_tf

    def test_workflow_alarms_use_state_machine_arn(self, cloudwatch_alarms_main_tf):
        """Test that workflow alarms monitor the correct state machine."""
        assert "StateMachineArn = var.state_machine_arn" in cloudwatch_alarms_main_tf


class TestLLMAnalyzerAlarms:
    """Test LLM analyzer monitoring alarms."""

    def test_llm_analyzer_errors_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that LLM analyzer errors alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "llm_analyzer_errors"'
            in cloudwatch_alarms_main_tf
        )
        assert "llm_analyzer_function_name" in cloudwatch_alarms_main_tf

    def test_llm_analyzer_timeouts_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that LLM analyzer timeouts alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "llm_analyzer_timeouts"'
            in cloudwatch_alarms_main_tf
        )
        assert "Duration" in cloudwatch_alarms_main_tf
        assert "threshold           = 35000" in cloudwatch_alarms_main_tf  # 35 seconds

    def test_llm_analyzer_throttles_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that LLM analyzer throttles alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "llm_analyzer_throttles"'
            in cloudwatch_alarms_main_tf
        )
        assert "Throttles" in cloudwatch_alarms_main_tf

    def test_llm_analyzer_alarms_use_function_name(self, cloudwatch_alarms_main_tf):
        """Test that LLM analyzer alarms monitor the correct Lambda function."""
        assert "FunctionName = var.llm_analyzer_function_name" in cloudwatch_alarms_main_tf


class TestNotificationServiceAlarms:
    """Test notification service monitoring alarms."""

    def test_notification_errors_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that notification service errors alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "notification_errors"'
            in cloudwatch_alarms_main_tf
        )
        assert "notification_service_function_name" in cloudwatch_alarms_main_tf

    def test_notification_delivery_failures_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that notification delivery failures alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "notification_delivery_failures"'
            in cloudwatch_alarms_main_tf
        )
        assert "NotificationDeliveryFailures" in cloudwatch_alarms_main_tf

    def test_notification_delivery_metric_filter_exists(self, cloudwatch_alarms_main_tf):
        """Test that custom metric filter for notification delivery failures exists."""
        assert (
            'resource "aws_cloudwatch_log_metric_filter" "notification_delivery_failures"'
            in cloudwatch_alarms_main_tf
        )
        assert "deliveryStatus.slack" in cloudwatch_alarms_main_tf
        assert "deliveryStatus.email" in cloudwatch_alarms_main_tf
        assert "failed" in cloudwatch_alarms_main_tf


class TestCollectorAlarms:
    """Test data collector monitoring alarms."""

    def test_collector_failures_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that collector failures alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "collector_failures"'
            in cloudwatch_alarms_main_tf
        )
        assert "CollectorFailures" in cloudwatch_alarms_main_tf

    def test_collector_failures_metric_filter_exists(self, cloudwatch_alarms_main_tf):
        """Test that custom metric filter for collector failures exists."""
        assert (
            'resource "aws_cloudwatch_log_metric_filter" "collector_failures"'
            in cloudwatch_alarms_main_tf
        )
        assert "TaskFailed" in cloudwatch_alarms_main_tf
        assert "metrics-collector" in cloudwatch_alarms_main_tf
        assert "logs-collector" in cloudwatch_alarms_main_tf
        assert "deploy-context-collector" in cloudwatch_alarms_main_tf

    def test_correlation_engine_errors_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that correlation engine errors alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "correlation_engine_errors"'
            in cloudwatch_alarms_main_tf
        )
        assert "correlation_engine_function_name" in cloudwatch_alarms_main_tf


class TestDynamoDBAlarms:
    """Test DynamoDB monitoring alarms."""

    def test_dynamodb_throttles_alarm_exists(self, cloudwatch_alarms_main_tf):
        """Test that DynamoDB throttles alarm is defined."""
        assert (
            'resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles"'
            in cloudwatch_alarms_main_tf
        )
        assert "UserErrors" in cloudwatch_alarms_main_tf
        assert "AWS/DynamoDB" in cloudwatch_alarms_main_tf

    def test_dynamodb_alarm_uses_table_name(self, cloudwatch_alarms_main_tf):
        """Test that DynamoDB alarm monitors the correct table."""
        assert "TableName = var.dynamodb_table_name" in cloudwatch_alarms_main_tf


class TestAlarmConfiguration:
    """Test alarm configuration and thresholds."""

    def test_all_alarms_publish_to_ops_alerts_topic(self, cloudwatch_alarms_main_tf):
        """Test that all alarms publish to the ops alerts SNS topic."""
        # Count alarm resources
        alarm_count = cloudwatch_alarms_main_tf.count('resource "aws_cloudwatch_metric_alarm"')
        assert alarm_count >= 10, f"Expected at least 10 alarms, found {alarm_count}"

        # Verify alarm_actions reference ops_alerts topic
        assert "alarm_actions = [aws_sns_topic.ops_alerts.arn]" in cloudwatch_alarms_main_tf

    def test_alarms_have_appropriate_evaluation_periods(self, cloudwatch_alarms_main_tf):
        """Test that alarms have appropriate evaluation periods."""
        # Critical alarms should have evaluation_periods = 1
        # Non-critical alarms can have evaluation_periods = 2
        assert "evaluation_periods  = 1" in cloudwatch_alarms_main_tf
        assert "evaluation_periods  = 2" in cloudwatch_alarms_main_tf

    def test_alarms_have_treat_missing_data_configured(self, cloudwatch_alarms_main_tf):
        """Test that alarms handle missing data appropriately."""
        assert 'treat_missing_data  = "notBreaching"' in cloudwatch_alarms_main_tf

    def test_alarms_have_tags(self, cloudwatch_alarms_main_tf):
        """Test that alarms are tagged with component and severity."""
        assert "Component" in cloudwatch_alarms_main_tf
        assert "Severity" in cloudwatch_alarms_main_tf


class TestCloudWatchDashboard:
    """Test CloudWatch dashboard configuration."""

    def test_dashboard_exists(self, cloudwatch_alarms_main_tf):
        """Test that CloudWatch dashboard is defined."""
        assert 'resource "aws_cloudwatch_dashboard" "system_health"' in cloudwatch_alarms_main_tf
        assert "system-health" in cloudwatch_alarms_main_tf

    def test_dashboard_has_workflow_widget(self, cloudwatch_alarms_main_tf):
        """Test that dashboard includes Step Functions workflow widget."""
        assert "ExecutionsStarted" in cloudwatch_alarms_main_tf
        assert "ExecutionsSucceeded" in cloudwatch_alarms_main_tf
        assert "ExecutionsFailed" in cloudwatch_alarms_main_tf

    def test_dashboard_has_llm_analyzer_widget(self, cloudwatch_alarms_main_tf):
        """Test that dashboard includes LLM analyzer widget."""
        assert "LLM Analyzer Health" in cloudwatch_alarms_main_tf

    def test_dashboard_has_notification_widget(self, cloudwatch_alarms_main_tf):
        """Test that dashboard includes notification service widget."""
        assert "Notification Service Health" in cloudwatch_alarms_main_tf

    def test_dashboard_has_collector_widget(self, cloudwatch_alarms_main_tf):
        """Test that dashboard includes data collector widget."""
        assert "Data Collector Health" in cloudwatch_alarms_main_tf

    def test_dashboard_has_dynamodb_widget(self, cloudwatch_alarms_main_tf):
        """Test that dashboard includes DynamoDB widget."""
        assert "DynamoDB Incident Store Health" in cloudwatch_alarms_main_tf


class TestModuleVariables:
    """Test module variable definitions."""

    def test_required_variables_defined(self, cloudwatch_alarms_variables_tf):
        """Test that all required variables are defined."""
        required_variables = [
            "project_name",
            "aws_region",
            "state_machine_arn",
            "state_machine_log_group_name",
            "llm_analyzer_function_name",
            "notification_service_function_name",
            "notification_service_log_group_name",
            "correlation_engine_function_name",
            "dynamodb_table_name",
            "kms_key_id",
        ]

        for var_name in required_variables:
            assert (
                f'variable "{var_name}"' in cloudwatch_alarms_variables_tf
            ), f"Required variable {var_name} not defined"

    def test_ops_email_variable_optional(self, cloudwatch_alarms_variables_tf):
        """Test that ops_email variable is optional with default empty string."""
        assert 'variable "ops_email"' in cloudwatch_alarms_variables_tf
        assert 'default     = ""' in cloudwatch_alarms_variables_tf

    def test_tags_variable_optional(self, cloudwatch_alarms_variables_tf):
        """Test that tags variable is optional with default empty map."""
        assert 'variable "tags"' in cloudwatch_alarms_variables_tf
        assert "map(string)" in cloudwatch_alarms_variables_tf


class TestModuleOutputs:
    """Test module output definitions."""

    def test_ops_alerts_topic_outputs(self, cloudwatch_alarms_outputs_tf):
        """Test that ops alerts topic outputs are defined."""
        assert 'output "ops_alerts_topic_arn"' in cloudwatch_alarms_outputs_tf
        assert 'output "ops_alerts_topic_name"' in cloudwatch_alarms_outputs_tf

    def test_alarm_arn_outputs(self, cloudwatch_alarms_outputs_tf):
        """Test that alarm ARN outputs are defined."""
        expected_outputs = [
            "workflow_failures_alarm_arn",
            "workflow_timeouts_alarm_arn",
            "llm_analyzer_errors_alarm_arn",
            "llm_analyzer_timeouts_alarm_arn",
            "notification_errors_alarm_arn",
            "notification_delivery_failures_alarm_arn",
            "collector_failures_alarm_arn",
            "dynamodb_throttles_alarm_arn",
            "correlation_engine_errors_alarm_arn",
        ]

        for output_name in expected_outputs:
            assert (
                f'output "{output_name}"' in cloudwatch_alarms_outputs_tf
            ), f"Expected output {output_name} not defined"

    def test_dashboard_outputs(self, cloudwatch_alarms_outputs_tf):
        """Test that dashboard outputs are defined."""
        assert 'output "dashboard_name"' in cloudwatch_alarms_outputs_tf
        assert 'output "dashboard_arn"' in cloudwatch_alarms_outputs_tf


class TestRequirementCompliance:
    """Test compliance with requirement 11.4."""

    def test_validates_requirement_11_4(self, cloudwatch_alarms_module_path):
        """
        Test that module validates Requirement 11.4:
        CloudWatch Alarms for workflow failures, LLM timeout, and notification delivery failures.
        """
        readme_path = cloudwatch_alarms_module_path / "README.md"
        readme_content = readme_path.read_text()

        # Verify README documents compliance
        assert "11.4" in readme_content, "README should reference requirement 11.4"
        assert "workflow failures" in readme_content.lower()
        assert "llm" in readme_content.lower() and "timeout" in readme_content.lower()
        assert "notification delivery" in readme_content.lower()

    def test_critical_alarms_present(self, cloudwatch_alarms_main_tf):
        """
        Test that the three critical alarms from requirement 11.4 are present:
        1. Step Functions workflow failures
        2. LLM analyzer timeouts
        3. Notification delivery failures
        """
        # 1. Workflow failures alarm
        assert (
            'resource "aws_cloudwatch_metric_alarm" "workflow_failures"'
            in cloudwatch_alarms_main_tf
        )

        # 2. LLM analyzer timeouts alarm
        assert (
            'resource "aws_cloudwatch_metric_alarm" "llm_analyzer_timeouts"'
            in cloudwatch_alarms_main_tf
        )

        # 3. Notification delivery failures alarm
        assert (
            'resource "aws_cloudwatch_metric_alarm" "notification_delivery_failures"'
            in cloudwatch_alarms_main_tf
        )


class TestSecurityConfiguration:
    """Test security configuration of alarms module."""

    def test_sns_topic_encrypted(self, cloudwatch_alarms_main_tf):
        """Test that SNS topic is encrypted with KMS."""
        assert "kms_master_key_id = var.kms_key_id" in cloudwatch_alarms_main_tf

    def test_sns_topic_policy_least_privilege(self, cloudwatch_alarms_main_tf):
        """Test that SNS topic policy follows least privilege."""
        # Only CloudWatch should be able to publish
        assert "cloudwatch.amazonaws.com" in cloudwatch_alarms_main_tf
        assert "SNS:Publish" in cloudwatch_alarms_main_tf


class TestCostOptimization:
    """Test cost optimization configuration."""

    def test_alarm_evaluation_periods_optimized(self, cloudwatch_alarms_main_tf):
        """Test that alarm evaluation periods are optimized (not excessive)."""
        # Evaluation periods should be 1 or 2, not higher
        assert "evaluation_periods  = 1" in cloudwatch_alarms_main_tf
        assert "evaluation_periods  = 2" in cloudwatch_alarms_main_tf
        # Should not have evaluation_periods > 2
        assert "evaluation_periods  = 3" not in cloudwatch_alarms_main_tf
        assert "evaluation_periods  = 5" not in cloudwatch_alarms_main_tf

    def test_alarm_periods_reasonable(self, cloudwatch_alarms_main_tf):
        """Test that alarm periods are reasonable (5 minutes)."""
        # Standard period should be 300 seconds (5 minutes)
        assert "period              = 300" in cloudwatch_alarms_main_tf
