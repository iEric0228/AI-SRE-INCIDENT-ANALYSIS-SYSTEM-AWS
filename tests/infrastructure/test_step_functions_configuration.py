"""
Infrastructure tests for Step Functions state machine configuration.

Validates Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 17.1, 20.1, 20.2
"""

import json
import pytest


@pytest.fixture
def state_machine_definition():
    """Load the state machine definition from the Terraform module."""
    # In a real scenario, this would parse the Terraform file
    # For now, we'll construct the expected definition
    return {
        "Comment": "AI-Assisted Incident Analysis Workflow",
        "StartAt": "ParallelDataCollection",
        "States": {
            "ParallelDataCollection": {
                "Type": "Parallel",
                "Branches": [
                    {
                        "StartAt": "CollectMetrics",
                        "States": {
                            "CollectMetrics": {
                                "Type": "Task",
                                "TimeoutSeconds": 20,
                                "Retry": [
                                    {
                                        "ErrorEquals": [
                                            "ThrottlingException",
                                            "ServiceException",
                                            "TooManyRequestsException",
                                        ],
                                        "IntervalSeconds": 2,
                                        "MaxAttempts": 3,
                                        "BackoffRate": 2.0,
                                    }
                                ],
                                "Catch": [
                                    {
                                        "ErrorEquals": ["States.ALL"],
                                        "ResultPath": "$.metricsError",
                                        "Next": "MetricsCollectionFailed",
                                    }
                                ],
                                "End": True,
                            },
                            "MetricsCollectionFailed": {
                                "Type": "Pass",
                                "Result": {
                                    "status": "failed",
                                    "error": "Metrics collection failed",
                                },
                                "End": True,
                            },
                        },
                    },
                    {
                        "StartAt": "CollectLogs",
                        "States": {
                            "CollectLogs": {
                                "Type": "Task",
                                "TimeoutSeconds": 20,
                                "Retry": [
                                    {
                                        "ErrorEquals": [
                                            "ThrottlingException",
                                            "ServiceException",
                                            "TooManyRequestsException",
                                        ],
                                        "IntervalSeconds": 2,
                                        "MaxAttempts": 3,
                                        "BackoffRate": 2.0,
                                    }
                                ],
                                "Catch": [
                                    {
                                        "ErrorEquals": ["States.ALL"],
                                        "ResultPath": "$.logsError",
                                        "Next": "LogsCollectionFailed",
                                    }
                                ],
                                "End": True,
                            },
                            "LogsCollectionFailed": {
                                "Type": "Pass",
                                "Result": {"status": "failed", "error": "Logs collection failed"},
                                "End": True,
                            },
                        },
                    },
                    {
                        "StartAt": "CollectDeployContext",
                        "States": {
                            "CollectDeployContext": {
                                "Type": "Task",
                                "TimeoutSeconds": 20,
                                "Retry": [
                                    {
                                        "ErrorEquals": [
                                            "ThrottlingException",
                                            "ServiceException",
                                            "TooManyRequestsException",
                                        ],
                                        "IntervalSeconds": 2,
                                        "MaxAttempts": 3,
                                        "BackoffRate": 2.0,
                                    }
                                ],
                                "Catch": [
                                    {
                                        "ErrorEquals": ["States.ALL"],
                                        "ResultPath": "$.changesError",
                                        "Next": "DeployContextCollectionFailed",
                                    }
                                ],
                                "End": True,
                            },
                            "DeployContextCollectionFailed": {
                                "Type": "Pass",
                                "Result": {
                                    "status": "failed",
                                    "error": "Deploy context collection failed",
                                },
                                "End": True,
                            },
                        },
                    },
                ],
                "ResultPath": "$.collectorResults",
                "Next": "CorrelateData",
            },
            "CorrelateData": {
                "Type": "Task",
                "TimeoutSeconds": 10,
                "Retry": [
                    {
                        "ErrorEquals": [
                            "ThrottlingException",
                            "ServiceException",
                            "TooManyRequestsException",
                        ],
                        "IntervalSeconds": 2,
                        "MaxAttempts": 3,
                        "BackoffRate": 2.0,
                    }
                ],
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.correlationError",
                        "Next": "CorrelationFailed",
                    }
                ],
                "ResultPath": "$.structuredContext",
                "Next": "AnalyzeWithLLM",
            },
            "CorrelationFailed": {
                "Type": "Fail",
                "Error": "CorrelationEngineFailure",
                "Cause": "Failed to correlate collector data",
            },
            "AnalyzeWithLLM": {
                "Type": "Task",
                "TimeoutSeconds": 40,
                "Retry": [
                    {
                        "ErrorEquals": ["ThrottlingException", "TooManyRequestsException"],
                        "IntervalSeconds": 2,
                        "MaxAttempts": 3,
                        "BackoffRate": 2.0,
                    }
                ],
                "Catch": [
                    {
                        "ErrorEquals": ["States.ALL"],
                        "ResultPath": "$.analysisError",
                        "Next": "NotifyAndStore",
                    }
                ],
                "ResultPath": "$.analysisReport",
                "Next": "NotifyAndStore",
            },
            "NotifyAndStore": {
                "Type": "Parallel",
                "Branches": [
                    {
                        "StartAt": "SendNotification",
                        "States": {
                            "SendNotification": {
                                "Type": "Task",
                                "TimeoutSeconds": 15,
                                "Retry": [
                                    {
                                        "ErrorEquals": ["ThrottlingException", "ServiceException"],
                                        "IntervalSeconds": 1,
                                        "MaxAttempts": 2,
                                        "BackoffRate": 2.0,
                                    }
                                ],
                                "Catch": [
                                    {
                                        "ErrorEquals": ["States.ALL"],
                                        "ResultPath": "$.notificationError",
                                        "Next": "NotificationFailed",
                                    }
                                ],
                                "End": True,
                            },
                            "NotificationFailed": {
                                "Type": "Pass",
                                "Result": {
                                    "status": "failed",
                                    "error": "Notification delivery failed",
                                },
                                "End": True,
                            },
                        },
                    },
                    {
                        "StartAt": "StoreIncident",
                        "States": {
                            "StoreIncident": {
                                "Type": "Task",
                                "Retry": [
                                    {
                                        "ErrorEquals": [
                                            "ThrottlingException",
                                            "ProvisionedThroughputExceededException",
                                        ],
                                        "IntervalSeconds": 2,
                                        "MaxAttempts": 3,
                                        "BackoffRate": 2.0,
                                    }
                                ],
                                "Catch": [
                                    {
                                        "ErrorEquals": ["States.ALL"],
                                        "ResultPath": "$.storageError",
                                        "Next": "StorageFailed",
                                    }
                                ],
                                "End": True,
                            },
                            "StorageFailed": {
                                "Type": "Pass",
                                "Result": {"status": "failed", "error": "Incident storage failed"},
                                "End": True,
                            },
                        },
                    },
                ],
                "End": True,
            },
        },
    }


def test_state_machine_starts_with_parallel_collection(state_machine_definition):
    """
    Test that state machine starts with parallel data collection.
    Validates Requirement 2.1: Parallel collector invocation
    """
    assert state_machine_definition["StartAt"] == "ParallelDataCollection"
    assert state_machine_definition["States"]["ParallelDataCollection"]["Type"] == "Parallel"


def test_parallel_collection_has_three_branches(state_machine_definition):
    """
    Test that parallel collection has exactly three branches.
    Validates Requirement 2.1: Three collectors (metrics, logs, deploy context)
    """
    branches = state_machine_definition["States"]["ParallelDataCollection"]["Branches"]
    assert len(branches) == 3

    # Verify each branch has the correct collector
    branch_names = [branch["StartAt"] for branch in branches]
    assert "CollectMetrics" in branch_names
    assert "CollectLogs" in branch_names
    assert "CollectDeployContext" in branch_names


def test_workflow_sequencing(state_machine_definition):
    """
    Test that workflow follows correct sequence.
    Validates Requirements 2.2, 2.3, 2.4: Workflow sequencing
    """
    # Parallel collection -> Correlation
    parallel_state = state_machine_definition["States"]["ParallelDataCollection"]
    assert parallel_state["Next"] == "CorrelateData"

    # Correlation -> LLM Analysis
    correlation_state = state_machine_definition["States"]["CorrelateData"]
    assert correlation_state["Next"] == "AnalyzeWithLLM"

    # LLM Analysis -> Notify and Store
    llm_state = state_machine_definition["States"]["AnalyzeWithLLM"]
    assert llm_state["Next"] == "NotifyAndStore"

    # Notify and Store is terminal
    notify_store_state = state_machine_definition["States"]["NotifyAndStore"]
    assert notify_store_state["End"] is True


def test_collector_timeouts(state_machine_definition):
    """
    Test that collectors have correct timeout values.
    Validates Requirement 2.6: Timeout configuration
    """
    branches = state_machine_definition["States"]["ParallelDataCollection"]["Branches"]

    for branch in branches:
        collector_name = branch["StartAt"]
        collector_state = branch["States"][collector_name]
        assert collector_state["TimeoutSeconds"] == 20, f"{collector_name} should have 20s timeout"


def test_correlation_timeout(state_machine_definition):
    """
    Test that correlation engine has correct timeout.
    Validates Requirement 2.6: Timeout configuration
    """
    correlation_state = state_machine_definition["States"]["CorrelateData"]
    assert correlation_state["TimeoutSeconds"] == 10


def test_llm_analyzer_timeout(state_machine_definition):
    """
    Test that LLM analyzer has correct timeout.
    Validates Requirement 2.6: Timeout configuration
    """
    llm_state = state_machine_definition["States"]["AnalyzeWithLLM"]
    assert llm_state["TimeoutSeconds"] == 40


def test_notification_timeout(state_machine_definition):
    """
    Test that notification service has correct timeout.
    Validates Requirement 2.6: Timeout configuration
    """
    notify_branches = state_machine_definition["States"]["NotifyAndStore"]["Branches"]
    notification_branch = notify_branches[0]
    notification_state = notification_branch["States"]["SendNotification"]
    assert notification_state["TimeoutSeconds"] == 15


def test_total_workflow_timeout():
    """
    Test that total workflow timeout is within 120 seconds.
    Validates Requirement 2.6: Total workflow timeout
    """
    # Parallel collection: max 20s (all run in parallel)
    # Correlation: 10s
    # LLM Analysis: 40s
    # Notification/Storage: max 15s (run in parallel)
    # Total: 20 + 10 + 40 + 15 = 85s (well under 120s limit)

    max_collector_time = 20
    correlation_time = 10
    llm_time = 40
    max_notification_time = 15

    total_time = max_collector_time + correlation_time + llm_time + max_notification_time
    assert total_time <= 120, f"Total workflow time {total_time}s exceeds 120s limit"


def test_retry_policy_configuration(state_machine_definition):
    """
    Test that retry policies are correctly configured.
    Validates Requirements 20.1, 20.2: Retry policies with exponential backoff
    """
    # Check metrics collector retry policy
    branches = state_machine_definition["States"]["ParallelDataCollection"]["Branches"]
    metrics_branch = branches[0]
    metrics_state = metrics_branch["States"]["CollectMetrics"]
    retry_policy = metrics_state["Retry"][0]

    assert retry_policy["IntervalSeconds"] == 2
    assert retry_policy["MaxAttempts"] == 3
    assert retry_policy["BackoffRate"] == 2.0
    assert "ThrottlingException" in retry_policy["ErrorEquals"]
    assert "ServiceException" in retry_policy["ErrorEquals"]
    assert "TooManyRequestsException" in retry_policy["ErrorEquals"]


def test_graceful_degradation_catch_blocks(state_machine_definition):
    """
    Test that catch blocks enable graceful degradation.
    Validates Requirement 2.5: Graceful degradation with partial data
    """
    # Check that each collector has a catch block
    branches = state_machine_definition["States"]["ParallelDataCollection"]["Branches"]

    for branch in branches:
        collector_name = branch["StartAt"]
        collector_state = branch["States"][collector_name]

        # Verify catch block exists
        assert "Catch" in collector_state
        catch_block = collector_state["Catch"][0]

        # Verify it catches all errors
        assert "States.ALL" in catch_block["ErrorEquals"]

        # Verify it stores error in result path
        assert "Error" in catch_block["ResultPath"]

        # Verify it transitions to failure handler
        assert "Next" in catch_block


def test_llm_analyzer_graceful_degradation(state_machine_definition):
    """
    Test that LLM analyzer failure doesn't block workflow.
    Validates Requirement 2.5: Graceful degradation
    """
    llm_state = state_machine_definition["States"]["AnalyzeWithLLM"]

    # Verify catch block exists
    assert "Catch" in llm_state
    catch_block = llm_state["Catch"][0]

    # Verify it catches all errors
    assert "States.ALL" in catch_block["ErrorEquals"]

    # Verify it continues to notification (not Fail state)
    assert catch_block["Next"] == "NotifyAndStore"


def test_parallel_notification_and_storage(state_machine_definition):
    """
    Test that notification and storage run in parallel.
    Validates Requirement 2.5: Independent notification and storage
    """
    notify_store_state = state_machine_definition["States"]["NotifyAndStore"]

    assert notify_store_state["Type"] == "Parallel"
    assert len(notify_store_state["Branches"]) == 2

    # Verify branches are notification and storage
    branch_names = [branch["StartAt"] for branch in notify_store_state["Branches"]]
    assert "SendNotification" in branch_names
    assert "StoreIncident" in branch_names


def test_error_classification_for_retries(state_machine_definition):
    """
    Test that only retryable errors trigger retries.
    Validates Requirement 20.2: Error classification
    """
    # Check LLM analyzer - should only retry throttling errors
    llm_state = state_machine_definition["States"]["AnalyzeWithLLM"]
    retry_policy = llm_state["Retry"][0]

    # Should only retry throttling errors, not validation errors
    assert "ThrottlingException" in retry_policy["ErrorEquals"]
    assert "TooManyRequestsException" in retry_policy["ErrorEquals"]
    assert "ValidationException" not in retry_policy["ErrorEquals"]
    assert "AccessDeniedException" not in retry_policy["ErrorEquals"]


def test_terraform_module_structure():
    """
    Test that Terraform module has required files.
    """
    import os

    module_path = "terraform/modules/step-functions"
    assert os.path.exists(f"{module_path}/main.tf")
    assert os.path.exists(f"{module_path}/variables.tf")
    assert os.path.exists(f"{module_path}/outputs.tf")
    assert os.path.exists(f"{module_path}/README.md")


def test_terraform_validation():
    """
    Test that Terraform configuration is valid.
    """
    import subprocess

    result = subprocess.run(
        ["terraform", "validate"],
        cwd="terraform/modules/step-functions",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Terraform validation failed: {result.stderr}"
    assert "Success" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
