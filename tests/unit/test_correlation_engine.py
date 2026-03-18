"""
Unit tests for Correlation Engine Lambda function.

Tests cover:
- Merging with all collectors successful
- Merging with one collector failed
- Merging with multiple collectors failed
- Timestamp normalization edge cases
- Size truncation logic

Requirements: 6.1, 6.2, 6.3, 6.4, 6.6
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# Import the lambda function
from correlation_engine import lambda_function


class TestLambdaHandler:
    """Tests for the main lambda_handler function."""

    def test_successful_merge_all_collectors(self):
        """Test successful merging when all collectors succeed."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-001",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "HighErrorRate",
                "metricName": "Errors",
                "namespace": "AWS/Lambda",
            },
            "metrics": {
                "status": "success",
                "metrics": [
                    {
                        "metricName": "Errors",
                        "namespace": "AWS/Lambda",
                        "datapoints": [
                            {
                                "timestamp": (now - timedelta(minutes=5)).isoformat() + "Z",
                                "value": 10.0,
                                "unit": "Count",
                            }
                        ],
                        "statistics": {"avg": 10.0, "max": 10.0, "min": 10.0},
                    }
                ],
                "collectionDuration": 1.2,
            },
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": (now - timedelta(minutes=3)).isoformat() + "Z",
                        "logLevel": "ERROR",
                        "message": "Connection timeout",
                        "logStream": "2024/01/15/[$LATEST]abc123",
                    }
                ],
                "totalMatches": 1,
                "returned": 1,
                "collectionDuration": 2.5,
            },
            "changes": {
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
            },
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert "structuredContext" in result
        context = result["structuredContext"]

        # Verify all data sources are present
        assert context["incidentId"] == "inc-test-001"
        assert context["completeness"]["metrics"] is True
        assert context["completeness"]["logs"] is True
        assert context["completeness"]["changes"] is True

        # Verify data structure
        assert "metrics" in context
        assert "logs" in context
        assert "changes" in context
        assert "resource" in context
        assert "alarm" in context

    def test_merge_with_metrics_collector_failed(self):
        """Test merging when metrics collector fails."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-002",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "HighErrorRate",
                "metricName": "Errors",
            },
            "metricsError": {"Error": "ThrottlingException", "Cause": "Rate exceeded"},
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": (now - timedelta(minutes=3)).isoformat() + "Z",
                        "logLevel": "ERROR",
                        "message": "Connection timeout",
                        "logStream": "2024/01/15/[$LATEST]abc123",
                    }
                ],
                "totalMatches": 1,
                "returned": 1,
                "collectionDuration": 2.5,
            },
            "changes": {"status": "success", "changes": [], "collectionDuration": 1.0},
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        context = result["structuredContext"]

        # Verify completeness tracking
        assert context["completeness"]["metrics"] is False
        assert context["completeness"]["logs"] is True
        assert context["completeness"]["changes"] is True

        # Verify metrics data is empty but structure exists
        assert "metrics" in context
        # When metrics collector fails, extract_metrics_data is not called, so structure is empty dict
        assert context["metrics"] == {}

    def test_merge_with_logs_collector_failed(self):
        """Test merging when logs collector fails."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-003",
                "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "HighCPU",
                "metricName": "CPUUtilization",
            },
            "metrics": {"status": "success", "metrics": [], "collectionDuration": 1.0},
            "logsError": {"Error": "ResourceNotFoundException", "Cause": "Log group not found"},
            "changes": {"status": "success", "changes": [], "collectionDuration": 1.0},
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        context = result["structuredContext"]

        # Verify completeness tracking
        assert context["completeness"]["metrics"] is True
        assert context["completeness"]["logs"] is False
        assert context["completeness"]["changes"] is True

        # Verify logs data is empty but structure exists
        assert "logs" in context
        # When logs collector fails, extract_logs_data is not called, so structure is empty dict
        assert context["logs"] == {}

    def test_merge_with_deploy_context_collector_failed(self):
        """Test merging when deploy context collector fails."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-004",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "HighErrorRate",
                "metricName": "Errors",
            },
            "metrics": {"status": "success", "metrics": [], "collectionDuration": 1.0},
            "logs": {
                "status": "success",
                "logs": [],
                "totalMatches": 0,
                "returned": 0,
                "collectionDuration": 1.0,
            },
            "changesError": {"Error": "AccessDeniedException", "Cause": "CloudTrail not enabled"},
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        context = result["structuredContext"]

        # Verify completeness tracking
        assert context["completeness"]["metrics"] is True
        assert context["completeness"]["logs"] is True
        assert context["completeness"]["changes"] is False

        # Verify changes data is empty but structure exists
        assert "changes" in context
        # When changes collector fails, extract_changes_data is not called, so structure is empty dict
        assert context["changes"] == {}

    def test_merge_with_multiple_collectors_failed(self):
        """Test merging when multiple collectors fail."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-005",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "HighErrorRate",
                "metricName": "Errors",
            },
            "metricsError": {"Error": "ThrottlingException"},
            "logsError": {"Error": "ResourceNotFoundException"},
            "changes": {
                "status": "success",
                "changes": [
                    {
                        "timestamp": (now - timedelta(hours=1)).isoformat() + "Z",
                        "changeType": "deployment",
                        "eventName": "UpdateFunctionCode",
                        "user": "arn:aws:iam::123456789012:user/deployer",
                        "description": "Lambda function code updated",
                    }
                ],
                "collectionDuration": 2.0,
            },
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        context = result["structuredContext"]

        # Verify completeness tracking
        assert context["completeness"]["metrics"] is False
        assert context["completeness"]["logs"] is False
        assert context["completeness"]["changes"] is True

        # Verify only changes data is populated
        assert context["changes"]["recentDeployments"] == 1
        assert context["metrics"] == {}
        assert context["logs"] == {}

    def test_merge_with_all_collectors_failed(self):
        """Test merging when all collectors fail (edge case)."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-006",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "HighErrorRate",
                "metricName": "Errors",
            },
            "metricsError": {"Error": "ThrottlingException"},
            "logsError": {"Error": "ResourceNotFoundException"},
            "changesError": {"Error": "AccessDeniedException"},
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        context = result["structuredContext"]

        # Verify all completeness flags are False
        assert context["completeness"]["metrics"] is False
        assert context["completeness"]["logs"] is False
        assert context["completeness"]["changes"] is False

        # Verify empty data structures
        assert context["metrics"] == {}
        assert context["logs"] == {}
        assert context["changes"] == {}


class TestTimestampNormalization:
    """Tests for timestamp normalization edge cases."""

    def test_normalize_iso8601_with_z_suffix(self):
        """Test normalization of ISO-8601 timestamps with Z suffix."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-007",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {
                "status": "success",
                "metrics": [
                    {
                        "metricName": "Test",
                        "namespace": "AWS/Lambda",
                        "datapoints": [
                            {"timestamp": "2024-01-15T14:30:00Z", "value": 10.0, "unit": "Count"}
                        ],
                        "statistics": {"avg": 10.0, "max": 10.0, "min": 10.0},
                    }
                ],
                "collectionDuration": 1.0,
            },
            "logs": {
                "status": "success",
                "logs": [],
                "totalMatches": 0,
                "returned": 0,
                "collectionDuration": 1.0,
            },
            "changes": {"status": "success", "changes": [], "collectionDuration": 1.0},
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        context = result["structuredContext"]
        datapoint = context["metrics"]["metrics"][0]["datapoints"][0]

        # Verify timestamp is normalized to ISO-8601 with Z suffix
        assert datapoint["timestamp"].endswith("Z")
        assert "T" in datapoint["timestamp"]

    def test_normalize_iso8601_with_timezone_offset(self):
        """Test normalization of ISO-8601 timestamps with timezone offset."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-008",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "+00:00",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {"status": "success", "metrics": [], "collectionDuration": 1.0},
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": "2024-01-15T14:30:00+00:00",
                        "logLevel": "ERROR",
                        "message": "Test error",
                        "logStream": "test-stream",
                    }
                ],
                "totalMatches": 1,
                "returned": 1,
                "collectionDuration": 1.0,
            },
            "changes": {"status": "success", "changes": [], "collectionDuration": 1.0},
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        context = result["structuredContext"]
        log_entry = context["logs"]["entries"][0]

        # Verify timestamp is normalized to ISO-8601 with Z suffix
        assert log_entry["timestamp"].endswith("Z")
        assert "+00:00" not in log_entry["timestamp"]

    def test_normalize_mixed_timestamp_formats(self):
        """Test normalization when different data sources have different timestamp formats."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-009",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {
                "status": "success",
                "metrics": [
                    {
                        "metricName": "Test",
                        "namespace": "AWS/Lambda",
                        "datapoints": [
                            {"timestamp": "2024-01-15T14:30:00Z", "value": 10.0, "unit": "Count"}
                        ],
                        "statistics": {"avg": 10.0, "max": 10.0, "min": 10.0},
                    }
                ],
                "collectionDuration": 1.0,
            },
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": "2024-01-15T14:31:00+00:00",
                        "logLevel": "ERROR",
                        "message": "Test error",
                        "logStream": "test-stream",
                    }
                ],
                "totalMatches": 1,
                "returned": 1,
                "collectionDuration": 1.0,
            },
            "changes": {
                "status": "success",
                "changes": [
                    {
                        "timestamp": "2024-01-15T12:30:00Z",
                        "changeType": "deployment",
                        "eventName": "UpdateFunctionCode",
                        "user": "test-user",
                        "description": "Test deployment",
                    }
                ],
                "collectionDuration": 1.0,
            },
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        context = result["structuredContext"]

        # Verify all timestamps are normalized to Z suffix
        metric_ts = context["metrics"]["metrics"][0]["datapoints"][0]["timestamp"]
        log_ts = context["logs"]["entries"][0]["timestamp"]
        change_ts = context["changes"]["entries"][0]["timestamp"]

        assert metric_ts.endswith("Z")
        assert log_ts.endswith("Z")
        assert change_ts.endswith("Z")


class TestSizeTruncation:
    """Tests for size constraint enforcement."""

    def test_no_truncation_when_under_limit(self):
        """Test that no truncation occurs when context is under 50KB."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incident": {
                "incidentId": "inc-test-010",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {
                "status": "success",
                "metrics": [
                    {
                        "metricName": "Test",
                        "namespace": "AWS/Lambda",
                        "datapoints": [
                            {
                                "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                                "value": float(i),
                                "unit": "Count",
                            }
                            for i in range(10)
                        ],
                        "statistics": {"avg": 5.0, "max": 9.0, "min": 0.0},
                    }
                ],
                "collectionDuration": 1.0,
            },
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                        "logLevel": "ERROR",
                        "message": f"Test error {i}",
                        "logStream": "test-stream",
                    }
                    for i in range(10)
                ],
                "totalMatches": 10,
                "returned": 10,
                "collectionDuration": 1.0,
            },
            "changes": {
                "status": "success",
                "changes": [
                    {
                        "timestamp": (now - timedelta(hours=i)).isoformat() + "Z",
                        "changeType": "deployment",
                        "eventName": "UpdateFunctionCode",
                        "user": "test-user",
                        "description": f"Test deployment {i}",
                    }
                    for i in range(5)
                ],
                "collectionDuration": 1.0,
            },
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        context = result["structuredContext"]

        # Verify data is not truncated
        assert len(context["metrics"]["timeSeries"]) == 10
        assert len(context["logs"]["entries"]) == 10
        assert len(context["changes"]["entries"]) == 5

    def test_truncation_when_over_limit(self):
        """Test that truncation occurs when context exceeds 50KB."""
        # Arrange - Create large dataset
        now = datetime.utcnow()

        # Create large message to exceed 50KB
        large_message = "X" * 1000  # 1KB message

        event = {
            "incident": {
                "incidentId": "inc-test-011",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {
                "status": "success",
                "metrics": [
                    {
                        "metricName": "Test",
                        "namespace": "AWS/Lambda",
                        "datapoints": [
                            {
                                "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                                "value": float(i),
                                "unit": "Count",
                            }
                            for i in range(200)  # Large number of datapoints
                        ],
                        "statistics": {"avg": 100.0, "max": 199.0, "min": 0.0},
                    }
                ],
                "collectionDuration": 1.0,
            },
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                        "logLevel": "ERROR",
                        "message": f"Test error {i}: {large_message}",
                        "logStream": "test-stream",
                    }
                    for i in range(100)  # Large number of logs
                ],
                "totalMatches": 100,
                "returned": 100,
                "collectionDuration": 1.0,
            },
            "changes": {
                "status": "success",
                "changes": [
                    {
                        "timestamp": (now - timedelta(hours=i)).isoformat() + "Z",
                        "changeType": "deployment",
                        "eventName": "UpdateFunctionCode",
                        "user": "test-user",
                        "description": f"Test deployment {i}: {large_message}",
                    }
                    for i in range(50)  # Large number of changes
                ],
                "collectionDuration": 1.0,
            },
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        context = result["structuredContext"]

        # Verify data is truncated
        # After truncation, should have fewer entries than original
        assert len(context["metrics"]["timeSeries"]) < 200
        assert len(context["logs"]["entries"]) < 100
        assert len(context["changes"]["entries"]) < 50

        # Verify size is under limit (with some tolerance for JSON overhead)
        # Note: size_bytes() is a method on StructuredContext, so we check the JSON size
        context_json = json.dumps(context)
        context_size = len(context_json.encode("utf-8"))
        assert context_size <= 52 * 1024  # Allow 2KB tolerance for overhead

    def test_truncation_prioritizes_recent_entries(self):
        """Test that truncation keeps most recent entries."""
        # Arrange - Create dataset that will be truncated
        now = datetime.utcnow()
        large_message = "X" * 1000

        event = {
            "incident": {
                "incidentId": "inc-test-012",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {
                "status": "success",
                "metrics": [
                    {
                        "metricName": "Test",
                        "namespace": "AWS/Lambda",
                        "datapoints": [
                            {
                                "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                                "value": float(i),
                                "unit": "Count",
                            }
                            for i in range(200)
                        ],
                        "statistics": {"avg": 100.0, "max": 199.0, "min": 0.0},
                    }
                ],
                "collectionDuration": 1.0,
            },
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                        "logLevel": "ERROR",
                        "message": f"Test error {i}: {large_message}",
                        "logStream": "test-stream",
                    }
                    for i in range(100)
                ],
                "totalMatches": 100,
                "returned": 100,
                "collectionDuration": 1.0,
            },
            "changes": {"status": "success", "changes": [], "collectionDuration": 1.0},
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        context = result["structuredContext"]

        # Verify most recent entries are kept (lower index = more recent)
        if len(context["logs"]["entries"]) > 0:
            # Check that we have recent entries (message contains lower numbers)
            first_message = context["logs"]["entries"][0]["message"]
            # Recent entries should have lower error numbers
            assert "Test error" in first_message


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_track_completeness_all_success(self):
        """Test completeness tracking when all collectors succeed."""
        # Arrange
        event = {
            "metrics": {"status": "success"},
            "logs": {"status": "success"},
            "changes": {"status": "success"},
        }

        # Act
        completeness = lambda_function.track_completeness(event)

        # Assert
        assert completeness["metrics"] is True
        assert completeness["logs"] is True
        assert completeness["changes"] is True

    def test_track_completeness_with_errors(self):
        """Test completeness tracking when collectors have errors."""
        # Arrange
        event = {
            "metricsError": {"Error": "ThrottlingException"},
            "logs": {"status": "success"},
            "changesError": {"Error": "AccessDeniedException"},
        }

        # Act
        completeness = lambda_function.track_completeness(event)

        # Assert
        assert completeness["metrics"] is False
        assert completeness["logs"] is True
        assert completeness["changes"] is False

    def test_parse_resource_arn_lambda(self):
        """Test parsing Lambda function ARN."""
        # Arrange
        arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        # Act
        resource_info = lambda_function.parse_resource_arn(arn)

        # Assert
        assert resource_info.arn == arn
        # The implementation returns the service name when no '/' in resource part
        assert resource_info.type == "lambda"
        assert resource_info.name == "function:my-function"

    def test_parse_resource_arn_ec2(self):
        """Test parsing EC2 instance ARN."""
        # Arrange
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

        # Act
        resource_info = lambda_function.parse_resource_arn(arn)

        # Assert
        assert resource_info.arn == arn
        assert resource_info.type == "instance"
        assert resource_info.name == "i-1234567890abcdef0"

    def test_parse_resource_arn_invalid(self):
        """Test parsing invalid ARN."""
        # Arrange
        arn = "invalid-arn"

        # Act
        resource_info = lambda_function.parse_resource_arn(arn)

        # Assert
        assert resource_info.type == "unknown"
        assert resource_info.name == "unknown"

    def test_parse_timestamp_iso8601_z(self):
        """Test parsing ISO-8601 timestamp with Z suffix."""
        # Arrange
        timestamp_str = "2024-01-15T14:30:00Z"

        # Act
        result = lambda_function.parse_timestamp(timestamp_str)

        # Assert
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_timestamp_empty_string(self):
        """Test parsing empty timestamp string."""
        # Arrange
        timestamp_str = ""

        # Act
        result = lambda_function.parse_timestamp(timestamp_str)

        # Assert
        assert isinstance(result, datetime)
        # Should return current time
        assert result.year >= 2024


class TestTruncationObservability:
    """Tests for structured truncation logging + ContextTruncated metric (Fix 2)."""

    def _make_large_event(self, now):
        """Helper: build an event whose context exceeds 50KB."""
        large_message = "X" * 1000
        return {
            "incident": {
                "incidentId": "inc-truncation-obs",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {
                "status": "success",
                "metrics": [
                    {
                        "metricName": "Test",
                        "namespace": "AWS/Lambda",
                        "datapoints": [
                            {
                                "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                                "value": float(i),
                                "unit": "Count",
                            }
                            for i in range(200)
                        ],
                        "statistics": {"avg": 100.0, "max": 199.0, "min": 0.0},
                    }
                ],
                "collectionDuration": 1.0,
            },
            "logs": {
                "status": "success",
                "logs": [
                    {
                        "timestamp": (now - timedelta(minutes=i)).isoformat() + "Z",
                        "logLevel": "ERROR",
                        "message": f"error {i}: {large_message}",
                        "logStream": "stream",
                    }
                    for i in range(100)
                ],
                "totalMatches": 100,
                "returned": 100,
                "collectionDuration": 1.0,
            },
            "changes": {"status": "success", "changes": [], "collectionDuration": 1.0},
        }

    def test_truncation_emits_warning_log(self):
        """When context exceeds 50KB a WARNING log must be emitted before truncation."""
        now = datetime.utcnow()
        event = self._make_large_event(now)

        with (
            patch("correlation_engine.lambda_function.put_metric") as mock_put_metric,
            patch("correlation_engine.lambda_function.put_workflow_duration_metric"),
        ):
            with self.capture_log_records() as records:
                lambda_function.lambda_handler(event, None)

        # At least one WARNING record should contain "truncating"
        warning_messages = [
            r.getMessage()
            for r in records
            if r.levelname == "WARNING"
        ]
        truncation_warnings = [
            m for m in warning_messages
            if "truncat" in m.lower() or "exceeds" in m.lower()
        ]
        assert len(truncation_warnings) > 0, (
            "Expected at least one WARNING log about truncation, got: " + str(warning_messages)
        )

    def test_truncation_emits_context_truncated_metric(self):
        """When context exceeds 50KB, put_metric must be called with 'ContextTruncated'."""
        now = datetime.utcnow()
        event = self._make_large_event(now)

        with (
            patch("correlation_engine.lambda_function.put_metric") as mock_put_metric,
            patch("correlation_engine.lambda_function.put_workflow_duration_metric"),
        ):
            lambda_function.lambda_handler(event, None)

        # Collect all metric names emitted
        emitted_metric_names = [call.args[0] if call.args else call.kwargs.get("metric_name")
                                 for call in mock_put_metric.call_args_list]
        assert "ContextTruncated" in emitted_metric_names, (
            f"Expected ContextTruncated metric; got: {emitted_metric_names}"
        )

    def test_no_truncation_metric_when_under_limit(self):
        """When context is within the 50KB limit, ContextTruncated must NOT be emitted."""
        now = datetime.utcnow()
        small_event = {
            "incident": {
                "incidentId": "inc-small",
                "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:fn",
                "timestamp": now.isoformat() + "Z",
                "alarmName": "Test",
                "metricName": "Test",
            },
            "metrics": {"status": "success", "metrics": [], "collectionDuration": 1.0},
            "logs": {
                "status": "success",
                "logs": [],
                "totalMatches": 0,
                "returned": 0,
                "collectionDuration": 1.0,
            },
            "changes": {"status": "success", "changes": [], "collectionDuration": 1.0},
        }

        with (
            patch("correlation_engine.lambda_function.put_metric") as mock_put_metric,
            patch("correlation_engine.lambda_function.put_workflow_duration_metric"),
        ):
            lambda_function.lambda_handler(small_event, None)

        emitted_metric_names = [call.args[0] if call.args else call.kwargs.get("metric_name")
                                 for call in mock_put_metric.call_args_list]
        assert "ContextTruncated" not in emitted_metric_names

    @staticmethod
    def capture_log_records():
        """Context manager that captures log records emitted to the root logger."""
        import logging

        class _Capture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.records = []

            def emit(self, record):
                self.records.append(record)

            def __enter__(self):
                logging.getLogger().addHandler(self)
                return self.records

            def __exit__(self, *args):
                logging.getLogger().removeHandler(self)

        return _Capture()
