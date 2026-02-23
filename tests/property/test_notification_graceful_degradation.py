"""
Property-based tests for notification graceful degradation.

This module tests that when Slack notification fails, email delivery is still attempted.
The system should continue with available notification channels even if one fails.

Validates Requirement 8.6
"""

import json
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock, Mock
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import composite
import requests

# Import notification service using package-qualified import
from notification_service import lambda_function
from notification_service.lambda_function import lambda_handler

# Import shared models
from shared.models import (
    AnalysisReport,
    Analysis,
    AnalysisMetadata,
    Confidence,
    Status,
    DeliveryStatus,
)

# Strategy generators


@composite
def incident_id_strategy(draw):
    """Generate arbitrary incident IDs."""
    return draw(
        st.one_of(
            st.uuids().map(str),
            st.text(
                min_size=10,
                max_size=50,
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
            ),
        )
    )


@composite
def confidence_strategy(draw):
    """Generate arbitrary confidence levels."""
    return draw(
        st.sampled_from([Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW, Confidence.NONE])
    )


@composite
def text_strategy(draw):
    """Generate arbitrary text content."""
    text = draw(
        st.text(
            min_size=20,
            max_size=500,
            alphabet=" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
        )
    )
    return text.replace("\x00", "")


@composite
def text_list_strategy(draw):
    """Generate arbitrary text lists."""
    return draw(
        st.lists(
            st.text(
                min_size=10,
                max_size=200,
                alphabet=" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
            ).map(lambda s: s.replace("\x00", "")),
            min_size=1,
            max_size=10,
        )
    )


@composite
def analysis_report_strategy(draw):
    """Generate arbitrary analysis reports."""
    incident_id = draw(incident_id_strategy())
    confidence = draw(confidence_strategy())
    hypothesis = draw(text_strategy())
    evidence = draw(text_list_strategy())
    contributing_factors = draw(text_list_strategy())
    actions = draw(text_list_strategy())

    # Create Analysis object
    analysis = Analysis(
        root_cause_hypothesis=hypothesis,
        confidence=confidence,
        evidence=evidence,
        contributing_factors=contributing_factors,
        recommended_actions=actions,
    )

    # Create AnalysisMetadata
    metadata = AnalysisMetadata(
        model_id="anthropic.claude-v2",
        model_version="2.1",
        prompt_version="v1.0",
        token_usage={"input": 1000, "output": 200},
        latency=2.5,
    )

    # Create AnalysisReport
    return AnalysisReport(
        incident_id=incident_id, timestamp=datetime.utcnow(), analysis=analysis, metadata=metadata
    )


@composite
def slack_error_strategy(draw):
    """Generate arbitrary Slack error scenarios."""
    error_types = [
        requests.exceptions.ConnectionError("Connection refused"),
        requests.exceptions.Timeout("Request timeout"),
        requests.exceptions.HTTPError("500 Server Error"),
        requests.exceptions.RequestException("Generic request error"),
        Exception("Webhook URL retrieval failed"),
        Exception("Invalid webhook response"),
    ]
    return draw(st.sampled_from(error_types))


# Property Tests


@settings(max_examples=10, deadline=None)
@given(analysis_report_strategy(), slack_error_strategy())
def test_property_22_email_attempted_when_slack_fails(analysis_report, slack_error):
    """
    **Property 22: Notification Graceful Degradation**
    **Validates: Requirement 8.6**

    For any notification where Slack fails, email delivery must still be attempted.

    This property verifies that:
    1. When Slack notification fails with any error, the system continues
    2. Email notification is still attempted after Slack failure
    3. The system returns partial success if email succeeds
    4. Both delivery statuses are tracked independently

    This ensures graceful degradation - one channel failure doesn't prevent
    notification through other channels.
    """
    # Set up environment variables
    os.environ["SLACK_SECRET_NAME"] = "test-slack-webhook"
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"
    os.environ["INCIDENT_STORE_BASE_URL"] = "https://test.example.com/incident"

    # Convert analysis report to event dict
    event = analysis_report.to_dict()

    # Mock context
    context = MagicMock()

    # Mock AWS clients and Slack webhook
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch("notification_service.lambda_function.sns_client.publish") as mock_sns_publish,
        patch("notification_service.lambda_function.requests.post") as mock_post,
        patch(
            "notification_service.lambda_function.SNS_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:test-topic",
        ),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure Secrets Manager to return webhook URL
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        # Configure Slack to fail with the given error
        mock_post.side_effect = slack_error

        # Configure SNS to succeed
        mock_sns_publish.return_value = {"MessageId": "test-message-id"}

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # CRITICAL ASSERTION: Email must be attempted even though Slack failed
        assert (
            mock_sns_publish.called
        ), "Email notification (SNS publish) must be attempted even when Slack fails"

        # Verify result structure
        assert isinstance(result, dict), "Result should be a dictionary"
        assert "status" in result, "Result should contain status"
        assert "deliveryStatus" in result, "Result should contain deliveryStatus"

        # Verify delivery status tracking
        delivery_status = result["deliveryStatus"]
        assert "slack" in delivery_status, "Delivery status should track Slack"
        assert "email" in delivery_status, "Delivery status should track email"

        # Verify Slack is marked as failed
        assert (
            delivery_status["slack"] == DeliveryStatus.FAILED.value
        ), "Slack delivery should be marked as failed"

        # Verify email is marked as delivered (since we mocked it to succeed)
        assert (
            delivery_status["email"] == DeliveryStatus.DELIVERED.value
        ), "Email delivery should be marked as delivered"

        # Verify overall status is partial (one succeeded, one failed)
        assert (
            result["status"] == Status.PARTIAL.value
        ), "Overall status should be partial when one channel fails"

        # Verify Slack error is tracked
        assert "slackError" in delivery_status, "Slack error should be tracked in delivery status"
        assert delivery_status["slackError"] is not None, "Slack error message should be present"

        # Verify email error is not present (since it succeeded)
        assert (
            delivery_status.get("emailError") is None
        ), "Email error should not be present when email succeeds"


@settings(max_examples=10, deadline=None)
@given(analysis_report_strategy())
def test_email_attempted_when_slack_secrets_retrieval_fails(analysis_report):
    """
    Property: Email is attempted even when Slack secrets retrieval fails.

    This verifies that failures in the Slack setup phase don't prevent email delivery.
    """
    # Set up environment variables
    os.environ["SLACK_SECRET_NAME"] = "test-slack-webhook"
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"
    os.environ["INCIDENT_STORE_BASE_URL"] = "https://test.example.com/incident"

    # Convert analysis report to event dict
    event = analysis_report.to_dict()

    # Mock context
    context = MagicMock()

    # Mock AWS clients
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch("notification_service.lambda_function.sns_client.publish") as mock_sns_publish,
        patch(
            "notification_service.lambda_function.SNS_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:test-topic",
        ),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure Secrets Manager to fail
        from botocore.exceptions import ClientError

        mock_secrets.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
            "GetSecretValue",
        )

        # Configure SNS to succeed
        mock_sns_publish.return_value = {"MessageId": "test-message-id"}

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # Email must still be attempted
        assert (
            mock_sns_publish.called
        ), "Email notification (SNS publish) must be attempted even when Slack secrets retrieval fails"

        # Verify Slack is marked as failed
        assert result["deliveryStatus"]["slack"] == DeliveryStatus.FAILED.value

        # Verify email is marked as delivered
        assert result["deliveryStatus"]["email"] == DeliveryStatus.DELIVERED.value

        # Verify overall status is partial
        assert result["status"] == Status.PARTIAL.value


@settings(max_examples=10, deadline=None)
@given(analysis_report_strategy())
def test_both_channels_fail_independently(analysis_report):
    """
    Property: When both channels fail, both failures are tracked independently.

    This verifies that failures in both channels are properly tracked and reported.
    """
    # Set up environment variables
    os.environ["SLACK_SECRET_NAME"] = "test-slack-webhook"
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"
    os.environ["INCIDENT_STORE_BASE_URL"] = "https://test.example.com/incident"

    # Convert analysis report to event dict
    event = analysis_report.to_dict()

    # Mock context
    context = MagicMock()

    # Mock AWS clients and Slack webhook
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch("notification_service.lambda_function.sns_client.publish") as mock_sns_publish,
        patch("notification_service.lambda_function.requests.post") as mock_post,
        patch(
            "notification_service.lambda_function.SNS_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:test-topic",
        ),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure Secrets Manager to succeed
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        # Configure Slack to fail
        mock_post.side_effect = requests.exceptions.ConnectionError("Slack connection failed")

        # Configure SNS to fail
        from botocore.exceptions import ClientError

        mock_sns_publish.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameter", "Message": "Invalid topic"}}, "Publish"
        )

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # Both channels must be attempted
        assert mock_post.called, "Slack notification must be attempted"
        assert (
            mock_sns_publish.called
        ), "Email notification (SNS publish) must be attempted even after Slack fails"

        # Verify both are marked as failed
        assert result["deliveryStatus"]["slack"] == DeliveryStatus.FAILED.value
        assert result["deliveryStatus"]["email"] == DeliveryStatus.FAILED.value

        # Verify overall status is failed
        assert result["status"] == Status.FAILED.value

        # Verify both errors are tracked
        assert result["deliveryStatus"]["slackError"] is not None
        assert result["deliveryStatus"]["emailError"] is not None


@settings(max_examples=10, deadline=None)
@given(analysis_report_strategy())
def test_both_channels_succeed_independently(analysis_report):
    """
    Property: When both channels succeed, both successes are tracked.

    This verifies that successful delivery through both channels is properly tracked.
    """
    # Set up environment variables
    os.environ["SLACK_SECRET_NAME"] = "test-slack-webhook"
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"
    os.environ["INCIDENT_STORE_BASE_URL"] = "https://test.example.com/incident"

    # Convert analysis report to event dict
    event = analysis_report.to_dict()

    # Mock context
    context = MagicMock()

    # Mock AWS clients and Slack webhook
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch("notification_service.lambda_function.sns_client.publish") as mock_sns_publish,
        patch("notification_service.lambda_function.requests.post") as mock_post,
        patch(
            "notification_service.lambda_function.SNS_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:test-topic",
        ),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure Secrets Manager to succeed
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        # Configure Slack to succeed
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Configure SNS to succeed
        mock_sns_publish.return_value = {"MessageId": "test-message-id"}

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # Both channels must be attempted
        assert mock_post.called, "Slack notification must be attempted"
        assert mock_sns_publish.called, "Email notification (SNS publish) must be attempted"

        # Verify both are marked as delivered
        assert result["deliveryStatus"]["slack"] == DeliveryStatus.DELIVERED.value
        assert result["deliveryStatus"]["email"] == DeliveryStatus.DELIVERED.value

        # Verify overall status is success
        assert result["status"] == Status.SUCCESS.value

        # Verify no errors are tracked
        assert result["deliveryStatus"].get("slackError") is None
        assert result["deliveryStatus"].get("emailError") is None


@settings(max_examples=10, deadline=None)
@given(analysis_report_strategy())
def test_email_fails_but_slack_succeeds(analysis_report):
    """
    Property: When email fails but Slack succeeds, status is partial.

    This verifies graceful degradation works in the opposite direction.
    """
    # Set up environment variables
    os.environ["SLACK_SECRET_NAME"] = "test-slack-webhook"
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"
    os.environ["INCIDENT_STORE_BASE_URL"] = "https://test.example.com/incident"

    # Convert analysis report to event dict
    event = analysis_report.to_dict()

    # Mock context
    context = MagicMock()

    # Mock AWS clients and Slack webhook
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch("notification_service.lambda_function.sns_client.publish") as mock_sns_publish,
        patch("notification_service.lambda_function.requests.post") as mock_post,
        patch(
            "notification_service.lambda_function.SNS_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:test-topic",
        ),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure Secrets Manager to succeed
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        # Configure Slack to succeed
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Configure SNS to fail
        from botocore.exceptions import ClientError

        mock_sns_publish.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameter", "Message": "Invalid topic"}}, "Publish"
        )

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # Both channels must be attempted
        assert mock_post.called, "Slack notification must be attempted"
        assert mock_sns_publish.called, "Email notification (SNS publish) must be attempted"

        # Verify Slack is marked as delivered
        assert result["deliveryStatus"]["slack"] == DeliveryStatus.DELIVERED.value

        # Verify email is marked as failed
        assert result["deliveryStatus"]["email"] == DeliveryStatus.FAILED.value

        # Verify overall status is partial
        assert result["status"] == Status.PARTIAL.value

        # Verify only email error is tracked
        assert result["deliveryStatus"].get("slackError") is None
        assert result["deliveryStatus"]["emailError"] is not None


@settings(max_examples=10, deadline=None)
@given(analysis_report_strategy())
def test_notification_duration_tracked_regardless_of_failures(analysis_report):
    """
    Property: Notification duration is tracked even when channels fail.

    This verifies that observability metrics are maintained during failures.
    """
    # Set up environment variables
    os.environ["SLACK_SECRET_NAME"] = "test-slack-webhook"
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"
    os.environ["INCIDENT_STORE_BASE_URL"] = "https://test.example.com/incident"

    # Convert analysis report to event dict
    event = analysis_report.to_dict()

    # Mock context
    context = MagicMock()

    # Mock AWS clients and Slack webhook to fail
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch("notification_service.lambda_function.sns_client.publish") as mock_sns_publish,
        patch("notification_service.lambda_function.requests.post") as mock_post,
        patch(
            "notification_service.lambda_function.SNS_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:test-topic",
        ),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure all to fail
        mock_secrets.get_secret_value.side_effect = Exception("Secrets retrieval failed")
        mock_sns_publish.side_effect = Exception("SNS publish failed")
        mock_post.side_effect = Exception("Slack post failed")

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # Verify duration is tracked
        assert (
            "notificationDuration" in result
        ), "Notification duration must be tracked even when channels fail"
        assert isinstance(
            result["notificationDuration"], (int, float)
        ), "Notification duration should be a number"
        assert result["notificationDuration"] >= 0, "Notification duration should be non-negative"


def test_slack_retry_exhaustion_still_attempts_email():
    """
    Property: When Slack retries are exhausted, email is still attempted.

    This verifies that retry logic doesn't prevent email delivery.
    """
    # Create a simple analysis report
    analysis = Analysis(
        root_cause_hypothesis="Test hypothesis",
        confidence=Confidence.HIGH,
        evidence=["Test evidence"],
        contributing_factors=["Test factor"],
        recommended_actions=["Test action"],
    )

    metadata = AnalysisMetadata(
        model_id="anthropic.claude-v2",
        model_version="2.1",
        prompt_version="v1.0",
        token_usage={"input": 1000, "output": 200},
        latency=2.5,
    )

    report = AnalysisReport(
        incident_id="test-incident-123",
        timestamp=datetime.utcnow(),
        analysis=analysis,
        metadata=metadata,
    )

    # Set up environment variables
    os.environ["SLACK_SECRET_NAME"] = "test-slack-webhook"
    os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-topic"
    os.environ["INCIDENT_STORE_BASE_URL"] = "https://test.example.com/incident"

    # Convert to event dict
    event = report.to_dict()

    # Mock context
    context = MagicMock()

    # Track attempts
    slack_attempt_count = 0
    email_attempted = False

    def mock_post(*args, **kwargs):
        nonlocal slack_attempt_count
        slack_attempt_count += 1
        raise requests.exceptions.Timeout("Request timeout")

    def mock_sns_publish(*args, **kwargs):
        nonlocal email_attempted
        email_attempted = True
        return {"MessageId": "test-message-id"}

    # Mock AWS clients and Slack webhook
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch(
            "notification_service.lambda_function.sns_client.publish", side_effect=mock_sns_publish
        ),
        patch("notification_service.lambda_function.requests.post", side_effect=mock_post),
        patch("time.sleep"),
        patch(
            "notification_service.lambda_function.SNS_TOPIC_ARN",
            "arn:aws:sns:us-east-1:123456789012:test-topic",
        ),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure Secrets Manager to succeed
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # Verify Slack was retried (should be 3 attempts: initial + 2 retries)
        assert (
            slack_attempt_count == 3
        ), f"Slack should be retried 3 times, got {slack_attempt_count}"

        # Email must still be attempted after all Slack retries fail
        assert (
            email_attempted
        ), "Email notification must be attempted even after Slack retries are exhausted"

        # Verify result
        assert result["deliveryStatus"]["slack"] == DeliveryStatus.FAILED.value
        assert result["deliveryStatus"]["email"] == DeliveryStatus.DELIVERED.value
        assert result["status"] == Status.PARTIAL.value


def test_missing_sns_topic_arn_still_attempts_slack():
    """
    Property: When SNS topic ARN is missing, Slack is still attempted.

    This verifies graceful degradation works in both directions.
    """
    # Create a simple analysis report
    analysis = Analysis(
        root_cause_hypothesis="Test hypothesis",
        confidence=Confidence.HIGH,
        evidence=["Test evidence"],
        contributing_factors=["Test factor"],
        recommended_actions=["Test action"],
    )

    metadata = AnalysisMetadata(
        model_id="anthropic.claude-v2",
        model_version="2.1",
        prompt_version="v1.0",
        token_usage={"input": 1000, "output": 200},
        latency=2.5,
    )

    report = AnalysisReport(
        incident_id="test-incident-456",
        timestamp=datetime.utcnow(),
        analysis=analysis,
        metadata=metadata,
    )

    # Convert to event dict
    event = report.to_dict()

    # Mock context
    context = MagicMock()

    # Track attempts
    slack_attempted = False

    def mock_post(*args, **kwargs):
        nonlocal slack_attempted
        slack_attempted = True
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        return mock_response

    # Mock AWS clients and Slack webhook (missing SNS_TOPIC_ARN)
    with (
        patch("notification_service.lambda_function.secrets_manager") as mock_secrets,
        patch("notification_service.lambda_function.requests.post", side_effect=mock_post),
        patch("notification_service.lambda_function.SNS_TOPIC_ARN", ""),
        patch("notification_service.lambda_function.put_notification_delivery_metric"),
    ):

        # Configure Secrets Manager to succeed
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        # Invoke lambda handler
        result = lambda_handler(event, context)

        # Slack must be attempted
        assert (
            slack_attempted
        ), "Slack notification must be attempted even when SNS topic ARN is missing"

        # Verify result
        assert result["deliveryStatus"]["slack"] == DeliveryStatus.DELIVERED.value
        assert result["deliveryStatus"]["email"] == DeliveryStatus.FAILED.value
        assert result["status"] == Status.PARTIAL.value
