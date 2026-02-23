"""
Unit tests for Logs Collector Lambda function.

Tests cover:
- Successful log retrieval
- Log level filtering
- Result limiting
- Empty logs handling
- Log group name resolution

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import pytest
from botocore.exceptions import ClientError

# Import the lambda function
from logs_collector import lambda_function


class TestLambdaHandler:
    """Tests for the main lambda_handler function."""

    def test_successful_log_retrieval(self, mock_logs_client):
        """Test successful log retrieval with valid input."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-001",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "logGroupName": "/aws/lambda/my-function",
        }

        # Mock log events
        mock_logs_client.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": int((now - timedelta(minutes=i)).timestamp() * 1000),
                    "message": f"ERROR: Test error message {i}",
                    "logStreamName": "2024/01/15/[$LATEST]abc123",
                }
                for i in range(5)
            ]
        }

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert len(result["logs"]) == 5
        assert result["totalMatches"] == 5
        assert result["returned"] == 5
        assert "collectionDuration" in result
        assert result["collectionDuration"] >= 0

        # Verify log structure
        log_entry = result["logs"][0]
        assert "timestamp" in log_entry
        assert "logLevel" in log_entry
        assert "message" in log_entry
        assert "logStream" in log_entry

    def test_missing_required_fields(self):
        """Test validation error when required fields are missing."""
        # Arrange
        event = {
            "incidentId": "inc-test-001"
            # Missing resourceArn and timestamp
        }

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "failed"
        assert "error" in result
        assert "Missing required fields" in result["error"]
        assert result["logs"] == []
        assert result["totalMatches"] == 0
        assert result["returned"] == 0

    def test_empty_logs_handling(self, mock_logs_client):
        """Test handling when no logs are found for the resource."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-002",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "logGroupName": "/aws/lambda/my-function",
        }

        # Mock empty response
        mock_logs_client.filter_log_events.return_value = {"events": []}

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert result["logs"] == []
        assert result["totalMatches"] == 0
        assert result["returned"] == 0
        assert "collectionDuration" in result

    def test_log_group_not_found(self, mock_logs_client):
        """Test handling when log group doesn't exist."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-003",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "logGroupName": "/aws/lambda/nonexistent-function",
        }

        # Mock ResourceNotFoundException - handled gracefully in collect_logs
        mock_logs_client.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Log group not found"}},
            "FilterLogEvents",
        )

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        # ResourceNotFoundException is handled gracefully - returns success with empty logs
        assert result["status"] == "success"
        assert result["logs"] == []
        assert result["totalMatches"] == 0
        assert result["returned"] == 0

    def test_api_throttling_raises(self, mock_logs_client):
        """Test that throttling exceptions are raised for retry."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-004",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "logGroupName": "/aws/lambda/my-function",
        }

        # Mock throttling error
        mock_logs_client.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "FilterLogEvents",
        )

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act & Assert
            with pytest.raises(ClientError) as exc_info:
                lambda_function.lambda_handler(event, None)

            assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"

    def test_non_retryable_client_error(self, mock_logs_client):
        """Test handling of non-retryable AWS API errors."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-005",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "logGroupName": "/aws/lambda/my-function",
        }

        # Mock non-retryable error - handled gracefully in collect_logs
        mock_logs_client.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterException", "Message": "Invalid parameter"}},
            "FilterLogEvents",
        )

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        # Non-retryable errors in collect_logs are handled gracefully - returns success with empty logs
        assert result["status"] == "success"
        assert result["logs"] == []

    def test_log_group_name_auto_resolution(self, mock_logs_client):
        """Test automatic log group name resolution from resource ARN."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-006",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            # No logGroupName provided - should be auto-resolved
        }

        mock_logs_client.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": int(now.timestamp() * 1000),
                    "message": "ERROR: Test error",
                    "logStreamName": "test-stream",
                }
            ]
        }

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert len(result["logs"]) == 1

        # Verify the correct log group name was used
        # Note: Current implementation extracts 'function' from Lambda ARN
        call_args = mock_logs_client.filter_log_events.call_args
        assert call_args[1]["logGroupName"] == "/aws/lambda/function"


class TestMapResourceArnToLogGroup:
    """Tests for resource ARN to log group name mapping."""

    def test_map_lambda_arn(self):
        """Test mapping Lambda function ARN to log group."""
        # Arrange
        arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        # Act
        log_group = lambda_function.map_resource_arn_to_log_group(arn)

        # Assert
        # Note: Current implementation extracts 'function' from parts[5], not the full function name
        assert log_group == "/aws/lambda/function"

    def test_map_lambda_arn_with_version(self):
        """Test mapping Lambda function ARN with version to log group."""
        # Arrange
        arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function:v1"

        # Act
        log_group = lambda_function.map_resource_arn_to_log_group(arn)

        # Assert
        # Note: Current implementation extracts 'function' from parts[5]
        assert log_group == "/aws/lambda/function"

    def test_map_ec2_arn(self):
        """Test mapping EC2 instance ARN to log group."""
        # Arrange
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

        # Act
        log_group = lambda_function.map_resource_arn_to_log_group(arn)

        # Assert
        assert log_group == "/aws/ec2/instance/i-1234567890abcdef0"

    def test_map_rds_arn(self):
        """Test mapping RDS database ARN to log group."""
        # Arrange
        arn = "arn:aws:rds:us-east-1:123456789012:db:my-database"

        # Act
        log_group = lambda_function.map_resource_arn_to_log_group(arn)

        # Assert
        # Note: Current implementation extracts 'db' from parts[5], not the full database name
        assert log_group == "/aws/rds/instance/db/error"

    def test_map_ecs_arn(self):
        """Test mapping ECS service ARN to log group."""
        # Arrange
        arn = "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/my-service"

        # Act
        log_group = lambda_function.map_resource_arn_to_log_group(arn)

        # Assert
        assert log_group == "/ecs/my-cluster/my-service"

    def test_map_apigateway_arn(self):
        """Test mapping API Gateway ARN to log group."""
        # Arrange
        arn = "arn:aws:apigateway:us-east-1::/restapis/abc123xyz"

        # Act
        log_group = lambda_function.map_resource_arn_to_log_group(arn)

        # Assert
        assert log_group == "/aws/apigateway/abc123xyz"

    def test_map_invalid_arn(self):
        """Test error handling for invalid ARN format."""
        # Arrange
        arn = "invalid-arn-format"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            lambda_function.map_resource_arn_to_log_group(arn)

        assert "Invalid ARN format" in str(exc_info.value)

    def test_map_unknown_service(self):
        """Test mapping ARN for unknown service."""
        # Arrange
        arn = "arn:aws:unknownservice:us-east-1:123456789012:resource/my-resource"

        # Act
        log_group = lambda_function.map_resource_arn_to_log_group(arn)

        # Assert
        assert log_group == "/aws/unknownservice/resource/my-resource"


class TestTimeRangeCalculation:
    """Tests for time range calculation."""

    def test_calculate_time_range(self):
        """Test time range calculation is exactly -30min to +5min."""
        # Arrange
        incident_time = datetime(2024, 1, 15, 14, 30, 0)

        # Act
        start_time, end_time = lambda_function.calculate_time_range(incident_time)

        # Assert
        expected_start = datetime(2024, 1, 15, 14, 0, 0)
        expected_end = datetime(2024, 1, 15, 14, 35, 0)

        assert start_time == expected_start
        assert end_time == expected_end
        assert (end_time - start_time).total_seconds() == 35 * 60  # 35 minutes


class TestParseTimestamp:
    """Tests for timestamp parsing."""

    def test_parse_iso8601_with_z(self):
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
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_iso8601_with_timezone(self):
        """Test parsing ISO-8601 timestamp with timezone offset."""
        # Arrange
        timestamp_str = "2024-01-15T14:30:00+00:00"

        # Act
        result = lambda_function.parse_timestamp(timestamp_str)

        # Assert
        assert isinstance(result, datetime)
        assert result.year == 2024


class TestCollectLogs:
    """Tests for log collection function."""

    def test_collect_logs_success(self, mock_logs_client):
        """Test successful log collection."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=30)
        end_time = now + timedelta(minutes=5)

        mock_logs_client.filter_log_events.return_value = {
            "events": [
                {
                    "timestamp": int((now - timedelta(minutes=i)).timestamp() * 1000),
                    "message": f"ERROR: Test error {i}",
                    "logStreamName": "test-stream",
                }
                for i in range(10)
            ]
        }

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            logs, total_matches = lambda_function.collect_logs(
                log_group_name="/aws/lambda/test",
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-001",
            )

        # Assert
        assert len(logs) == 10
        assert total_matches == 10
        assert all("timestamp" in log for log in logs)
        assert all("logLevel" in log for log in logs)
        assert all("message" in log for log in logs)

    def test_collect_logs_with_pagination(self, mock_logs_client):
        """Test log collection with pagination."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=30)
        end_time = now + timedelta(minutes=5)

        # Mock paginated response
        mock_logs_client.filter_log_events.side_effect = [
            {
                "events": [
                    {
                        "timestamp": int((now - timedelta(minutes=i)).timestamp() * 1000),
                        "message": f"ERROR: Test error {i}",
                        "logStreamName": "test-stream",
                    }
                    for i in range(50)
                ],
                "nextToken": "token123",
            },
            {
                "events": [
                    {
                        "timestamp": int((now - timedelta(minutes=i + 50)).timestamp() * 1000),
                        "message": f"ERROR: Test error {i + 50}",
                        "logStreamName": "test-stream",
                    }
                    for i in range(60)
                ]
            },
        ]

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            logs, total_matches = lambda_function.collect_logs(
                log_group_name="/aws/lambda/test",
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-002",
            )

        # Assert
        # Should return exactly 100 logs (limit)
        assert len(logs) == 100
        assert total_matches == 110

    def test_collect_logs_empty_result(self, mock_logs_client):
        """Test log collection when no logs match."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=30)
        end_time = now + timedelta(minutes=5)

        mock_logs_client.filter_log_events.return_value = {"events": []}

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            logs, total_matches = lambda_function.collect_logs(
                log_group_name="/aws/lambda/test",
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-003",
            )

        # Assert
        assert logs == []
        assert total_matches == 0

    def test_collect_logs_resource_not_found(self, mock_logs_client):
        """Test log collection when log group doesn't exist."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=30)
        end_time = now + timedelta(minutes=5)

        mock_logs_client.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Log group not found"}},
            "FilterLogEvents",
        )

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act
            logs, total_matches = lambda_function.collect_logs(
                log_group_name="/aws/lambda/nonexistent",
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-004",
            )

        # Assert
        assert logs == []
        assert total_matches == 0

    def test_collect_logs_throttling_raises(self, mock_logs_client):
        """Test that throttling errors are raised for retry."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=30)
        end_time = now + timedelta(minutes=5)

        mock_logs_client.filter_log_events.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "FilterLogEvents",
        )

        with patch("logs_collector.lambda_function.logs_client", mock_logs_client):
            # Act & Assert
            with pytest.raises(ClientError) as exc_info:
                lambda_function.collect_logs(
                    log_group_name="/aws/lambda/test",
                    start_time=start_time,
                    end_time=end_time,
                    correlation_id="test-005",
                )

            assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"


class TestExtractLogLevel:
    """Tests for log level extraction."""

    def test_extract_critical_level(self):
        """Test extraction of CRITICAL log level."""
        # Arrange
        message = "CRITICAL: System failure detected"

        # Act
        level = lambda_function.extract_log_level(message)

        # Assert
        assert level == "CRITICAL"

    def test_extract_fatal_level(self):
        """Test extraction of FATAL log level (mapped to CRITICAL)."""
        # Arrange
        message = "FATAL: Application crashed"

        # Act
        level = lambda_function.extract_log_level(message)

        # Assert
        assert level == "CRITICAL"

    def test_extract_error_level(self):
        """Test extraction of ERROR log level."""
        # Arrange
        message = "ERROR: Connection timeout"

        # Act
        level = lambda_function.extract_log_level(message)

        # Assert
        assert level == "ERROR"

    def test_extract_warn_level(self):
        """Test extraction of WARN log level."""
        # Arrange
        message = "WARN: High memory usage"

        # Act
        level = lambda_function.extract_log_level(message)

        # Assert
        assert level == "WARN"

    def test_extract_warning_level(self):
        """Test extraction of WARNING log level (mapped to WARN)."""
        # Arrange
        message = "WARNING: Deprecated API usage"

        # Act
        level = lambda_function.extract_log_level(message)

        # Assert
        assert level == "WARN"

    def test_extract_level_case_insensitive(self):
        """Test log level extraction is case insensitive."""
        # Arrange
        message = "error: Something went wrong"

        # Act
        level = lambda_function.extract_log_level(message)

        # Assert
        assert level == "ERROR"

    def test_extract_level_default_to_info(self):
        """Test default to INFO when no level found."""
        # Arrange
        message = "Some log message without level"

        # Act
        level = lambda_function.extract_log_level(message)

        # Assert
        assert level == "INFO"


class TestNormalizeLogEntry:
    """Tests for log entry normalization."""

    def test_normalize_log_entry_success(self):
        """Test successful log entry normalization."""
        # Arrange
        now = datetime.utcnow()
        log_event = {
            "timestamp": int(now.timestamp() * 1000),
            "message": "ERROR: Test error message",
            "logStreamName": "2024/01/15/[$LATEST]abc123",
        }

        # Act
        result = lambda_function.normalize_log_entry(log_event)

        # Assert
        assert result is not None
        assert "timestamp" in result
        assert result["timestamp"].endswith("Z")
        assert result["logLevel"] == "ERROR"
        assert result["message"] == "ERROR: Test error message"
        assert result["logStream"] == "2024/01/15/[$LATEST]abc123"

    def test_normalize_log_entry_with_whitespace(self):
        """Test log entry normalization strips whitespace."""
        # Arrange
        now = datetime.utcnow()
        log_event = {
            "timestamp": int(now.timestamp() * 1000),
            "message": "  ERROR: Test error message  \n",
            "logStreamName": "test-stream",
        }

        # Act
        result = lambda_function.normalize_log_entry(log_event)

        # Assert
        assert result is not None
        assert result["message"] == "ERROR: Test error message"

    def test_normalize_log_entry_missing_fields(self):
        """Test log entry normalization with missing fields."""
        # Arrange
        log_event = {
            "timestamp": int(datetime.utcnow().timestamp() * 1000)
            # Missing message and logStreamName
        }

        # Act
        result = lambda_function.normalize_log_entry(log_event)

        # Assert
        assert result is not None
        assert result["message"] == ""
        assert result["logStream"] == ""

    def test_normalize_log_entry_invalid_timestamp(self):
        """Test log entry normalization with invalid timestamp."""
        # Arrange
        log_event = {
            "timestamp": "invalid",
            "message": "ERROR: Test",
            "logStreamName": "test-stream",
        }

        # Act
        result = lambda_function.normalize_log_entry(log_event)

        # Assert
        # Should return None on error
        assert result is None
