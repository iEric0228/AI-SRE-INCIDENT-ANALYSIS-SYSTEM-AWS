"""
Property-based tests for context size constraint enforcement.

This module tests that the correlation engine enforces the 50KB size limit
on structured context by truncating data when necessary.

Validates Requirement 6.6
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st, assume, settings, HealthCheck
from hypothesis.strategies import composite
import sys
import os
import json

# Import shared models
from shared.models import (
    StructuredContext,
    ResourceInfo,
    AlarmInfo,
    CompletenessInfo,
)

# Import correlation engine functions directly
# Clear any cached lambda_function module first
if "lambda_function" in sys.modules:
    del sys.modules["lambda_function"]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "correlation_engine"))
import lambda_function as correlation_lambda

enforce_size_constraint = correlation_lambda.enforce_size_constraint


# Strategy generators


@composite
def datetime_strategy(draw):
    """Generate datetime objects with timezone info."""
    timestamp = draw(st.integers(min_value=1577836800, max_value=1893456000))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


@composite
def large_string_strategy(draw, min_size=100, max_size=1000):
    """Generate large strings for testing size constraints."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    return draw(
        st.text(
            min_size=size,
            max_size=size,
            alphabet=st.characters(min_codepoint=65, max_codepoint=122),
        )
    )


@composite
def metric_timeseries_entry_strategy(draw):
    """Generate a metric time series entry."""
    return {
        "timestamp": draw(datetime_strategy()).isoformat() + "Z",
        "metricName": draw(
            st.text(
                min_size=10,
                max_size=50,
                alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            )
        ),
        "value": draw(
            st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
        ),
        "unit": draw(st.sampled_from(["Percent", "Count", "Bytes", "Seconds"])),
    }


@composite
def log_entry_strategy(draw):
    """Generate a log entry with potentially large message."""
    return {
        "timestamp": draw(datetime_strategy()).isoformat() + "Z",
        "logLevel": draw(st.sampled_from(["ERROR", "WARN", "CRITICAL"])),
        "message": draw(large_string_strategy(min_size=50, max_size=500)),
        "logStream": draw(
            st.text(
                min_size=10,
                max_size=50,
                alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            )
        ),
    }


@composite
def change_entry_strategy(draw):
    """Generate a change entry with potentially large description."""
    return {
        "timestamp": draw(datetime_strategy()).isoformat() + "Z",
        "changeType": draw(st.sampled_from(["deployment", "configuration", "infrastructure"])),
        "eventName": draw(
            st.text(
                min_size=10,
                max_size=50,
                alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            )
        ),
        "user": f"arn:aws:iam::123456789012:user/{draw(st.text(min_size=10, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=122)))}",
        "description": draw(large_string_strategy(min_size=50, max_size=300)),
    }


@composite
def structured_context_strategy(draw, target_size_kb=None):
    """
    Generate a StructuredContext with controllable size.

    Args:
        target_size_kb: If specified, generate context that exceeds this size
    """
    # Generate base context
    incident_id = draw(st.uuids()).hex
    timestamp = draw(datetime_strategy())

    resource = ResourceInfo(
        arn=f"arn:aws:lambda:us-east-1:123456789012:function/{draw(st.text(min_size=5, max_size=20, alphabet=st.characters(min_codepoint=65, max_codepoint=90)))}",
        type="lambda",
        name=draw(
            st.text(
                min_size=5, max_size=20, alphabet=st.characters(min_codepoint=65, max_codepoint=90)
            )
        ),
    )

    alarm = AlarmInfo(
        name=draw(
            st.text(
                min_size=5, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=90)
            )
        ),
        metric=draw(
            st.text(
                min_size=5, max_size=20, alphabet=st.characters(min_codepoint=65, max_codepoint=90)
            )
        ),
        threshold=draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        ),
    )

    completeness = CompletenessInfo(
        metrics=draw(st.booleans()), logs=draw(st.booleans()), changes=draw(st.booleans())
    )

    # Generate data with size control
    if target_size_kb:
        # Generate large amounts of data to exceed target size
        num_metrics = draw(st.integers(min_value=200, max_value=400))
        num_logs = draw(st.integers(min_value=200, max_value=400))
        num_changes = draw(st.integers(min_value=100, max_value=150))
    else:
        # Generate moderate amounts of data
        num_metrics = draw(st.integers(min_value=5, max_value=50))
        num_logs = draw(st.integers(min_value=5, max_value=50))
        num_changes = draw(st.integers(min_value=2, max_value=25))

    metrics_data = {
        "summary": {
            "avg": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "max": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "min": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "count": num_metrics,
        },
        "timeSeries": [draw(metric_timeseries_entry_strategy()) for _ in range(num_metrics)],
        "metrics": [],
    }

    logs_data = {
        "errorCount": num_logs,
        "errorCountsByLevel": {
            "ERROR": draw(st.integers(min_value=0, max_value=num_logs)),
            "WARN": draw(st.integers(min_value=0, max_value=num_logs)),
            "CRITICAL": draw(st.integers(min_value=0, max_value=num_logs)),
        },
        "topErrors": [
            draw(large_string_strategy(min_size=20, max_size=100)) for _ in range(min(10, num_logs))
        ],
        "entries": [draw(log_entry_strategy()) for _ in range(num_logs)],
        "totalMatches": num_logs,
        "returned": num_logs,
    }

    changes_data = {
        "recentDeployments": draw(st.integers(min_value=0, max_value=num_changes)),
        "lastDeployment": draw(datetime_strategy()).isoformat() + "Z" if num_changes > 0 else None,
        "changeCountsByType": {
            "deployment": draw(st.integers(min_value=0, max_value=num_changes)),
            "configuration": draw(st.integers(min_value=0, max_value=num_changes)),
            "infrastructure": draw(st.integers(min_value=0, max_value=num_changes)),
        },
        "totalChanges": num_changes,
        "entries": [draw(change_entry_strategy()) for _ in range(num_changes)],
    }

    context = StructuredContext(
        incident_id=incident_id,
        timestamp=timestamp,
        resource=resource,
        alarm=alarm,
        metrics=metrics_data,
        logs=logs_data,
        changes=changes_data,
        completeness=completeness,
    )

    return context


# Property Tests


@given(structured_context_strategy())
@settings(suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
def test_property_17_context_size_constraint_enforcement(context):
    """
    **Property 17: Context Size Constraint**
    **Validates: Requirements 6.6**

    For any structured context, serialized size must not exceed 50KB.

    This property verifies that:
    1. The enforce_size_constraint function respects the 50KB limit
    2. Contexts under 50KB are not modified
    3. Contexts over 50KB are truncated to meet the constraint
    4. The truncated context is still valid and serializable
    """
    max_size_kb = 50
    max_size_bytes = max_size_kb * 1024

    # Get original size
    original_size = context.size_bytes()

    # Apply size constraint
    constrained_context = enforce_size_constraint(context, max_size_kb=max_size_kb)

    # Get constrained size
    constrained_size = constrained_context.size_bytes()

    # Verify size constraint is enforced
    assert (
        constrained_size <= max_size_bytes
    ), f"Constrained context size {constrained_size} bytes exceeds limit of {max_size_bytes} bytes"

    # Verify context is still valid and serializable
    try:
        serialized = json.dumps(constrained_context.to_dict())
        assert (
            len(serialized.encode("utf-8")) == constrained_size
        ), "Size calculation should match actual serialized size"
    except Exception as e:
        raise AssertionError(f"Constrained context should be serializable: {e}")

    # If original was under limit, it should not be modified
    if original_size <= max_size_bytes:
        assert (
            constrained_size == original_size
        ), f"Context under size limit should not be modified: original {original_size}, constrained {constrained_size}"

        # Verify data is preserved when under limit
        assert len(constrained_context.metrics.get("timeSeries", [])) == len(
            context.metrics.get("timeSeries", [])
        )
        assert len(constrained_context.logs.get("entries", [])) == len(
            context.logs.get("entries", [])
        )
        assert len(constrained_context.changes.get("entries", [])) == len(
            context.changes.get("entries", [])
        )
    else:
        # If original was over limit, it should be reduced
        assert (
            constrained_size < original_size
        ), f"Context over size limit should be reduced: original {original_size}, constrained {constrained_size}"

        # Verify some data was truncated
        original_total_entries = (
            len(context.metrics.get("timeSeries", []))
            + len(context.logs.get("entries", []))
            + len(context.changes.get("entries", []))
        )

        constrained_total_entries = (
            len(constrained_context.metrics.get("timeSeries", []))
            + len(constrained_context.logs.get("entries", []))
            + len(constrained_context.changes.get("entries", []))
        )

        assert (
            constrained_total_entries < original_total_entries
        ), "Truncation should reduce the number of entries"


def test_property_17_large_context_truncation():
    """
    **Property 17: Context Size Constraint - Large Context Truncation**
    **Validates: Requirements 6.6**

    For any structured context that exceeds 50KB, the enforce_size_constraint
    function must truncate it to meet the limit while preserving essential data.

    This property specifically tests large contexts to ensure truncation works correctly.
    """
    max_size_kb = 50
    max_size_bytes = max_size_kb * 1024

    # Create a deliberately large context
    context = StructuredContext(
        incident_id="test-large-context",
        timestamp=datetime.now(timezone.utc),
        resource=ResourceInfo(
            arn="arn:aws:lambda:us-east-1:123456789012:function:test-function",
            type="lambda",
            name="test-function",
        ),
        alarm=AlarmInfo(name="TestAlarm", metric="Errors", threshold=10.0),
        metrics={
            "summary": {"avg": 50.0, "max": 100.0, "min": 0.0, "count": 500},
            "timeSeries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "metricName": f"MetricWithLongName{i}",
                    "value": float(i),
                    "unit": "Count",
                }
                for i in range(500)  # Large number of metrics
            ],
            "metrics": [],
        },
        logs={
            "errorCount": 500,
            "errorCountsByLevel": {"ERROR": 500},
            "topErrors": [f"Error message {i} with additional context" for i in range(10)],
            "entries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "logLevel": "ERROR",
                    "message": f"Error message {i} with some additional context and details about what went wrong",
                    "logStream": f"stream-{i}",
                }
                for i in range(500)  # Large number of logs
            ],
            "totalMatches": 500,
            "returned": 500,
        },
        changes={
            "recentDeployments": 50,
            "lastDeployment": datetime.now(timezone.utc).isoformat() + "Z",
            "changeCountsByType": {"deployment": 50},
            "totalChanges": 50,
            "entries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "changeType": "deployment",
                    "eventName": f"UpdateFunction{i}",
                    "user": f"arn:aws:iam::123456789012:user/deployer{i}",
                    "description": f"Deployment {i} description with additional details",
                }
                for i in range(50)
            ],
        },
        completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
    )

    # Verify context is large
    original_size = context.size_bytes()
    assert (
        original_size > max_size_bytes
    ), f"Test context should be large (>{max_size_bytes} bytes), got {original_size}"

    # Apply size constraint
    constrained_context = enforce_size_constraint(context, max_size_kb=max_size_kb)

    # Get constrained size
    constrained_size = constrained_context.size_bytes()

    # Verify size constraint is enforced
    assert (
        constrained_size <= max_size_bytes
    ), f"Large context size {constrained_size} bytes exceeds limit of {max_size_bytes} bytes"

    # Verify context structure is preserved
    assert constrained_context.incident_id == context.incident_id, "Incident ID should be preserved"
    assert (
        constrained_context.resource.arn == context.resource.arn
    ), "Resource ARN should be preserved"
    assert constrained_context.alarm.name == context.alarm.name, "Alarm name should be preserved"

    # Verify completeness info is preserved
    assert constrained_context.completeness.metrics == context.completeness.metrics
    assert constrained_context.completeness.logs == context.completeness.logs
    assert constrained_context.completeness.changes == context.completeness.changes

    # Verify summary statistics are preserved (not truncated)
    assert "summary" in constrained_context.metrics, "Metrics summary should be preserved"
    assert "errorCount" in constrained_context.logs, "Logs error count should be preserved"
    assert "totalChanges" in constrained_context.changes, "Changes total count should be preserved"

    # Verify data was actually truncated
    assert constrained_size < original_size, "Context should be smaller after truncation"

    # Verify some entries were removed (or all were truncated to minimum)
    assert len(constrained_context.metrics["timeSeries"]) <= len(context.metrics["timeSeries"])
    assert len(constrained_context.logs["entries"]) <= len(context.logs["entries"])
    assert len(constrained_context.changes["entries"]) <= len(context.changes["entries"])


@given(st.integers(min_value=5, max_value=100))
def test_property_17_custom_size_limit(max_size_kb):
    """
    **Property 17: Context Size Constraint - Custom Size Limit**
    **Validates: Requirements 6.6**

    For any custom size limit, the enforce_size_constraint function must
    respect that limit.

    This property verifies that the size constraint is configurable.
    """
    # Create a context with known size
    context = StructuredContext(
        incident_id="test-incident-123",
        timestamp=datetime.now(timezone.utc),
        resource=ResourceInfo(
            arn="arn:aws:lambda:us-east-1:123456789012:function:test-function",
            type="lambda",
            name="test-function",
        ),
        alarm=AlarmInfo(name="TestAlarm", metric="Errors", threshold=10.0),
        metrics={
            "summary": {"avg": 50.0, "max": 100.0, "min": 0.0, "count": 100},
            "timeSeries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "metricName": f"Metric{i}",
                    "value": float(i),
                    "unit": "Count",
                }
                for i in range(200)  # Generate enough data to potentially exceed small limits
            ],
            "metrics": [],
        },
        logs={
            "errorCount": 100,
            "errorCountsByLevel": {"ERROR": 100},
            "topErrors": [f"Error message {i}" for i in range(10)],
            "entries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "logLevel": "ERROR",
                    "message": f"Error message {i} with some additional context",
                    "logStream": f"stream-{i}",
                }
                for i in range(100)
            ],
            "totalMatches": 100,
            "returned": 100,
        },
        changes={
            "recentDeployments": 10,
            "lastDeployment": datetime.now(timezone.utc).isoformat() + "Z",
            "changeCountsByType": {"deployment": 10},
            "totalChanges": 10,
            "entries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "changeType": "deployment",
                    "eventName": f"UpdateFunction{i}",
                    "user": f"arn:aws:iam::123456789012:user/deployer{i}",
                    "description": f"Deployment {i} description",
                }
                for i in range(10)
            ],
        },
        completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
    )

    # Apply custom size constraint
    max_size_bytes = max_size_kb * 1024
    constrained_context = enforce_size_constraint(context, max_size_kb=max_size_kb)

    # Verify size constraint is enforced
    constrained_size = constrained_context.size_bytes()
    assert (
        constrained_size <= max_size_bytes
    ), f"Context size {constrained_size} bytes exceeds custom limit of {max_size_bytes} bytes"


@given(structured_context_strategy())
@settings(suppress_health_check=[HealthCheck.data_too_large, HealthCheck.too_slow])
def test_property_17_idempotent_constraint_enforcement(context):
    """
    **Property 17: Context Size Constraint - Idempotent Enforcement**
    **Validates: Requirements 6.6**

    For any structured context, applying the size constraint multiple times
    should produce the same result.

    This property verifies that constraint enforcement is idempotent.
    """
    max_size_kb = 50

    # Apply constraint once
    constrained_once = enforce_size_constraint(context, max_size_kb=max_size_kb)
    size_once = constrained_once.size_bytes()

    # Apply constraint again
    constrained_twice = enforce_size_constraint(constrained_once, max_size_kb=max_size_kb)
    size_twice = constrained_twice.size_bytes()

    # Verify idempotency
    assert (
        size_once == size_twice
    ), f"Applying constraint twice should produce same size: first {size_once}, second {size_twice}"

    # Verify data is the same
    assert len(constrained_once.metrics.get("timeSeries", [])) == len(
        constrained_twice.metrics.get("timeSeries", [])
    )
    assert len(constrained_once.logs.get("entries", [])) == len(
        constrained_twice.logs.get("entries", [])
    )
    assert len(constrained_once.changes.get("entries", [])) == len(
        constrained_twice.changes.get("entries", [])
    )


def test_empty_context_size_constraint():
    """
    Property: Empty context should always be under size limit.

    This tests the edge case of an empty context.
    """
    context = StructuredContext(
        incident_id="test-incident-empty",
        timestamp=datetime.now(timezone.utc),
        resource=ResourceInfo(arn="", type="", name=""),
        alarm=AlarmInfo(name="", metric="", threshold=0.0),
        metrics={},
        logs={},
        changes={},
        completeness=CompletenessInfo(metrics=False, logs=False, changes=False),
    )

    max_size_kb = 50
    max_size_bytes = max_size_kb * 1024

    # Apply constraint
    constrained_context = enforce_size_constraint(context, max_size_kb=max_size_kb)

    # Verify size is under limit
    assert (
        constrained_context.size_bytes() <= max_size_bytes
    ), "Empty context should be under size limit"

    # Verify context is unchanged
    assert (
        constrained_context.size_bytes() == context.size_bytes()
    ), "Empty context should not be modified"


def test_minimal_context_size_constraint():
    """
    Property: Minimal context with one entry of each type should be under size limit.

    This tests the edge case of a minimal context.
    """
    context = StructuredContext(
        incident_id="test-incident-minimal",
        timestamp=datetime.now(timezone.utc),
        resource=ResourceInfo(
            arn="arn:aws:lambda:us-east-1:123456789012:function:test", type="lambda", name="test"
        ),
        alarm=AlarmInfo(name="TestAlarm", metric="Errors", threshold=10.0),
        metrics={
            "summary": {"avg": 1.0, "max": 1.0, "min": 1.0, "count": 1},
            "timeSeries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "metricName": "Errors",
                    "value": 1.0,
                    "unit": "Count",
                }
            ],
            "metrics": [],
        },
        logs={
            "errorCount": 1,
            "errorCountsByLevel": {"ERROR": 1},
            "topErrors": ["Error"],
            "entries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "logLevel": "ERROR",
                    "message": "Error",
                    "logStream": "stream",
                }
            ],
            "totalMatches": 1,
            "returned": 1,
        },
        changes={
            "recentDeployments": 1,
            "lastDeployment": datetime.now(timezone.utc).isoformat() + "Z",
            "changeCountsByType": {"deployment": 1},
            "totalChanges": 1,
            "entries": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "changeType": "deployment",
                    "eventName": "UpdateFunction",
                    "user": "arn:aws:iam::123456789012:user/deployer",
                    "description": "Deployment",
                }
            ],
        },
        completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
    )

    max_size_kb = 50
    max_size_bytes = max_size_kb * 1024

    # Apply constraint
    constrained_context = enforce_size_constraint(context, max_size_kb=max_size_kb)

    # Verify size is under limit
    assert (
        constrained_context.size_bytes() <= max_size_bytes
    ), "Minimal context should be under size limit"

    # Verify context is unchanged (should be small enough)
    assert (
        constrained_context.size_bytes() == context.size_bytes()
    ), "Minimal context should not be modified"
    assert len(constrained_context.metrics["timeSeries"]) == 1
    assert len(constrained_context.logs["entries"]) == 1
    assert len(constrained_context.changes["entries"]) == 1
