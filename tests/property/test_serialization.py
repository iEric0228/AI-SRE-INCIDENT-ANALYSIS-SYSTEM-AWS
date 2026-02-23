"""
Property-based tests for data model serialization.

This module tests the serialization round-trip property: for any data model instance,
serializing to dict then deserializing must produce an equivalent object.

Validates Requirements 6.1, 9.2
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from shared.models import (
    IncidentEvent,
    MetricDatapoint,
    MetricStatistics,
    MetricData,
    MetricsCollectorOutput,
    LogEntry,
    LogsCollectorOutput,
    ChangeEvent,
    DeployContextCollectorOutput,
    ResourceInfo,
    AlarmInfo,
    CompletenessInfo,
    StructuredContext,
    AnalysisMetadata,
    Analysis,
    AnalysisReport,
    NotificationDeliveryStatus,
    NotificationOutput,
    IncidentRecord,
)

# Strategy generators for data models


@composite
def datetime_strategy(draw):
    """Generate datetime objects with timezone info."""
    # Generate datetime in a reasonable range (2020-2030)
    timestamp = draw(st.integers(min_value=1577836800, max_value=1893456000))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


@composite
def incident_event_strategy(draw):
    """Generate arbitrary IncidentEvent instances."""
    return IncidentEvent(
        incident_id=draw(st.uuids()).hex,
        alarm_name=draw(st.text(min_size=1, max_size=100)),
        alarm_arn=f"arn:aws:cloudwatch:us-east-1:123456789012:alarm:{draw(st.text(min_size=1, max_size=50))}",
        resource_arn=f"arn:aws:ec2:us-east-1:123456789012:instance/{draw(st.text(min_size=1, max_size=50))}",
        timestamp=draw(datetime_strategy()),
        alarm_state=draw(st.sampled_from(["ALARM", "OK", "INSUFFICIENT_DATA"])),
        metric_name=draw(st.text(min_size=1, max_size=50)),
        namespace=draw(st.text(min_size=1, max_size=50)),
        alarm_description=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


@composite
def metric_datapoint_strategy(draw):
    """Generate arbitrary MetricDatapoint instances."""
    return MetricDatapoint(
        timestamp=draw(datetime_strategy()),
        value=draw(
            st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
        ),
        unit=draw(st.sampled_from(["Percent", "Count", "Bytes", "Seconds"])),
    )


@composite
def metric_statistics_strategy(draw):
    """Generate arbitrary MetricStatistics instances."""
    min_val = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    max_val = draw(
        st.floats(min_value=min_val, max_value=1000.0, allow_nan=False, allow_infinity=False)
    )
    avg_val = draw(
        st.floats(min_value=min_val, max_value=max_val, allow_nan=False, allow_infinity=False)
    )

    return MetricStatistics(
        avg=avg_val,
        max=max_val,
        min=min_val,
        p95=draw(
            st.one_of(
                st.none(),
                st.floats(
                    min_value=min_val, max_value=max_val, allow_nan=False, allow_infinity=False
                ),
            )
        ),
    )


@composite
def metric_data_strategy(draw):
    """Generate arbitrary MetricData instances."""
    return MetricData(
        metric_name=draw(st.text(min_size=1, max_size=50)),
        namespace=draw(st.text(min_size=1, max_size=50)),
        datapoints=draw(st.lists(metric_datapoint_strategy(), max_size=10)),
        statistics=draw(metric_statistics_strategy()),
    )


@composite
def metrics_collector_output_strategy(draw):
    """Generate arbitrary MetricsCollectorOutput instances."""
    return MetricsCollectorOutput(
        status=draw(st.sampled_from(["success", "partial", "failed"])),
        metrics=draw(st.lists(metric_data_strategy(), max_size=5)),
        collection_duration=draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        error=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


@composite
def log_entry_strategy(draw):
    """Generate arbitrary LogEntry instances."""
    return LogEntry(
        timestamp=draw(datetime_strategy()),
        log_level=draw(st.sampled_from(["ERROR", "WARN", "CRITICAL", "INFO"])),
        message=draw(st.text(min_size=1, max_size=500)),
        log_stream=draw(st.text(min_size=1, max_size=100)),
    )


@composite
def logs_collector_output_strategy(draw):
    """Generate arbitrary LogsCollectorOutput instances."""
    returned = draw(st.integers(min_value=0, max_value=100))
    total_matches = draw(st.integers(min_value=returned, max_value=1000))

    return LogsCollectorOutput(
        status=draw(st.sampled_from(["success", "partial", "failed"])),
        logs=draw(st.lists(log_entry_strategy(), min_size=0, max_size=returned)),
        total_matches=total_matches,
        returned=returned,
        collection_duration=draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        error=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


@composite
def change_event_strategy(draw):
    """Generate arbitrary ChangeEvent instances."""
    return ChangeEvent(
        timestamp=draw(datetime_strategy()),
        change_type=draw(st.sampled_from(["deployment", "configuration", "infrastructure"])),
        event_name=draw(st.text(min_size=1, max_size=100)),
        user=f"arn:aws:iam::123456789012:user/{draw(st.text(min_size=1, max_size=50))}",
        description=draw(st.text(min_size=1, max_size=200)),
    )


@composite
def deploy_context_collector_output_strategy(draw):
    """Generate arbitrary DeployContextCollectorOutput instances."""
    return DeployContextCollectorOutput(
        status=draw(st.sampled_from(["success", "partial", "failed"])),
        changes=draw(st.lists(change_event_strategy(), max_size=10)),
        collection_duration=draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        error=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


@composite
def resource_info_strategy(draw):
    """Generate arbitrary ResourceInfo instances."""
    resource_type = draw(st.sampled_from(["lambda", "ec2", "rds", "ecs"]))
    return ResourceInfo(
        arn=f"arn:aws:{resource_type}:us-east-1:123456789012:resource/{draw(st.text(min_size=1, max_size=50))}",
        type=resource_type,
        name=draw(st.text(min_size=1, max_size=100)),
    )


@composite
def alarm_info_strategy(draw):
    """Generate arbitrary AlarmInfo instances."""
    return AlarmInfo(
        name=draw(st.text(min_size=1, max_size=100)),
        metric=draw(st.text(min_size=1, max_size=50)),
        threshold=draw(
            st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
        ),
    )


@composite
def completeness_info_strategy(draw):
    """Generate arbitrary CompletenessInfo instances."""
    return CompletenessInfo(
        metrics=draw(st.booleans()),
        logs=draw(st.booleans()),
        changes=draw(st.booleans()),
    )


@composite
def structured_context_strategy(draw):
    """Generate arbitrary StructuredContext instances."""
    return StructuredContext(
        incident_id=draw(st.uuids()).hex,
        timestamp=draw(datetime_strategy()),
        resource=draw(resource_info_strategy()),
        alarm=draw(alarm_info_strategy()),
        metrics=draw(
            st.dictionaries(
                st.text(min_size=1, max_size=20),
                st.floats(allow_nan=False, allow_infinity=False),
                max_size=5,
            )
        ),
        logs=draw(st.dictionaries(st.text(min_size=1, max_size=20), st.integers(), max_size=5)),
        changes=draw(
            st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=5)
        ),
        completeness=draw(completeness_info_strategy()),
    )


@composite
def analysis_metadata_strategy(draw):
    """Generate arbitrary AnalysisMetadata instances."""
    return AnalysisMetadata(
        model_id=draw(st.text(min_size=1, max_size=100)),
        model_version=draw(st.text(min_size=1, max_size=20)),
        prompt_version=draw(st.text(min_size=1, max_size=20)),
        token_usage={
            "input": draw(st.integers(min_value=0, max_value=10000)),
            "output": draw(st.integers(min_value=0, max_value=5000)),
        },
        latency=draw(
            st.floats(min_value=0.1, max_value=60.0, allow_nan=False, allow_infinity=False)
        ),
    )


@composite
def analysis_strategy(draw):
    """Generate arbitrary Analysis instances."""
    return Analysis(
        root_cause_hypothesis=draw(st.text(min_size=1, max_size=500)),
        confidence=draw(st.sampled_from(["high", "medium", "low", "none"])),
        evidence=draw(st.lists(st.text(min_size=1, max_size=200), max_size=10)),
        contributing_factors=draw(st.lists(st.text(min_size=1, max_size=200), max_size=10)),
        recommended_actions=draw(st.lists(st.text(min_size=1, max_size=200), max_size=10)),
    )


@composite
def analysis_report_strategy(draw):
    """Generate arbitrary AnalysisReport instances."""
    return AnalysisReport(
        incident_id=draw(st.uuids()).hex,
        timestamp=draw(datetime_strategy()),
        analysis=draw(analysis_strategy()),
        metadata=draw(analysis_metadata_strategy()),
    )


@composite
def notification_delivery_status_strategy(draw):
    """Generate arbitrary NotificationDeliveryStatus instances."""
    return NotificationDeliveryStatus(
        slack=draw(st.sampled_from(["delivered", "failed", "skipped"])),
        email=draw(st.sampled_from(["delivered", "failed", "skipped"])),
        slack_error=draw(st.one_of(st.none(), st.text(max_size=200))),
        email_error=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


@composite
def notification_output_strategy(draw):
    """Generate arbitrary NotificationOutput instances."""
    return NotificationOutput(
        status=draw(st.sampled_from(["success", "partial", "failed"])),
        delivery_status=draw(notification_delivery_status_strategy()),
        notification_duration=draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
    )


@composite
def incident_record_strategy(draw):
    """Generate arbitrary IncidentRecord instances."""
    return IncidentRecord(
        incident_id=draw(st.uuids()).hex,
        timestamp=draw(datetime_strategy()).isoformat(),
        resource_arn=f"arn:aws:ec2:us-east-1:123456789012:instance/{draw(st.text(min_size=1, max_size=50))}",
        resource_type=draw(st.sampled_from(["lambda", "ec2", "rds", "ecs"])),
        alarm_name=draw(st.text(min_size=1, max_size=100)),
        severity=draw(st.sampled_from(["critical", "high", "medium", "low"])),
        structured_context=draw(
            st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=5)
        ),
        analysis_report=draw(
            st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=5)
        ),
        notification_status=draw(
            st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=5)
        ),
        ttl=draw(st.integers(min_value=1577836800, max_value=1893456000)),
    )


# Property Tests


@given(incident_event_strategy())
def test_incident_event_serialization_round_trip(incident_event):
    """
    Property: Serialization Round Trip for IncidentEvent

    For any IncidentEvent instance, serializing to dict then deserializing
    must produce an equivalent object.

    Validates: Requirements 6.1, 9.2
    """
    # Serialize to dict
    serialized = incident_event.to_dict()

    # Deserialize back to object
    deserialized = IncidentEvent.from_dict(serialized)

    # Verify equivalence
    assert deserialized.incident_id == incident_event.incident_id
    assert deserialized.alarm_name == incident_event.alarm_name
    assert deserialized.alarm_arn == incident_event.alarm_arn
    assert deserialized.resource_arn == incident_event.resource_arn
    assert deserialized.alarm_state == incident_event.alarm_state
    assert deserialized.metric_name == incident_event.metric_name
    assert deserialized.namespace == incident_event.namespace
    assert deserialized.alarm_description == incident_event.alarm_description

    # Timestamps should be equivalent (allowing for timezone differences)
    assert abs((deserialized.timestamp - incident_event.timestamp).total_seconds()) < 1


@given(metric_datapoint_strategy())
def test_metric_datapoint_serialization_round_trip(datapoint):
    """
    Property: Serialization Round Trip for MetricDatapoint

    Validates: Requirements 6.1, 9.2
    """
    serialized = datapoint.to_dict()
    deserialized = MetricDatapoint.from_dict(serialized)

    assert abs((deserialized.timestamp - datapoint.timestamp).total_seconds()) < 1
    assert abs(deserialized.value - datapoint.value) < 0.001
    assert deserialized.unit == datapoint.unit


@given(metric_statistics_strategy())
def test_metric_statistics_serialization_round_trip(stats):
    """
    Property: Serialization Round Trip for MetricStatistics

    Validates: Requirements 6.1, 9.2
    """
    serialized = stats.to_dict()
    deserialized = MetricStatistics.from_dict(serialized)

    assert abs(deserialized.avg - stats.avg) < 0.001
    assert abs(deserialized.max - stats.max) < 0.001
    assert abs(deserialized.min - stats.min) < 0.001

    if stats.p95 is not None:
        assert deserialized.p95 is not None
        assert abs(deserialized.p95 - stats.p95) < 0.001
    else:
        assert deserialized.p95 is None


@given(metric_data_strategy())
def test_metric_data_serialization_round_trip(metric_data):
    """
    Property: Serialization Round Trip for MetricData

    Validates: Requirements 6.1, 9.2
    """
    serialized = metric_data.to_dict()
    deserialized = MetricData.from_dict(serialized)

    assert deserialized.metric_name == metric_data.metric_name
    assert deserialized.namespace == metric_data.namespace
    assert len(deserialized.datapoints) == len(metric_data.datapoints)
    assert abs(deserialized.statistics.avg - metric_data.statistics.avg) < 0.001


@given(metrics_collector_output_strategy())
def test_metrics_collector_output_serialization_round_trip(output):
    """
    Property: Serialization Round Trip for MetricsCollectorOutput

    Validates: Requirements 6.1, 9.2
    """
    serialized = output.to_dict()
    deserialized = MetricsCollectorOutput.from_dict(serialized)

    assert deserialized.status == output.status
    assert len(deserialized.metrics) == len(output.metrics)
    assert abs(deserialized.collection_duration - output.collection_duration) < 0.001
    assert deserialized.error == output.error


@given(log_entry_strategy())
def test_log_entry_serialization_round_trip(log_entry):
    """
    Property: Serialization Round Trip for LogEntry

    Validates: Requirements 6.1, 9.2
    """
    serialized = log_entry.to_dict()
    deserialized = LogEntry.from_dict(serialized)

    assert abs((deserialized.timestamp - log_entry.timestamp).total_seconds()) < 1
    assert deserialized.log_level == log_entry.log_level
    assert deserialized.message == log_entry.message
    assert deserialized.log_stream == log_entry.log_stream


@given(logs_collector_output_strategy())
def test_logs_collector_output_serialization_round_trip(output):
    """
    Property: Serialization Round Trip for LogsCollectorOutput

    Validates: Requirements 6.1, 9.2
    """
    serialized = output.to_dict()
    deserialized = LogsCollectorOutput.from_dict(serialized)

    assert deserialized.status == output.status
    assert len(deserialized.logs) == len(output.logs)
    assert deserialized.total_matches == output.total_matches
    assert deserialized.returned == output.returned
    assert abs(deserialized.collection_duration - output.collection_duration) < 0.001
    assert deserialized.error == output.error


@given(change_event_strategy())
def test_change_event_serialization_round_trip(change_event):
    """
    Property: Serialization Round Trip for ChangeEvent

    Validates: Requirements 6.1, 9.2
    """
    serialized = change_event.to_dict()
    deserialized = ChangeEvent.from_dict(serialized)

    assert abs((deserialized.timestamp - change_event.timestamp).total_seconds()) < 1
    assert deserialized.change_type == change_event.change_type
    assert deserialized.event_name == change_event.event_name
    assert deserialized.user == change_event.user
    assert deserialized.description == change_event.description


@given(deploy_context_collector_output_strategy())
def test_deploy_context_collector_output_serialization_round_trip(output):
    """
    Property: Serialization Round Trip for DeployContextCollectorOutput

    Validates: Requirements 6.1, 9.2
    """
    serialized = output.to_dict()
    deserialized = DeployContextCollectorOutput.from_dict(serialized)

    assert deserialized.status == output.status
    assert len(deserialized.changes) == len(output.changes)
    assert abs(deserialized.collection_duration - output.collection_duration) < 0.001
    assert deserialized.error == output.error


@given(resource_info_strategy())
def test_resource_info_serialization_round_trip(resource_info):
    """
    Property: Serialization Round Trip for ResourceInfo

    Validates: Requirements 6.1, 9.2
    """
    serialized = resource_info.to_dict()
    deserialized = ResourceInfo.from_dict(serialized)

    assert deserialized.arn == resource_info.arn
    assert deserialized.type == resource_info.type
    assert deserialized.name == resource_info.name


@given(alarm_info_strategy())
def test_alarm_info_serialization_round_trip(alarm_info):
    """
    Property: Serialization Round Trip for AlarmInfo

    Validates: Requirements 6.1, 9.2
    """
    serialized = alarm_info.to_dict()
    deserialized = AlarmInfo.from_dict(serialized)

    assert deserialized.name == alarm_info.name
    assert deserialized.metric == alarm_info.metric
    assert abs(deserialized.threshold - alarm_info.threshold) < 0.001


@given(completeness_info_strategy())
def test_completeness_info_serialization_round_trip(completeness_info):
    """
    Property: Serialization Round Trip for CompletenessInfo

    Validates: Requirements 6.1, 9.2
    """
    serialized = completeness_info.to_dict()
    deserialized = CompletenessInfo.from_dict(serialized)

    assert deserialized.metrics == completeness_info.metrics
    assert deserialized.logs == completeness_info.logs
    assert deserialized.changes == completeness_info.changes


@given(structured_context_strategy())
def test_structured_context_serialization_round_trip(context):
    """
    Property: Serialization Round Trip for StructuredContext

    Validates: Requirements 6.1, 9.2
    """
    serialized = context.to_dict()
    deserialized = StructuredContext.from_dict(serialized)

    assert deserialized.incident_id == context.incident_id
    assert abs((deserialized.timestamp - context.timestamp).total_seconds()) < 1
    assert deserialized.resource.arn == context.resource.arn
    assert deserialized.alarm.name == context.alarm.name
    assert deserialized.completeness.metrics == context.completeness.metrics


@given(analysis_metadata_strategy())
def test_analysis_metadata_serialization_round_trip(metadata):
    """
    Property: Serialization Round Trip for AnalysisMetadata

    Validates: Requirements 6.1, 9.2
    """
    serialized = metadata.to_dict()
    deserialized = AnalysisMetadata.from_dict(serialized)

    assert deserialized.model_id == metadata.model_id
    assert deserialized.model_version == metadata.model_version
    assert deserialized.prompt_version == metadata.prompt_version
    assert deserialized.token_usage == metadata.token_usage
    assert abs(deserialized.latency - metadata.latency) < 0.001


@given(analysis_strategy())
def test_analysis_serialization_round_trip(analysis):
    """
    Property: Serialization Round Trip for Analysis

    Validates: Requirements 6.1, 9.2
    """
    serialized = analysis.to_dict()
    deserialized = Analysis.from_dict(serialized)

    assert deserialized.root_cause_hypothesis == analysis.root_cause_hypothesis
    assert deserialized.confidence == analysis.confidence
    assert deserialized.evidence == analysis.evidence
    assert deserialized.contributing_factors == analysis.contributing_factors
    assert deserialized.recommended_actions == analysis.recommended_actions


@given(analysis_report_strategy())
def test_analysis_report_serialization_round_trip(report):
    """
    Property: Serialization Round Trip for AnalysisReport

    Validates: Requirements 6.1, 9.2
    """
    serialized = report.to_dict()
    deserialized = AnalysisReport.from_dict(serialized)

    assert deserialized.incident_id == report.incident_id
    assert abs((deserialized.timestamp - report.timestamp).total_seconds()) < 1
    assert deserialized.analysis.confidence == report.analysis.confidence
    assert deserialized.metadata.model_id == report.metadata.model_id


@given(notification_delivery_status_strategy())
def test_notification_delivery_status_serialization_round_trip(status):
    """
    Property: Serialization Round Trip for NotificationDeliveryStatus

    Validates: Requirements 6.1, 9.2
    """
    serialized = status.to_dict()
    deserialized = NotificationDeliveryStatus.from_dict(serialized)

    assert deserialized.slack == status.slack
    assert deserialized.email == status.email
    assert deserialized.slack_error == status.slack_error
    assert deserialized.email_error == status.email_error


@given(notification_output_strategy())
def test_notification_output_serialization_round_trip(output):
    """
    Property: Serialization Round Trip for NotificationOutput

    Validates: Requirements 6.1, 9.2
    """
    serialized = output.to_dict()
    deserialized = NotificationOutput.from_dict(serialized)

    assert deserialized.status == output.status
    assert deserialized.delivery_status.slack == output.delivery_status.slack
    assert abs(deserialized.notification_duration - output.notification_duration) < 0.001


@given(incident_record_strategy())
def test_incident_record_serialization_round_trip(record):
    """
    Property: Serialization Round Trip for IncidentRecord

    Validates: Requirements 6.1, 9.2
    """
    serialized = record.to_dict()
    deserialized = IncidentRecord.from_dict(serialized)

    assert deserialized.incident_id == record.incident_id
    assert deserialized.timestamp == record.timestamp
    assert deserialized.resource_arn == record.resource_arn
    assert deserialized.resource_type == record.resource_type
    assert deserialized.alarm_name == record.alarm_name
    assert deserialized.severity == record.severity
    assert deserialized.ttl == record.ttl
