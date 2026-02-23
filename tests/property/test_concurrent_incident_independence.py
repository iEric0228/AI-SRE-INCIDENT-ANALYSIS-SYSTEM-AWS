"""
Property-based tests for concurrent incident independence.

This module tests the concurrent incident independence property: for any set
of simultaneous alarms, each must have unique incident IDs. This ensures that
concurrent incidents are processed independently without ID collisions.

Validates Requirement 1.4
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st
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


@composite
def simultaneous_alarm_events_strategy(draw):
    """
    Generate a list of simultaneous alarm events.

    Generates 2-10 alarm events that occur at the same timestamp,
    simulating concurrent alarm firings.
    """
    # Generate number of simultaneous alarms (2-10)
    num_alarms = draw(st.integers(min_value=2, max_value=10))

    # Generate a common timestamp for all alarms
    timestamp_int = draw(st.integers(min_value=1577836800, max_value=1924905600))
    common_timestamp = (
        datetime.fromtimestamp(timestamp_int, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )

    # Generate multiple alarm events with the same timestamp
    alarm_events = []
    for _ in range(num_alarms):
        # Generate alarm name (required)
        alarm_name = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-_", min_size=5, max_size=50))

        # Generate alarm state (required)
        alarm_state = draw(alarm_state_strategy())

        # Generate AWS account and region
        account = draw(st.text(alphabet="0123456789", min_size=12, max_size=12))
        region = draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]))

        # Generate alarm ARN
        alarm_arn = f"arn:aws:cloudwatch:{region}:{account}:alarm:{alarm_name}"

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

        # Construct CloudWatch Alarm event with common timestamp
        event = {
            "version": "0",
            "id": str(uuid.uuid4()),
            "detail-type": "CloudWatch Alarm State Change",
            "source": "aws.cloudwatch",
            "account": account,
            "time": common_timestamp,  # Use common timestamp
            "region": region,
            "resources": [alarm_arn],
            "detail": {
                "alarmName": alarm_name,
                "alarmArn": alarm_arn,
                "state": {
                    "value": alarm_state,
                    "reason": f"Threshold Crossed: 1 datapoint was greater than the threshold",
                    "timestamp": common_timestamp,
                },
                "previousState": {"value": "OK", "timestamp": common_timestamp},
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

        alarm_events.append(event)

    return alarm_events


# Property Tests


@given(simultaneous_alarm_events_strategy())
def test_concurrent_incident_independence_unique_ids(simultaneous_alarms):
    """
    Property 2: Concurrent Incident Independence

    **Validates: Requirement 1.4**

    For any set of simultaneous alarms (alarms that fire at the same timestamp),
    each must be assigned a unique incident ID. This ensures that concurrent
    incidents are processed independently without ID collisions.

    This property is critical for:
    1. Preventing incident data from being overwritten in storage
    2. Ensuring each incident can be tracked independently
    3. Maintaining data integrity in concurrent processing scenarios
    """
    # Transform all simultaneous alarm events
    incident_events = [transform_alarm_event(alarm) for alarm in simultaneous_alarms]

    # Extract all incident IDs
    incident_ids = [event["incidentId"] for event in incident_events]

    # Property 1: All incident IDs must be unique
    unique_ids = set(incident_ids)
    assert len(unique_ids) == len(incident_ids), (
        f"All incident IDs must be unique. Generated {len(incident_ids)} incidents "
        f"but only {len(unique_ids)} unique IDs. Duplicate IDs detected."
    )

    # Property 2: Each incident ID must be a valid UUID v4
    for incident_id in incident_ids:
        try:
            parsed_uuid = uuid.UUID(incident_id, version=4)
            assert str(parsed_uuid) == incident_id, f"Incident ID should be a valid UUID v4 string"
        except (ValueError, AttributeError):
            raise AssertionError(f"Incident ID '{incident_id}' is not a valid UUID v4")

    # Property 3: Verify all incidents have the same timestamp (simultaneous)
    timestamps = [event["timestamp"] for event in incident_events]
    unique_timestamps = set(timestamps)
    assert len(unique_timestamps) == 1, (
        f"All simultaneous alarms should have the same timestamp. "
        f"Found {len(unique_timestamps)} different timestamps: {unique_timestamps}"
    )


@given(st.lists(cloudwatch_alarm_event_strategy(), min_size=2, max_size=20))
def test_concurrent_incident_independence_any_alarms(alarm_events):
    """
    Property: Concurrent Incident Independence (General Case)

    **Validates: Requirement 1.4**

    For any list of alarm events (whether simultaneous or not), each must
    be assigned a unique incident ID. This is a more general test that doesn't
    require alarms to be simultaneous.
    """
    # Transform all alarm events
    incident_events = [transform_alarm_event(alarm) for alarm in alarm_events]

    # Extract all incident IDs
    incident_ids = [event["incidentId"] for event in incident_events]

    # Property: All incident IDs must be unique
    unique_ids = set(incident_ids)
    assert len(unique_ids) == len(incident_ids), (
        f"All incident IDs must be unique across {len(incident_ids)} incidents. "
        f"Found {len(incident_ids) - len(unique_ids)} duplicate(s)."
    )


@given(cloudwatch_alarm_event_strategy())
def test_concurrent_incident_independence_same_alarm_multiple_times(alarm_event):
    """
    Property: Concurrent Incident Independence (Same Alarm)

    **Validates: Requirement 1.4**

    Even when the same alarm fires multiple times (identical alarm events),
    each occurrence must be assigned a unique incident ID. This ensures that
    repeated alarms are tracked as separate incidents.
    """
    # Transform the same alarm event multiple times (simulating repeated firings)
    num_repetitions = 5
    incident_events = [transform_alarm_event(alarm_event) for _ in range(num_repetitions)]

    # Extract all incident IDs
    incident_ids = [event["incidentId"] for event in incident_events]

    # Property 1: All incident IDs must be unique
    unique_ids = set(incident_ids)
    assert len(unique_ids) == num_repetitions, (
        f"Same alarm fired {num_repetitions} times should generate {num_repetitions} "
        f"unique incident IDs, but only {len(unique_ids)} unique IDs were generated."
    )

    # Property 2: All other fields should be identical (except incidentId)
    for i in range(1, num_repetitions):
        for field in incident_events[0]:
            if field == "incidentId":
                # Incident IDs must be different
                assert (
                    incident_events[0]["incidentId"] != incident_events[i]["incidentId"]
                ), f"Incident IDs must be unique across repeated alarm firings"
            else:
                # All other fields should be identical
                assert incident_events[0][field] == incident_events[i][field], (
                    f"Field '{field}' should be identical across repeated alarm firings. "
                    f"First: {incident_events[0][field]}, Repetition {i}: {incident_events[i][field]}"
                )


@given(simultaneous_alarm_events_strategy())
def test_concurrent_incident_independence_no_id_collisions(simultaneous_alarms):
    """
    Property: Concurrent Incident Independence (No Collisions)

    **Validates: Requirement 1.4**

    For any set of simultaneous alarms, the probability of incident ID
    collisions should be negligible (UUID v4 collision probability is
    approximately 1 in 2^122). This test verifies that the ID generation
    mechanism produces cryptographically random UUIDs.
    """
    # Transform all simultaneous alarm events
    incident_events = [transform_alarm_event(alarm) for alarm in simultaneous_alarms]

    # Extract all incident IDs
    incident_ids = [event["incidentId"] for event in incident_events]

    # Property 1: No duplicate IDs
    assert len(incident_ids) == len(
        set(incident_ids)
    ), "Incident ID collision detected. UUID v4 should have negligible collision probability."

    # Property 2: All IDs should be valid UUID v4 format
    for incident_id in incident_ids:
        try:
            parsed_uuid = uuid.UUID(incident_id, version=4)
            # Verify it's actually version 4
            assert (
                parsed_uuid.version == 4
            ), f"Incident ID should be UUID version 4, got version {parsed_uuid.version}"
        except (ValueError, AttributeError) as e:
            raise AssertionError(f"Invalid UUID v4: {incident_id}, error: {e}")

    # Property 3: IDs should have sufficient entropy (not sequential or predictable)
    # Check that IDs are not sequential by comparing adjacent IDs
    if len(incident_ids) >= 2:
        for i in range(len(incident_ids) - 1):
            uuid1 = uuid.UUID(incident_ids[i])
            uuid2 = uuid.UUID(incident_ids[i + 1])

            # Convert to integers and check they're not sequential
            int1 = uuid1.int
            int2 = uuid2.int

            # UUIDs should not be sequential (difference should be large)
            difference = abs(int1 - int2)
            assert difference > 1000, (
                f"Incident IDs appear to be sequential or predictable. "
                f"Difference between adjacent IDs: {difference}"
            )
