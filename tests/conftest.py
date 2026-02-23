"""
Pytest configuration and shared fixtures for AI-SRE Incident Analysis System tests.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import MagicMock

import pytest
from hypothesis import settings, Verbosity

# Hypothesis profiles for property-based testing
settings.register_profile("dev", max_examples=20, verbosity=Verbosity.normal)
settings.register_profile("ci", max_examples=100, verbosity=Verbosity.verbose)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture
def sample_incident_event() -> Dict[str, Any]:
    """Sample CloudWatch Alarm event for testing."""
    return {
        "version": "0",
        "id": "test-event-id-123",
        "detail-type": "CloudWatch Alarm State Change",
        "source": "aws.cloudwatch",
        "account": "123456789012",
        "time": datetime.utcnow().isoformat() + "Z",
        "region": "us-east-1",
        "resources": ["arn:aws:cloudwatch:us-east-1:123456789012:alarm:test-alarm"],
        "detail": {
            "alarmName": "test-high-cpu-alarm",
            "state": {
                "value": "ALARM",
                "reason": "Threshold Crossed: 1 datapoint [75.0] was greater than the threshold (50.0).",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            "previousState": {
                "value": "OK",
                "timestamp": (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z",
            },
            "configuration": {
                "description": "Test alarm for high CPU utilization",
                "metrics": [
                    {
                        "id": "m1",
                        "metricStat": {
                            "metric": {
                                "namespace": "AWS/EC2",
                                "name": "CPUUtilization",
                                "dimensions": {"InstanceId": "i-1234567890abcdef0"},
                            },
                            "period": 60,
                            "stat": "Average",
                        },
                        "returnData": True,
                    }
                ],
            },
        },
    }


@pytest.fixture
def sample_metrics_data() -> Dict[str, Any]:
    """Sample CloudWatch metrics data for testing."""
    now = datetime.utcnow()
    return {
        "status": "success",
        "metrics": [
            {
                "metricName": "CPUUtilization",
                "namespace": "AWS/EC2",
                "datapoints": [
                    {
                        "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                        "value": 50.0 + (i * 5.0),
                        "unit": "Percent",
                    }
                    for i in range(10)
                ],
                "statistics": {"avg": 75.0, "max": 95.0, "min": 50.0},
            }
        ],
        "collectionDuration": 1.2,
    }


@pytest.fixture
def sample_logs_data() -> Dict[str, Any]:
    """Sample CloudWatch Logs data for testing."""
    now = datetime.utcnow()
    return {
        "status": "success",
        "logs": [
            {
                "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                "logLevel": "ERROR",
                "message": f"Test error message {i}",
                "logStream": "2024/01/15/[$LATEST]abc123",
            }
            for i in range(5)
        ],
        "totalMatches": 5,
        "returned": 5,
        "collectionDuration": 2.5,
    }


@pytest.fixture
def sample_deploy_context_data() -> Dict[str, Any]:
    """Sample deployment context data for testing."""
    now = datetime.utcnow()
    return {
        "status": "success",
        "changes": [
            {
                "timestamp": (now - timedelta(hours=2)).isoformat() + "Z",
                "changeType": "deployment",
                "eventName": "UpdateFunctionCode",
                "user": "arn:aws:iam::123456789012:user/deployer",
                "description": "Lambda function code updated",
            }
        ],
        "collectionDuration": 3.1,
    }


@pytest.fixture
def sample_structured_context() -> Dict[str, Any]:
    """Sample structured context after correlation for testing."""
    now = datetime.utcnow()
    return {
        "incidentId": "inc-test-001",
        "timestamp": now.isoformat() + "Z",
        "resource": {
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "type": "ec2",
            "name": "test-instance",
        },
        "alarm": {"name": "test-high-cpu-alarm", "metric": "CPUUtilization", "threshold": 50.0},
        "metrics": {
            "summary": {"avgCPU": 75.0, "maxCPU": 95.0},
            "timeSeries": [],
        },
        "logs": {
            "errorCount": 5,
            "topErrors": ["Test error message"],
            "entries": [],
        },
        "changes": {
            "recentDeployments": 1,
            "lastDeployment": (now - timedelta(hours=2)).isoformat() + "Z",
            "entries": [],
        },
        "completeness": {"metrics": True, "logs": True, "changes": True},
    }


@pytest.fixture
def sample_analysis_report() -> Dict[str, Any]:
    """Sample LLM analysis report for testing."""
    now = datetime.utcnow()
    return {
        "incidentId": "inc-test-001",
        "timestamp": now.isoformat() + "Z",
        "analysis": {
            "rootCauseHypothesis": "High CPU utilization due to resource-intensive process",
            "confidence": "high",
            "evidence": [
                "CPU spiked to 95% at incident time",
                "Recent deployment 2 hours before incident",
            ],
            "contributingFactors": ["Undersized instance type", "No auto-scaling configured"],
            "recommendedActions": [
                "Check running processes",
                "Review recent deployment",
                "Consider instance upgrade",
            ],
        },
        "metadata": {
            "modelId": "anthropic.claude-v2",
            "modelVersion": "2.1",
            "promptVersion": "v1.0",
            "tokenUsage": {"input": 1200, "output": 250},
            "latency": 2.3,
        },
    }


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 client for AWS service testing."""
    mock_client = MagicMock()
    return mock_client


@pytest.fixture
def mock_cloudwatch_client(mock_boto3_client):
    """Mock CloudWatch client with common methods."""
    mock_boto3_client.get_metric_statistics.return_value = {
        "Datapoints": [{"Timestamp": datetime.utcnow(), "Average": 75.0, "Unit": "Percent"}]
    }
    return mock_boto3_client


@pytest.fixture
def mock_logs_client(mock_boto3_client):
    """Mock CloudWatch Logs client with common methods."""
    mock_boto3_client.filter_log_events.return_value = {
        "events": [
            {
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
                "message": "ERROR: Test error message",
                "logStreamName": "test-stream",
            }
        ]
    }
    return mock_boto3_client


@pytest.fixture
def mock_cloudtrail_client(mock_boto3_client):
    """Mock CloudTrail client with common methods."""
    mock_boto3_client.lookup_events.return_value = {
        "Events": [
            {
                "EventTime": datetime.utcnow(),
                "EventName": "StartInstances",
                "Username": "test-user",
                "Resources": [{"ResourceName": "i-1234567890abcdef0"}],
            }
        ]
    }
    return mock_boto3_client


@pytest.fixture
def mock_bedrock_client(mock_boto3_client):
    """Mock Bedrock client with common methods."""
    mock_boto3_client.invoke_model.return_value = {
        "body": MagicMock(
            read=lambda: json.dumps(
                {
                    "completion": json.dumps(
                        {
                            "rootCauseHypothesis": "Test hypothesis",
                            "confidence": "high",
                            "evidence": ["Test evidence"],
                            "contributingFactors": ["Test factor"],
                            "recommendedActions": ["Test action"],
                        }
                    )
                }
            ).encode()
        )
    }
    return mock_boto3_client


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables before each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)
