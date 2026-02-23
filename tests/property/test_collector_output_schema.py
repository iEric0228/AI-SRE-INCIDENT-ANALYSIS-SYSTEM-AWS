"""
Property-based tests for collector output schema compliance.

This module tests that collector outputs conform to the required schema:
- status field (string)
- metrics/logs/changes array (list)
- collection_duration field (float)

Validates Requirements 3.3
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from shared.models import (
    MetricsCollectorOutput,
    LogsCollectorOutput,
    DeployContextCollectorOutput,
)

# Strategy generators for collector outputs


@composite
def metrics_collector_output_strategy(draw):
    """Generate arbitrary MetricsCollectorOutput instances."""
    from shared.models import MetricData, MetricDatapoint, MetricStatistics

    # Generate metrics
    metrics = []
    num_metrics = draw(st.integers(min_value=0, max_value=5))
    for _ in range(num_metrics):
        datapoints = []
        num_datapoints = draw(st.integers(min_value=0, max_value=10))
        for _ in range(num_datapoints):
            datapoints.append(
                MetricDatapoint(
                    timestamp=datetime.fromtimestamp(
                        draw(st.integers(min_value=1577836800, max_value=1893456000)),
                        tz=timezone.utc,
                    ),
                    value=draw(
                        st.floats(
                            min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False
                        )
                    ),
                    unit=draw(st.sampled_from(["Percent", "Count", "Bytes", "Seconds"])),
                )
            )

        min_val = draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        )
        max_val = draw(
            st.floats(min_value=min_val, max_value=1000.0, allow_nan=False, allow_infinity=False)
        )
        avg_val = draw(
            st.floats(min_value=min_val, max_value=max_val, allow_nan=False, allow_infinity=False)
        )

        statistics = MetricStatistics(
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

        metrics.append(
            MetricData(
                metric_name=draw(st.text(min_size=1, max_size=50)),
                namespace=draw(st.text(min_size=1, max_size=50)),
                datapoints=datapoints,
                statistics=statistics,
            )
        )

    return MetricsCollectorOutput(
        status=draw(st.sampled_from(["success", "partial", "failed"])),
        metrics=metrics,
        collection_duration=draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        error=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


@composite
def logs_collector_output_strategy(draw):
    """Generate arbitrary LogsCollectorOutput instances."""
    from shared.models import LogEntry

    returned = draw(st.integers(min_value=0, max_value=100))
    total_matches = draw(st.integers(min_value=returned, max_value=1000))

    logs = []
    for _ in range(returned):
        logs.append(
            LogEntry(
                timestamp=datetime.fromtimestamp(
                    draw(st.integers(min_value=1577836800, max_value=1893456000)), tz=timezone.utc
                ),
                log_level=draw(st.sampled_from(["ERROR", "WARN", "CRITICAL", "INFO"])),
                message=draw(st.text(min_size=1, max_size=500)),
                log_stream=draw(st.text(min_size=1, max_size=100)),
            )
        )

    return LogsCollectorOutput(
        status=draw(st.sampled_from(["success", "partial", "failed"])),
        logs=logs,
        total_matches=total_matches,
        returned=returned,
        collection_duration=draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        error=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


@composite
def deploy_context_collector_output_strategy(draw):
    """Generate arbitrary DeployContextCollectorOutput instances."""
    from shared.models import ChangeEvent

    changes = []
    num_changes = draw(st.integers(min_value=0, max_value=10))
    for _ in range(num_changes):
        changes.append(
            ChangeEvent(
                timestamp=datetime.fromtimestamp(
                    draw(st.integers(min_value=1577836800, max_value=1893456000)), tz=timezone.utc
                ),
                change_type=draw(
                    st.sampled_from(["deployment", "configuration", "infrastructure"])
                ),
                event_name=draw(st.text(min_size=1, max_size=100)),
                user=f"arn:aws:iam::123456789012:user/{draw(st.text(min_size=1, max_size=50))}",
                description=draw(st.text(min_size=1, max_size=200)),
            )
        )

    return DeployContextCollectorOutput(
        status=draw(st.sampled_from(["success", "partial", "failed"])),
        changes=changes,
        collection_duration=draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        error=draw(st.one_of(st.none(), st.text(max_size=200))),
    )


# Property Tests


@given(metrics_collector_output_strategy())
def test_metrics_collector_output_schema_compliance(output):
    """
    Property 9: Collector Output Schema Compliance (Metrics Collector)

    **Validates: Requirements 3.3**

    For any metrics collector output, JSON must contain:
    - status field (string with valid values)
    - metrics array (list)
    - collection_duration field (float)

    This property ensures that the output can be serialized to JSON
    and contains all required fields with correct types.
    """
    # Serialize to JSON
    output_dict = output.to_dict()
    json_str = json.dumps(output_dict)
    parsed = json.loads(json_str)

    # Property 1: Must contain 'status' field
    assert "status" in parsed, "Output must contain 'status' field"
    assert isinstance(parsed["status"], str), "'status' must be a string"
    assert parsed["status"] in [
        "success",
        "partial",
        "failed",
    ], f"'status' must be one of: success, partial, failed. Got: {parsed['status']}"

    # Property 2: Must contain 'metrics' field as array
    assert "metrics" in parsed, "Output must contain 'metrics' field"
    assert isinstance(parsed["metrics"], list), "'metrics' must be an array/list"

    # Property 3: Must contain 'collectionDuration' field
    assert "collectionDuration" in parsed, "Output must contain 'collectionDuration' field"
    assert isinstance(
        parsed["collectionDuration"], (int, float)
    ), "'collectionDuration' must be a number"
    assert parsed["collectionDuration"] >= 0, "'collectionDuration' must be non-negative"

    # Property 4: Each metric in array must have required fields
    for i, metric in enumerate(parsed["metrics"]):
        assert isinstance(metric, dict), f"Metric {i} must be a dictionary"
        assert "metricName" in metric, f"Metric {i} must have 'metricName'"
        assert "namespace" in metric, f"Metric {i} must have 'namespace'"
        assert "datapoints" in metric, f"Metric {i} must have 'datapoints'"
        assert "statistics" in metric, f"Metric {i} must have 'statistics'"

        # Validate datapoints structure
        assert isinstance(metric["datapoints"], list), f"Metric {i} 'datapoints' must be an array"

        # Validate statistics structure
        assert isinstance(
            metric["statistics"], dict
        ), f"Metric {i} 'statistics' must be a dictionary"
        assert "avg" in metric["statistics"], f"Metric {i} statistics must have 'avg'"
        assert "max" in metric["statistics"], f"Metric {i} statistics must have 'max'"
        assert "min" in metric["statistics"], f"Metric {i} statistics must have 'min'"


@given(logs_collector_output_strategy())
def test_logs_collector_output_schema_compliance(output):
    """
    Property 9: Collector Output Schema Compliance (Logs Collector)

    **Validates: Requirements 4.4**

    For any logs collector output, JSON must contain:
    - status field (string with valid values)
    - logs array (list)
    - collection_duration field (float)
    """
    # Serialize to JSON
    output_dict = output.to_dict()
    json_str = json.dumps(output_dict)
    parsed = json.loads(json_str)

    # Property 1: Must contain 'status' field
    assert "status" in parsed, "Output must contain 'status' field"
    assert isinstance(parsed["status"], str), "'status' must be a string"
    assert parsed["status"] in [
        "success",
        "partial",
        "failed",
    ], f"'status' must be one of: success, partial, failed. Got: {parsed['status']}"

    # Property 2: Must contain 'logs' field as array
    assert "logs" in parsed, "Output must contain 'logs' field"
    assert isinstance(parsed["logs"], list), "'logs' must be an array/list"

    # Property 3: Must contain 'collectionDuration' field
    assert "collectionDuration" in parsed, "Output must contain 'collectionDuration' field"
    assert isinstance(
        parsed["collectionDuration"], (int, float)
    ), "'collectionDuration' must be a number"
    assert parsed["collectionDuration"] >= 0, "'collectionDuration' must be non-negative"

    # Property 4: Each log entry must have required fields
    for i, log in enumerate(parsed["logs"]):
        assert isinstance(log, dict), f"Log entry {i} must be a dictionary"
        assert "timestamp" in log, f"Log entry {i} must have 'timestamp'"
        assert "logLevel" in log, f"Log entry {i} must have 'logLevel'"
        assert "message" in log, f"Log entry {i} must have 'message'"
        assert "logStream" in log, f"Log entry {i} must have 'logStream'"


@given(deploy_context_collector_output_strategy())
def test_deploy_context_collector_output_schema_compliance(output):
    """
    Property 9: Collector Output Schema Compliance (Deploy Context Collector)

    **Validates: Requirements 5.3**

    For any deploy context collector output, JSON must contain:
    - status field (string with valid values)
    - changes array (list)
    - collection_duration field (float)
    """
    # Serialize to JSON
    output_dict = output.to_dict()
    json_str = json.dumps(output_dict)
    parsed = json.loads(json_str)

    # Property 1: Must contain 'status' field
    assert "status" in parsed, "Output must contain 'status' field"
    assert isinstance(parsed["status"], str), "'status' must be a string"
    assert parsed["status"] in [
        "success",
        "partial",
        "failed",
    ], f"'status' must be one of: success, partial, failed. Got: {parsed['status']}"

    # Property 2: Must contain 'changes' field as array
    assert "changes" in parsed, "Output must contain 'changes' field"
    assert isinstance(parsed["changes"], list), "'changes' must be an array/list"

    # Property 3: Must contain 'collectionDuration' field
    assert "collectionDuration" in parsed, "Output must contain 'collectionDuration' field"
    assert isinstance(
        parsed["collectionDuration"], (int, float)
    ), "'collectionDuration' must be a number"
    assert parsed["collectionDuration"] >= 0, "'collectionDuration' must be non-negative"

    # Property 4: Each change event must have required fields
    for i, change in enumerate(parsed["changes"]):
        assert isinstance(change, dict), f"Change event {i} must be a dictionary"
        assert "timestamp" in change, f"Change event {i} must have 'timestamp'"
        assert "changeType" in change, f"Change event {i} must have 'changeType'"
        assert "eventName" in change, f"Change event {i} must have 'eventName'"
        assert "user" in change, f"Change event {i} must have 'user'"
        assert "description" in change, f"Change event {i} must have 'description'"


@given(metrics_collector_output_strategy())
def test_metrics_collector_output_json_serializable(output):
    """
    Property: Collector Output is JSON Serializable

    **Validates: Requirements 3.3**

    For any collector output, it must be serializable to valid JSON
    without errors or data loss.
    """
    # Serialize to JSON
    output_dict = output.to_dict()

    # Should not raise exception
    json_str = json.dumps(output_dict)

    # Should be valid JSON
    parsed = json.loads(json_str)

    # Should be a dictionary
    assert isinstance(parsed, dict), "Parsed JSON must be a dictionary"

    # Should contain at least the required fields
    required_fields = ["status", "metrics", "collectionDuration"]
    for field in required_fields:
        assert field in parsed, f"Required field '{field}' missing from JSON output"


@given(metrics_collector_output_strategy())
def test_metrics_collector_empty_metrics_valid(output):
    """
    Property: Empty Metrics Array is Valid

    **Validates: Requirements 3.4**

    For any collector output with empty metrics array, the output
    should still be valid and contain all required fields.
    """
    # Force empty metrics
    output.metrics = []

    # Serialize to JSON
    output_dict = output.to_dict()
    json_str = json.dumps(output_dict)
    parsed = json.loads(json_str)

    # Should still have all required fields
    assert "status" in parsed
    assert "metrics" in parsed
    assert "collectionDuration" in parsed

    # Metrics should be empty array
    assert isinstance(parsed["metrics"], list)
    assert len(parsed["metrics"]) == 0


@given(
    st.sampled_from(["success", "partial", "failed"]),
    st.lists(st.text(min_size=1, max_size=50), max_size=5),
    st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False),
)
def test_minimal_collector_output_schema(status, metric_names, duration):
    """
    Property: Minimal Collector Output Schema

    **Validates: Requirements 3.3**

    For any valid status, metric names, and duration, we can construct
    a minimal valid collector output that passes schema validation.
    """
    # Construct minimal output
    output = MetricsCollectorOutput(
        status=status, metrics=[], collection_duration=duration, error=None
    )

    # Serialize to JSON
    output_dict = output.to_dict()
    json_str = json.dumps(output_dict)
    parsed = json.loads(json_str)

    # Validate schema compliance
    assert parsed["status"] == status
    assert isinstance(parsed["metrics"], list)
    assert abs(parsed["collectionDuration"] - duration) < 0.001
