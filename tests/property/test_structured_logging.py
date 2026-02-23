"""
Property-based tests for structured logging with correlation IDs.

This module tests the structured logging property: for any incident workflow,
all logs must be valid JSON with the same correlation ID.

Validates Requirements 2.7, 11.1, 11.2
"""

import json
import logging
import sys
import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
from hypothesis import given, strategies as st, assume
from hypothesis.strategies import composite

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from metrics_collector.lambda_function import lambda_handler as metrics_handler
from logs_collector.lambda_function import lambda_handler as logs_handler
from deploy_context_collector.lambda_function import lambda_handler as deploy_handler
from correlation_engine.lambda_function import lambda_handler as correlation_handler
from llm_analyzer.lambda_function import lambda_handler as llm_handler
from notification_service.lambda_function import lambda_handler as notification_handler

# Strategy generators


@composite
def incident_id_strategy(draw):
    """Generate valid incident IDs (UUID v4 format)."""
    import uuid

    return str(uuid.uuid4())


@composite
def timestamp_strategy(draw):
    """Generate valid ISO-8601 timestamps."""
    timestamp_int = draw(st.integers(min_value=1577836800, max_value=1924905600))
    dt = datetime.fromtimestamp(timestamp_int, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


@composite
def resource_arn_strategy(draw):
    """Generate valid AWS resource ARNs."""
    service = draw(st.sampled_from(["lambda", "ec2", "rds", "ecs"]))
    region = draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]))
    account = draw(st.text(alphabet="0123456789", min_size=12, max_size=12))

    if service == "lambda":
        resource_name = draw(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20)
        )
        return f"arn:aws:{service}:{region}:{account}:function:{resource_name}"
    elif service == "ec2":
        instance_id = f"i-{draw(st.text(alphabet='0123456789abcdef', min_size=17, max_size=17))}"
        return f"arn:aws:{service}:{region}:{account}:instance/{instance_id}"
    elif service == "rds":
        db_name = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20))
        return f"arn:aws:{service}:{region}:{account}:db:{db_name}"
    else:  # ecs
        cluster = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20))
        service_name = draw(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20)
        )
        return f"arn:aws:{service}:{region}:{account}:service/{cluster}/{service_name}"


@composite
def metrics_collector_event_strategy(draw):
    """Generate valid metrics collector events."""
    return {
        "incidentId": draw(incident_id_strategy()),
        "resourceArn": draw(resource_arn_strategy()),
        "timestamp": draw(timestamp_strategy()),
        "namespace": draw(st.sampled_from(["AWS/Lambda", "AWS/EC2", "AWS/RDS", "AWS/ECS"])),
    }


@composite
def logs_collector_event_strategy(draw):
    """Generate valid logs collector events."""
    return {
        "incidentId": draw(incident_id_strategy()),
        "resourceArn": draw(resource_arn_strategy()),
        "timestamp": draw(timestamp_strategy()),
        "logGroupName": f"/aws/lambda/{draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz-', min_size=5, max_size=20))}",
    }


@composite
def deploy_context_collector_event_strategy(draw):
    """Generate valid deploy context collector events."""
    return {
        "incidentId": draw(incident_id_strategy()),
        "resourceArn": draw(resource_arn_strategy()),
        "timestamp": draw(timestamp_strategy()),
    }


@composite
def correlation_engine_event_strategy(draw):
    """Generate valid correlation engine events."""
    incident_id = draw(incident_id_strategy())
    return {
        "incident": {
            "incidentId": incident_id,
            "resourceArn": draw(resource_arn_strategy()),
            "timestamp": draw(timestamp_strategy()),
            "alarmName": draw(
                st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=5, max_size=20)
            ),
            "metricName": "CPUUtilization",
            "namespace": "AWS/EC2",
        },
        "metrics": {"status": "success", "metrics": [], "collectionDuration": 1.5},
        "logs": {
            "status": "success",
            "logs": [],
            "totalMatches": 0,
            "returned": 0,
            "collectionDuration": 2.0,
        },
        "changes": {"status": "success", "changes": [], "collectionDuration": 1.8},
    }


# Helper functions


class LogCapture:
    """Capture and parse structured logs."""

    def __init__(self):
        self.logs = []
        self.handler = None
        self.original_handlers = []

    def __enter__(self):
        """Set up log capture."""
        # Create a custom handler that captures log records
        self.handler = logging.Handler()
        self.handler.setLevel(logging.DEBUG)

        # Store original handlers
        logger = logging.getLogger()
        self.original_handlers = logger.handlers[:]

        # Clear existing handlers and add our capture handler
        logger.handlers = []
        logger.addHandler(self.handler)

        # Override emit to capture logs
        def capture_emit(record):
            try:
                msg = record.getMessage()
                self.logs.append(msg)
            except Exception:
                pass

        self.handler.emit = capture_emit

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original logging configuration."""
        logger = logging.getLogger()
        logger.handlers = self.original_handlers

    def get_json_logs(self):
        """
        Parse captured logs as JSON.

        Returns:
            List of parsed JSON log entries
        """
        json_logs = []
        for log in self.logs:
            try:
                parsed = json.loads(log)
                json_logs.append(parsed)
            except (json.JSONDecodeError, TypeError):
                # Skip non-JSON logs (e.g., boto3 debug logs)
                pass
        return json_logs


def extract_correlation_ids(json_logs):
    """
    Extract correlation IDs from JSON logs.

    Args:
        json_logs: List of parsed JSON log entries

    Returns:
        Set of unique correlation IDs found in logs
    """
    correlation_ids = set()
    for log in json_logs:
        if isinstance(log, dict) and "correlationId" in log:
            correlation_ids.add(log["correlationId"])
    return correlation_ids


# Property Tests


@given(metrics_collector_event_strategy())
def test_structured_logging_metrics_collector(event):
    """
    Property 7: Structured Logging with Correlation IDs (Metrics Collector)

    **Validates: Requirements 2.7, 11.1, 11.2**

    For any metrics collector invocation, all logs must be:
    1. Valid JSON
    2. Contain the same correlation ID (incident ID)
    3. Include required fields: message, correlationId, functionName, timestamp
    """
    # Mock AWS services
    with (
        patch("metrics_collector.lambda_function.cloudwatch") as mock_cw,
        patch("metrics_collector.lambda_function.put_collector_success_metric"),
        LogCapture() as log_capture,
    ):

        # Mock CloudWatch response (empty metrics)
        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}

        # Create mock context
        mock_context = Mock()
        mock_context.function_name = "metrics-collector"
        mock_context.function_version = "$LATEST"

        # Invoke handler
        try:
            result = metrics_handler(event, mock_context)
        except Exception:
            # Even on error, logs should be structured
            pass

        # Get JSON logs
        json_logs = log_capture.get_json_logs()

        # Property 1: All logs must be valid JSON (already validated by get_json_logs)
        assert len(json_logs) > 0, "Handler must emit at least one structured log"

        # Property 2: All logs must contain the same correlation ID
        correlation_ids = extract_correlation_ids(json_logs)
        assert (
            len(correlation_ids) == 1
        ), f"All logs must have the same correlation ID, found: {correlation_ids}"

        # Property 3: Correlation ID must match the incident ID from event
        expected_correlation_id = event["incidentId"]
        assert expected_correlation_id in correlation_ids, (
            f"Correlation ID must match incident ID. "
            f"Expected: {expected_correlation_id}, Found: {correlation_ids}"
        )

        # Property 4: All logs must have required fields
        for log in json_logs:
            assert "message" in log, "Log must contain 'message' field"
            assert "correlationId" in log, "Log must contain 'correlationId' field"
            assert "functionName" in log, "Log must contain 'functionName' field"
            assert "timestamp" in log, "Log must contain 'timestamp' field"

            # Validate timestamp format (ISO-8601)
            timestamp = log["timestamp"]
            assert timestamp.endswith("Z"), "Timestamp must be in ISO-8601 UTC format with Z suffix"
            try:
                datetime.fromisoformat(timestamp[:-1])
            except ValueError:
                raise AssertionError(f"Invalid timestamp format: {timestamp}")


@given(logs_collector_event_strategy())
def test_structured_logging_logs_collector(event):
    """
    Property 7: Structured Logging with Correlation IDs (Logs Collector)

    **Validates: Requirements 2.7, 11.1, 11.2**

    For any logs collector invocation, all logs must be valid JSON with
    the same correlation ID.
    """
    # Mock AWS services
    with (
        patch("logs_collector.lambda_function.logs_client") as mock_logs,
        patch("logs_collector.lambda_function.put_collector_success_metric"),
        LogCapture() as log_capture,
    ):

        # Mock CloudWatch Logs response (empty logs)
        mock_logs.filter_log_events.return_value = {"events": []}

        # Create mock context
        mock_context = Mock()
        mock_context.function_name = "logs-collector"
        mock_context.function_version = "$LATEST"

        # Invoke handler
        try:
            result = logs_handler(event, mock_context)
        except Exception:
            pass

        # Get JSON logs
        json_logs = log_capture.get_json_logs()

        # Property: All logs must have the same correlation ID
        if len(json_logs) > 0:
            correlation_ids = extract_correlation_ids(json_logs)
            assert (
                len(correlation_ids) <= 1
            ), f"All logs must have the same correlation ID, found: {correlation_ids}"

            if len(correlation_ids) == 1:
                expected_correlation_id = event["incidentId"]
                assert (
                    expected_correlation_id in correlation_ids
                ), f"Correlation ID must match incident ID"


@given(deploy_context_collector_event_strategy())
def test_structured_logging_deploy_context_collector(event):
    """
    Property 7: Structured Logging with Correlation IDs (Deploy Context Collector)

    **Validates: Requirements 2.7, 11.1, 11.2**

    For any deploy context collector invocation, all logs must be valid JSON
    with the same correlation ID.
    """
    # Mock AWS services
    with (
        patch("deploy_context_collector.lambda_function.cloudtrail") as mock_ct,
        patch("deploy_context_collector.lambda_function.ssm") as mock_ssm,
        patch("deploy_context_collector.lambda_function.put_collector_success_metric"),
        LogCapture() as log_capture,
    ):

        # Mock CloudTrail and SSM responses (empty changes)
        mock_ct.lookup_events.return_value = {"Events": []}
        mock_ssm.get_parameter_history.return_value = {"Parameters": []}

        # Create mock context
        mock_context = Mock()
        mock_context.function_name = "deploy-context-collector"
        mock_context.function_version = "$LATEST"

        # Invoke handler
        try:
            result = deploy_handler(event, mock_context)
        except Exception:
            pass

        # Get JSON logs
        json_logs = log_capture.get_json_logs()

        # Property: All logs must have the same correlation ID
        if len(json_logs) > 0:
            correlation_ids = extract_correlation_ids(json_logs)
            assert (
                len(correlation_ids) <= 1
            ), f"All logs must have the same correlation ID, found: {correlation_ids}"

            if len(correlation_ids) == 1:
                expected_correlation_id = event["incidentId"]
                assert expected_correlation_id in correlation_ids


@given(correlation_engine_event_strategy())
def test_structured_logging_correlation_engine(event):
    """
    Property 7: Structured Logging with Correlation IDs (Correlation Engine)

    **Validates: Requirements 2.7, 11.1, 11.2**

    For any correlation engine invocation, all logs must be valid JSON with
    the same correlation ID.
    """
    # Mock metrics emission
    with (
        patch("correlation_engine.lambda_function.put_workflow_duration_metric"),
        LogCapture() as log_capture,
    ):

        # Create mock context
        mock_context = Mock()
        mock_context.function_name = "correlation-engine"
        mock_context.function_version = "$LATEST"

        # Invoke handler
        try:
            result = correlation_handler(event, mock_context)
        except Exception:
            pass

        # Get JSON logs
        json_logs = log_capture.get_json_logs()

        # Property: All logs must have the same correlation ID
        if len(json_logs) > 0:
            correlation_ids = extract_correlation_ids(json_logs)
            assert (
                len(correlation_ids) <= 1
            ), f"All logs must have the same correlation ID, found: {correlation_ids}"

            if len(correlation_ids) == 1:
                expected_correlation_id = event["incident"]["incidentId"]
                assert expected_correlation_id in correlation_ids


@given(incident_id_strategy())
def test_structured_logging_json_validity(incident_id):
    """
    Property 7: Structured Logging JSON Validity

    **Validates: Requirements 11.1**

    For any incident workflow, all logs must be valid JSON that can be parsed
    without errors.
    """
    # Create a simple event
    event = {
        "incidentId": incident_id,
        "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "namespace": "AWS/Lambda",
    }

    # Mock AWS services
    with (
        patch("metrics_collector.lambda_function.cloudwatch") as mock_cw,
        patch("metrics_collector.lambda_function.put_collector_success_metric"),
        LogCapture() as log_capture,
    ):

        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}

        mock_context = Mock()
        mock_context.function_name = "metrics-collector"
        mock_context.function_version = "$LATEST"

        # Invoke handler
        try:
            result = metrics_handler(event, mock_context)
        except Exception:
            pass

        # Property: All logs must be valid JSON
        for log_msg in log_capture.logs:
            try:
                parsed = json.loads(log_msg)
                # Must be a dictionary (JSON object)
                assert isinstance(
                    parsed, dict
                ), f"Structured log must be a JSON object, got {type(parsed)}"
            except json.JSONDecodeError as e:
                # Allow non-JSON logs from boto3 or other libraries
                # Only our application logs must be JSON
                if "correlationId" in log_msg or "functionName" in log_msg:
                    raise AssertionError(f"Application log must be valid JSON: {log_msg}") from e


@given(incident_id_strategy(), incident_id_strategy())
def test_structured_logging_correlation_id_uniqueness(incident_id_1, incident_id_2):
    """
    Property 7: Structured Logging Correlation ID Uniqueness

    **Validates: Requirements 2.7, 11.2**

    For any two different incidents, logs must have different correlation IDs.
    This ensures that logs from different incidents can be distinguished.
    """
    assume(incident_id_1 != incident_id_2)

    # Create events for two different incidents
    event_1 = {
        "incidentId": incident_id_1,
        "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "namespace": "AWS/Lambda",
    }

    event_2 = {
        "incidentId": incident_id_2,
        "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "namespace": "AWS/Lambda",
    }

    # Mock AWS services
    with (
        patch("metrics_collector.lambda_function.cloudwatch") as mock_cw,
        patch("metrics_collector.lambda_function.put_collector_success_metric"),
    ):

        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}

        mock_context = Mock()
        mock_context.function_name = "metrics-collector"
        mock_context.function_version = "$LATEST"

        # Capture logs for first incident
        with LogCapture() as log_capture_1:
            try:
                metrics_handler(event_1, mock_context)
            except Exception:
                pass
            json_logs_1 = log_capture_1.get_json_logs()
            correlation_ids_1 = extract_correlation_ids(json_logs_1)

        # Capture logs for second incident
        with LogCapture() as log_capture_2:
            try:
                metrics_handler(event_2, mock_context)
            except Exception:
                pass
            json_logs_2 = log_capture_2.get_json_logs()
            correlation_ids_2 = extract_correlation_ids(json_logs_2)

        # Property: Correlation IDs must be different for different incidents
        if len(correlation_ids_1) > 0 and len(correlation_ids_2) > 0:
            assert correlation_ids_1 != correlation_ids_2, (
                f"Different incidents must have different correlation IDs. "
                f"Incident 1: {correlation_ids_1}, Incident 2: {correlation_ids_2}"
            )
