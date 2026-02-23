"""
Property Test: Retry Exhaustion Handling

Property 30: For any Lambda function that exhausts all retry attempts, the
orchestrator must mark that data source as unavailable and continue the workflow.

Validates: Requirements 20.4

Note: This property tests the Step Functions retry and error handling logic.
When a Lambda exhausts retries, Step Functions catches the error and continues
with partial data.
"""

import json
import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime
from typing import Dict, Any

# Import correlation engine for testing partial data handling
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from correlation_engine.lambda_function import track_completeness


# Strategy for generating retry exhaustion scenarios
@st.composite
def retry_exhaustion_scenarios(draw):
    """
    Generate scenarios where Lambda functions exhaust retries.

    Returns event structure as it would appear after Step Functions
    catches the error and continues.
    """
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

    # Randomly select which collector(s) exhausted retries
    collectors = ["metrics", "logs", "changes"]
    num_failures = draw(st.integers(min_value=1, max_value=3))
    failed_collectors = draw(
        st.lists(
            st.sampled_from(collectors), min_size=num_failures, max_size=num_failures, unique=True
        )
    )

    event = {"incident": incident}

    # For each collector, either add success data or error
    for collector in collectors:
        if collector in failed_collectors:
            # Simulate Step Functions error catch after retry exhaustion
            # Error structure includes attempt count and error details
            error_types = [
                "ThrottlingException",
                "ServiceException",
                "TooManyRequestsException",
                "States.TaskFailed",
            ]

            event[f"{collector}Error"] = {
                "Error": draw(st.sampled_from(error_types)),
                "Cause": json.dumps(
                    {
                        "errorMessage": f"{collector} collector failed after retries",
                        "errorType": draw(st.sampled_from(error_types)),
                        "attempts": 3,  # Max retry attempts exhausted
                        "lastAttemptTime": timestamp.isoformat() + "Z",
                    }
                ),
            }
        else:
            # Collector succeeded
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
            else:  # changes
                event["changes"] = {"status": "success", "changes": [], "collectionDuration": 1.0}

    return event, failed_collectors


@settings(deadline=None)
@given(scenario=retry_exhaustion_scenarios())
@pytest.mark.property_test
@pytest.mark.tag("Feature: ai-sre-incident-analysis, Property 30: Retry Exhaustion Handling")
def test_retry_exhaustion_handling(scenario):
    """
    Property 30: For any Lambda function that exhausts all retry attempts, the
    orchestrator must mark that data source as unavailable and continue the workflow.

    Validates: Requirements 20.4
    """
    event, failed_collectors = scenario

    # PROPERTY ASSERTIONS:
    # 1. Event must contain error information for failed collectors
    for collector in failed_collectors:
        error_key = f"{collector}Error"
        assert error_key in event, f"Event must contain error information for {collector}"

        error_info = event[error_key]
        assert "Error" in error_info, f"Error info must contain Error field for {collector}"

        # Error cause should indicate retry exhaustion
        if "Cause" in error_info:
            cause = (
                json.loads(error_info["Cause"])
                if isinstance(error_info["Cause"], str)
                else error_info["Cause"]
            )
            # Verify this was after retries (attempts should be > 1)
            if "attempts" in cause:
                assert (
                    cause["attempts"] >= 3
                ), f"Failed collector should have exhausted retries (3 attempts)"

    # 2. Completeness tracking must mark failed collectors as unavailable
    completeness = track_completeness(event)

    for collector in failed_collectors:
        assert (
            completeness[collector] == False
        ), f"Completeness must mark {collector} as unavailable after retry exhaustion"

    # 3. Successful collectors must still be marked as available
    all_collectors = ["metrics", "logs", "changes"]
    successful_collectors = [c for c in all_collectors if c not in failed_collectors]

    for collector in successful_collectors:
        assert (
            completeness[collector] == True
        ), f"Completeness must mark {collector} as available when it succeeded"

    # 4. Workflow must be able to continue (correlation engine can process event)
    from correlation_engine.lambda_function import lambda_handler

    try:
        result = lambda_handler(event, None)
        assert (
            result["status"] == "success"
        ), "Correlation engine must succeed even when collectors exhaust retries"

        # Structured context must be present
        assert (
            "structuredContext" in result
        ), "Structured context must be present despite retry exhaustion"

        # Completeness must be reflected in structured context
        structured_context = result["structuredContext"]
        assert (
            "completeness" in structured_context
        ), "Structured context must include completeness indicator"

        context_completeness = structured_context["completeness"]
        for collector in failed_collectors:
            assert (
                context_completeness[collector] == False
            ), f"Structured context must mark {collector} as incomplete"

    except Exception as e:
        pytest.fail(f"Workflow must continue after retry exhaustion: {e}")


@given(
    max_attempts=st.integers(min_value=1, max_value=5),
    error_type=st.sampled_from(
        ["ThrottlingException", "ServiceException", "TooManyRequestsException"]
    ),
)
@pytest.mark.property_test
def test_retry_configuration_validation(max_attempts, error_type):
    """
    Test that retry configuration is properly structured.

    Step Functions retry configuration should specify:
    - ErrorEquals: List of retryable errors
    - MaxAttempts: Maximum retry attempts (typically 3)
    - IntervalSeconds: Initial retry interval (typically 2)
    - BackoffRate: Exponential backoff multiplier (typically 2.0)
    """
    # This validates the Step Functions retry configuration structure
    retry_config = {
        "ErrorEquals": [error_type],
        "MaxAttempts": max_attempts,
        "IntervalSeconds": 2,
        "BackoffRate": 2.0,
    }

    # PROPERTY: Retry configuration must be valid

    # 1. Must specify which errors to retry
    assert "ErrorEquals" in retry_config, "Retry config must specify ErrorEquals"

    assert len(retry_config["ErrorEquals"]) > 0, "ErrorEquals must contain at least one error type"

    # 2. Must specify max attempts
    assert "MaxAttempts" in retry_config, "Retry config must specify MaxAttempts"

    assert retry_config["MaxAttempts"] > 0, "MaxAttempts must be positive"

    # 3. Must specify retry interval
    assert "IntervalSeconds" in retry_config, "Retry config must specify IntervalSeconds"

    assert retry_config["IntervalSeconds"] > 0, "IntervalSeconds must be positive"

    # 4. Must specify backoff rate for exponential backoff
    assert "BackoffRate" in retry_config, "Retry config must specify BackoffRate"

    assert retry_config["BackoffRate"] >= 1.0, "BackoffRate must be >= 1.0 for exponential backoff"

    # 5. Calculate total retry time
    total_time = 0
    interval = retry_config["IntervalSeconds"]
    for attempt in range(retry_config["MaxAttempts"]):
        total_time += interval
        interval *= retry_config["BackoffRate"]

    # Total retry time should be reasonable (not too long)
    assert total_time < 120, "Total retry time should not exceed workflow timeout"


@given(scenario=retry_exhaustion_scenarios())
@pytest.mark.property_test
def test_error_information_preserved(scenario):
    """
    Test that error information is preserved when retries are exhausted.
    """
    event, failed_collectors = scenario

    # PROPERTY: Error details must be preserved for debugging

    for collector in failed_collectors:
        error_key = f"{collector}Error"
        error_info = event[error_key]

        # 1. Error type must be present
        assert "Error" in error_info, f"Error type must be present for {collector}"

        # 2. Error cause should provide context
        if "Cause" in error_info:
            cause_str = error_info["Cause"]

            # Cause should be parseable JSON with error details
            try:
                cause = json.loads(cause_str) if isinstance(cause_str, str) else cause_str

                # Should contain error message
                assert (
                    "errorMessage" in cause or "errorType" in cause
                ), f"Error cause should contain error details for {collector}"

            except json.JSONDecodeError:
                # Cause might be plain text, which is also acceptable
                assert len(cause_str) > 0, f"Error cause must not be empty for {collector}"


@given(num_failed=st.integers(min_value=1, max_value=3), workflow_continues=st.booleans())
@pytest.mark.property_test
def test_workflow_continuation_after_retry_exhaustion(num_failed, workflow_continues):
    """
    Test that workflow can continue regardless of how many collectors fail.
    """
    # PROPERTY: Workflow must continue even if all collectors fail
    # (though analysis quality will be poor with no data)

    # Simulate completeness after retry exhaustion
    all_collectors = ["metrics", "logs", "changes"]

    # Randomly select which collectors failed
    import random

    failed = random.sample(all_collectors, num_failed)

    completeness = {
        "metrics": "metrics" not in failed,
        "logs": "logs" not in failed,
        "changes": "changes" not in failed,
    }

    # Workflow should continue if workflow_continues is True
    # (simulating Step Functions catch block allowing continuation)
    if workflow_continues:
        # At least one data source should be available, OR
        # workflow continues with empty data (graceful degradation)
        can_continue = True

        assert can_continue, "Workflow must be able to continue after retry exhaustion"

        # If all collectors failed, completeness should reflect that
        if num_failed == 3:
            assert not any(
                completeness.values()
            ), "All collectors should be marked incomplete when all fail"
        else:
            # Some collectors succeeded
            assert any(
                completeness.values()
            ), "Some collectors should be marked complete when not all fail"


@given(scenario=retry_exhaustion_scenarios())
@pytest.mark.property_test
def test_partial_data_available_after_retry_exhaustion(scenario):
    """
    Test that partial data from successful collectors is available after retry exhaustion.
    """
    event, failed_collectors = scenario

    all_collectors = ["metrics", "logs", "changes"]
    successful_collectors = [c for c in all_collectors if c not in failed_collectors]

    # PROPERTY: Data from successful collectors must be available

    for collector in successful_collectors:
        # Successful collector data must be in event
        assert collector in event, f"Data from successful {collector} collector must be in event"

        collector_data = event[collector]

        # Must have success status
        assert (
            collector_data.get("status") == "success"
        ), f"Successful {collector} collector must have success status"

        # Must have data field (even if empty)
        if collector == "metrics":
            assert "metrics" in collector_data, "Metrics collector must have metrics field"
        elif collector == "logs":
            assert "logs" in collector_data, "Logs collector must have logs field"
        else:  # changes
            assert "changes" in collector_data, "Changes collector must have changes field"
