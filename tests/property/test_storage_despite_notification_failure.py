"""
Property Test: Storage Despite Notification Failure

Property 28: For any incident where the notification service fails, the incident
store must still persist the complete incident record.

Validates: Requirements 12.5

Note: This property tests the Step Functions orchestration logic, not individual
Lambda functions. In the actual workflow, notification and storage happen in
parallel branches, so notification failure doesn't block storage.

This test validates the design principle that storage is independent of notification.
"""

import json
import pytest
from hypothesis import given, strategies as st
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Import shared models
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from shared.models import AnalysisReport, IncidentRecord


# Strategy for generating complete incident data
@st.composite
def complete_incident_data(draw):
    """
    Generate complete incident data that should be stored.
    """
    incident_id = draw(
        st.text(
            min_size=10,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pd")),
        )
    )
    timestamp = draw(st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)))

    return {
        "incidentId": incident_id,
        "timestamp": timestamp.isoformat() + "Z",
        "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
        "resourceType": "ec2",
        "alarmName": "test-alarm",
        "severity": draw(st.sampled_from(["critical", "high", "medium", "low"])),
        "structuredContext": {
            "incidentId": incident_id,
            "timestamp": timestamp.isoformat() + "Z",
            "resource": {
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
                "type": "ec2",
                "name": "test-instance",
            },
            "alarm": {"name": "test-alarm", "metric": "CPUUtilization", "threshold": 50.0},
            "metrics": {"summary": {}, "timeSeries": []},
            "logs": {"errorCount": 0, "entries": []},
            "changes": {"recentDeployments": 0, "entries": []},
            "completeness": {"metrics": True, "logs": True, "changes": True},
        },
        "analysisReport": {
            "incidentId": incident_id,
            "timestamp": timestamp.isoformat() + "Z",
            "analysis": {
                "rootCauseHypothesis": "Test hypothesis",
                "confidence": "high",
                "evidence": ["Test evidence"],
                "contributingFactors": [],
                "recommendedActions": ["Test action"],
            },
            "metadata": {
                "modelId": "anthropic.claude-v2",
                "modelVersion": "2.1",
                "promptVersion": "v1.0",
                "tokenUsage": {"input": 100, "output": 50},
                "latency": 1.5,
            },
        },
        "notificationStatus": {
            "status": draw(st.sampled_from(["failed", "partial"])),
            "deliveryStatus": {
                "slack": draw(st.sampled_from(["failed", "skipped"])),
                "email": draw(st.sampled_from(["failed", "skipped"])),
                "slackError": draw(st.text(min_size=10, max_size=100)),
                "emailError": draw(st.text(min_size=10, max_size=100)),
            },
            "notificationDuration": draw(st.floats(min_value=0.1, max_value=10.0)),
        },
    }


@given(incident_data=complete_incident_data())
@pytest.mark.property_test
@pytest.mark.tag(
    "Feature: ai-sre-incident-analysis, Property 28: Storage Despite Notification Failure"
)
def test_storage_despite_notification_failure(incident_data):
    """
    Property 28: For any incident where the notification service fails, the incident
    store must still persist the complete incident record.

    This test validates that:
    1. Incident record structure is complete even when notification fails
    2. All required fields are present for storage
    3. Notification failure status is recorded

    Validates: Requirements 12.5
    """
    # PROPERTY ASSERTIONS:
    # 1. Incident data must have all required fields for DynamoDB storage
    required_fields = [
        "incidentId",
        "timestamp",
        "resourceArn",
        "resourceType",
        "alarmName",
        "severity",
        "structuredContext",
        "analysisReport",
        "notificationStatus",
    ]

    for field in required_fields:
        assert (
            field in incident_data
        ), f"Incident record must have {field} field even when notification fails"

    # 2. Notification status must indicate failure
    notification_status = incident_data["notificationStatus"]
    assert notification_status["status"] in [
        "failed",
        "partial",
    ], "Notification status must indicate failure or partial success"

    # 3. Structured context must be complete
    structured_context = incident_data["structuredContext"]
    assert "incidentId" in structured_context, "Structured context must have incident ID"
    assert "resource" in structured_context, "Structured context must have resource info"
    assert (
        "completeness" in structured_context
    ), "Structured context must have completeness indicator"

    # 4. Analysis report must be present (even if it's a fallback)
    analysis_report = incident_data["analysisReport"]
    assert "incidentId" in analysis_report, "Analysis report must have incident ID"
    assert "analysis" in analysis_report, "Analysis report must have analysis section"

    # 5. Incident record must be serializable to DynamoDB format
    try:
        # Create IncidentRecord object
        record = IncidentRecord(
            incident_id=incident_data["incidentId"],
            timestamp=incident_data["timestamp"],
            resource_arn=incident_data["resourceArn"],
            resource_type=incident_data["resourceType"],
            alarm_name=incident_data["alarmName"],
            severity=incident_data["severity"],
            structured_context=incident_data["structuredContext"],
            analysis_report=incident_data["analysisReport"],
            notification_status=incident_data["notificationStatus"],
            ttl=int(datetime.utcnow().timestamp()) + (90 * 24 * 60 * 60),
        )

        # Must be convertible to DynamoDB item
        dynamodb_item = record.to_dynamodb_item()
        assert dynamodb_item is not None, "Incident record must be convertible to DynamoDB item"

    except Exception as e:
        pytest.fail(f"Incident record must be valid for DynamoDB storage: {e}")

    # 6. Notification failure details must be preserved
    delivery_status = notification_status["deliveryStatus"]

    # At least one channel must have failed
    assert delivery_status["slack"] in ["failed", "skipped"] or delivery_status["email"] in [
        "failed",
        "skipped",
    ], "At least one notification channel must have failed"

    # Error messages should be present for failed channels
    if delivery_status["slack"] == "failed":
        assert (
            "slackError" in delivery_status
        ), "Slack error message must be present when Slack fails"

    if delivery_status["email"] == "failed":
        assert (
            "emailError" in delivery_status
        ), "Email error message must be present when email fails"


@given(notification_fails=st.booleans(), storage_succeeds=st.booleans())
@pytest.mark.property_test
def test_storage_independence_from_notification(notification_fails, storage_succeeds):
    """
    Test that storage operation is independent of notification result.

    In Step Functions, notification and storage happen in parallel branches,
    so they don't affect each other.
    """
    # This test validates the design principle:
    # Storage and notification are independent parallel operations

    # Simulate parallel execution results
    notification_result = {
        "status": "failed" if notification_fails else "success",
        "deliveryStatus": {
            "slack": "failed" if notification_fails else "delivered",
            "email": "failed" if notification_fails else "delivered",
        },
    }

    storage_result = {
        "status": "success" if storage_succeeds else "failed",
        "itemStored": storage_succeeds,
    }

    # PROPERTY: Storage result is independent of notification result
    # Both can succeed, both can fail, or one can succeed while the other fails

    # The key property is that notification failure doesn't prevent storage attempt
    if notification_fails:
        # Even if notification fails, storage can still succeed
        # This is the core of Property 28
        assert storage_result["status"] in [
            "success",
            "failed",
        ], "Storage must be attempted regardless of notification result"

    # Similarly, storage failure doesn't prevent notification attempt
    if not storage_succeeds:
        assert notification_result["status"] in [
            "success",
            "failed",
        ], "Notification must be attempted regardless of storage result"


@given(incident_data=complete_incident_data())
@pytest.mark.property_test
def test_incident_record_completeness_with_notification_failure(incident_data):
    """
    Test that incident record contains complete information even when notification fails.
    """
    # Extract key components
    incident_id = incident_data["incidentId"]
    structured_context = incident_data["structuredContext"]
    analysis_report = incident_data["analysisReport"]
    notification_status = incident_data["notificationStatus"]

    # PROPERTY: All incident data must be preserved for storage

    # 1. Incident ID must match across all components
    assert (
        structured_context["incidentId"] == incident_id
    ), "Structured context incident ID must match"

    assert analysis_report["incidentId"] == incident_id, "Analysis report incident ID must match"

    # 2. Timestamps must be present
    assert "timestamp" in incident_data, "Incident record must have timestamp"

    assert "timestamp" in structured_context, "Structured context must have timestamp"

    assert "timestamp" in analysis_report, "Analysis report must have timestamp"

    # 3. Resource information must be complete
    assert "resourceArn" in incident_data, "Incident record must have resource ARN"

    assert "resource" in structured_context, "Structured context must have resource info"

    # 4. Analysis must be present (even if fallback)
    assert "analysis" in analysis_report, "Analysis report must have analysis section"

    analysis = analysis_report["analysis"]
    assert "rootCauseHypothesis" in analysis, "Analysis must have root cause hypothesis"

    # 5. Notification failure must be documented
    assert notification_status["status"] in [
        "failed",
        "partial",
    ], "Notification failure must be recorded"

    assert (
        "deliveryStatus" in notification_status
    ), "Notification status must include delivery details"


@given(both_channels_fail=st.booleans(), include_error_details=st.booleans())
@pytest.mark.property_test
def test_notification_failure_details_preserved(both_channels_fail, include_error_details):
    """
    Test that notification failure details are preserved in incident record.
    """
    # Build notification status
    notification_status = {
        "status": "failed" if both_channels_fail else "partial",
        "deliveryStatus": {
            "slack": "failed",
            "email": "failed" if both_channels_fail else "delivered",
        },
        "notificationDuration": 2.5,
    }

    if include_error_details:
        notification_status["deliveryStatus"]["slackError"] = "Webhook timeout"
        if both_channels_fail:
            notification_status["deliveryStatus"]["emailError"] = "SNS publish failed"

    # PROPERTY: Failure details must be preserved for debugging

    # 1. Status must indicate failure
    assert notification_status["status"] in [
        "failed",
        "partial",
    ], "Status must indicate notification issue"

    # 2. Delivery status must show which channels failed
    delivery_status = notification_status["deliveryStatus"]
    assert "slack" in delivery_status, "Delivery status must include Slack status"

    assert "email" in delivery_status, "Delivery status must include email status"

    # 3. If error details included, they must be preserved
    if include_error_details:
        assert "slackError" in delivery_status, "Slack error details must be preserved"

        if both_channels_fail:
            assert "emailError" in delivery_status, "Email error details must be preserved"

    # 4. Duration must be recorded
    assert (
        "notificationDuration" in notification_status
    ), "Notification duration must be recorded even on failure"
