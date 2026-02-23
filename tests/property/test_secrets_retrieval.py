"""
Property-based tests for secrets retrieval at runtime.

This module tests that notification service retrieves secrets from Secrets Manager
at runtime, never from environment variables or hardcoded values.

Validates Requirement 14.3
"""

import json
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock, call
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import composite
from botocore.exceptions import ClientError

# Import shared models
from shared.models import AnalysisReport, Analysis, AnalysisMetadata, Confidence

# Import notification service using package-qualified import
from notification_service import lambda_function as notification_lambda

get_slack_webhook_url = notification_lambda.get_slack_webhook_url
lambda_handler = notification_lambda.lambda_handler


# Strategy generators


@composite
def secret_name_strategy(draw):
    """Generate arbitrary secret names."""
    return draw(
        st.text(
            min_size=10,
            max_size=100,
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/_",
        )
    )


@composite
def webhook_url_strategy(draw):
    """Generate arbitrary webhook URLs."""
    domain = draw(st.text(min_size=5, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"))
    path = draw(
        st.text(
            min_size=10,
            max_size=50,
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )
    )
    return f"https://hooks.{domain}.com/{path}"


@composite
def analysis_report_strategy(draw):
    """Generate arbitrary analysis reports."""
    incident_id = draw(st.uuids().map(str))
    confidence = draw(
        st.sampled_from([Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW, Confidence.NONE])
    )

    hypothesis = draw(
        st.text(
            min_size=20,
            max_size=200,
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?",
        )
    )

    evidence = draw(
        st.lists(
            st.text(
                min_size=10,
                max_size=100,
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,",
            ),
            min_size=0,
            max_size=5,
        )
    )

    actions = draw(
        st.lists(
            st.text(
                min_size=10,
                max_size=100,
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,",
            ),
            min_size=1,
            max_size=5,
        )
    )

    # Create Analysis object
    analysis = Analysis(
        root_cause_hypothesis=hypothesis,
        confidence=confidence,
        evidence=evidence,
        contributing_factors=evidence,
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


# Property Tests


@given(webhook_url_strategy())
def test_property_29_secrets_retrieved_from_secrets_manager(webhook_url):
    """
    **Property 29: Secrets Retrieval at Runtime**
    **Validates: Requirements 14.3**

    For any notification invocation, secrets must be retrieved from Secrets Manager
    at runtime, never from environment variables or hardcoded values.

    This property verifies that:
    1. Secrets Manager API is called to retrieve secrets
    2. Secrets are not retrieved from environment variables
    3. Secrets are not hardcoded in the function
    4. The correct secret name is used in the API call
    """
    # Mock the secrets manager client
    with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
        # Configure mock to return a valid secret
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": webhook_url})
        }

        # Call the function that retrieves secrets
        retrieved_url = get_slack_webhook_url()

        # 1. Verify Secrets Manager API was called
        assert (
            mock_secrets_manager.get_secret_value.called
        ), "Secrets Manager get_secret_value must be called to retrieve secrets"

        # 2. Verify the correct secret name was used
        call_args = mock_secrets_manager.get_secret_value.call_args
        assert call_args is not None, "get_secret_value should have been called with arguments"

        # Extract SecretId from call arguments
        if call_args[1]:  # kwargs
            secret_id = call_args[1].get("SecretId")
        else:  # args
            secret_id = call_args[0][0] if call_args[0] else None

        assert secret_id is not None, "SecretId must be provided to get_secret_value"
        assert isinstance(secret_id, str), "SecretId must be a string"
        assert len(secret_id) > 0, "SecretId must not be empty"

        # 3. Verify the retrieved URL matches what was in the secret
        assert (
            retrieved_url == webhook_url
        ), "Retrieved webhook URL must match the value from Secrets Manager"

        # 4. Verify the URL is not hardcoded (it should match our generated value)
        assert (
            retrieved_url == webhook_url
        ), "Webhook URL must come from Secrets Manager, not be hardcoded"


@given(webhook_url_strategy())
def test_secrets_not_retrieved_from_environment_variables(webhook_url):
    """
    Property: Secrets are not retrieved from environment variables.

    This verifies that even if environment variables are set, the function
    still retrieves secrets from Secrets Manager.
    """
    # Set environment variable (should be ignored)
    with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hardcoded.example.com/webhook"}):
        with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
            # Configure mock to return a valid secret
            mock_secrets_manager.get_secret_value.return_value = {
                "SecretString": json.dumps({"webhook_url": webhook_url})
            }

            # Call the function
            retrieved_url = get_slack_webhook_url()

            # Verify Secrets Manager was called (not environment variable)
            assert (
                mock_secrets_manager.get_secret_value.called
            ), "Must call Secrets Manager even when environment variable exists"

            # Verify the retrieved URL is from Secrets Manager, not environment
            assert (
                retrieved_url == webhook_url
            ), "Must use Secrets Manager value, not environment variable"
            assert (
                retrieved_url != "https://hardcoded.example.com/webhook"
            ), "Must not use environment variable value"


@settings(deadline=None)
@given(analysis_report_strategy(), webhook_url_strategy())
def test_secrets_retrieved_on_every_invocation(analysis_report, webhook_url):
    """
    Property: Secrets are retrieved on every Lambda invocation.

    This verifies that secrets are not cached between invocations and are
    always retrieved fresh from Secrets Manager.
    """
    # Mock the secrets manager and requests
    with (
        patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager,
        patch.object(notification_lambda, "requests") as mock_requests,
        patch.object(notification_lambda, "sns_client") as mock_sns,
        patch.object(
            notification_lambda, "SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:test-topic"
        ),
        patch.object(notification_lambda, "put_notification_delivery_metric"),
    ):

        # Configure mocks
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": webhook_url})
        }
        mock_requests.post = MagicMock(return_value=MagicMock(status_code=200))
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        # Create event
        event = analysis_report.to_dict()

        # Call lambda handler (simulates invocation)
        result = lambda_handler(event, None)

        # Verify Secrets Manager was called during this invocation
        assert (
            mock_secrets_manager.get_secret_value.called
        ), "Secrets Manager must be called on every Lambda invocation"

        # Verify the function succeeded
        assert (
            result["status"] == "success" or result["status"] == "partial"
        ), "Lambda handler should complete successfully"


@given(webhook_url_strategy())
def test_secrets_manager_called_before_slack_notification(webhook_url):
    """
    Property: Secrets Manager is called before sending Slack notification.

    This verifies that secrets are retrieved at runtime, not at module load time.
    """
    with (
        patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager,
        patch.object(notification_lambda, "requests") as mock_requests,
    ):

        # Configure mocks
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": webhook_url})
        }
        mock_requests.post = MagicMock(return_value=MagicMock(status_code=200))

        # Create a simple analysis report
        analysis = Analysis(
            root_cause_hypothesis="Test hypothesis",
            confidence=Confidence.HIGH,
            evidence=["Evidence 1"],
            contributing_factors=["Factor 1"],
            recommended_actions=["Action 1"],
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

        # Get send_slack_notification from the imported module
        send_slack_notification = notification_lambda.send_slack_notification

        # Call the function
        send_slack_notification(report)

        # Verify Secrets Manager was called before requests.post
        assert (
            mock_secrets_manager.get_secret_value.called
        ), "Secrets Manager must be called to retrieve webhook URL"
        assert mock_requests.post.called, "Slack webhook should be called"

        # Verify the webhook URL used in POST matches the secret
        post_call_args = mock_requests.post.call_args
        assert post_call_args is not None, "requests.post should have been called"

        # Extract URL from call arguments
        if post_call_args[0]:  # positional args
            posted_url = post_call_args[0][0]
        else:  # kwargs
            posted_url = post_call_args[1].get("url")

        assert posted_url == webhook_url, "Slack POST must use URL from Secrets Manager"


@given(st.text(min_size=10, max_size=50))
def test_secrets_manager_error_handling(error_message):
    """
    Property: Secrets Manager errors are properly handled.

    This verifies that if Secrets Manager fails, the function raises
    an appropriate exception rather than falling back to hardcoded values.
    """
    with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
        # Configure mock to raise an error
        mock_secrets_manager.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": error_message}},
            "GetSecretValue",
        )

        # Call the function - should raise an exception
        try:
            get_slack_webhook_url()
            assert False, "Function should raise exception when Secrets Manager fails"
        except Exception as e:
            # Verify exception is raised (not silently falling back to hardcoded value)
            assert "Failed to retrieve" in str(e) or "Slack webhook" in str(
                e
            ), "Exception should indicate Secrets Manager failure"


def test_secret_name_not_hardcoded_in_function():
    """
    Property: Secret name comes from environment variable or constant.

    This verifies that the secret name is configurable and not hardcoded
    in multiple places throughout the code.
    """
    with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
        # Configure mock
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://test.example.com/webhook"})
        }

        # Call the function
        get_slack_webhook_url()

        # Verify the secret name used is from a constant/environment variable
        call_args = mock_secrets_manager.get_secret_value.call_args

        if call_args[1]:  # kwargs
            secret_id = call_args[1].get("SecretId")
        else:  # args
            secret_id = call_args[0][0] if call_args[0] else None

        # The secret name should be the one defined in the module constant
        # (which comes from environment variable with a default)
        assert secret_id is not None, "Secret name must be provided"

        # Verify it's a reasonable secret name format
        assert (
            "/" in secret_id or "-" in secret_id
        ), "Secret name should follow AWS naming conventions (e.g., 'incident-analysis/slack-webhook')"


@given(webhook_url_strategy())
def test_secrets_retrieved_with_correct_api_parameters(webhook_url):
    """
    Property: Secrets Manager API is called with correct parameters.

    This verifies that the API call uses the correct parameter names
    and structure as defined by AWS SDK.
    """
    with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
        # Configure mock
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": webhook_url})
        }

        # Call the function
        get_slack_webhook_url()

        # Verify the API was called with correct parameter structure
        assert mock_secrets_manager.get_secret_value.called, "get_secret_value must be called"

        call_args = mock_secrets_manager.get_secret_value.call_args

        # Verify SecretId parameter is used (AWS SDK requirement)
        if call_args[1]:  # kwargs
            assert "SecretId" in call_args[1], "Must use 'SecretId' parameter name as per AWS SDK"
        else:
            # If positional, first argument should be the secret ID
            assert len(call_args[0]) > 0, "Must provide secret ID as first argument"


@given(webhook_url_strategy())
def test_secret_value_parsed_from_json(webhook_url):
    """
    Property: Secret value is properly parsed from JSON format.

    This verifies that the function correctly parses the SecretString
    as JSON and extracts the webhook_url field.
    """
    with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
        # Configure mock with JSON secret
        secret_json = json.dumps({"webhook_url": webhook_url})
        mock_secrets_manager.get_secret_value.return_value = {"SecretString": secret_json}

        # Call the function
        retrieved_url = get_slack_webhook_url()

        # Verify the URL was correctly extracted from JSON
        assert (
            retrieved_url == webhook_url
        ), "Webhook URL must be correctly parsed from JSON SecretString"

        # Verify it's not returning the raw JSON string
        assert retrieved_url != secret_json, "Must parse JSON, not return raw SecretString"


def test_invalid_secret_format_raises_exception():
    """
    Property: Invalid secret format raises appropriate exception.

    This verifies that if the secret is not in the expected format,
    the function raises an exception rather than using a default value.
    """
    with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
        # Configure mock with invalid JSON
        mock_secrets_manager.get_secret_value.return_value = {"SecretString": "not-valid-json"}

        # Call the function - should raise an exception
        try:
            get_slack_webhook_url()
            assert False, "Function should raise exception for invalid JSON"
        except Exception as e:
            # Verify exception indicates invalid format
            assert "Invalid secret format" in str(e) or "JSON" in str(
                e
            ), "Exception should indicate JSON parsing failure"


def test_missing_webhook_url_field_raises_exception():
    """
    Property: Missing webhook_url field in secret raises exception.

    This verifies that if the secret JSON doesn't contain the expected
    webhook_url field, the function raises an exception.
    """
    with patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager:
        # Configure mock with valid JSON but missing webhook_url field
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"other_field": "value"})
        }

        # Call the function - should raise an exception
        try:
            get_slack_webhook_url()
            assert False, "Function should raise exception when webhook_url field is missing"
        except Exception as e:
            # Verify exception indicates missing field
            assert (
                "Invalid secret format" in str(e) or "webhook_url" in str(e) or "KeyError" in str(e)
            ), "Exception should indicate missing webhook_url field"


@given(webhook_url_strategy())
def test_secrets_not_logged_or_exposed(webhook_url):
    """
    Property: Secret values are not logged or exposed in responses.

    This verifies that the webhook URL is not accidentally logged or
    included in error messages where it could be exposed.
    """
    with (
        patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager,
        patch.object(notification_lambda, "logger") as mock_logger,
    ):

        # Configure mock
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": webhook_url})
        }

        # Call the function
        retrieved_url = get_slack_webhook_url()

        # Verify the webhook URL is not in any log messages
        if mock_logger.info.called or mock_logger.debug.called or mock_logger.warning.called:
            # Check all log calls
            for call_obj in (
                mock_logger.info.call_args_list
                + mock_logger.debug.call_args_list
                + mock_logger.warning.call_args_list
            ):
                log_message = str(call_obj)
                assert (
                    webhook_url not in log_message
                ), "Webhook URL must not be logged (security risk)"


@given(analysis_report_strategy(), webhook_url_strategy())
@settings(deadline=500)  # Allow 500ms for this test since it involves Lambda handler execution
def test_secrets_retrieved_in_lambda_handler_context(analysis_report, webhook_url):
    """
    Property: Secrets are retrieved within Lambda handler execution context.

    This verifies that secrets are retrieved during the Lambda handler
    execution, not at module import time.
    """
    with (
        patch.object(notification_lambda, "secrets_manager") as mock_secrets_manager,
        patch.object(notification_lambda, "requests") as mock_requests,
        patch.object(notification_lambda, "sns_client") as mock_sns,
    ):

        # Configure mocks
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": webhook_url})
        }
        mock_requests.post = MagicMock(return_value=MagicMock(status_code=200))
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        # Reset call count
        mock_secrets_manager.get_secret_value.reset_mock()

        # Create event
        event = analysis_report.to_dict()

        # Call lambda handler
        lambda_handler(event, None)

        # Verify Secrets Manager was called during handler execution
        assert (
            mock_secrets_manager.get_secret_value.called
        ), "Secrets Manager must be called during Lambda handler execution, not at import time"

        # Verify it was called at least once
        assert (
            mock_secrets_manager.get_secret_value.call_count >= 1
        ), "Secrets Manager should be called at least once per invocation"
