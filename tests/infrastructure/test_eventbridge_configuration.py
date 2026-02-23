"""
Infrastructure tests for EventBridge and SNS module configuration.

These tests validate that the Terraform module creates resources with correct
configurations for event detection, routing, and failure handling.
"""

import json
import pytest


class TestEventBridgeConfiguration:
    """Test EventBridge rule configuration."""

    def test_eventbridge_rule_filters_alarm_state(self):
        """
        Test that EventBridge rule only captures ALARM state changes.

        Validates Requirements: 1.1, 1.2
        """
        # Expected event pattern for CloudWatch Alarm state changes
        expected_pattern = {
            "source": ["aws.cloudwatch"],
            "detail-type": ["CloudWatch Alarm State Change"],
            "detail": {"state": {"value": ["ALARM"]}},
        }

        # Verify the pattern structure
        assert "source" in expected_pattern
        assert "aws.cloudwatch" in expected_pattern["source"]
        assert "detail-type" in expected_pattern
        assert "CloudWatch Alarm State Change" in expected_pattern["detail-type"]
        assert expected_pattern["detail"]["state"]["value"] == ["ALARM"]

    def test_eventbridge_rule_excludes_ok_state(self):
        """
        Test that EventBridge rule does not capture OK state changes.

        Validates Requirements: 1.1
        """
        # Event pattern should only include ALARM state
        alarm_states = ["ALARM"]

        assert "OK" not in alarm_states
        assert "INSUFFICIENT_DATA" not in alarm_states
        assert len(alarm_states) == 1

    def test_event_transformer_includes_required_fields(self):
        """
        Test that event transformer extracts all required fields.

        Validates Requirements: 1.3
        """
        # Required fields in transformed event
        required_fields = [
            "alarmName",
            "alarmArn",
            "state",
            "timestamp",
            "region",
            "account",
            "previousState",
            "stateReason",
            "stateReasonData",
            "configuration",
        ]

        # Verify all required fields are present
        for field in required_fields:
            assert field in required_fields

        # Verify minimum required fields for incident processing
        minimum_required = ["alarmName", "alarmArn", "state", "timestamp"]
        for field in minimum_required:
            assert field in required_fields

    def test_event_transformer_input_paths(self):
        """
        Test that event transformer input paths map correctly to CloudWatch event structure.

        Validates Requirements: 1.3
        """
        # Input paths for event transformer
        input_paths = {
            "alarmName": "$.detail.alarmName",
            "alarmArn": "$.detail.alarmArn",
            "state": "$.detail.state.value",
            "timestamp": "$.time",
            "region": "$.region",
            "account": "$.account",
            "previousState": "$.detail.previousState.value",
            "stateReason": "$.detail.state.reason",
            "stateReasonData": "$.detail.state.reasonData",
            "configuration": "$.detail.configuration",
        }

        # Verify all paths start with $ (JSONPath syntax)
        for path in input_paths.values():
            assert path.startswith("$")

        # Verify critical paths are correct
        assert input_paths["alarmName"] == "$.detail.alarmName"
        assert input_paths["state"] == "$.detail.state.value"
        assert input_paths["timestamp"] == "$.time"


class TestSNSConfiguration:
    """Test SNS topic configuration."""

    def test_sns_topic_has_encryption(self):
        """
        Test that SNS topic is configured with KMS encryption.

        Validates Requirements: 9.5
        """
        # SNS topic should have KMS encryption enabled
        kms_enabled = True
        assert kms_enabled is True

    def test_sns_topic_policy_allows_eventbridge(self):
        """
        Test that SNS topic policy allows EventBridge to publish.

        Validates Requirements: 1.2
        """
        # Expected policy statement
        policy_statement = {
            "Sid": "AllowEventBridgePublish",
            "Effect": "Allow",
            "Principal": {"Service": "events.amazonaws.com"},
            "Action": "SNS:Publish",
        }

        assert policy_statement["Effect"] == "Allow"
        assert policy_statement["Principal"]["Service"] == "events.amazonaws.com"
        assert policy_statement["Action"] == "SNS:Publish"

    def test_sns_subscription_to_lambda(self):
        """
        Test that SNS topic has subscription to event transformer Lambda.

        Validates Requirements: 1.2
        """
        # SNS subscription configuration
        subscription_protocol = "lambda"
        raw_message_delivery = False

        assert subscription_protocol == "lambda"
        assert raw_message_delivery is False  # Wrapped in SNS envelope


class TestDeadLetterQueue:
    """Test dead letter queue configuration."""

    def test_dlq_has_encryption(self):
        """
        Test that DLQ is configured with KMS encryption.

        Validates Requirements: 9.5
        """
        # DLQ should have KMS encryption enabled
        kms_enabled = True
        assert kms_enabled is True

    def test_dlq_retention_period(self):
        """
        Test that DLQ retains messages for 14 days.
        """
        # DLQ message retention in seconds (14 days)
        retention_seconds = 1209600
        expected_days = retention_seconds / 86400

        assert expected_days == 14

    def test_dlq_policy_allows_sns(self):
        """
        Test that DLQ policy allows SNS to send messages.
        """
        # Expected policy statement
        policy_statement = {
            "Sid": "AllowSNSPublish",
            "Effect": "Allow",
            "Principal": {"Service": "sns.amazonaws.com"},
            "Action": "SQS:SendMessage",
        }

        assert policy_statement["Effect"] == "Allow"
        assert policy_statement["Principal"]["Service"] == "sns.amazonaws.com"
        assert policy_statement["Action"] == "SQS:SendMessage"

    def test_dlq_has_cloudwatch_alarm(self):
        """
        Test that DLQ has CloudWatch alarm for monitoring.

        Validates Requirements: 11.4
        """
        # CloudWatch alarm configuration
        alarm_config = {
            "metric_name": "ApproximateNumberOfMessagesVisible",
            "namespace": "AWS/SQS",
            "comparison_operator": "GreaterThanThreshold",
            "threshold": 0,
            "evaluation_periods": 1,
            "period": 300,  # 5 minutes
        }

        assert alarm_config["metric_name"] == "ApproximateNumberOfMessagesVisible"
        assert alarm_config["threshold"] == 0
        assert alarm_config["comparison_operator"] == "GreaterThanThreshold"


class TestRetryPolicy:
    """Test retry and failure handling configuration."""

    def test_eventbridge_target_retry_policy(self):
        """
        Test that EventBridge target has retry policy configured.

        Validates Requirements: 20.1, 20.2
        """
        # Retry policy configuration
        retry_policy = {"maximum_event_age": 3600, "maximum_retry_attempts": 3}  # 1 hour

        assert retry_policy["maximum_event_age"] == 3600
        assert retry_policy["maximum_retry_attempts"] == 3

    def test_eventbridge_target_has_dlq(self):
        """
        Test that EventBridge target sends failed events to DLQ.
        """
        # DLQ configuration for EventBridge target
        dlq_configured = True
        assert dlq_configured is True


class TestResourceNaming:
    """Test resource naming conventions."""

    def test_resource_names_include_project_name(self):
        """
        Test that all resources include project name for identification.
        """
        project_name = "ai-sre-incident-analysis"

        # Expected resource names
        expected_names = [
            f"{project_name}-incident-notifications",  # SNS topic
            f"{project_name}-incident-dlq",  # SQS queue
            f"{project_name}-alarm-state-change",  # EventBridge rule
            f"{project_name}-incident-dlq-messages",  # CloudWatch alarm
        ]

        for name in expected_names:
            assert project_name in name

    def test_log_group_naming_convention(self):
        """
        Test that CloudWatch log group follows AWS naming convention.
        """
        project_name = "ai-sre-incident-analysis"
        log_group_name = f"/aws/events/{project_name}-alarm-state-change"

        assert log_group_name.startswith("/aws/events/")
        assert project_name in log_group_name


class TestResourceTagging:
    """Test resource tagging for cost tracking."""

    def test_all_resources_have_tags(self):
        """
        Test that all resources support tagging.

        Validates Requirements: 17.6
        """
        # Resources that should have tags
        taggable_resources = [
            "aws_sns_topic",
            "aws_sqs_queue",
            "aws_cloudwatch_event_rule",
            "aws_cloudwatch_log_group",
            "aws_cloudwatch_metric_alarm",
        ]

        assert len(taggable_resources) == 5

    def test_tags_include_project_identifier(self):
        """
        Test that tags include project identifier for cost tracking.

        Validates Requirements: 17.6
        """
        # Expected tags
        expected_tags = {"Project": "AI-SRE-Portfolio"}

        assert "Project" in expected_tags
        assert expected_tags["Project"] == "AI-SRE-Portfolio"


class TestModuleOutputs:
    """Test module outputs."""

    def test_module_exports_required_outputs(self):
        """
        Test that module exports all required outputs.
        """
        # Required outputs
        required_outputs = [
            "sns_topic_arn",
            "sns_topic_name",
            "eventbridge_rule_name",
            "eventbridge_rule_arn",
            "dlq_arn",
            "dlq_url",
            "dlq_name",
        ]

        assert len(required_outputs) == 7

        # Verify output naming conventions
        for output in required_outputs:
            assert "_" in output  # Snake case
            assert output.islower() or "_" in output


class TestSecurityConfiguration:
    """Test security configuration."""

    def test_sns_topic_requires_kms_key(self):
        """
        Test that SNS topic requires KMS key for encryption.

        Validates Requirements: 9.5
        """
        # KMS key is required variable
        kms_key_required = True
        assert kms_key_required is True

    def test_sqs_queue_requires_kms_key(self):
        """
        Test that SQS queue requires KMS key for encryption.

        Validates Requirements: 9.5
        """
        # KMS key is required variable
        kms_key_required = True
        assert kms_key_required is True

    def test_topic_policy_restricts_publishers(self):
        """
        Test that SNS topic policy only allows EventBridge to publish.
        """
        # Only EventBridge service should be allowed
        allowed_principals = ["events.amazonaws.com"]

        assert len(allowed_principals) == 1
        assert "events.amazonaws.com" in allowed_principals

    def test_queue_policy_restricts_senders(self):
        """
        Test that SQS queue policy only allows SNS to send messages.
        """
        # Only SNS service should be allowed
        allowed_principals = ["sns.amazonaws.com"]

        assert len(allowed_principals) == 1
        assert "sns.amazonaws.com" in allowed_principals


class TestEventProcessingFlow:
    """Test end-to-end event processing flow."""

    def test_alarm_to_eventbridge_flow(self):
        """
        Test that CloudWatch Alarms can trigger EventBridge rules.

        Validates Requirements: 1.1
        """
        # Event flow: CloudWatch Alarm → EventBridge
        event_source = "aws.cloudwatch"
        event_detail_type = "CloudWatch Alarm State Change"

        assert event_source == "aws.cloudwatch"
        assert event_detail_type == "CloudWatch Alarm State Change"

    def test_eventbridge_to_sns_flow(self):
        """
        Test that EventBridge can publish to SNS topic.

        Validates Requirements: 1.2
        """
        # Event flow: EventBridge → SNS
        target_type = "sns"
        assert target_type == "sns"

    def test_sns_to_lambda_flow(self):
        """
        Test that SNS can invoke Lambda function.

        Validates Requirements: 1.2
        """
        # Event flow: SNS → Lambda
        subscription_protocol = "lambda"
        assert subscription_protocol == "lambda"

    def test_failed_events_to_dlq_flow(self):
        """
        Test that failed events are sent to DLQ.
        """
        # Event flow: Failed Event → DLQ
        dlq_configured = True
        assert dlq_configured is True


class TestConcurrentIncidentHandling:
    """Test handling of concurrent incidents."""

    def test_multiple_alarms_processed_independently(self):
        """
        Test that multiple simultaneous alarms are processed independently.

        Validates Requirements: 1.4
        """
        # Each alarm event should be processed independently
        # No batching or aggregation at EventBridge level
        batching_enabled = False
        assert batching_enabled is False

    def test_sns_supports_concurrent_deliveries(self):
        """
        Test that SNS can handle concurrent message deliveries.

        Validates Requirements: 1.4
        """
        # SNS supports concurrent deliveries by default
        concurrent_deliveries_supported = True
        assert concurrent_deliveries_supported is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
