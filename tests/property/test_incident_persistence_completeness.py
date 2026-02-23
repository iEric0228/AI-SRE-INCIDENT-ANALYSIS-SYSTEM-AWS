"""
Property-based tests for incident persistence completeness.

Property 23: Incident Persistence Completeness
For any completed incident, stored record must contain all required fields.

Validates Requirements: 9.1, 9.2
"""

import json
from datetime import datetime, timedelta
from hypothesis import given, strategies as st
import pytest
from shared.models import (
    IncidentRecord,
    StructuredContext,
    AnalysisReport,
    NotificationOutput,
    ResourceInfo,
    AlarmInfo,
    CompletenessInfo,
    Analysis,
    AnalysisMetadata,
    DeliveryStatus,
)


# Strategy for generating valid incident IDs (UUIDs)
@st.composite
def incident_id_strategy(draw):
    """Generate valid UUID v4 incident IDs."""
    import uuid

    return str(uuid.uuid4())


# Strategy for generating resource ARNs
@st.composite
def resource_arn_strategy(draw):
    """Generate valid AWS resource ARNs."""
    service = draw(st.sampled_from(["lambda", "ec2", "rds", "ecs", "dynamodb"]))
    region = draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]))
    account = draw(st.integers(min_value=100000000000, max_value=999999999999))
    resource_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"
            ),
            min_size=1,
            max_size=50,
        )
    )

    return f"arn:aws:{service}:{region}:{account}:function/{resource_name}"


# Strategy for generating structured context
@st.composite
def structured_context_strategy(draw):
    """Generate valid structured context."""
    incident_id = draw(incident_id_strategy())
    timestamp = draw(st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)))
    resource_arn = draw(resource_arn_strategy())

    return {
        "incidentId": incident_id,
        "timestamp": timestamp.isoformat(),
        "resource": {"arn": resource_arn, "type": "lambda", "name": "test-function"},
        "alarm": {"name": "HighErrorRate", "metric": "Errors", "threshold": 10.0},
        "metrics": {"summary": {"errorRate": 15.5}, "timeSeries": []},
        "logs": {"errorCount": 45, "topErrors": ["Connection timeout"], "entries": []},
        "changes": {"recentDeployments": 2, "lastDeployment": timestamp.isoformat(), "entries": []},
        "completeness": {"metrics": True, "logs": True, "changes": True},
    }


# Strategy for generating analysis reports
@st.composite
def analysis_report_strategy(draw):
    """Generate valid analysis reports."""
    incident_id = draw(incident_id_strategy())
    timestamp = draw(st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)))

    return {
        "incidentId": incident_id,
        "timestamp": timestamp.isoformat(),
        "analysis": {
            "rootCauseHypothesis": draw(st.text(min_size=10, max_size=200)),
            "confidence": draw(st.sampled_from(["high", "medium", "low", "none"])),
            "evidence": draw(st.lists(st.text(min_size=5, max_size=100), min_size=0, max_size=5)),
            "contributingFactors": draw(
                st.lists(st.text(min_size=5, max_size=100), min_size=0, max_size=3)
            ),
            "recommendedActions": draw(
                st.lists(st.text(min_size=5, max_size=100), min_size=1, max_size=5)
            ),
        },
        "metadata": {
            "modelId": "anthropic.claude-v2",
            "modelVersion": "2.1",
            "promptVersion": "v1.0",
            "tokenUsage": {
                "input": draw(st.integers(min_value=100, max_value=5000)),
                "output": draw(st.integers(min_value=50, max_value=2000)),
            },
            "latency": draw(st.floats(min_value=0.5, max_value=30.0)),
        },
    }


# Strategy for generating notification status
@st.composite
def notification_status_strategy(draw):
    """Generate valid notification status."""
    return {
        "status": draw(st.sampled_from(["success", "partial", "failed"])),
        "deliveryStatus": {
            "slack": draw(st.sampled_from(["delivered", "failed", "skipped"])),
            "email": draw(st.sampled_from(["delivered", "failed", "skipped"])),
            "slackError": None,
            "emailError": None,
        },
        "notificationDuration": draw(st.floats(min_value=0.1, max_value=10.0)),
    }


@given(
    incident_id=incident_id_strategy(),
    timestamp=st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)),
    resource_arn=resource_arn_strategy(),
    structured_context=structured_context_strategy(),
    analysis_report=analysis_report_strategy(),
    notification_status=notification_status_strategy(),
)
@pytest.mark.property_test
@pytest.mark.tag(
    "Feature: ai-sre-incident-analysis, Property 23: Incident Persistence Completeness"
)
def test_incident_persistence_completeness(
    incident_id, timestamp, resource_arn, structured_context, analysis_report, notification_status
):
    """
    Property 23: For any completed incident, stored record must contain all required fields.

    Validates Requirements: 9.1, 9.2

    PROPERTY ASSERTIONS:
    1. Incident record must have incident ID
    2. Incident record must have timestamp
    3. Incident record must have resource ARN
    4. Incident record must have resource type
    5. Incident record must have alarm name
    6. Incident record must have severity
    7. Incident record must have structured context
    8. Incident record must have analysis report
    9. Incident record must have notification status
    10. Incident record must have TTL (90 days from incident)
    11. All fields must be serializable to DynamoDB format
    """

    # Calculate TTL (90 days from incident timestamp)
    ttl_timestamp = int((timestamp + timedelta(days=90)).timestamp())

    # Create incident record
    record = IncidentRecord(
        incident_id=incident_id,
        timestamp=timestamp.isoformat(),
        resource_arn=resource_arn,
        resource_type="lambda",
        alarm_name="HighErrorRate",
        severity="high",
        structured_context=structured_context,
        analysis_report=analysis_report,
        notification_status=notification_status,
        ttl=ttl_timestamp,
    )

    # PROPERTY ASSERTION 1: Incident record must have incident ID
    assert record.incident_id is not None, "Incident record must have incident ID"
    assert isinstance(record.incident_id, str), "Incident ID must be a string"
    assert len(record.incident_id) > 0, "Incident ID must not be empty"

    # PROPERTY ASSERTION 2: Incident record must have timestamp
    assert record.timestamp is not None, "Incident record must have timestamp"
    assert isinstance(record.timestamp, str), "Timestamp must be a string"
    # Verify ISO 8601 format
    try:
        datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
    except ValueError:
        pytest.fail("Timestamp must be in ISO 8601 format")

    # PROPERTY ASSERTION 3: Incident record must have resource ARN
    assert record.resource_arn is not None, "Incident record must have resource ARN"
    assert isinstance(record.resource_arn, str), "Resource ARN must be a string"
    assert record.resource_arn.startswith("arn:aws:"), "Resource ARN must be valid AWS ARN format"

    # PROPERTY ASSERTION 4: Incident record must have resource type
    assert record.resource_type is not None, "Incident record must have resource type"
    assert isinstance(record.resource_type, str), "Resource type must be a string"
    assert record.resource_type in [
        "lambda",
        "ec2",
        "rds",
        "ecs",
        "dynamodb",
        "sqs",
        "sns",
    ], "Resource type must be valid AWS service"

    # PROPERTY ASSERTION 5: Incident record must have alarm name
    assert record.alarm_name is not None, "Incident record must have alarm name"
    assert isinstance(record.alarm_name, str), "Alarm name must be a string"
    assert len(record.alarm_name) > 0, "Alarm name must not be empty"

    # PROPERTY ASSERTION 6: Incident record must have severity
    assert record.severity is not None, "Incident record must have severity"
    assert isinstance(record.severity, str), "Severity must be a string"
    assert record.severity in ["critical", "high", "medium", "low"], "Severity must be valid level"

    # PROPERTY ASSERTION 7: Incident record must have structured context
    assert record.structured_context is not None, "Incident record must have structured context"
    assert isinstance(record.structured_context, dict), "Structured context must be a dictionary"
    # Verify required fields in structured context
    required_context_fields = ["incidentId", "timestamp", "resource", "alarm", "completeness"]
    for field in required_context_fields:
        assert field in record.structured_context, f"Structured context must have '{field}' field"

    # PROPERTY ASSERTION 8: Incident record must have analysis report
    assert record.analysis_report is not None, "Incident record must have analysis report"
    assert isinstance(record.analysis_report, dict), "Analysis report must be a dictionary"
    # Verify required fields in analysis report
    required_report_fields = ["incidentId", "timestamp", "analysis", "metadata"]
    for field in required_report_fields:
        assert field in record.analysis_report, f"Analysis report must have '{field}' field"

    # PROPERTY ASSERTION 9: Incident record must have notification status
    assert record.notification_status is not None, "Incident record must have notification status"
    assert isinstance(record.notification_status, dict), "Notification status must be a dictionary"
    assert "status" in record.notification_status, "Notification status must have 'status' field"

    # PROPERTY ASSERTION 10: Incident record must have TTL (90 days from incident)
    assert record.ttl is not None, "Incident record must have TTL"
    assert isinstance(record.ttl, int), "TTL must be an integer (Unix timestamp)"

    # Verify TTL is exactly 90 days from incident timestamp
    incident_dt = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
    expected_ttl = int((incident_dt + timedelta(days=90)).timestamp())
    # Allow 1 second tolerance for rounding
    assert (
        abs(record.ttl - expected_ttl) <= 1
    ), f"TTL must be exactly 90 days from incident timestamp (expected {expected_ttl}, got {record.ttl})"

    # PROPERTY ASSERTION 11: All fields must be serializable to DynamoDB format
    try:
        dynamodb_item = record.to_dynamodb_item()

        # Verify DynamoDB item structure
        assert dynamodb_item is not None, "DynamoDB item must not be None"
        assert isinstance(dynamodb_item, dict), "DynamoDB item must be a dictionary"

        # Verify all required DynamoDB attributes
        required_dynamodb_fields = [
            "incidentId",
            "timestamp",
            "resourceArn",
            "resourceType",
            "alarmName",
            "severity",
            "structuredContext",
            "analysisReport",
            "notificationStatus",
            "ttl",
        ]
        for field in required_dynamodb_fields:
            assert field in dynamodb_item, f"DynamoDB item must have '{field}' attribute"

        # Verify DynamoDB type descriptors
        assert "S" in dynamodb_item["incidentId"], "incidentId must have String type descriptor"
        assert "S" in dynamodb_item["timestamp"], "timestamp must have String type descriptor"
        assert "S" in dynamodb_item["resourceArn"], "resourceArn must have String type descriptor"
        assert "N" in dynamodb_item["ttl"], "ttl must have Number type descriptor"

        # Verify JSON fields are serialized as strings
        assert (
            "S" in dynamodb_item["structuredContext"]
        ), "structuredContext must be serialized as String"
        assert "S" in dynamodb_item["analysisReport"], "analysisReport must be serialized as String"

        # Verify JSON strings are valid
        json.loads(dynamodb_item["structuredContext"]["S"])
        json.loads(dynamodb_item["analysisReport"]["S"])
        json.loads(dynamodb_item["notificationStatus"]["S"])

    except Exception as e:
        pytest.fail(f"Incident record must be serializable to DynamoDB format: {e}")
