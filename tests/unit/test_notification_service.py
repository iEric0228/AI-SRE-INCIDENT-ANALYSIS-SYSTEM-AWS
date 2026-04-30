"""
Unit tests for Notification Service Lambda function.

Tests cover:
- Slack message formatting
- Email message formatting
- Slack webhook delivery
- SNS email publishing
- Graceful degradation on Slack failure
- Secrets retrieval

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
"""

import json

# Import the lambda function
import os
from datetime import datetime
from unittest.mock import MagicMock, Mock, call, patch

import pytest
import requests
from botocore.exceptions import ClientError

from notification_service import lambda_function


@pytest.fixture
def sample_analysis_report():
    """Sample analysis report for testing."""
    return {
        "incidentId": "inc-test-001",
        "timestamp": "2024-01-15T14:30:00Z",
        "analysis": {
            "rootCauseHypothesis": "Lambda function exhausted memory due to memory leak in recent deployment",
            "confidence": "high",
            "evidence": [
                "Memory utilization increased from 60% to 95% after deployment at 14:23",
                "Error logs show 'MemoryError' starting at 14:25",
                "Deployment occurred 2 minutes before incident",
            ],
            "contributingFactors": [
                "Increased traffic during peak hours",
                "Memory limit not adjusted after code changes",
            ],
            "recommendedActions": [
                "Rollback deployment to previous version",
                "Increase Lambda memory limit to 2048 MB",
                "Investigate memory leak in new code",
            ],
        },
        "metadata": {
            "modelId": "anthropic.claude-v2",
            "modelVersion": "2.1",
            "promptVersion": "v1.2",
            "tokenUsage": {"input": 1500, "output": 300},
            "latency": 2.5,
        },
    }


@pytest.fixture
def mock_secrets_manager():
    """Mock Secrets Manager client."""
    client = MagicMock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
    }
    return client


@pytest.fixture
def mock_sns_client():
    """Mock SNS client."""
    client = MagicMock()
    client.publish.return_value = {"MessageId": "test-message-id"}
    return client


class TestLambdaHandler:
    """Tests for the main lambda_handler function."""

    @patch("notification_service.lambda_function.send_slack_notification")
    @patch("notification_service.lambda_function.send_email_notification")
    def test_successful_notification_both_channels(
        self, mock_email, mock_slack, sample_analysis_report
    ):
        """Test successful notification to both Slack and email."""
        # Arrange
        event = sample_analysis_report

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert result["deliveryStatus"]["slack"] == "delivered"
        assert result["deliveryStatus"]["email"] == "delivered"
        assert result["notificationDuration"] >= 0

        # Verify both notification methods were called
        mock_slack.assert_called_once()
        mock_email.assert_called_once()

    @patch("notification_service.lambda_function.send_slack_notification")
    @patch("notification_service.lambda_function.send_email_notification")
    def test_graceful_degradation_slack_fails(self, mock_email, mock_slack, sample_analysis_report):
        """Test graceful degradation when Slack fails but email succeeds."""
        # Arrange
        event = sample_analysis_report
        mock_slack.side_effect = Exception("Slack webhook failed")

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "partial"
        assert result["deliveryStatus"]["slack"] == "failed"
        assert result["deliveryStatus"]["email"] == "delivered"
        assert "Slack webhook failed" in result["deliveryStatus"]["slackError"]

        # Verify email was still attempted
        mock_email.assert_called_once()

    @patch("notification_service.lambda_function.send_slack_notification")
    @patch("notification_service.lambda_function.send_email_notification")
    def test_graceful_degradation_email_fails(self, mock_email, mock_slack, sample_analysis_report):
        """Test graceful degradation when email fails but Slack succeeds."""
        # Arrange
        event = sample_analysis_report
        mock_email.side_effect = Exception("SNS publish failed")

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "partial"
        assert result["deliveryStatus"]["slack"] == "delivered"
        assert result["deliveryStatus"]["email"] == "failed"
        assert "SNS publish failed" in result["deliveryStatus"]["emailError"]

    @patch("notification_service.lambda_function.send_slack_notification")
    @patch("notification_service.lambda_function.send_email_notification")
    def test_both_channels_fail(self, mock_email, mock_slack, sample_analysis_report):
        """Test when both notification channels fail."""
        # Arrange
        event = sample_analysis_report
        mock_slack.side_effect = Exception("Slack failed")
        mock_email.side_effect = Exception("Email failed")

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "failed"
        assert result["deliveryStatus"]["slack"] == "failed"
        assert result["deliveryStatus"]["email"] == "failed"
        assert result["deliveryStatus"]["slackError"] is not None
        assert result["deliveryStatus"]["emailError"] is not None

    @patch("notification_service.lambda_function.send_slack_notification")
    @patch("notification_service.lambda_function.send_email_notification")
    def test_invalid_event_structure(self, mock_email, mock_slack):
        """Test handling of invalid event structure."""
        # Arrange
        event = {"invalid": "structure"}

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "failed"
        assert result["deliveryStatus"]["slack"] == "failed"
        assert result["deliveryStatus"]["email"] == "failed"

    @patch("notification_service.lambda_function.send_slack_notification")
    @patch("notification_service.lambda_function.send_email_notification")
    def test_correlation_id_logging(self, mock_email, mock_slack, sample_analysis_report):
        """Test that correlation ID is properly logged."""
        # Arrange
        event = sample_analysis_report

        with patch("notification_service.lambda_function.logger") as mock_logger:
            # Act
            lambda_function.lambda_handler(event, None)

            # Assert - verify correlation ID in logs
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            log_messages = [json.loads(msg) for msg in log_calls]

            # Check that correlation ID appears in logs
            assert any(msg.get("correlationId") == "inc-test-001" for msg in log_messages)


class TestSlackNotification:
    """Tests for Slack notification functionality."""

    @patch("notification_service.lambda_function.get_slack_webhook_url")
    @patch("requests.post")
    def test_successful_slack_delivery(self, mock_post, mock_get_url, sample_analysis_report):
        """Test successful Slack webhook delivery."""
        # Arrange
        mock_get_url.return_value = "https://hooks.slack.com/test"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        lambda_function.send_slack_notification(report)

        # Assert
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://hooks.slack.com/test"
        assert "json" in call_args[1]
        assert "blocks" in call_args[1]["json"]
        assert call_args[1]["timeout"] == 5

    @patch("notification_service.lambda_function.get_slack_webhook_url")
    @patch("requests.post")
    def test_slack_retry_on_failure(self, mock_post, mock_get_url, sample_analysis_report):
        """Test Slack webhook retry logic."""
        # Arrange
        mock_get_url.return_value = "https://hooks.slack.com/test"
        mock_post.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            requests.exceptions.Timeout("Timeout"),
            MagicMock(status_code=200),
        ]

        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        lambda_function.send_slack_notification(report)

        # Assert - should retry 2 times before success
        assert mock_post.call_count == 3

    @patch("notification_service.lambda_function.get_slack_webhook_url")
    @patch("requests.post")
    @patch("time.sleep")
    def test_slack_fails_after_max_retries(
        self, mock_sleep, mock_post, mock_get_url, sample_analysis_report
    ):
        """Test Slack webhook fails after max retries."""
        # Arrange
        mock_get_url.return_value = "https://hooks.slack.com/test"
        mock_post.side_effect = requests.exceptions.Timeout("Timeout")

        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            lambda_function.send_slack_notification(report)

        assert "failed after 3 attempts" in str(exc_info.value)
        assert mock_post.call_count == 3

    @patch("notification_service.lambda_function.get_slack_webhook_url")
    @patch("requests.post")
    def test_slack_http_error(self, mock_post, mock_get_url, sample_analysis_report):
        """Test Slack webhook HTTP error handling."""
        # Arrange
        mock_get_url.return_value = "https://hooks.slack.com/test"
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Bad Request")
        mock_post.return_value = mock_response

        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act & Assert
        with pytest.raises(Exception):
            lambda_function.send_slack_notification(report)


class TestEmailNotification:
    """Tests for email notification functionality."""

    @patch(
        "notification_service.lambda_function.SNS_TOPIC_ARN",
        "arn:aws:sns:us-east-1:123456789012:test-topic",
    )
    @patch("notification_service.lambda_function.sns_client")
    def test_successful_email_delivery(self, mock_sns_client, sample_analysis_report):
        """Test successful SNS email delivery."""
        # Arrange
        mock_sns_client.publish.return_value = {"MessageId": "test-message-id"}

        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        lambda_function.send_email_notification(report)

        # Assert
        mock_sns_client.publish.assert_called_once()
        call_args = mock_sns_client.publish.call_args

        assert call_args[1]["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:test-topic"
        assert "Subject" in call_args[1]
        assert "Message" in call_args[1]
        assert "MessageAttributes" in call_args[1]
        assert call_args[1]["MessageAttributes"]["incidentId"]["StringValue"] == "inc-test-001"

    @patch.dict(os.environ, {"SNS_TOPIC_ARN": ""})
    def test_email_missing_topic_arn(self, sample_analysis_report):
        """Test email notification fails when SNS_TOPIC_ARN is not set."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            lambda_function.send_email_notification(report)

        assert "SNS_TOPIC_ARN environment variable not set" in str(exc_info.value)

    @patch(
        "notification_service.lambda_function.SNS_TOPIC_ARN",
        "arn:aws:sns:us-east-1:123456789012:test-topic",
    )
    @patch("notification_service.lambda_function.sns_client")
    def test_email_sns_client_error(self, mock_sns_client, sample_analysis_report):
        """Test email notification handles SNS client errors."""
        # Arrange
        mock_sns_client.publish.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameter", "Message": "Invalid topic"}}, "Publish"
        )

        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            lambda_function.send_email_notification(report)

        assert "SNS publish failed" in str(exc_info.value)


class TestSecretsRetrieval:
    """Tests for secrets retrieval from Secrets Manager."""

    @pytest.fixture(autouse=True)
    def reset_webhook_cache(self):
        """Reset the webhook URL cache before each test."""
        lambda_function._webhook_cache["url"] = None
        lambda_function._webhook_cache["expires"] = 0.0

    def test_successful_secret_retrieval(self, mock_secrets_manager):
        """Test successful retrieval of Slack webhook URL."""
        # Arrange
        with patch("notification_service.lambda_function.secrets_manager", mock_secrets_manager):
            # Act
            result = lambda_function.get_slack_webhook_url()

        # Assert
        assert result == "https://hooks.slack.com/test"
        mock_secrets_manager.get_secret_value.assert_called_once_with(
            SecretId="incident-analysis/slack-webhook"
        )

    def test_secret_not_found(self, mock_secrets_manager):
        """Test handling when secret is not found."""
        # Arrange
        mock_secrets_manager.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
            "GetSecretValue",
        )

        with patch("notification_service.lambda_function.secrets_manager", mock_secrets_manager):
            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                lambda_function.get_slack_webhook_url()

            assert "Failed to retrieve Slack webhook URL" in str(exc_info.value)

    def test_secret_access_denied(self, mock_secrets_manager):
        """Test handling when access to secret is denied."""
        # Arrange
        mock_secrets_manager.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
            "GetSecretValue",
        )

        with patch("notification_service.lambda_function.secrets_manager", mock_secrets_manager):
            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                lambda_function.get_slack_webhook_url()

            assert "Failed to retrieve Slack webhook URL" in str(exc_info.value)

    def test_invalid_secret_format(self, mock_secrets_manager):
        """Test handling when secret has invalid JSON format."""
        # Arrange
        mock_secrets_manager.get_secret_value.return_value = {"SecretString": "not valid json"}

        with patch("notification_service.lambda_function.secrets_manager", mock_secrets_manager):
            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                lambda_function.get_slack_webhook_url()

            assert "Invalid secret format" in str(exc_info.value)

    def test_missing_webhook_url_key(self, mock_secrets_manager):
        """Test handling when secret JSON is missing webhook_url key."""
        # Arrange
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"wrong_key": "value"})
        }

        with patch("notification_service.lambda_function.secrets_manager", mock_secrets_manager):
            # Act & Assert
            with pytest.raises(Exception) as exc_info:
                lambda_function.get_slack_webhook_url()

            assert "Invalid secret format" in str(exc_info.value)

    @patch("notification_service.lambda_function.SLACK_SECRET_NAME", "custom/secret/path")
    @patch("notification_service.lambda_function.secrets_manager")
    def test_custom_secret_name(self, mock_secrets_manager):
        """Test retrieval with custom secret name from environment."""
        # Arrange
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/custom"})
        }

        # Act
        lambda_function.get_slack_webhook_url()

        # Assert
        mock_secrets_manager.get_secret_value.assert_called_once_with(SecretId="custom/secret/path")


class TestSlackMessageFormatting:
    """Tests for Slack message formatting."""

    def test_slack_message_structure(self, sample_analysis_report):
        """Test Slack message has correct block structure."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        assert "blocks" in result
        blocks = result["blocks"]
        assert len(blocks) > 0

        # Verify header block
        assert blocks[0]["type"] == "header"
        assert "Incident Alert" in blocks[0]["text"]["text"]

    def test_slack_message_includes_required_fields(self, sample_analysis_report):
        """Test Slack message includes all required fields."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        message_text = json.dumps(result)
        assert "inc-test-001" in message_text
        assert "High" in message_text  # Severity
        assert "Lambda function exhausted memory" in message_text
        assert "View Full Incident Details" in message_text

    def test_slack_message_high_confidence_formatting(self, sample_analysis_report):
        """Test Slack message formatting for high confidence."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        header_text = result["blocks"][0]["text"]["text"]
        assert "🔴" in header_text

        message_text = json.dumps(result)
        assert "High" in message_text

    def test_slack_message_medium_confidence_formatting(self, sample_analysis_report):
        """Test Slack message formatting for medium confidence."""
        # Arrange
        sample_analysis_report["analysis"]["confidence"] = "medium"
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        header_text = result["blocks"][0]["text"]["text"]
        assert "🟡" in header_text

        message_text = json.dumps(result)
        assert "Medium" in message_text

    def test_slack_message_low_confidence_formatting(self, sample_analysis_report):
        """Test Slack message formatting for low confidence."""
        # Arrange
        sample_analysis_report["analysis"]["confidence"] = "low"
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        header_text = result["blocks"][0]["text"]["text"]
        assert "🟢" in header_text

        message_text = json.dumps(result)
        assert "Low" in message_text

    def test_slack_message_includes_evidence(self, sample_analysis_report):
        """Test Slack message includes evidence section."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        message_text = json.dumps(result)
        assert "Evidence:" in message_text
        assert "Memory utilization increased" in message_text

    def test_slack_message_includes_contributing_factors(self, sample_analysis_report):
        """Test Slack message includes contributing factors."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        message_text = json.dumps(result)
        assert "Contributing Factors:" in message_text
        assert "Increased traffic" in message_text

    def test_slack_message_includes_recommended_actions(self, sample_analysis_report):
        """Test Slack message includes recommended actions."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        message_text = json.dumps(result)
        assert "Recommended Actions:" in message_text
        assert "Rollback deployment" in message_text

    def test_slack_message_includes_incident_link(self, sample_analysis_report):
        """Test Slack message includes link to incident details."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert
        message_text = json.dumps(result)
        assert "View Full Incident Details" in message_text
        assert "inc-test-001" in message_text

    def test_slack_message_empty_evidence(self, sample_analysis_report):
        """Test Slack message handles empty evidence list."""
        # Arrange
        sample_analysis_report["analysis"]["evidence"] = []
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_slack_message(report)

        # Assert - should not include evidence section
        message_text = json.dumps(result)
        # Evidence section should not be present if list is empty
        blocks_with_evidence = [b for b in result["blocks"] if "Evidence:" in json.dumps(b)]
        assert len(blocks_with_evidence) == 0


class TestEmailMessageFormatting:
    """Tests for email message formatting."""

    def test_email_subject_formatting(self, sample_analysis_report):
        """Test email subject line formatting."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_email_subject(report)

        # Assert
        assert "[High]" in result
        assert "Incident Alert" in result
        assert "inc-test-001" in result

    def test_email_plain_text_structure(self, sample_analysis_report):
        """Test email plain text formatting."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_email_plain_text(report)

        # Assert
        assert "INCIDENT ALERT" in result
        assert "inc-test-001" in result
        assert "ROOT CAUSE HYPOTHESIS:" in result
        assert "Lambda function exhausted memory" in result
        assert "EVIDENCE:" in result
        assert "RECOMMENDED ACTIONS:" in result
        assert "View Full Incident Details:" in result

    def test_email_html_structure(self, sample_analysis_report):
        """Test email HTML formatting."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_email_html(report)

        # Assert
        assert "<html>" in result
        assert "<body>" in result
        assert "Incident Alert" in result
        assert "inc-test-001" in result
        assert "Root Cause Hypothesis" in result
        assert "View Full Incident Details" in result

    def test_email_html_color_coding_high_severity(self, sample_analysis_report):
        """Test HTML email uses correct color for high severity."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_email_html(report)

        # Assert
        assert "#dc3545" in result  # Red color for high severity

    def test_email_html_color_coding_medium_severity(self, sample_analysis_report):
        """Test HTML email uses correct color for medium severity."""
        # Arrange
        sample_analysis_report["analysis"]["confidence"] = "medium"
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_email_html(report)

        # Assert
        assert "#ffc107" in result  # Yellow color for medium severity

    def test_email_html_color_coding_low_severity(self, sample_analysis_report):
        """Test HTML email uses correct color for low severity."""
        # Arrange
        sample_analysis_report["analysis"]["confidence"] = "low"
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        result = lambda_function.format_email_html(report)

        # Assert
        assert "#28a745" in result  # Green color for low severity

    def test_email_includes_all_sections(self, sample_analysis_report):
        """Test email includes all required sections."""
        # Arrange
        from shared.models import AnalysisReport

        report = AnalysisReport.from_dict(sample_analysis_report)

        # Act
        plain_text = lambda_function.format_email_plain_text(report)
        html_text = lambda_function.format_email_html(report)

        # Assert - both formats should include key sections
        for text in [plain_text, html_text]:
            assert "inc-test-001" in text
            assert "Lambda function exhausted memory" in text
            assert "Memory utilization increased" in text
            assert "Rollback deployment" in text


class TestSeverityMapping:
    """Tests for confidence to severity mapping."""

    def test_high_confidence_maps_to_high_severity(self):
        """Test high confidence maps to High severity."""
        assert lambda_function.get_severity_from_confidence("high") == "High"

    def test_medium_confidence_maps_to_medium_severity(self):
        """Test medium confidence maps to Medium severity."""
        assert lambda_function.get_severity_from_confidence("medium") == "Medium"

    def test_low_confidence_maps_to_low_severity(self):
        """Test low confidence maps to Low severity."""
        assert lambda_function.get_severity_from_confidence("low") == "Low"

    def test_none_confidence_maps_to_low_severity(self):
        """Test none confidence maps to Low severity."""
        assert lambda_function.get_severity_from_confidence("none") == "Low"

    def test_unknown_confidence_maps_to_low_severity(self):
        """Test unknown confidence values map to Low severity."""
        assert lambda_function.get_severity_from_confidence("unknown") == "Low"
        assert lambda_function.get_severity_from_confidence("invalid") == "Low"

    def test_case_insensitive_mapping(self):
        """Test confidence mapping is case insensitive."""
        assert lambda_function.get_severity_from_confidence("HIGH") == "High"
        assert lambda_function.get_severity_from_confidence("Medium") == "Medium"
        assert lambda_function.get_severity_from_confidence("LOW") == "Low"
