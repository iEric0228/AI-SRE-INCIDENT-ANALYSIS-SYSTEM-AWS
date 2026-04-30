"""
Unit tests for EventBridge Event Transformer Lambda function.

Tests event transformation, incident ID generation, resource ARN extraction,
and SNS publishing functionality.

Requirements: 1.1, 1.2, 1.3
"""

import json

# Import the lambda function
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

# Set environment variable before importing
os.environ.setdefault("SNS_TOPIC_ARN", "")

from event_transformer import lambda_function


class TestResourceArnExtraction:
    """Test resource ARN extraction from CloudWatch Alarm events."""

    def test_extract_ec2_instance_arn(self):
        """Test extracting EC2 instance ARN from alarm event."""
        alarm_event = {
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "HighCPU",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
                "configuration": {
                    "metrics": [
                        {
                            "metricStat": {
                                "metric": {"dimensions": {"InstanceId": "i-1234567890abcdef0"}}
                            }
                        }
                    ]
                },
            },
        }

        result = lambda_function.extract_resource_arn(alarm_event)

        assert result == "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

    def test_extract_lambda_function_arn(self):
        """Test extracting Lambda function ARN from alarm event."""
        alarm_event = {
            "region": "us-west-2",
            "account": "123456789012",
            "detail": {
                "alarmName": "HighErrors",
                "alarmArn": "arn:aws:cloudwatch:us-west-2:123456789012:alarm:HighErrors",
                "configuration": {
                    "metrics": [
                        {"metricStat": {"metric": {"dimensions": {"FunctionName": "my-function"}}}}
                    ]
                },
            },
        }

        result = lambda_function.extract_resource_arn(alarm_event)

        assert result == "arn:aws:lambda:us-west-2:123456789012:function:my-function"

    def test_extract_rds_instance_arn(self):
        """Test extracting RDS instance ARN from alarm event."""
        alarm_event = {
            "region": "eu-west-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "HighConnections",
                "alarmArn": "arn:aws:cloudwatch:eu-west-1:123456789012:alarm:HighConnections",
                "configuration": {
                    "metrics": [
                        {
                            "metricStat": {
                                "metric": {"dimensions": {"DBInstanceIdentifier": "my-database"}}
                            }
                        }
                    ]
                },
            },
        }

        result = lambda_function.extract_resource_arn(alarm_event)

        assert result == "arn:aws:rds:eu-west-1:123456789012:db:my-database"

    def test_extract_ecs_cluster_arn(self):
        """Test extracting ECS cluster ARN from alarm event."""
        alarm_event = {
            "region": "ap-southeast-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "HighMemory",
                "alarmArn": "arn:aws:cloudwatch:ap-southeast-1:123456789012:alarm:HighMemory",
                "configuration": {
                    "metrics": [
                        {"metricStat": {"metric": {"dimensions": {"ClusterName": "my-cluster"}}}}
                    ]
                },
            },
        }

        result = lambda_function.extract_resource_arn(alarm_event)

        assert result == "arn:aws:ecs:ap-southeast-1:123456789012:cluster/my-cluster"

    def test_fallback_to_alarm_arn(self):
        """Test fallback to alarm ARN when resource ARN not found."""
        alarm_event = {
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "CustomMetric",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:CustomMetric",
                "configuration": {"metrics": [{"metricStat": {"metric": {"dimensions": {}}}}]},
            },
        }

        result = lambda_function.extract_resource_arn(alarm_event)

        assert result == "arn:aws:cloudwatch:us-east-1:123456789012:alarm:CustomMetric"

    def test_handle_missing_dimensions(self):
        """Test handling of alarm event with missing dimensions."""
        alarm_event = {
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "configuration": {"metrics": []},
            },
        }

        result = lambda_function.extract_resource_arn(alarm_event)

        assert result == "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm"


class TestEventTransformation:
    """Test CloudWatch Alarm event transformation to IncidentEvent."""

    def test_transform_complete_alarm_event(self):
        """Test transformation of complete alarm event with all fields."""
        alarm_event = {
            "version": "0",
            "id": "event-id-123",
            "detail-type": "CloudWatch Alarm State Change",
            "source": "aws.cloudwatch",
            "account": "123456789012",
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "detail": {
                "alarmName": "HighCPUAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPUAlarm",
                "alarmDescription": "CPU utilization is too high",
                "state": {"value": "ALARM", "reason": "Threshold Crossed"},
                "configuration": {
                    "metricName": "CPUUtilization",
                    "namespace": "AWS/EC2",
                    "metrics": [
                        {
                            "metricStat": {
                                "metric": {"dimensions": {"InstanceId": "i-1234567890abcdef0"}}
                            }
                        }
                    ],
                },
            },
        }

        result = lambda_function.transform_alarm_event(alarm_event)

        # Verify all required fields present
        assert "incidentId" in result
        assert "alarmName" in result
        assert "alarmArn" in result
        assert "resourceArn" in result
        assert "timestamp" in result
        assert "alarmState" in result
        assert "metricName" in result
        assert "namespace" in result

        # Verify field values
        assert result["alarmName"] == "HighCPUAlarm"
        assert result["alarmArn"] == "arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPUAlarm"
        assert result["alarmState"] == "ALARM"
        assert result["metricName"] == "CPUUtilization"
        assert result["namespace"] == "AWS/EC2"
        assert result["alarmDescription"] == "CPU utilization is too high"
        assert (
            result["resourceArn"]
            == "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        )
        assert result["timestamp"] == "2024-01-15T14:30:00Z"

        # Verify incident ID is valid UUID
        try:
            uuid.UUID(result["incidentId"])
        except ValueError:
            pytest.fail("incidentId is not a valid UUID")

    def test_transform_minimal_alarm_event(self):
        """Test transformation of minimal alarm event with only required fields."""
        alarm_event = {
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "MinimalAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:MinimalAlarm",
                "state": {"value": "ALARM"},
                "configuration": {
                    "metricName": "CustomMetric",
                    "namespace": "Custom",
                    "metrics": [],
                },
            },
        }

        result = lambda_function.transform_alarm_event(alarm_event)

        assert result["alarmName"] == "MinimalAlarm"
        assert result["alarmState"] == "ALARM"
        assert result["metricName"] == "CustomMetric"
        assert result["namespace"] == "Custom"
        assert result["alarmDescription"] is None

    def test_transform_missing_alarm_name(self):
        """Test that missing alarm name raises ValueError."""
        alarm_event = {
            "detail": {"alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:Test"}
        }

        with pytest.raises(ValueError, match="Missing 'alarmName'"):
            lambda_function.transform_alarm_event(alarm_event)

    def test_transform_missing_detail(self):
        """Test that missing detail field raises ValueError."""
        alarm_event = {"time": "2024-01-15T14:30:00Z"}

        with pytest.raises(ValueError, match="Missing 'detail' field"):
            lambda_function.transform_alarm_event(alarm_event)

    def test_transform_uses_current_time_if_missing(self):
        """Test that current time is used if event time is missing."""
        alarm_event = {
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "state": {"value": "ALARM"},
                "configuration": {"metricName": "TestMetric", "namespace": "Test", "metrics": []},
            },
        }

        result = lambda_function.transform_alarm_event(alarm_event)

        # Verify timestamp is present and is a valid ISO format string
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)
        # Should be able to parse as ISO format
        from datetime import datetime

        datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00"))

    def test_incident_id_uniqueness(self):
        """Test that each transformation generates a unique incident ID."""
        alarm_event = {
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "state": {"value": "ALARM"},
                "configuration": {"metricName": "TestMetric", "namespace": "Test", "metrics": []},
            },
        }

        # Generate multiple incident IDs
        incident_ids = set()
        for _ in range(10):
            result = lambda_function.transform_alarm_event(alarm_event)
            incident_ids.add(result["incidentId"])

        # All should be unique
        assert len(incident_ids) == 10

    def test_ttl_calculation(self):
        """Test that TTL is correctly calculated as 90 days from incident timestamp."""
        alarm_event = {
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "state": {"value": "ALARM"},
                "configuration": {"metricName": "TestMetric", "namespace": "Test", "metrics": []},
            },
        }

        result = lambda_function.transform_alarm_event(alarm_event)

        # Verify TTL field exists
        assert "ttl" in result
        assert isinstance(result["ttl"], int)

        # Parse the incident timestamp
        incident_time = datetime.fromisoformat(result["timestamp"].replace("Z", ""))
        incident_unix = int(incident_time.timestamp())

        # TTL should be incident time + 90 days (7,776,000 seconds)
        expected_ttl = incident_unix + 7776000

        assert result["ttl"] == expected_ttl

    def test_ttl_calculation_with_current_time(self):
        """Test TTL calculation when event time is missing (uses current time)."""
        alarm_event = {
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "state": {"value": "ALARM"},
                "configuration": {"metricName": "TestMetric", "namespace": "Test", "metrics": []},
            },
        }

        result = lambda_function.transform_alarm_event(alarm_event)

        # Verify TTL field exists
        assert "ttl" in result
        assert isinstance(result["ttl"], int)

        # TTL should be approximately current time + 90 days
        # Allow 5 second tolerance for test execution time
        current_unix = int(datetime.now(timezone.utc).timestamp())
        expected_ttl = current_unix + 7776000

        assert abs(result["ttl"] - expected_ttl) < 5


class TestSNSPublishing:
    """Test SNS publishing functionality."""

    @patch.dict(os.environ, {"SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:test-topic"})
    @patch("event_transformer.lambda_function.sns_client")
    def test_publish_to_sns_success(self, mock_sns):
        """Test successful SNS publishing."""
        mock_sns.publish.return_value = {"MessageId": "msg-123"}

        incident_event = {
            "incidentId": "incident-123",
            "alarmName": "TestAlarm",
            "alarmState": "ALARM",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            "timestamp": "2024-01-15T14:30:00Z",
            "metricName": "CPUUtilization",
            "namespace": "AWS/EC2",
        }

        message_id = lambda_function.publish_to_sns(incident_event)

        assert message_id == "msg-123"

        # Verify SNS publish was called with correct parameters
        mock_sns.publish.assert_called_once()
        call_args = mock_sns.publish.call_args
        assert call_args[1]["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:test-topic"
        assert call_args[1]["Subject"] == "Incident: TestAlarm"

        # Verify message content
        message = json.loads(call_args[1]["Message"])
        assert message["incidentId"] == "incident-123"
        assert message["alarmName"] == "TestAlarm"

        # Verify message attributes
        assert call_args[1]["MessageAttributes"]["incidentId"]["StringValue"] == "incident-123"
        assert call_args[1]["MessageAttributes"]["alarmState"]["StringValue"] == "ALARM"

    @patch("event_transformer.lambda_function.sns_client")
    def test_publish_missing_topic_arn(self, mock_sns):
        """Test that missing SNS_TOPIC_ARN raises ValueError."""
        incident_event = {"incidentId": "incident-123", "alarmName": "TestAlarm"}

        with patch.dict(os.environ, {"SNS_TOPIC_ARN": ""}):
            with pytest.raises(ValueError, match="SNS_TOPIC_ARN environment variable not set"):
                lambda_function.publish_to_sns(incident_event)

    @patch.dict(os.environ, {"SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:test-topic"})
    @patch("event_transformer.lambda_function.sns_client")
    def test_publish_sns_client_error(self, mock_sns):
        """Test handling of SNS ClientError."""
        mock_sns.publish.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameter", "Message": "Invalid topic"}}, "Publish"
        )

        incident_event = {
            "incidentId": "incident-123",
            "alarmName": "TestAlarm",
            "alarmState": "ALARM",
        }

        with pytest.raises(ClientError):
            lambda_function.publish_to_sns(incident_event)


class TestLambdaHandler:
    """Test Lambda handler integration."""

    @patch.dict(os.environ, {
        "SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "STATE_MACHINE_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:test-sm",
    })
    @patch("event_transformer.lambda_function.sfn_client")
    @patch("event_transformer.lambda_function.sns_client")
    def test_handler_success(self, mock_sns, mock_sfn):
        """Test successful end-to-end event processing."""
        mock_sns.publish.return_value = {"MessageId": "msg-123"}
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-sm:incident-123",
        }

        event = {
            "version": "0",
            "id": "event-id-123",
            "detail-type": "CloudWatch Alarm State Change",
            "source": "aws.cloudwatch",
            "account": "123456789012",
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "detail": {
                "alarmName": "HighCPUAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPUAlarm",
                "state": {"value": "ALARM"},
                "configuration": {
                    "metricName": "CPUUtilization",
                    "namespace": "AWS/EC2",
                    "metrics": [
                        {
                            "metricStat": {
                                "metric": {"dimensions": {"InstanceId": "i-1234567890abcdef0"}}
                            }
                        }
                    ],
                },
            },
        }

        context = MagicMock()

        response = lambda_function.lambda_handler(event, context)

        assert response["statusCode"] == 200

        body = json.loads(response["body"])
        assert body["status"] == "success"
        assert "incidentId" in body
        assert "executionArn" in body
        assert body["alarmName"] == "HighCPUAlarm"
        assert (
            body["resourceArn"] == "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        )

    @patch("event_transformer.lambda_function.sns_client")
    def test_handler_validation_error(self, mock_sns):
        """Test handler response for validation errors."""
        event = {"source": "aws.cloudwatch", "detail": {}}  # Missing required fields

        context = MagicMock()

        response = lambda_function.lambda_handler(event, context)

        assert response["statusCode"] == 400

        body = json.loads(response["body"])
        assert body["status"] == "failed"
        assert body["errorType"] == "ValidationException"

    @patch.dict(os.environ, {
        "SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "STATE_MACHINE_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:test-sm",
    })
    @patch("event_transformer.lambda_function.sfn_client")
    def test_handler_retryable_error(self, mock_sfn):
        """Test that retryable errors are raised for Lambda retry."""
        mock_sfn.start_execution.side_effect = ClientError(
            {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}, "StartExecution"
        )

        event = {
            "source": "aws.cloudwatch",
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "state": {"value": "ALARM"},
                "configuration": {"metricName": "TestMetric", "namespace": "Test", "metrics": []},
            },
        }

        context = MagicMock()

        with pytest.raises(ClientError) as exc_info:
            lambda_function.lambda_handler(event, context)

        assert exc_info.value.response["Error"]["Code"] == "Throttling"

    @patch.dict(os.environ, {
        "SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "STATE_MACHINE_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:test-sm",
    })
    @patch("event_transformer.lambda_function.sfn_client")
    def test_handler_non_retryable_error(self, mock_sfn):
        """Test that non-retryable errors return error response."""
        mock_sfn.start_execution.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameter", "Message": "Invalid state machine"}}, "StartExecution"
        )

        event = {
            "source": "aws.cloudwatch",
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "state": {"value": "ALARM"},
                "configuration": {"metricName": "TestMetric", "namespace": "Test", "metrics": []},
            },
        }

        context = MagicMock()

        response = lambda_function.lambda_handler(event, context)

        assert response["statusCode"] == 500

        body = json.loads(response["body"])
        assert body["status"] == "failed"
        assert body["errorType"] == "InvalidParameter"

    @patch.dict(os.environ, {
        "SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "STATE_MACHINE_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:test-sm",
    })
    @patch("event_transformer.lambda_function.sfn_client")
    def test_handler_unexpected_event_source(self, mock_sfn):
        """Test handler logs warning for unexpected event source."""
        mock_sfn.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-sm:incident-123",
        }

        event = {
            "source": "aws.ec2",  # Unexpected source
            "time": "2024-01-15T14:30:00Z",
            "region": "us-east-1",
            "account": "123456789012",
            "detail": {
                "alarmName": "TestAlarm",
                "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm",
                "state": {"value": "ALARM"},
                "configuration": {"metricName": "TestMetric", "namespace": "Test", "metrics": []},
            },
        }

        context = MagicMock()

        response = lambda_function.lambda_handler(event, context)

        # Should still succeed despite unexpected source
        assert response["statusCode"] == 200
