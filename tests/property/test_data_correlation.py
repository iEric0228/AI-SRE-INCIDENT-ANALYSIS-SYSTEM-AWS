"""
Property-based tests for data correlation and merging.

This module tests that the correlation engine correctly merges data from all collectors
and that all available data is present in the merged structured context.

Validates Requirement 6.1
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os

# Import shared models
from shared.models import (
    MetricDatapoint,
    MetricStatistics,
    MetricData,
    MetricsCollectorOutput,
    LogEntry,
    LogsCollectorOutput,
    ChangeEvent,
    DeployContextCollectorOutput,
)

# Import correlation engine functions directly
# Clear any cached lambda_function module first
if "lambda_function" in sys.modules:
    del sys.modules["lambda_function"]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "correlation_engine"))
import lambda_function as correlation_lambda

track_completeness = correlation_lambda.track_completeness
extract_metrics_data = correlation_lambda.extract_metrics_data
extract_logs_data = correlation_lambda.extract_logs_data
extract_changes_data = correlation_lambda.extract_changes_data
parse_resource_arn = correlation_lambda.parse_resource_arn
extract_alarm_info = correlation_lambda.extract_alarm_info


# Strategy generators


@composite
def datetime_strategy(draw):
    """Generate datetime objects with timezone info."""
    timestamp = draw(st.integers(min_value=1577836800, max_value=1893456000))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


@composite
def metric_datapoint_strategy(draw):
    """Generate arbitrary MetricDatapoint instances."""
    return {
        "timestamp": draw(datetime_strategy()).isoformat() + "Z",
        "value": draw(
            st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)
        ),
        "unit": draw(st.sampled_from(["Percent", "Count", "Bytes", "Seconds"])),
    }


@composite
def metric_data_strategy(draw):
    """Generate arbitrary MetricData dict."""
    return {
        "metricName": draw(
            st.text(
                min_size=1, max_size=50, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
            )
        ),
        "namespace": draw(st.sampled_from(["AWS/EC2", "AWS/Lambda", "AWS/RDS"])),
        "datapoints": draw(st.lists(metric_datapoint_strategy(), min_size=1, max_size=10)),
        "statistics": {
            "avg": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "max": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "min": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
        },
    }


@composite
def metrics_collector_output_strategy(draw):
    """Generate arbitrary MetricsCollectorOutput dict."""
    status = draw(st.sampled_from(["success", "partial", "failed"]))
    return {
        "status": status,
        "metrics": draw(st.lists(metric_data_strategy(), min_size=0, max_size=5)),
        "collectionDuration": draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        "error": (
            None
            if status == "success"
            else draw(
                st.one_of(
                    st.none(),
                    st.text(
                        max_size=100, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
                    ),
                )
            )
        ),
    }


@composite
def log_entry_strategy(draw):
    """Generate arbitrary LogEntry dict."""
    return {
        "timestamp": draw(datetime_strategy()).isoformat() + "Z",
        "logLevel": draw(st.sampled_from(["ERROR", "WARN", "CRITICAL", "INFO"])),
        "message": draw(
            st.text(
                min_size=1,
                max_size=200,
                alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            )
        ),
        "logStream": draw(
            st.text(
                min_size=1, max_size=50, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
            )
        ),
    }


@composite
def logs_collector_output_strategy(draw):
    """Generate arbitrary LogsCollectorOutput dict."""
    status = draw(st.sampled_from(["success", "partial", "failed"]))
    returned = draw(st.integers(min_value=0, max_value=100))

    return {
        "status": status,
        "logs": draw(st.lists(log_entry_strategy(), min_size=0, max_size=returned)),
        "totalMatches": draw(st.integers(min_value=returned, max_value=1000)),
        "returned": returned,
        "collectionDuration": draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        "error": (
            None
            if status == "success"
            else draw(
                st.one_of(
                    st.none(),
                    st.text(
                        max_size=100, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
                    ),
                )
            )
        ),
    }


@composite
def change_event_strategy(draw):
    """Generate arbitrary ChangeEvent dict."""
    return {
        "timestamp": draw(datetime_strategy()).isoformat() + "Z",
        "changeType": draw(st.sampled_from(["deployment", "configuration", "infrastructure"])),
        "eventName": draw(
            st.text(
                min_size=1, max_size=50, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
            )
        ),
        "user": f"arn:aws:iam::123456789012:user/{draw(st.text(min_size=1, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=122)))}",
        "description": draw(
            st.text(
                min_size=1,
                max_size=100,
                alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            )
        ),
    }


@composite
def deploy_context_collector_output_strategy(draw):
    """Generate arbitrary DeployContextCollectorOutput dict."""
    status = draw(st.sampled_from(["success", "partial", "failed"]))
    return {
        "status": status,
        "changes": draw(st.lists(change_event_strategy(), min_size=0, max_size=10)),
        "collectionDuration": draw(
            st.floats(min_value=0.1, max_value=30.0, allow_nan=False, allow_infinity=False)
        ),
        "error": (
            None
            if status == "success"
            else draw(
                st.one_of(
                    st.none(),
                    st.text(
                        max_size=100, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
                    ),
                )
            )
        ),
    }


@composite
def incident_event_strategy(draw):
    """Generate arbitrary incident event dict."""
    resource_type = draw(st.sampled_from(["ec2", "lambda", "rds", "ecs"]))
    return {
        "incidentId": draw(st.uuids()).hex,
        "alarmName": draw(
            st.text(
                min_size=1, max_size=50, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
            )
        ),
        "alarmArn": f"arn:aws:cloudwatch:us-east-1:123456789012:alarm:{draw(st.text(min_size=1, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=122)))}",
        "resourceArn": f"arn:aws:{resource_type}:us-east-1:123456789012:instance/{draw(st.text(min_size=1, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=122)))}",
        "timestamp": draw(datetime_strategy()).isoformat() + "Z",
        "alarmState": "ALARM",
        "metricName": draw(
            st.text(
                min_size=1, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
            )
        ),
        "namespace": draw(st.sampled_from(["AWS/EC2", "AWS/Lambda", "AWS/RDS"])),
    }


@composite
def correlation_event_strategy(draw):
    """Generate a complete correlation engine event with all collector outputs."""
    return {
        "incident": draw(incident_event_strategy()),
        "metrics": draw(metrics_collector_output_strategy()),
        "logs": draw(logs_collector_output_strategy()),
        "changes": draw(deploy_context_collector_output_strategy()),
    }


# Property Tests


@given(correlation_event_strategy())
def test_property_13_data_correlation_and_merging(event):
    """
    **Property 13: Data Correlation and Merging**
    **Validates: Requirements 6.1**

    For any set of collector outputs, merged context must contain all available data.

    This property verifies that:
    1. All successful collector data is present in the merged context
    2. Completeness tracking correctly identifies which collectors succeeded
    3. Data from each collector is properly extracted and structured
    4. No data is lost during the merging process
    """
    # Track completeness
    completeness = track_completeness(event)

    # Extract data from each collector
    metrics_data = extract_metrics_data(event) if completeness["metrics"] else {}
    logs_data = extract_logs_data(event) if completeness["logs"] else {}
    changes_data = extract_changes_data(event) if completeness["changes"] else {}

    # Verify completeness tracking is correct
    metrics_output = event.get("metrics", {})
    logs_output = event.get("logs", {})
    changes_output = event.get("changes", {})

    # Check metrics completeness
    if metrics_output.get("status") == "success" and "metricsError" not in event:
        assert completeness[
            "metrics"
        ], "Metrics should be marked as complete when status is success"

        # Verify all metrics data is present
        original_metrics = metrics_output.get("metrics", [])
        if original_metrics:
            assert "metrics" in metrics_data, "Metrics data should contain 'metrics' key"
            assert len(metrics_data["metrics"]) == len(
                original_metrics
            ), "All metrics should be preserved"

            # Verify time series data is created
            assert "timeSeries" in metrics_data, "Metrics data should contain 'timeSeries' key"

            # Count expected datapoints
            expected_datapoints = sum(len(m.get("datapoints", [])) for m in original_metrics)
            actual_datapoints = len(metrics_data["timeSeries"])
            assert (
                actual_datapoints == expected_datapoints
            ), f"All datapoints should be in time series: expected {expected_datapoints}, got {actual_datapoints}"

            # Verify summary statistics are calculated
            assert "summary" in metrics_data, "Metrics data should contain 'summary' key"
            if expected_datapoints > 0:
                assert "avg" in metrics_data["summary"], "Summary should contain average"
                assert "max" in metrics_data["summary"], "Summary should contain max"
                assert "min" in metrics_data["summary"], "Summary should contain min"
                assert "count" in metrics_data["summary"], "Summary should contain count"
    else:
        assert not completeness[
            "metrics"
        ], "Metrics should be marked as incomplete when status is not success or error present"

    # Check logs completeness
    if logs_output.get("status") == "success" and "logsError" not in event:
        assert completeness["logs"], "Logs should be marked as complete when status is success"

        # Verify all logs data is present
        original_logs = logs_output.get("logs", [])
        assert "entries" in logs_data, "Logs data should contain 'entries' key"
        assert len(logs_data["entries"]) == len(
            original_logs
        ), "All log entries should be preserved"

        # Verify log statistics are calculated
        assert "errorCount" in logs_data, "Logs data should contain 'errorCount' key"
        assert (
            "errorCountsByLevel" in logs_data
        ), "Logs data should contain 'errorCountsByLevel' key"
        assert "topErrors" in logs_data, "Logs data should contain 'topErrors' key"

        # Verify error count matches
        assert logs_data["errorCount"] == len(
            original_logs
        ), "Error count should match number of log entries"

        # Verify metadata is preserved
        assert logs_data["totalMatches"] == logs_output.get(
            "totalMatches", 0
        ), "Total matches should be preserved"
        assert logs_data["returned"] == logs_output.get(
            "returned", 0
        ), "Returned count should be preserved"
    else:
        assert not completeness[
            "logs"
        ], "Logs should be marked as incomplete when status is not success or error present"

    # Check changes completeness
    if changes_output.get("status") == "success" and "changesError" not in event:
        assert completeness[
            "changes"
        ], "Changes should be marked as complete when status is success"

        # Verify all changes data is present
        original_changes = changes_output.get("changes", [])
        assert "entries" in changes_data, "Changes data should contain 'entries' key"
        assert len(changes_data["entries"]) == len(
            original_changes
        ), "All change entries should be preserved"

        # Verify change statistics are calculated
        assert (
            "recentDeployments" in changes_data
        ), "Changes data should contain 'recentDeployments' key"
        assert (
            "changeCountsByType" in changes_data
        ), "Changes data should contain 'changeCountsByType' key"
        assert "totalChanges" in changes_data, "Changes data should contain 'totalChanges' key"

        # Verify total changes matches
        assert changes_data["totalChanges"] == len(
            original_changes
        ), "Total changes should match number of change entries"

        # Verify deployment count is correct
        deployment_count = sum(1 for c in original_changes if c.get("changeType") == "deployment")
        assert (
            changes_data["recentDeployments"] == deployment_count
        ), "Deployment count should be correct"

        # Verify change counts by type
        for change in original_changes:
            change_type = change.get("changeType", "unknown")
            assert (
                change_type in changes_data["changeCountsByType"]
            ), f"Change type {change_type} should be in counts"
    else:
        assert not completeness[
            "changes"
        ], "Changes should be marked as incomplete when status is not success or error present"

    # Verify that at least one data source is available (or all can be empty)
    # This ensures the property handles all cases including complete failures
    if completeness["metrics"] or completeness["logs"] or completeness["changes"]:
        # At least one collector succeeded, verify data is present
        has_data = bool(metrics_data) or bool(logs_data) or bool(changes_data)
        assert has_data, "When collectors succeed, merged context should contain data"


@given(
    st.lists(metric_data_strategy(), min_size=1, max_size=5),
    st.lists(log_entry_strategy(), min_size=1, max_size=10),
    st.lists(change_event_strategy(), min_size=1, max_size=10),
)
def test_all_collectors_successful_contains_all_data(metrics_list, logs_list, changes_list):
    """
    Property: When all collectors succeed, merged context contains all data from all sources.

    This is a focused test that ensures no data loss when all collectors are successful.
    """
    # Create event with all successful collectors
    event = {
        "incident": {
            "incidentId": "test-incident-123",
            "alarmName": "TestAlarm",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "metricName": "CPUUtilization",
            "namespace": "AWS/EC2",
        },
        "metrics": {
            "status": "success",
            "metrics": metrics_list,
            "collectionDuration": 1.5,
        },
        "logs": {
            "status": "success",
            "logs": logs_list,
            "totalMatches": len(logs_list),
            "returned": len(logs_list),
            "collectionDuration": 2.0,
        },
        "changes": {
            "status": "success",
            "changes": changes_list,
            "collectionDuration": 1.8,
        },
    }

    # Track completeness
    completeness = track_completeness(event)

    # All should be complete
    assert completeness["metrics"], "Metrics should be complete"
    assert completeness["logs"], "Logs should be complete"
    assert completeness["changes"], "Changes should be complete"

    # Extract data
    metrics_data = extract_metrics_data(event)
    logs_data = extract_logs_data(event)
    changes_data = extract_changes_data(event)

    # Verify all metrics are present
    assert len(metrics_data["metrics"]) == len(metrics_list), "All metrics should be present"

    # Verify all datapoints are in time series
    expected_datapoints = sum(len(m.get("datapoints", [])) for m in metrics_list)
    assert (
        len(metrics_data["timeSeries"]) == expected_datapoints
    ), "All datapoints should be in time series"

    # Verify all logs are present
    assert len(logs_data["entries"]) == len(logs_list), "All log entries should be present"

    # Verify all changes are present
    assert len(changes_data["entries"]) == len(changes_list), "All change entries should be present"


@given(
    st.sampled_from([True, False]), st.sampled_from([True, False]), st.sampled_from([True, False])
)
def test_partial_collector_failure_preserves_available_data(
    metrics_success, logs_success, changes_success
):
    """
    Property: When some collectors fail, available data from successful collectors is preserved.

    This tests graceful degradation - partial failures should not prevent merging available data.
    """
    # Skip the case where all fail (no data to test)
    if not (metrics_success or logs_success or changes_success):
        return

    # Create event with mixed success/failure
    event = {
        "incident": {
            "incidentId": "test-incident-456",
            "alarmName": "TestAlarm",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test-function",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "metricName": "Errors",
            "namespace": "AWS/Lambda",
        }
    }

    # Add metrics if successful
    if metrics_success:
        event["metrics"] = {
            "status": "success",
            "metrics": [
                {
                    "metricName": "Errors",
                    "namespace": "AWS/Lambda",
                    "datapoints": [
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                            "value": 5.0,
                            "unit": "Count",
                        }
                    ],
                    "statistics": {"avg": 5.0, "max": 5.0, "min": 5.0},
                }
            ],
            "collectionDuration": 1.0,
        }
    else:
        event["metricsError"] = {"error": "Metrics collection failed"}
        event["metrics"] = {
            "status": "failed",
            "metrics": [],
            "collectionDuration": 0.5,
            "error": "API error",
        }

    # Add logs if successful
    if logs_success:
        event["logs"] = {
            "status": "success",
            "logs": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "logLevel": "ERROR",
                    "message": "Test error message",
                    "logStream": "test-stream",
                }
            ],
            "totalMatches": 1,
            "returned": 1,
            "collectionDuration": 1.5,
        }
    else:
        event["logsError"] = {"error": "Logs collection failed"}
        event["logs"] = {
            "status": "failed",
            "logs": [],
            "totalMatches": 0,
            "returned": 0,
            "collectionDuration": 0.5,
            "error": "API error",
        }

    # Add changes if successful
    if changes_success:
        event["changes"] = {
            "status": "success",
            "changes": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                    "changeType": "deployment",
                    "eventName": "UpdateFunctionCode",
                    "user": "arn:aws:iam::123456789012:user/deployer",
                    "description": "Function code updated",
                }
            ],
            "collectionDuration": 1.2,
        }
    else:
        event["changesError"] = {"error": "Changes collection failed"}
        event["changes"] = {
            "status": "failed",
            "changes": [],
            "collectionDuration": 0.5,
            "error": "API error",
        }

    # Track completeness
    completeness = track_completeness(event)

    # Verify completeness matches expected
    assert (
        completeness["metrics"] == metrics_success
    ), f"Metrics completeness should be {metrics_success}"
    assert completeness["logs"] == logs_success, f"Logs completeness should be {logs_success}"
    assert (
        completeness["changes"] == changes_success
    ), f"Changes completeness should be {changes_success}"

    # Extract data only from successful collectors
    if metrics_success:
        metrics_data = extract_metrics_data(event)
        assert len(metrics_data["metrics"]) > 0, "Successful metrics collector should have data"
        assert (
            len(metrics_data["timeSeries"]) > 0
        ), "Successful metrics collector should have time series"

    if logs_success:
        logs_data = extract_logs_data(event)
        assert len(logs_data["entries"]) > 0, "Successful logs collector should have data"

    if changes_success:
        changes_data = extract_changes_data(event)
        assert len(changes_data["entries"]) > 0, "Successful changes collector should have data"
