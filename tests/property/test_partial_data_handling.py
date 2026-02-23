"""
Property Test: Graceful Degradation with Partial Data

Property 6: For any incident workflow where one or more collectors fail,
the workflow must continue with available data and mark the incident as
partial in the completeness indicator.

Validates: Requirements 2.5, 12.1, 12.2, 12.3, 12.6
"""

import json
import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from typing import Dict, Any

# Import the correlation engine
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from correlation_engine.lambda_function import lambda_handler, track_completeness


# Strategy for generating collector failure combinations
@st.composite
def collector_failure_scenarios(draw):
    """
    Generate scenarios with different collector failure combinations.

    Returns a tuple of (event_dict, expected_completeness)
    """
    # Base incident data
    incident_id = draw(
        st.text(
            min_size=10,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pd")),
        )
    )
    timestamp = draw(st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)))

    incident = {
        "incidentId": incident_id,
        "timestamp": timestamp.isoformat() + "Z",
        "alarmName": "test-alarm",
        "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
        "metricName": "CPUUtilization",
    }

    # Randomly decide which collectors fail
    metrics_fails = draw(st.booleans())
    logs_fails = draw(st.booleans())
    changes_fails = draw(st.booleans())

    # Ensure at least one collector fails (otherwise not a partial data scenario)
    if not (metrics_fails or logs_fails or changes_fails):
        # Force at least one failure
        failure_choice = draw(st.sampled_from(["metrics", "logs", "changes"]))
        if failure_choice == "metrics":
            metrics_fails = True
        elif failure_choice == "logs":
            logs_fails = True
        else:
            changes_fails = True

    event = {"incident": incident}
    expected_completeness = {}

    # Add metrics data or error
    if metrics_fails:
        event["metricsError"] = {"Error": "MetricsCollectorFailed", "Cause": "Simulated failure"}
        expected_completeness["metrics"] = False
    else:
        event["metrics"] = {
            "status": "success",
            "metrics": [{"metricName": "CPUUtilization", "datapoints": []}],
            "collectionDuration": 1.0,
        }
        expected_completeness["metrics"] = True

    # Add logs data or error
    if logs_fails:
        event["logsError"] = {"Error": "LogsCollectorFailed", "Cause": "Simulated failure"}
        expected_completeness["logs"] = False
    else:
        event["logs"] = {
            "status": "success",
            "logs": [
                {"timestamp": timestamp.isoformat() + "Z", "logLevel": "ERROR", "message": "test"}
            ],
            "totalMatches": 1,
            "returned": 1,
            "collectionDuration": 1.0,
        }
        expected_completeness["logs"] = True

    # Add changes data or error
    if changes_fails:
        event["changesError"] = {"Error": "ChangesCollectorFailed", "Cause": "Simulated failure"}
        expected_completeness["changes"] = False
    else:
        event["changes"] = {
            "status": "success",
            "changes": [
                {
                    "timestamp": timestamp.isoformat() + "Z",
                    "changeType": "deployment",
                    "eventName": "test",
                }
            ],
            "collectionDuration": 1.0,
        }
        expected_completeness["changes"] = True

    return event, expected_completeness


@settings(deadline=None)
@given(scenario=collector_failure_scenarios())
@pytest.mark.property_test
@pytest.mark.tag(
    "Feature: ai-sre-incident-analysis, Property 6: Graceful Degradation with Partial Data"
)
def test_graceful_degradation_with_partial_data(scenario):
    """
    Property 6: For any incident workflow where one or more collectors fail,
    the workflow must continue with available data and mark the incident as
    partial in the completeness indicator.

    Validates: Requirements 2.5, 12.1, 12.2, 12.3, 12.6
    """
    event, expected_completeness = scenario

    # Invoke correlation engine
    result = lambda_handler(event, None)

    # PROPERTY ASSERTIONS:
    # 1. Correlation engine must succeed even with collector failures
    assert result["status"] == "success", "Correlation engine must succeed with partial data"

    # 2. Structured context must be present
    assert (
        "structuredContext" in result
    ), "Structured context must be present even with collector failures"

    structured_context = result["structuredContext"]

    # 3. Completeness indicator must accurately reflect which collectors succeeded
    assert "completeness" in structured_context, "Completeness indicator must be present"

    completeness = structured_context["completeness"]

    # Verify each collector's completeness matches expected
    assert (
        completeness["metrics"] == expected_completeness["metrics"]
    ), f"Metrics completeness mismatch: expected {expected_completeness['metrics']}, got {completeness['metrics']}"

    assert (
        completeness["logs"] == expected_completeness["logs"]
    ), f"Logs completeness mismatch: expected {expected_completeness['logs']}, got {completeness['logs']}"

    assert (
        completeness["changes"] == expected_completeness["changes"]
    ), f"Changes completeness mismatch: expected {expected_completeness['changes']}, got {completeness['changes']}"

    # 4. At least one collector must have failed (partial data scenario)
    assert not all(
        [completeness["metrics"], completeness["logs"], completeness["changes"]]
    ), "At least one collector must have failed in partial data scenario"

    # 5. Available data must be included in structured context
    if completeness["metrics"]:
        assert (
            "metrics" in structured_context
        ), "Metrics data must be present when metrics collector succeeded"

    if completeness["logs"]:
        assert (
            "logs" in structured_context
        ), "Logs data must be present when logs collector succeeded"

    if completeness["changes"]:
        assert (
            "changes" in structured_context
        ), "Changes data must be present when changes collector succeeded"

    # 6. Incident ID must be preserved
    assert (
        structured_context["incidentId"] == event["incident"]["incidentId"]
    ), "Incident ID must be preserved through correlation"


@given(metrics_fails=st.booleans(), logs_fails=st.booleans(), changes_fails=st.booleans())
@pytest.mark.property_test
def test_completeness_tracking_accuracy(metrics_fails, logs_fails, changes_fails):
    """
    Test that completeness tracking accurately reflects collector success/failure.
    """
    # Build event with specified failure pattern
    event = {
        "incident": {
            "incidentId": "test-inc-001",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "metricName": "CPUUtilization",
        }
    }

    # Add metrics
    if metrics_fails:
        event["metricsError"] = {"Error": "Failed"}
    else:
        event["metrics"] = {"status": "success", "metrics": [], "collectionDuration": 1.0}

    # Add logs
    if logs_fails:
        event["logsError"] = {"Error": "Failed"}
    else:
        event["logs"] = {
            "status": "success",
            "logs": [],
            "totalMatches": 0,
            "returned": 0,
            "collectionDuration": 1.0,
        }

    # Add changes
    if changes_fails:
        event["changesError"] = {"Error": "Failed"}
    else:
        event["changes"] = {"status": "success", "changes": [], "collectionDuration": 1.0}

    # Track completeness
    completeness = track_completeness(event)

    # Verify accuracy
    assert completeness["metrics"] == (
        not metrics_fails
    ), f"Metrics completeness should be {not metrics_fails}"
    assert completeness["logs"] == (not logs_fails), f"Logs completeness should be {not logs_fails}"
    assert completeness["changes"] == (
        not changes_fails
    ), f"Changes completeness should be {not changes_fails}"


@settings(deadline=None)
@given(num_failed_collectors=st.integers(min_value=1, max_value=3))
@pytest.mark.property_test
def test_workflow_continues_with_any_number_of_failures(num_failed_collectors):
    """
    Test that workflow continues regardless of how many collectors fail (1, 2, or 3).
    """
    # Create event with specified number of failures
    event = {
        "incident": {
            "incidentId": "test-inc-001",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "metricName": "CPUUtilization",
        }
    }

    collectors = ["metrics", "logs", "changes"]

    # Randomly select which collectors fail
    import random

    failed_collectors = random.sample(collectors, num_failed_collectors)

    for collector in collectors:
        if collector in failed_collectors:
            event[f"{collector}Error"] = {"Error": "Failed"}
        else:
            if collector == "metrics":
                event["metrics"] = {"status": "success", "metrics": [], "collectionDuration": 1.0}
            elif collector == "logs":
                event["logs"] = {
                    "status": "success",
                    "logs": [],
                    "totalMatches": 0,
                    "returned": 0,
                    "collectionDuration": 1.0,
                }
            else:
                event["changes"] = {"status": "success", "changes": [], "collectionDuration": 1.0}

    # Invoke correlation engine
    result = lambda_handler(event, None)

    # Workflow must continue
    assert (
        result["status"] == "success"
    ), f"Workflow must continue with {num_failed_collectors} collector failure(s)"

    # Structured context must be present
    assert "structuredContext" in result, "Structured context must be present"

    # Completeness must reflect failures
    completeness = result["structuredContext"]["completeness"]
    num_incomplete = sum(
        [not completeness["metrics"], not completeness["logs"], not completeness["changes"]]
    )

    assert (
        num_incomplete == num_failed_collectors
    ), f"Expected {num_failed_collectors} incomplete collectors, got {num_incomplete}"
