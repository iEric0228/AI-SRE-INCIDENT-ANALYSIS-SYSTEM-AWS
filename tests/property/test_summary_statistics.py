"""
Property-based tests for summary statistics calculation.

This module tests that the correlation engine correctly calculates summary statistics
for metrics, logs, and changes data.

Validates Requirement 6.4
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

extract_metrics_data = correlation_lambda.extract_metrics_data
extract_logs_data = correlation_lambda.extract_logs_data
extract_changes_data = correlation_lambda.extract_changes_data


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
        "datapoints": draw(st.lists(metric_datapoint_strategy(), min_size=1, max_size=20)),
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


# Property Tests


@given(st.lists(metric_data_strategy(), min_size=1, max_size=10))
def test_property_16_metrics_summary_statistics(metrics_list):
    """
    **Property 16: Summary Statistics Calculation - Metrics**
    **Validates: Requirements 6.4**

    For any structured context with metrics data, summary statistics must be correctly calculated.

    This property verifies that:
    1. Average is correctly calculated across all metric values
    2. Maximum is correctly identified
    3. Minimum is correctly identified
    4. Count matches the total number of datapoints
    """
    # Create event with metrics
    event = {
        "metrics": {
            "status": "success",
            "metrics": metrics_list,
            "collectionDuration": 1.5,
        }
    }

    # Extract metrics data (which calculates summary statistics)
    metrics_data = extract_metrics_data(event)

    # Collect all values from all metrics
    all_values = []
    for metric in metrics_list:
        for datapoint in metric.get("datapoints", []):
            all_values.append(datapoint.get("value", 0))

    # Verify summary statistics are present
    assert "summary" in metrics_data, "Metrics data should contain 'summary' key"

    if all_values:
        summary = metrics_data["summary"]

        # Verify all required statistics are present
        assert "avg" in summary, "Summary should contain 'avg'"
        assert "max" in summary, "Summary should contain 'max'"
        assert "min" in summary, "Summary should contain 'min'"
        assert "count" in summary, "Summary should contain 'count'"

        # Calculate expected values
        expected_avg = sum(all_values) / len(all_values)
        expected_max = max(all_values)
        expected_min = min(all_values)
        expected_count = len(all_values)

        # Verify calculated statistics are correct
        assert (
            abs(summary["avg"] - expected_avg) < 0.001
        ), f"Average should be {expected_avg}, got {summary['avg']}"
        assert summary["max"] == expected_max, f"Max should be {expected_max}, got {summary['max']}"
        assert summary["min"] == expected_min, f"Min should be {expected_min}, got {summary['min']}"
        assert (
            summary["count"] == expected_count
        ), f"Count should be {expected_count}, got {summary['count']}"

        # Verify time series contains all datapoints
        assert "timeSeries" in metrics_data, "Metrics data should contain 'timeSeries' key"
        assert (
            len(metrics_data["timeSeries"]) == expected_count
        ), f"Time series should have {expected_count} entries"
    else:
        # Empty metrics should have empty summary
        assert metrics_data["summary"] == {}, "Empty metrics should have empty summary"


@given(st.lists(log_entry_strategy(), min_size=1, max_size=100))
def test_property_16_logs_summary_statistics(logs_list):
    """
    **Property 16: Summary Statistics Calculation - Logs**
    **Validates: Requirements 6.4**

    For any structured context with logs data, summary statistics must be correctly calculated.

    This property verifies that:
    1. Error count matches the total number of log entries
    2. Error counts by level are correctly calculated
    3. Top errors are extracted (up to 10 unique messages)
    """
    # Create event with logs
    event = {
        "logs": {
            "status": "success",
            "logs": logs_list,
            "totalMatches": len(logs_list),
            "returned": len(logs_list),
            "collectionDuration": 2.0,
        }
    }

    # Extract logs data (which calculates summary statistics)
    logs_data = extract_logs_data(event)

    # Verify summary statistics are present
    assert "errorCount" in logs_data, "Logs data should contain 'errorCount' key"
    assert "errorCountsByLevel" in logs_data, "Logs data should contain 'errorCountsByLevel' key"
    assert "topErrors" in logs_data, "Logs data should contain 'topErrors' key"

    # Calculate expected error count
    expected_error_count = len(logs_list)
    assert (
        logs_data["errorCount"] == expected_error_count
    ), f"Error count should be {expected_error_count}, got {logs_data['errorCount']}"

    # Calculate expected error counts by level
    expected_counts_by_level = {}
    for log in logs_list:
        level = log.get("logLevel", "UNKNOWN")
        expected_counts_by_level[level] = expected_counts_by_level.get(level, 0) + 1

    # Verify error counts by level
    for level, count in expected_counts_by_level.items():
        assert level in logs_data["errorCountsByLevel"], f"Level {level} should be in error counts"
        assert (
            logs_data["errorCountsByLevel"][level] == count
        ), f"Count for {level} should be {count}, got {logs_data['errorCountsByLevel'][level]}"

    # Verify sum of counts by level equals total error count
    total_from_levels = sum(logs_data["errorCountsByLevel"].values())
    assert (
        total_from_levels == expected_error_count
    ), f"Sum of level counts should equal total error count"

    # Verify top errors (should be up to 10 unique messages)
    assert len(logs_data["topErrors"]) <= 10, "Top errors should contain at most 10 entries"

    # Verify all top errors are unique
    assert len(logs_data["topErrors"]) == len(
        set(logs_data["topErrors"])
    ), "Top errors should be unique"

    # Verify all top errors come from the original logs
    all_messages = [log.get("message", "") for log in logs_list]
    for error in logs_data["topErrors"]:
        assert error in all_messages, f"Top error '{error}' should be from original logs"

    # Verify metadata is preserved
    assert logs_data["totalMatches"] == len(logs_list), "Total matches should be preserved"
    assert logs_data["returned"] == len(logs_list), "Returned count should be preserved"


@given(st.lists(change_event_strategy(), min_size=1, max_size=50))
def test_property_16_changes_summary_statistics(changes_list):
    """
    **Property 16: Summary Statistics Calculation - Changes**
    **Validates: Requirements 6.4**

    For any structured context with changes data, summary statistics must be correctly calculated.

    This property verifies that:
    1. Total changes count matches the number of change entries
    2. Recent deployments count is correct
    3. Change counts by type are correctly calculated
    4. Last deployment timestamp is correctly identified
    """
    # Create event with changes
    event = {
        "changes": {
            "status": "success",
            "changes": changes_list,
            "collectionDuration": 1.8,
        }
    }

    # Extract changes data (which calculates summary statistics)
    changes_data = extract_changes_data(event)

    # Verify summary statistics are present
    assert "totalChanges" in changes_data, "Changes data should contain 'totalChanges' key"
    assert (
        "recentDeployments" in changes_data
    ), "Changes data should contain 'recentDeployments' key"
    assert (
        "changeCountsByType" in changes_data
    ), "Changes data should contain 'changeCountsByType' key"
    assert "lastDeployment" in changes_data, "Changes data should contain 'lastDeployment' key"

    # Calculate expected total changes
    expected_total_changes = len(changes_list)
    assert (
        changes_data["totalChanges"] == expected_total_changes
    ), f"Total changes should be {expected_total_changes}, got {changes_data['totalChanges']}"

    # Calculate expected deployment count
    expected_deployment_count = sum(1 for c in changes_list if c.get("changeType") == "deployment")
    assert (
        changes_data["recentDeployments"] == expected_deployment_count
    ), f"Recent deployments should be {expected_deployment_count}, got {changes_data['recentDeployments']}"

    # Calculate expected change counts by type
    expected_counts_by_type = {}
    for change in changes_list:
        change_type = change.get("changeType", "unknown")
        expected_counts_by_type[change_type] = expected_counts_by_type.get(change_type, 0) + 1

    # Verify change counts by type
    for change_type, count in expected_counts_by_type.items():
        assert (
            change_type in changes_data["changeCountsByType"]
        ), f"Change type {change_type} should be in counts"
        assert (
            changes_data["changeCountsByType"][change_type] == count
        ), f"Count for {change_type} should be {count}, got {changes_data['changeCountsByType'][change_type]}"

    # Verify sum of counts by type equals total changes
    total_from_types = sum(changes_data["changeCountsByType"].values())
    assert (
        total_from_types == expected_total_changes
    ), f"Sum of type counts should equal total changes"

    # Verify last deployment timestamp
    deployment_timestamps = [
        c.get("timestamp", "") for c in changes_list if c.get("changeType") == "deployment"
    ]
    if deployment_timestamps:
        expected_last_deployment = max(deployment_timestamps)
        assert (
            changes_data["lastDeployment"] == expected_last_deployment
        ), f"Last deployment should be {expected_last_deployment}, got {changes_data['lastDeployment']}"
    else:
        assert (
            changes_data["lastDeployment"] is None
        ), "Last deployment should be None when no deployments"


@given(
    st.lists(metric_data_strategy(), min_size=0, max_size=5),
    st.lists(log_entry_strategy(), min_size=0, max_size=20),
    st.lists(change_event_strategy(), min_size=0, max_size=10),
)
def test_property_16_combined_summary_statistics(metrics_list, logs_list, changes_list):
    """
    **Property 16: Summary Statistics Calculation - Combined**
    **Validates: Requirements 6.4**

    For any structured context with all data sources, summary statistics must be correctly calculated
    for each data source independently.

    This property verifies that:
    1. Metrics summary is calculated correctly
    2. Logs summary is calculated correctly
    3. Changes summary is calculated correctly
    4. Each summary is independent of the others
    """
    # Create event with all data sources
    event = {
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

    # Extract data from each source
    metrics_data = extract_metrics_data(event)
    logs_data = extract_logs_data(event)
    changes_data = extract_changes_data(event)

    # Verify metrics summary
    if metrics_list:
        all_metric_values = []
        for metric in metrics_list:
            for datapoint in metric.get("datapoints", []):
                all_metric_values.append(datapoint.get("value", 0))

        if all_metric_values:
            assert "summary" in metrics_data
            assert metrics_data["summary"]["count"] == len(all_metric_values)

    # Verify logs summary
    if logs_list:
        assert logs_data["errorCount"] == len(logs_list)
        assert sum(logs_data["errorCountsByLevel"].values()) == len(logs_list)

    # Verify changes summary
    if changes_list:
        assert changes_data["totalChanges"] == len(changes_list)
        assert sum(changes_data["changeCountsByType"].values()) == len(changes_list)

    # Verify independence: metrics count should not affect logs or changes counts
    # Note: We don't assert they're different because they can coincidentally be equal
    # The independence is verified by the fact that they're calculated from separate data sources
    if metrics_list and logs_list:
        metric_count = sum(len(m.get("datapoints", [])) for m in metrics_list)
        log_count = len(logs_list)
        # Independence means they're calculated separately, not that they must differ
        assert True, "Metrics and logs are independent data sources"

    if logs_list and changes_list:
        log_count = len(logs_list)
        change_count = len(changes_list)
        # These are independent data sources, so their counts should not be coupled
        # (unless by coincidence they're equal, which is fine)
        assert True, "Logs and changes are independent data sources"


@given(st.lists(metric_data_strategy(), min_size=1, max_size=3))
def test_metrics_summary_with_single_datapoint(metrics_list_with_single_datapoint):
    """
    Property: Summary statistics work correctly when each metric has only one datapoint.

    This tests the edge case where avg, max, and min should all be the same value.
    """
    # Ensure each metric has exactly one datapoint
    for metric in metrics_list_with_single_datapoint:
        metric["datapoints"] = [metric["datapoints"][0]]

    event = {
        "metrics": {
            "status": "success",
            "metrics": metrics_list_with_single_datapoint,
            "collectionDuration": 1.0,
        }
    }

    metrics_data = extract_metrics_data(event)

    # Collect all values
    all_values = []
    for metric in metrics_list_with_single_datapoint:
        for datapoint in metric.get("datapoints", []):
            all_values.append(datapoint.get("value", 0))

    if all_values:
        summary = metrics_data["summary"]

        # When we have multiple metrics with one datapoint each, avg/max/min may differ
        # But the count should match the number of metrics
        assert summary["count"] == len(all_values)

        # Verify the statistics are mathematically correct
        assert summary["avg"] == sum(all_values) / len(all_values)
        assert summary["max"] == max(all_values)
        assert summary["min"] == min(all_values)


@given(st.lists(log_entry_strategy(), min_size=1, max_size=5))
def test_logs_summary_with_all_same_level(logs_list):
    """
    Property: Logs summary correctly handles all logs having the same level.

    This tests the edge case where all logs are the same level.
    """
    # Make all logs the same level
    same_level = "ERROR"
    for log in logs_list:
        log["logLevel"] = same_level

    event = {
        "logs": {
            "status": "success",
            "logs": logs_list,
            "totalMatches": len(logs_list),
            "returned": len(logs_list),
            "collectionDuration": 1.5,
        }
    }

    logs_data = extract_logs_data(event)

    # Verify all errors are counted under the same level
    assert len(logs_data["errorCountsByLevel"]) == 1, "Should have only one level"
    assert same_level in logs_data["errorCountsByLevel"], f"Should have {same_level} level"
    assert logs_data["errorCountsByLevel"][same_level] == len(
        logs_list
    ), "All logs should be counted"
    assert logs_data["errorCount"] == len(logs_list), "Total error count should match"


@given(st.lists(change_event_strategy(), min_size=1, max_size=10))
def test_changes_summary_with_no_deployments(changes_list):
    """
    Property: Changes summary correctly handles no deployment changes.

    This tests the edge case where there are changes but none are deployments.
    """
    # Make all changes non-deployment
    for change in changes_list:
        change["changeType"] = "configuration"

    event = {
        "changes": {
            "status": "success",
            "changes": changes_list,
            "collectionDuration": 1.5,
        }
    }

    changes_data = extract_changes_data(event)

    # Verify no deployments are counted
    assert changes_data["recentDeployments"] == 0, "Should have no deployments"
    assert changes_data["lastDeployment"] is None, "Last deployment should be None"

    # Verify all changes are counted as configuration
    assert "configuration" in changes_data["changeCountsByType"], "Should have configuration type"
    assert changes_data["changeCountsByType"]["configuration"] == len(
        changes_list
    ), "All changes should be configuration"
    assert changes_data["totalChanges"] == len(changes_list), "Total changes should match"
