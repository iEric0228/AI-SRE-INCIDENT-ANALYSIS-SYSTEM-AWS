"""
Property-based tests for event routing completeness.

This module tests the event routing completeness property: for any CloudWatch
Alarm state change event, the resulting incident event must contain all required
fields (incident ID, alarm name, resource ARN, timestamp, alarm state).

Validates Requirements 1.1, 1.2, 1.3
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st, assume
from hypothesis.strategies import composite
import sys
import os
import uuid

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from event_transformer.lambda_function import transform_alarm_event

# Strategy generators


@composite
def alarm_state_strategy(draw):
    """Generate valid CloudWatch Alarm states."""
    return draw(st.sampled_from(["ALARM", "OK", "INSUFFICIENT_DATA"]))


@composite
def resource_dimension_strategy(draw):
    """
    Generate resource dimensions for CloudWatch metrics.

    Generates one of the common AWS resource dimension types:
    - InstanceId (EC2)
    - FunctionName (Lambda)
    - DBInstanceIdentifier (RDS)
    - ClusterName (ECS)
    """
    dimension_type = draw(
        st.sampled_from(["InstanceId", "FunctionName", "DBInstanceIdentifier", "ClusterName"])
    )

    # Generate appropriate value based on dimension type
    if dimension_type == "InstanceId":
        value = f"i-{draw(st.text(alphabet='0123456789abcdef', min_size=17, max_size=17))}"
    elif dimension_type == "FunctionName":
        value = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20))
    elif dimension_type == "DBInstanceIdentifier":
        value = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20))
    elif dimension_type == "ClusterName":
        value = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20))

    return {dimension_type: value}


@composite
def cloudwatch_alarm_event_strategy(draw):
    """
    Generate arbitrary CloudWatch Alarm state change events.

    Generates events that match the EventBridge schema for CloudWatch Alarm
    state changes, with various combinations of required and optional fields.
    """
    # Generate alarm name (required)
    alarm_name = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-_", min_size=5, max_size=50))

    # Generate alarm state (required)
    alarm_state = draw(alarm_state_strategy())

    # Generate AWS account and region
    account = draw(st.text(alphabet="0123456789", min_size=12, max_size=12))
    region = draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]))

    # Generate alarm ARN
    alarm_arn = f"arn:aws:cloudwatch:{region}:{account}:alarm:{alarm_name}"

    # Generate timestamp
    timestamp_int = draw(st.integers(min_value=1577836800, max_value=1924905600))
    timestamp = (
        datetime.fromtimestamp(timestamp_int, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )

    # Generate metric information
    metric_name = draw(
        st.sampled_from(
            [
                "CPUUtilization",
                "MemoryUtilization",
                "NetworkIn",
                "NetworkOut",
                "Errors",
                "Duration",
                "Invocations",
                "DatabaseConnections",
            ]
        )
    )

    namespace = draw(
        st.sampled_from(["AWS/EC2", "AWS/Lambda", "AWS/RDS", "AWS/ECS", "AWS/DynamoDB"])
    )

    # Generate resource dimensions
    dimensions = draw(resource_dimension_strategy())

    # Generate optional alarm description
    has_description = draw(st.booleans())
    alarm_description = draw(st.text(min_size=10, max_size=100)) if has_description else ""

    # Construct CloudWatch Alarm event
    event = {
        "version": "0",
        "id": str(uuid.uuid4()),
        "detail-type": "CloudWatch Alarm State Change",
        "source": "aws.cloudwatch",
        "account": account,
        "time": timestamp,
        "region": region,
        "resources": [alarm_arn],
        "detail": {
            "alarmName": alarm_name,
            "alarmArn": alarm_arn,
            "state": {
                "value": alarm_state,
                "reason": f"Threshold Crossed: 1 datapoint was greater than the threshold",
                "timestamp": timestamp,
            },
            "previousState": {"value": "OK", "timestamp": timestamp},
            "configuration": {
                "description": alarm_description,
                "metricName": metric_name,
                "namespace": namespace,
                "metrics": [
                    {
                        "id": "m1",
                        "metricStat": {
                            "metric": {
                                "namespace": namespace,
                                "name": metric_name,
                                "dimensions": dimensions,
                            },
                            "period": 60,
                            "stat": "Average",
                        },
                    }
                ],
            },
        },
    }

    # Optionally add alarm description to detail level
    if has_description:
        event["detail"]["alarmDescription"] = alarm_description

    return event


# Property Tests


@given(cloudwatch_alarm_event_strategy())
def test_event_routing_completeness_required_fields(alarm_event):
    """
    Property 1: Event Routing Completeness

    **Validates: Requirements 1.1, 1.2, 1.3**

    For any CloudWatch Alarm state change event, the resulting incident event
    must contain all required fields:
    - incidentId (UUID v4)
    - alarmName
    - resourceArn
    - timestamp
    - alarmState
    - metricName
    - namespace

    This property ensures that the event transformation is complete and no
    required fields are missing.
    """
    # Transform the alarm event
    incident_event = transform_alarm_event(alarm_event)

    # Property 1: All required fields must be present
    required_fields = [
        "incidentId",
        "alarmName",
        "resourceArn",
        "timestamp",
        "alarmState",
        "metricName",
        "namespace",
    ]

    for field in required_fields:
        assert field in incident_event, f"Required field '{field}' is missing from incident event"
        assert incident_event[field] is not None, f"Required field '{field}' must not be None"
        assert incident_event[field] != "", f"Required field '{field}' must not be empty string"

    # Property 2: incidentId must be a valid UUID v4
    incident_id = incident_event["incidentId"]
    try:
        parsed_uuid = uuid.UUID(incident_id, version=4)
        assert str(parsed_uuid) == incident_id, f"incidentId should be a valid UUID v4 string"
    except (ValueError, AttributeError):
        raise AssertionError(f"incidentId '{incident_id}' is not a valid UUID v4")

    # Property 3: alarmName must match the input
    assert (
        incident_event["alarmName"] == alarm_event["detail"]["alarmName"]
    ), f"alarmName should match the input alarm event"

    # Property 4: timestamp must be present and valid ISO-8601
    timestamp = incident_event["timestamp"]
    try:
        # Parse ISO-8601 timestamp
        if timestamp.endswith("Z"):
            datetime.fromisoformat(timestamp[:-1])
        else:
            datetime.fromisoformat(timestamp)
    except (ValueError, AttributeError):
        raise AssertionError(f"timestamp '{timestamp}' is not a valid ISO-8601 format")

    # Property 5: alarmState must be a valid state
    valid_states = ["ALARM", "OK", "INSUFFICIENT_DATA"]
    assert (
        incident_event["alarmState"] in valid_states
    ), f"alarmState must be one of {valid_states}, got '{incident_event['alarmState']}'"

    # Property 6: resourceArn must be a valid ARN format
    resource_arn = incident_event["resourceArn"]
    assert resource_arn.startswith(
        "arn:aws:"
    ), f"resourceArn should start with 'arn:aws:', got '{resource_arn}'"

    # Property 7: metricName must match the input
    expected_metric_name = alarm_event["detail"]["configuration"]["metricName"]
    assert incident_event["metricName"] == expected_metric_name, (
        f"metricName should match the input, expected '{expected_metric_name}', "
        f"got '{incident_event['metricName']}'"
    )

    # Property 8: namespace must match the input
    expected_namespace = alarm_event["detail"]["configuration"]["namespace"]
    assert incident_event["namespace"] == expected_namespace, (
        f"namespace should match the input, expected '{expected_namespace}', "
        f"got '{incident_event['namespace']}'"
    )


@given(cloudwatch_alarm_event_strategy())
def test_event_routing_completeness_optional_fields(alarm_event):
    """
    Property: Event Routing Handles Optional Fields

    **Validates: Requirements 1.1, 1.2, 1.3**

    For any CloudWatch Alarm event, optional fields (like alarmDescription)
    should be included if present, or set to None if absent.
    """
    incident_event = transform_alarm_event(alarm_event)

    # Optional field: alarmDescription
    if "alarmDescription" in incident_event:
        # If present, it should match the input or be None
        input_description = alarm_event["detail"].get("alarmDescription", "")
        if input_description:
            assert (
                incident_event["alarmDescription"] == input_description
            ), "alarmDescription should match input when present"
        else:
            assert (
                incident_event["alarmDescription"] is None
            ), "alarmDescription should be None when not present in input"


@given(cloudwatch_alarm_event_strategy())
def test_event_routing_completeness_ttl_field(alarm_event):
    """
    Property: Event Routing Includes TTL Field

    **Validates: Requirements 1.1, 1.2, 1.3, 9.4**

    For any CloudWatch Alarm event, the incident event must include a TTL
    field that is a Unix timestamp representing 90 days from the incident time.
    """
    incident_event = transform_alarm_event(alarm_event)

    # Property 1: TTL field must be present
    assert "ttl" in incident_event, "TTL field must be present in incident event"

    # Property 2: TTL must be an integer
    ttl = incident_event["ttl"]
    assert isinstance(ttl, int), f"TTL must be an integer, got {type(ttl)}"

    # Property 3: TTL must be positive
    assert ttl > 0, f"TTL must be positive, got {ttl}"

    # Property 4: TTL should be approximately 90 days (7,776,000 seconds) from incident time
    # Parse incident timestamp
    timestamp_str = incident_event["timestamp"]
    if timestamp_str.endswith("Z"):
        incident_dt = datetime.fromisoformat(timestamp_str[:-1])
    else:
        incident_dt = datetime.fromisoformat(timestamp_str)

    incident_unix = int(incident_dt.timestamp())
    expected_ttl = incident_unix + 7776000  # 90 days in seconds

    # Allow small variance due to calculation differences
    ttl_difference = abs(ttl - expected_ttl)
    assert ttl_difference <= 1, (
        f"TTL should be approximately 90 days from incident time. "
        f"Expected: {expected_ttl}, Got: {ttl}, Difference: {ttl_difference}"
    )


@given(cloudwatch_alarm_event_strategy())
def test_event_routing_completeness_alarm_arn_field(alarm_event):
    """
    Property: Event Routing Includes Alarm ARN

    **Validates: Requirements 1.1, 1.2, 1.3**

    For any CloudWatch Alarm event, the incident event must include the
    alarm ARN field.
    """
    incident_event = transform_alarm_event(alarm_event)

    # Property 1: alarmArn field must be present
    assert "alarmArn" in incident_event, "alarmArn field must be present in incident event"

    # Property 2: alarmArn must match the input
    expected_alarm_arn = alarm_event["detail"]["alarmArn"]
    assert incident_event["alarmArn"] == expected_alarm_arn, (
        f"alarmArn should match input. Expected: {expected_alarm_arn}, "
        f"Got: {incident_event['alarmArn']}"
    )


@given(cloudwatch_alarm_event_strategy(), cloudwatch_alarm_event_strategy())
def test_event_routing_unique_incident_ids(alarm_event_1, alarm_event_2):
    """
    Property: Event Routing Generates Unique Incident IDs

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

    For any two alarm events (even if identical), the resulting incident
    events must have unique incident IDs.
    """
    # Transform both events
    incident_event_1 = transform_alarm_event(alarm_event_1)
    incident_event_2 = transform_alarm_event(alarm_event_2)

    # Property: Incident IDs must be unique
    assert (
        incident_event_1["incidentId"] != incident_event_2["incidentId"]
    ), "Each alarm event must generate a unique incident ID"


@given(cloudwatch_alarm_event_strategy())
def test_event_routing_idempotent_except_incident_id(alarm_event):
    """
    Property: Event Routing is Idempotent (Except Incident ID)

    **Validates: Requirements 1.1, 1.2, 1.3**

    For any alarm event, transforming it multiple times should produce
    the same field values except for the incident ID (which must be unique).
    """
    # Transform the same event twice
    incident_event_1 = transform_alarm_event(alarm_event)
    incident_event_2 = transform_alarm_event(alarm_event)

    # All fields except incidentId should be identical
    for field in incident_event_1:
        if field == "incidentId":
            # Incident IDs must be different
            assert (
                incident_event_1["incidentId"] != incident_event_2["incidentId"]
            ), "Incident IDs must be unique across transformations"
        else:
            # All other fields should be identical
            assert incident_event_1[field] == incident_event_2[field], (
                f"Field '{field}' should be identical across transformations. "
                f"First: {incident_event_1[field]}, Second: {incident_event_2[field]}"
            )
