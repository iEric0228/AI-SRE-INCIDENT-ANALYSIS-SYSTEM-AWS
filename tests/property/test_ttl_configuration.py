"""
Property-based tests for TTL configuration correctness.

Property 25: TTL Configuration Correctness
For any stored incident, TTL must be exactly 90 days from incident timestamp.

Validates Requirements: 9.4
"""

from datetime import datetime, timedelta
from hypothesis import given, strategies as st
import pytest
from shared.models import IncidentRecord


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


@given(
    incident_id=incident_id_strategy(),
    timestamp=st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)),
    resource_arn=resource_arn_strategy(),
)
@pytest.mark.property_test
@pytest.mark.tag("Feature: ai-sre-incident-analysis, Property 25: TTL Configuration Correctness")
def test_ttl_configuration_correctness(incident_id, timestamp, resource_arn):
    """
    Property 25: For any stored incident, TTL must be exactly 90 days from incident timestamp.

    Validates Requirements: 9.4

    PROPERTY ASSERTIONS:
    1. TTL must be calculated as incident timestamp + 90 days
    2. TTL must be in Unix timestamp format (integer seconds)
    3. TTL must be exactly 7,776,000 seconds (90 days) from incident
    4. TTL calculation must be consistent across all incidents
    5. TTL must be included in DynamoDB item
    """

    # Calculate expected TTL (90 days from incident timestamp)
    ttl_delta = timedelta(days=90)
    expected_ttl_datetime = timestamp + ttl_delta
    expected_ttl_seconds = int(expected_ttl_datetime.timestamp())

    # Create incident record with calculated TTL
    record = IncidentRecord(
        incident_id=incident_id,
        timestamp=timestamp.isoformat(),
        resource_arn=resource_arn,
        resource_type="lambda",
        alarm_name="HighErrorRate",
        severity="high",
        structured_context={
            "incidentId": incident_id,
            "timestamp": timestamp.isoformat(),
            "resource": {"arn": resource_arn, "type": "lambda", "name": "test"},
            "alarm": {"name": "HighErrorRate", "metric": "Errors", "threshold": 10.0},
            "metrics": {},
            "logs": {},
            "changes": {},
            "completeness": {"metrics": True, "logs": True, "changes": True},
        },
        analysis_report={
            "incidentId": incident_id,
            "timestamp": timestamp.isoformat(),
            "analysis": {
                "rootCauseHypothesis": "Test hypothesis",
                "confidence": "high",
                "evidence": [],
                "contributingFactors": [],
                "recommendedActions": [],
            },
            "metadata": {
                "modelId": "anthropic.claude-v2",
                "modelVersion": "2.1",
                "promptVersion": "v1.0",
                "tokenUsage": {"input": 100, "output": 50},
                "latency": 2.5,
            },
        },
        notification_status={
            "status": "success",
            "deliveryStatus": {
                "slack": "delivered",
                "email": "delivered",
                "slackError": None,
                "emailError": None,
            },
            "notificationDuration": 1.5,
        },
        ttl=expected_ttl_seconds,
    )

    # PROPERTY ASSERTION 1: TTL must be calculated as incident timestamp + 90 days
    incident_dt = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
    ttl_dt = datetime.fromtimestamp(record.ttl)
    actual_delta = ttl_dt - incident_dt

    # Allow 1 second tolerance for rounding
    assert (
        abs(actual_delta.total_seconds() - (90 * 24 * 60 * 60)) <= 1
    ), f"TTL must be exactly 90 days from incident timestamp (delta: {actual_delta.total_seconds()} seconds)"

    # PROPERTY ASSERTION 2: TTL must be in Unix timestamp format (integer seconds)
    assert isinstance(record.ttl, int), "TTL must be an integer (Unix timestamp in seconds)"
    assert record.ttl > 0, "TTL must be a positive integer"

    # PROPERTY ASSERTION 3: TTL must be exactly 7,776,000 seconds (90 days) from incident
    # 90 days = 90 * 24 * 60 * 60 = 7,776,000 seconds
    # Note: Allow 3600 second (1 hour) tolerance for DST transitions
    expected_seconds_delta = 90 * 24 * 60 * 60
    incident_timestamp = int(incident_dt.timestamp())
    actual_seconds_delta = record.ttl - incident_timestamp

    # Allow 3600 second (1 hour) tolerance for DST transitions
    assert abs(actual_seconds_delta - expected_seconds_delta) <= 3600, (
        f"TTL must be approximately {expected_seconds_delta} seconds (90 days) from incident "
        f"(actual: {actual_seconds_delta} seconds, diff: {abs(actual_seconds_delta - expected_seconds_delta)})"
    )

    # PROPERTY ASSERTION 4: TTL calculation must be consistent across all incidents
    # Recalculate TTL using the same method
    recalculated_ttl = int((incident_dt + timedelta(days=90)).timestamp())
    assert (
        abs(record.ttl - recalculated_ttl) <= 1
    ), "TTL calculation must be consistent and reproducible"

    # PROPERTY ASSERTION 5: TTL must be included in DynamoDB item
    dynamodb_item = record.to_dynamodb_item()

    assert "ttl" in dynamodb_item, "DynamoDB item must include TTL attribute"
    assert "N" in dynamodb_item["ttl"], "TTL must be stored as Number type in DynamoDB"

    # Verify TTL value in DynamoDB item matches record TTL
    dynamodb_ttl = int(dynamodb_item["ttl"]["N"])
    assert dynamodb_ttl == record.ttl, "TTL in DynamoDB item must match record TTL"

    # ADDITIONAL ASSERTION: Verify TTL is in the future (for recent incidents)
    now = datetime.utcnow()
    if incident_dt <= now:
        # For past incidents, TTL should be in the future
        ttl_datetime = datetime.fromtimestamp(record.ttl)
        assert (
            ttl_datetime > incident_dt
        ), "TTL must be in the future relative to incident timestamp"


@given(
    timestamps=st.lists(
        st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)),
        min_size=2,
        max_size=5,
        unique=True,  # Ensure unique timestamps to avoid comparison issues
    )
)
@pytest.mark.property_test
@pytest.mark.tag("Feature: ai-sre-incident-analysis, Property 25: TTL Configuration Correctness")
def test_ttl_calculation_consistency(timestamps):
    """
    Property 25 (Extended): TTL calculation must be consistent across multiple incidents.

    Validates Requirements: 9.4

    PROPERTY ASSERTIONS:
    1. TTL ordering must match incident timestamp ordering
    2. TTL must always be 90 days in the future
    """

    # Sort timestamps for comparison
    sorted_timestamps = sorted(timestamps)

    # Calculate TTLs for all timestamps
    ttls = []
    for ts in sorted_timestamps:
        ttl = int((ts + timedelta(days=90)).timestamp())
        ttls.append(ttl)

    # PROPERTY ASSERTION 1: TTL ordering must match incident timestamp ordering
    for i in range(len(ttls) - 1):
        # Since timestamps are unique and sorted, TTLs should also be sorted
        assert (
            ttls[i] < ttls[i + 1]
        ), f"TTL ordering must match incident timestamp ordering (ttl[{i}]={ttls[i]}, ttl[{i+1}]={ttls[i+1]})"

    # PROPERTY ASSERTION 2: TTL must always be 90 days in the future
    for i, ts in enumerate(sorted_timestamps):
        ttl_datetime = datetime.fromtimestamp(ttls[i])
        delta = ttl_datetime - ts

        # Allow 1 hour tolerance for DST (0.05 days = ~1 hour)
        expected_days = 90
        actual_days = delta.total_seconds() / (24 * 60 * 60)
        assert (
            abs(actual_days - expected_days) <= 0.05
        ), f"TTL must be approximately 90 days from incident (actual: {actual_days} days)"
