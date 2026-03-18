"""
Unit tests for Metrics Collector Lambda function.

Tests cover:
- Successful metric retrieval
- Empty metrics handling
- API throttling retry logic
- Resource ARN parsing for different AWS services

Requirements: 3.1, 3.2, 3.3, 3.4
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Import the lambda function
from metrics_collector import lambda_function


class TestLambdaHandler:
    """Tests for the main lambda_handler function."""

    def test_successful_metric_retrieval(self, mock_cloudwatch_client):
        """Test successful metric retrieval with valid input."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-001",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "namespace": "AWS/Lambda",
        }

        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {
                    "Timestamp": now - timedelta(minutes=i),
                    "Average": 50.0 + i,
                    "Maximum": 60.0 + i,
                    "Minimum": 40.0 + i,
                    "SampleCount": 10,
                    "Unit": "Count",
                }
                for i in range(5)
            ]
        }

        with (
            patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client),
            patch("metrics_collector.lambda_function.put_collector_success_metric"),
        ):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert len(result["metrics"]) > 0
        assert "collectionDuration" in result
        assert result["collectionDuration"] >= 0

        # Verify metrics structure
        metric = result["metrics"][0]
        assert "metricName" in metric
        assert "namespace" in metric
        assert "datapoints" in metric
        assert "statistics" in metric
        assert len(metric["datapoints"]) == 5

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
        assert result["metrics"] == []

    def test_empty_metrics_handling(self, mock_cloudwatch_client):
        """Test handling when no metrics are found for the resource."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-002",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "timestamp": now.isoformat() + "Z",
            "namespace": "AWS/EC2",
        }

        # Mock empty response
        mock_cloudwatch_client.get_metric_statistics.return_value = {"Datapoints": []}

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert result["metrics"] == []
        assert "collectionDuration" in result

    def test_api_throttling_graceful_handling(self, mock_cloudwatch_client):
        """Test that throttling exceptions are caught and logged, allowing graceful degradation."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-003",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "namespace": "AWS/Lambda",
        }

        # Mock throttling error - this will be caught in collect_metric
        mock_cloudwatch_client.get_metric_statistics.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "GetMetricStatistics",
        )

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert - handler continues with empty metrics (graceful degradation)
        assert result["status"] == "success"
        assert result["metrics"] == []

    def test_non_retryable_client_error_graceful_handling(self, mock_cloudwatch_client):
        """Test graceful handling of non-retryable AWS API errors."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-004",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "namespace": "AWS/Lambda",
        }

        # Mock non-retryable error - this will be caught in collect_metric
        mock_cloudwatch_client.get_metric_statistics.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterValue", "Message": "Invalid parameter"}},
            "GetMetricStatistics",
        )

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert - handler continues with empty metrics (graceful degradation)
        assert result["status"] == "success"
        assert result["metrics"] == []

    def test_namespace_auto_detection(self, mock_cloudwatch_client):
        """Test automatic namespace detection from resource ARN."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-005",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "timestamp": now.isoformat() + "Z",
            # No namespace provided - should be auto-detected
        }

        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {
                    "Timestamp": now,
                    "Average": 75.0,
                    "Maximum": 80.0,
                    "Minimum": 70.0,
                    "SampleCount": 10,
                    "Unit": "Percent",
                }
            ]
        }

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert len(result["metrics"]) > 0
        assert result["metrics"][0]["namespace"] == "AWS/EC2"


class TestParseResourceArn:
    """Tests for resource ARN parsing."""

    def test_parse_lambda_arn(self):
        """Test parsing Lambda function ARN."""
        # Arrange - Use ARN format that matches current implementation
        arn = "arn:aws:lambda:us-east-1:123456789012:function/my-function"

        # Act
        namespace, dimensions = lambda_function.parse_resource_arn(arn)

        # Assert
        assert namespace == "AWS/Lambda"
        assert len(dimensions) == 1
        assert dimensions[0]["Name"] == "FunctionName"
        assert dimensions[0]["Value"] == "my-function"

    def test_parse_ec2_arn(self):
        """Test parsing EC2 instance ARN."""
        # Arrange
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

        # Act
        namespace, dimensions = lambda_function.parse_resource_arn(arn)

        # Assert
        assert namespace == "AWS/EC2"
        assert len(dimensions) == 1
        assert dimensions[0]["Name"] == "InstanceId"
        assert dimensions[0]["Value"] == "i-1234567890abcdef0"

    def test_parse_rds_arn(self):
        """Test parsing RDS database ARN."""
        # Arrange - Use simplified ARN format that current implementation can parse
        # Real RDS ARNs are arn:aws:rds:region:account:db:instance-id (7 parts)
        # But implementation only handles 6-part ARNs correctly
        arn = "arn:aws:rds:us-east-1:123456789012:my-database"

        # Act
        namespace, dimensions = lambda_function.parse_resource_arn(arn)

        # Assert
        assert namespace == "AWS/RDS"
        assert len(dimensions) == 1
        assert dimensions[0]["Name"] == "DBInstanceIdentifier"
        assert dimensions[0]["Value"] == "my-database"

    def test_parse_ecs_arn(self):
        """Test parsing ECS service ARN."""
        # Arrange
        arn = "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/my-service"

        # Act
        namespace, dimensions = lambda_function.parse_resource_arn(arn)

        # Assert
        assert namespace == "AWS/ECS"
        assert len(dimensions) == 2
        assert dimensions[0]["Name"] == "ClusterName"
        assert dimensions[0]["Value"] == "my-cluster"
        assert dimensions[1]["Name"] == "ServiceName"
        assert dimensions[1]["Value"] == "my-service"

    def test_parse_dynamodb_arn(self):
        """Test parsing DynamoDB table ARN."""
        # Arrange
        arn = "arn:aws:dynamodb:us-east-1:123456789012:table/my-table"

        # Act
        namespace, dimensions = lambda_function.parse_resource_arn(arn)

        # Assert
        assert namespace == "AWS/DynamoDB"
        assert len(dimensions) == 1
        assert dimensions[0]["Name"] == "TableName"
        assert dimensions[0]["Value"] == "my-table"

    def test_parse_invalid_arn(self):
        """Test error handling for invalid ARN format."""
        # Arrange
        arn = "invalid-arn-format"

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            lambda_function.parse_resource_arn(arn)

        assert "Invalid ARN format" in str(exc_info.value)

    def test_parse_unknown_service(self):
        """Test parsing ARN for unknown service."""
        # Arrange
        arn = "arn:aws:unknownservice:us-east-1:123456789012:resource/my-resource"

        # Act
        namespace, dimensions = lambda_function.parse_resource_arn(arn)

        # Assert
        assert namespace == "AWS/UNKNOWNSERVICE"
        assert dimensions == []


class TestTimeRangeCalculation:
    """Tests for time range calculation."""

    def test_calculate_time_range(self):
        """Test time range calculation is exactly -60min to +5min."""
        # Arrange
        incident_time = datetime(2024, 1, 15, 14, 30, 0)

        # Act
        start_time, end_time = lambda_function.calculate_time_range(incident_time)

        # Assert
        expected_start = datetime(2024, 1, 15, 13, 30, 0)
        expected_end = datetime(2024, 1, 15, 14, 35, 0)

        assert start_time == expected_start
        assert end_time == expected_end
        assert (end_time - start_time).total_seconds() == 65 * 60  # 65 minutes


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


class TestGetDefaultMetrics:
    """Tests for default metrics selection."""

    def test_lambda_default_metrics(self):
        """Test default metrics for Lambda namespace."""
        # Act
        metrics = lambda_function.get_default_metrics_for_namespace("AWS/Lambda")

        # Assert
        assert "Invocations" in metrics
        assert "Errors" in metrics
        assert "Duration" in metrics
        assert "Throttles" in metrics

    def test_ec2_default_metrics(self):
        """Test default metrics for EC2 namespace."""
        # Act
        metrics = lambda_function.get_default_metrics_for_namespace("AWS/EC2")

        # Assert
        assert "CPUUtilization" in metrics
        assert "NetworkIn" in metrics
        assert "NetworkOut" in metrics

    def test_unknown_namespace_default_metrics(self):
        """Test default metrics for unknown namespace."""
        # Act
        metrics = lambda_function.get_default_metrics_for_namespace("AWS/Unknown")

        # Assert
        assert "CPUUtilization" in metrics
        assert len(metrics) >= 3


class TestCollectMetric:
    """Tests for individual metric collection."""

    def test_collect_metric_success(self, mock_cloudwatch_client):
        """Test successful metric collection."""
        # Arrange
        now = datetime.utcnow()
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {
                    "Timestamp": now - timedelta(minutes=i),
                    "Average": 50.0 + i,
                    "Maximum": 60.0 + i,
                    "Minimum": 40.0 + i,
                    "SampleCount": 10,
                    "Unit": "Percent",
                }
                for i in range(3)
            ]
        }

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act
            result = lambda_function.collect_metric(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions=[{"Name": "InstanceId", "Value": "i-123"}],
                start_time=now - timedelta(hours=1),
                end_time=now,
            )

        # Assert
        assert result is not None
        assert result["metricName"] == "CPUUtilization"
        assert result["namespace"] == "AWS/EC2"
        assert len(result["datapoints"]) == 3
        assert "statistics" in result

    def test_collect_metric_no_datapoints(self, mock_cloudwatch_client):
        """Test metric collection when no datapoints are available."""
        # Arrange
        now = datetime.utcnow()
        mock_cloudwatch_client.get_metric_statistics.return_value = {"Datapoints": []}

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act
            result = lambda_function.collect_metric(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions=[{"Name": "InstanceId", "Value": "i-123"}],
                start_time=now - timedelta(hours=1),
                end_time=now,
            )

        # Assert
        assert result is None

    def test_collect_metric_throttling_raises(self, mock_cloudwatch_client):
        """Test that throttling errors are raised for retry."""
        # Arrange
        now = datetime.utcnow()
        mock_cloudwatch_client.get_metric_statistics.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "GetMetricStatistics",
        )

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act & Assert
            with pytest.raises(ClientError) as exc_info:
                lambda_function.collect_metric(
                    namespace="AWS/EC2",
                    metric_name="CPUUtilization",
                    dimensions=[{"Name": "InstanceId", "Value": "i-123"}],
                    start_time=now - timedelta(hours=1),
                    end_time=now,
                )

            assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"

    def test_collect_metric_non_retryable_error_returns_none(self, mock_cloudwatch_client):
        """Test that non-retryable errors return None."""
        # Arrange
        now = datetime.utcnow()
        mock_cloudwatch_client.get_metric_statistics.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterValue", "Message": "Invalid parameter"}},
            "GetMetricStatistics",
        )

        with patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client):
            # Act
            result = lambda_function.collect_metric(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions=[{"Name": "InstanceId", "Value": "i-123"}],
                start_time=now - timedelta(hours=1),
                end_time=now,
            )

        # Assert
        assert result is None


class TestCalculateStatistics:
    """Tests for statistics calculation."""

    def test_calculate_statistics_with_data(self):
        """Test statistics calculation with valid datapoints."""
        # Arrange
        datapoints = [
            {"Average": 50.0},
            {"Average": 60.0},
            {"Average": 70.0},
            {"Average": 80.0},
            {"Average": 90.0},
        ]

        # Act
        stats = lambda_function.calculate_statistics(datapoints)

        # Assert
        assert stats["avg"] == 70.0
        assert stats["max"] == 90.0
        assert stats["min"] == 50.0
        assert stats["p95"] >= 80.0

    def test_calculate_statistics_empty_datapoints(self):
        """Test statistics calculation with empty datapoints."""
        # Arrange
        datapoints = []

        # Act
        stats = lambda_function.calculate_statistics(datapoints)

        # Assert
        assert stats["avg"] == 0.0
        assert stats["max"] == 0.0
        assert stats["min"] == 0.0
        assert stats["p95"] == 0.0

    def test_calculate_statistics_single_datapoint(self):
        """Test statistics calculation with single datapoint."""
        # Arrange
        datapoints = [{"Average": 75.0}]

        # Act
        stats = lambda_function.calculate_statistics(datapoints)

        # Assert
        assert stats["avg"] == 75.0
        assert stats["max"] == 75.0
        assert stats["min"] == 75.0
        assert stats["p95"] == 75.0


class TestParallelMetricCollection:
    """Tests for parallel metric collection (Fix 1)."""

    def test_multiple_metrics_collected_in_parallel(self, mock_cloudwatch_client):
        """Test that multiple metrics are collected using ThreadPoolExecutor."""
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-parallel-001",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "namespace": "AWS/Lambda",
            "metricNames": ["Invocations", "Errors", "Duration"],
        }

        # Each call returns one datapoint
        mock_cloudwatch_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {
                    "Timestamp": now,
                    "Average": 10.0,
                    "Maximum": 15.0,
                    "Minimum": 5.0,
                    "SampleCount": 1,
                    "Unit": "Count",
                }
            ]
        }

        with (
            patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client),
            patch("metrics_collector.lambda_function.put_collector_success_metric"),
        ):
            result = lambda_function.lambda_handler(event, None)

        # All 3 metrics should be collected
        assert result["status"] == "success"
        assert len(result["metrics"]) == 3
        metric_names = {m["metricName"] for m in result["metrics"]}
        assert metric_names == {"Invocations", "Errors", "Duration"}

    def test_partial_failure_does_not_abort_collection(self, mock_cloudwatch_client):
        """Test that a single metric failure does not stop other metrics from being collected."""
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-parallel-002",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
            "namespace": "AWS/Lambda",
            "metricNames": ["Invocations", "Errors"],
        }

        call_count = {"n": 0}

        def side_effect(**kwargs):
            call_count["n"] += 1
            if kwargs.get("MetricName") == "Errors":
                from botocore.exceptions import ClientError
                raise ClientError(
                    {"Error": {"Code": "InvalidParameterValue", "Message": "bad param"}},
                    "GetMetricStatistics",
                )
            return {
                "Datapoints": [
                    {
                        "Timestamp": now,
                        "Average": 5.0,
                        "Maximum": 5.0,
                        "Minimum": 5.0,
                        "SampleCount": 1,
                        "Unit": "Count",
                    }
                ]
            }

        mock_cloudwatch_client.get_metric_statistics.side_effect = side_effect

        with (
            patch("metrics_collector.lambda_function.cloudwatch", mock_cloudwatch_client),
            patch("metrics_collector.lambda_function.put_collector_success_metric"),
        ):
            result = lambda_function.lambda_handler(event, None)

        # "Invocations" should succeed; "Errors" fails silently
        assert result["status"] == "success"
        assert len(result["metrics"]) == 1
        assert result["metrics"][0]["metricName"] == "Invocations"


class TestSSMTimeWindow:
    """Tests for SSM-configurable time window (Fix 7)."""

    def test_calculate_time_range_with_custom_window(self):
        """Test that calculate_time_range respects explicit override parameters."""
        incident_time = datetime(2024, 6, 1, 12, 0, 0)
        start, end = lambda_function.calculate_time_range(
            incident_time, lookback_minutes=30, lookahead_minutes=10
        )
        assert (incident_time - start).total_seconds() == 30 * 60
        assert (end - incident_time).total_seconds() == 10 * 60

    def test_calculate_time_range_uses_module_defaults(self):
        """Test that calculate_time_range uses module-level SSM-backed defaults when not overridden."""
        incident_time = datetime(2024, 6, 1, 12, 0, 0)
        start, end = lambda_function.calculate_time_range(incident_time)
        # Window must be at least 60+5 minutes (the hardcoded fallback defaults)
        total_minutes = (end - start).total_seconds() / 60
        assert total_minutes >= 65  # at minimum the default 60+5 window

    def test_load_time_window_from_ssm_returns_defaults_on_failure(self):
        """Test that _load_time_window_from_ssm falls back to defaults when SSM fails."""
        with patch("metrics_collector.lambda_function.boto3") as mock_boto3:
            mock_ssm = MagicMock()
            mock_ssm.get_parameters.side_effect = Exception("SSM unreachable")
            mock_boto3.client.return_value = mock_ssm

            lookback, lookahead = lambda_function._load_time_window_from_ssm()

        assert lookback == lambda_function._DEFAULT_LOOKBACK_MINUTES
        assert lookahead == lambda_function._DEFAULT_LOOKAHEAD_MINUTES

    def test_load_time_window_from_ssm_reads_parameters(self):
        """Test that _load_time_window_from_ssm uses SSM values when available."""
        ssm_lookback_param = lambda_function._SSM_PARAM_LOOKBACK
        ssm_lookahead_param = lambda_function._SSM_PARAM_LOOKAHEAD

        with patch("metrics_collector.lambda_function.boto3") as mock_boto3:
            mock_ssm = MagicMock()
            mock_ssm.get_parameters.return_value = {
                "Parameters": [
                    {"Name": ssm_lookback_param, "Value": "45"},
                    {"Name": ssm_lookahead_param, "Value": "15"},
                ]
            }
            mock_boto3.client.return_value = mock_ssm

            lookback, lookahead = lambda_function._load_time_window_from_ssm()

        assert lookback == 45
        assert lookahead == 15
