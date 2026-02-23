"""
Unit tests for observability features.

Tests structured logging, correlation ID propagation, metric emission,
and error logging format.

Validates Requirements 11.1, 11.2, 11.3, 11.6
"""

import json
import logging
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, call, MagicMock
from io import StringIO

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from shared.structured_logger import StructuredLogger, get_correlation_id
from shared.metrics import (
    put_metric,
    put_collector_success_metric,
    put_llm_invocation_metric,
    put_notification_delivery_metric,
    put_workflow_duration_metric,
)


class TestStructuredLogger:
    """Test StructuredLogger class for structured logging."""

    def setup_method(self):
        """Set up test fixtures."""
        self.logger = StructuredLogger("test-function", "v1.0")
        self.correlation_id = "test-correlation-id-123"

    def test_info_log_structure(self, caplog):
        """
        Test that INFO logs have correct JSON structure.

        Validates: Requirement 11.1 (structured JSON logs)
        """
        with caplog.at_level(logging.INFO):
            self.logger.info(
                message="Test info message",
                correlation_id=self.correlation_id,
                extra_field="extra_value",
            )

        # Parse the log message as JSON
        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        # Validate required fields
        assert log_json["level"] == "INFO"
        assert log_json["message"] == "Test info message"
        assert log_json["correlationId"] == self.correlation_id
        assert log_json["functionName"] == "test-function"
        assert log_json["functionVersion"] == "v1.0"
        assert "timestamp" in log_json
        assert log_json["extra_field"] == "extra_value"

        # Validate timestamp format (ISO-8601 with Z suffix)
        assert log_json["timestamp"].endswith("Z")
        datetime.fromisoformat(log_json["timestamp"][:-1])  # Should not raise

    def test_warning_log_structure(self, caplog):
        """
        Test that WARNING logs have correct JSON structure.

        Validates: Requirement 11.1 (structured JSON logs)
        """
        with caplog.at_level(logging.WARNING):
            self.logger.warning(message="Test warning message", correlation_id=self.correlation_id)

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        assert log_json["level"] == "WARNING"
        assert log_json["message"] == "Test warning message"
        assert log_json["correlationId"] == self.correlation_id

    def test_error_log_structure_with_exception(self, caplog):
        """
        Test that ERROR logs include exception details and stack trace.

        Validates: Requirement 11.6 (error logging with stack traces)
        """
        try:
            raise ValueError("Test error")
        except ValueError as e:
            with caplog.at_level(logging.ERROR):
                self.logger.error(
                    message="Test error occurred",
                    correlation_id=self.correlation_id,
                    error=e,
                    include_trace=True,
                )

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        # Validate error fields
        assert log_json["level"] == "ERROR"
        assert log_json["message"] == "Test error occurred"
        assert log_json["correlationId"] == self.correlation_id
        assert log_json["error"] == "Test error"
        assert log_json["errorType"] == "ValueError"
        assert "stackTrace" in log_json
        assert "Traceback" in log_json["stackTrace"]
        assert "ValueError: Test error" in log_json["stackTrace"]

    def test_error_log_without_exception(self, caplog):
        """
        Test that ERROR logs work without exception object.

        Validates: Requirement 11.6 (error logging)
        """
        with caplog.at_level(logging.ERROR):
            self.logger.error(
                message="Generic error message",
                correlation_id=self.correlation_id,
                include_trace=False,
            )

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        assert log_json["level"] == "ERROR"
        assert log_json["message"] == "Generic error message"
        assert "error" not in log_json
        assert "errorType" not in log_json
        assert "stackTrace" not in log_json

    def test_debug_log_structure(self, caplog):
        """
        Test that DEBUG logs have correct JSON structure.

        Validates: Requirement 11.1 (structured JSON logs)
        """
        with caplog.at_level(logging.DEBUG):
            self.logger.debug(message="Test debug message", correlation_id=self.correlation_id)

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        assert log_json["level"] == "DEBUG"
        assert log_json["message"] == "Test debug message"
        assert log_json["correlationId"] == self.correlation_id

    def test_correlation_id_propagation(self, caplog):
        """
        Test that correlation ID is included in all log levels.

        Validates: Requirement 11.2 (correlation IDs in logs)
        """
        test_correlation_id = "incident-abc-123"

        with caplog.at_level(logging.DEBUG):
            self.logger.info("Info log", correlation_id=test_correlation_id)
            self.logger.warning("Warning log", correlation_id=test_correlation_id)
            self.logger.debug("Debug log", correlation_id=test_correlation_id)

        # All logs should have the same correlation ID
        for record in caplog.records:
            log_json = json.loads(record.message)
            assert log_json["correlationId"] == test_correlation_id

    def test_default_correlation_id(self, caplog):
        """
        Test that logs use 'unknown' as default correlation ID.

        Validates: Requirement 11.2 (correlation IDs in logs)
        """
        with caplog.at_level(logging.INFO):
            self.logger.info("Test message")  # No correlation_id provided

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        assert log_json["correlationId"] == "unknown"

    def test_additional_fields_in_logs(self, caplog):
        """
        Test that additional fields can be added to logs.

        Validates: Requirement 11.1 (structured JSON logs)
        """
        with caplog.at_level(logging.INFO):
            self.logger.info(
                message="Test message",
                correlation_id=self.correlation_id,
                resource_arn="arn:aws:lambda:us-east-1:123456789012:function:test",
                duration=1.5,
                status="success",
            )

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        assert log_json["resource_arn"] == "arn:aws:lambda:us-east-1:123456789012:function:test"
        assert log_json["duration"] == 1.5
        assert log_json["status"] == "success"


class TestGetCorrelationId:
    """Test get_correlation_id function for extracting incident IDs."""

    def test_extract_from_direct_field(self):
        """
        Test extracting correlation ID from direct incidentId field.

        Validates: Requirement 11.2 (correlation ID propagation)
        """
        event = {
            "incidentId": "incident-123",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
        }

        correlation_id = get_correlation_id(event)
        assert correlation_id == "incident-123"

    def test_extract_from_nested_incident_object(self):
        """
        Test extracting correlation ID from nested incident object.

        Validates: Requirement 11.2 (correlation ID propagation)
        """
        event = {
            "incident": {"incidentId": "incident-456", "alarmName": "HighErrorRate"},
            "metrics": {"status": "success"},
        }

        correlation_id = get_correlation_id(event)
        assert correlation_id == "incident-456"

    def test_extract_from_structured_context(self):
        """
        Test extracting correlation ID from structuredContext.

        Validates: Requirement 11.2 (correlation ID propagation)
        """
        event = {
            "structuredContext": {
                "incidentId": "incident-789",
                "resource": {"arn": "arn:aws:lambda:us-east-1:123456789012:function:test"},
            }
        }

        correlation_id = get_correlation_id(event)
        assert correlation_id == "incident-789"

    def test_default_to_unknown(self):
        """
        Test that function returns 'unknown' when no incident ID found.

        Validates: Requirement 11.2 (correlation ID propagation)
        """
        event = {
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        correlation_id = get_correlation_id(event)
        assert correlation_id == "unknown"

    def test_empty_event(self):
        """
        Test that function handles empty event gracefully.

        Validates: Requirement 11.2 (correlation ID propagation)
        """
        event = {}

        correlation_id = get_correlation_id(event)
        assert correlation_id == "unknown"


class TestMetricEmission:
    """Test CloudWatch metric emission functions."""

    @patch("shared.metrics.cloudwatch")
    def test_put_metric_basic(self, mock_cloudwatch):
        """
        Test basic metric emission.

        Validates: Requirement 11.3 (custom CloudWatch metrics)
        """
        put_metric(metric_name="TestMetric", value=42.0, unit="Count")

        # Verify CloudWatch API was called
        mock_cloudwatch.put_metric_data.assert_called_once()

        # Verify metric data structure
        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]["Namespace"] == "AI-SRE-IncidentAnalysis"

        metric_data = call_args[1]["MetricData"][0]
        assert metric_data["MetricName"] == "TestMetric"
        assert metric_data["Value"] == 42.0
        assert metric_data["Unit"] == "Count"
        assert "Timestamp" in metric_data

    @patch("shared.metrics.cloudwatch")
    def test_put_metric_with_dimensions(self, mock_cloudwatch):
        """
        Test metric emission with dimensions.

        Validates: Requirement 11.3 (custom CloudWatch metrics)
        """
        dimensions = [
            {"Name": "Collector", "Value": "metrics"},
            {"Name": "Status", "Value": "Success"},
        ]

        put_metric(
            metric_name="CollectorInvocations", value=1.0, unit="Count", dimensions=dimensions
        )

        call_args = mock_cloudwatch.put_metric_data.call_args
        metric_data = call_args[1]["MetricData"][0]

        assert metric_data["Dimensions"] == dimensions

    @patch("shared.metrics.cloudwatch")
    def test_put_metric_handles_client_error(self, mock_cloudwatch, caplog):
        """
        Test that metric emission handles ClientError gracefully.

        Validates: Requirement 11.3 (custom CloudWatch metrics)
        """
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        mock_cloudwatch.put_metric_data.side_effect = ClientError(error_response, "PutMetricData")

        with caplog.at_level(logging.WARNING):
            # Should not raise exception
            put_metric(metric_name="TestMetric", value=1.0)

        # Should log warning
        assert any("Failed to emit metric" in record.message for record in caplog.records)

    @patch("shared.metrics.put_metric")
    def test_put_collector_success_metric(self, mock_put_metric):
        """
        Test collector success metric emission.

        Validates: Requirement 11.3 (collector success rates)
        """
        put_collector_success_metric(collector_name="metrics", success=True, duration=1.5)

        # Should emit two metrics: invocation count and duration
        assert mock_put_metric.call_count == 2

        # Check invocation count metric
        call_1 = mock_put_metric.call_args_list[0]
        assert call_1[1]["metric_name"] == "CollectorInvocations"
        assert call_1[1]["value"] == 1.0
        assert call_1[1]["unit"] == "Count"

        # Check dimensions include collector name and status
        dimensions_1 = call_1[1]["dimensions"]
        assert {"Name": "Collector", "Value": "metrics"} in dimensions_1
        assert {"Name": "Status", "Value": "Success"} in dimensions_1

        # Check duration metric
        call_2 = mock_put_metric.call_args_list[1]
        assert call_2[1]["metric_name"] == "CollectorDuration"
        assert call_2[1]["value"] == 1.5
        assert call_2[1]["unit"] == "Seconds"

    @patch("shared.metrics.put_metric")
    def test_put_collector_failure_metric(self, mock_put_metric):
        """
        Test collector failure metric emission.

        Validates: Requirement 11.3 (collector success rates)
        """
        put_collector_success_metric(collector_name="logs", success=False, duration=2.0)

        # Check that failure status is recorded
        call_1 = mock_put_metric.call_args_list[0]
        dimensions_1 = call_1[1]["dimensions"]
        assert {"Name": "Status", "Value": "Failure"} in dimensions_1

    @patch("shared.metrics.put_metric")
    def test_put_llm_invocation_metric(self, mock_put_metric):
        """
        Test LLM invocation metric emission.

        Validates: Requirement 11.3 (LLM invocation latency)
        """
        put_llm_invocation_metric(latency=2.5, success=True, model_id="anthropic.claude-v2")

        # Should emit two metrics: latency and invocation count
        assert mock_put_metric.call_count == 2

        # Check latency metric
        call_1 = mock_put_metric.call_args_list[0]
        assert call_1[1]["metric_name"] == "LLMInvocationLatency"
        assert call_1[1]["value"] == 2.5
        assert call_1[1]["unit"] == "Seconds"

        # Check dimensions include model ID
        dimensions_1 = call_1[1]["dimensions"]
        assert {"Name": "ModelId", "Value": "anthropic.claude-v2"} in dimensions_1

        # Check invocation count metric
        call_2 = mock_put_metric.call_args_list[1]
        assert call_2[1]["metric_name"] == "LLMInvocations"
        assert call_2[1]["value"] == 1.0
        dimensions_2 = call_2[1]["dimensions"]
        assert {"Name": "Status", "Value": "Success"} in dimensions_2

    @patch("shared.metrics.put_metric")
    def test_put_notification_delivery_metric(self, mock_put_metric):
        """
        Test notification delivery metric emission.

        Validates: Requirement 11.3 (notification delivery status)
        """
        put_notification_delivery_metric(channel="slack", success=True, duration=1.2)

        # Should emit two metrics: delivery count and duration
        assert mock_put_metric.call_count == 2

        # Check delivery count metric
        call_1 = mock_put_metric.call_args_list[0]
        assert call_1[1]["metric_name"] == "NotificationDeliveries"
        assert call_1[1]["value"] == 1.0

        # Check dimensions include channel and status
        dimensions_1 = call_1[1]["dimensions"]
        assert {"Name": "Channel", "Value": "slack"} in dimensions_1
        assert {"Name": "Status", "Value": "Success"} in dimensions_1

        # Check duration metric
        call_2 = mock_put_metric.call_args_list[1]
        assert call_2[1]["metric_name"] == "NotificationDuration"
        assert call_2[1]["value"] == 1.2
        assert call_2[1]["unit"] == "Seconds"

    @patch("shared.metrics.put_metric")
    def test_put_workflow_duration_metric(self, mock_put_metric):
        """
        Test workflow duration metric emission.

        Validates: Requirement 11.3 (workflow duration)
        """
        put_workflow_duration_metric(duration=45.5, success=True)

        # Should emit two metrics: duration and completion count
        assert mock_put_metric.call_count == 2

        # Check duration metric
        call_1 = mock_put_metric.call_args_list[0]
        assert call_1[1]["metric_name"] == "WorkflowDuration"
        assert call_1[1]["value"] == 45.5
        assert call_1[1]["unit"] == "Seconds"

        # Check dimensions include status
        dimensions_1 = call_1[1]["dimensions"]
        assert {"Name": "Status", "Value": "Success"} in dimensions_1

        # Check completion count metric
        call_2 = mock_put_metric.call_args_list[1]
        assert call_2[1]["metric_name"] == "WorkflowCompletions"
        assert call_2[1]["value"] == 1.0
        assert call_2[1]["unit"] == "Count"


class TestErrorLoggingFormat:
    """Test error logging format and stack trace inclusion."""

    def test_error_log_includes_stack_trace(self, caplog):
        """
        Test that error logs include full stack trace.

        Validates: Requirement 11.6 (error logging with stack traces)
        """
        logger = StructuredLogger("test-function", "v1.0")

        try:
            # Create a nested call stack
            def inner_function():
                raise RuntimeError("Inner error")

            def outer_function():
                inner_function()

            outer_function()
        except RuntimeError as e:
            with caplog.at_level(logging.ERROR):
                logger.error(
                    message="Caught runtime error",
                    correlation_id="test-123",
                    error=e,
                    include_trace=True,
                )

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        # Verify stack trace contains function names
        stack_trace = log_json["stackTrace"]
        assert "inner_function" in stack_trace
        assert "outer_function" in stack_trace
        assert "RuntimeError: Inner error" in stack_trace

    def test_error_log_includes_context(self, caplog):
        """
        Test that error logs include context information.

        Validates: Requirement 11.6 (error logging with context)
        """
        logger = StructuredLogger("test-function", "v1.0")

        try:
            raise ValueError("Test error")
        except ValueError as e:
            with caplog.at_level(logging.ERROR):
                logger.error(
                    message="Error processing request",
                    correlation_id="incident-abc-123",
                    error=e,
                    include_trace=True,
                    resource_arn="arn:aws:lambda:us-east-1:123456789012:function:test",
                    operation="data_collection",
                )

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        # Verify context fields are included
        assert log_json["correlationId"] == "incident-abc-123"
        assert log_json["resource_arn"] == "arn:aws:lambda:us-east-1:123456789012:function:test"
        assert log_json["operation"] == "data_collection"
        assert log_json["functionName"] == "test-function"

    def test_error_log_without_trace(self, caplog):
        """
        Test that error logs can omit stack trace when requested.

        Validates: Requirement 11.6 (error logging)
        """
        logger = StructuredLogger("test-function", "v1.0")

        with caplog.at_level(logging.ERROR):
            logger.error(
                message="Simple error message", correlation_id="test-123", include_trace=False
            )

        log_record = caplog.records[0]
        log_json = json.loads(log_record.message)

        # Verify no stack trace is included
        assert "stackTrace" not in log_json
        assert log_json["message"] == "Simple error message"
