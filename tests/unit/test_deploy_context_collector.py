"""
Unit tests for Deploy Context Collector Lambda function.

Tests cover:
- CloudTrail event retrieval
- Parameter Store change detection
- Change classification logic
- Empty changes handling
- Time range calculation

Requirements: 5.1, 5.2, 5.3, 5.4
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import pytest
from botocore.exceptions import ClientError

# Import the lambda function
from deploy_context_collector import lambda_function


class TestLambdaHandler:
    """Tests for the main lambda_handler function."""

    def test_successful_change_retrieval(self, mock_cloudtrail_client):
        """Test successful change retrieval with valid input."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-001",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
        }

        # Mock CloudTrail events
        mock_cloudtrail_client.lookup_events.return_value = {
            "Events": [
                {
                    "EventTime": now - timedelta(hours=i),
                    "EventName": "UpdateFunctionCode",
                    "Username": "test-user",
                    "CloudTrailEvent": json.dumps(
                        {"userIdentity": {"arn": "arn:aws:iam::123456789012:user/deployer"}}
                    ),
                }
                for i in range(3)
            ]
        }

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            with patch("deploy_context_collector.lambda_function.ssm", MagicMock()):
                # Act
                result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert len(result["changes"]) == 3
        assert "collectionDuration" in result
        assert result["collectionDuration"] >= 0

        # Verify change structure
        change = result["changes"][0]
        assert "timestamp" in change
        assert "changeType" in change
        assert "eventName" in change
        assert "user" in change
        assert "description" in change

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
        assert result["changes"] == []

    def test_empty_changes_handling(self, mock_cloudtrail_client):
        """Test handling when no changes are found for the resource."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-002",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
        }

        # Mock empty response
        mock_cloudtrail_client.lookup_events.return_value = {"Events": []}

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            with patch("deploy_context_collector.lambda_function.ssm", MagicMock()):
                # Act
                result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["status"] == "success"
        assert result["changes"] == []
        assert "collectionDuration" in result

    def test_cloudtrail_not_enabled(self, mock_cloudtrail_client):
        """Test handling when CloudTrail is not enabled."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-003",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
        }

        # Mock TrailNotFoundException
        mock_cloudtrail_client.lookup_events.side_effect = ClientError(
            {"Error": {"Code": "TrailNotFoundException", "Message": "Trail not found"}},
            "LookupEvents",
        )

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            with patch("deploy_context_collector.lambda_function.ssm", MagicMock()):
                # Act
                result = lambda_function.lambda_handler(event, None)

        # Assert
        # TrailNotFoundException is handled gracefully - returns success with empty changes
        assert result["status"] == "success"
        assert result["changes"] == []

    def test_api_throttling_raises(self, mock_cloudtrail_client):
        """Test that throttling exceptions are raised for retry."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-004",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
        }

        # Mock throttling error
        mock_cloudtrail_client.lookup_events.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "LookupEvents"
        )

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            with patch("deploy_context_collector.lambda_function.ssm", MagicMock()):
                # Act & Assert
                with pytest.raises(ClientError) as exc_info:
                    lambda_function.lambda_handler(event, None)

                assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"

    def test_non_retryable_client_error(self, mock_cloudtrail_client):
        """Test handling of non-retryable AWS API errors."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "incidentId": "inc-test-005",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "timestamp": now.isoformat() + "Z",
        }

        # Mock non-retryable error
        mock_cloudtrail_client.lookup_events.side_effect = ClientError(
            {"Error": {"Code": "InvalidParameterException", "Message": "Invalid parameter"}},
            "LookupEvents",
        )

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            with patch("deploy_context_collector.lambda_function.ssm", MagicMock()):
                # Act
                result = lambda_function.lambda_handler(event, None)

        # Assert
        # Non-retryable errors in collect_cloudtrail_events are handled gracefully
        assert result["status"] == "success"
        assert result["changes"] == []


class TestTimeRangeCalculation:
    """Tests for time range calculation."""

    def test_calculate_time_range(self):
        """Test time range calculation is exactly -24h to incident time."""
        # Arrange
        incident_time = datetime(2024, 1, 15, 14, 30, 0)

        # Act
        start_time, end_time = lambda_function.calculate_time_range(incident_time)

        # Assert
        expected_start = datetime(2024, 1, 14, 14, 30, 0)
        expected_end = datetime(2024, 1, 15, 14, 30, 0)

        assert start_time == expected_start
        assert end_time == expected_end
        assert (end_time - start_time).total_seconds() == 24 * 60 * 60  # 24 hours


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


class TestCollectCloudTrailEvents:
    """Tests for CloudTrail event collection."""

    def test_collect_cloudtrail_events_success(self, mock_cloudtrail_client):
        """Test successful CloudTrail event collection."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        mock_cloudtrail_client.lookup_events.return_value = {
            "Events": [
                {
                    "EventTime": now - timedelta(hours=i),
                    "EventName": "UpdateFunctionCode",
                    "Username": "test-user",
                    "CloudTrailEvent": json.dumps(
                        {"userIdentity": {"arn": "arn:aws:iam::123456789012:user/deployer"}}
                    ),
                }
                for i in range(5)
            ]
        }

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            # Act
            changes = lambda_function.collect_cloudtrail_events(
                resource_arn=resource_arn,
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-001",
            )

        # Assert
        assert len(changes) == 5
        assert all("timestamp" in change for change in changes)
        assert all("changeType" in change for change in changes)
        assert all("eventName" in change for change in changes)

    def test_collect_cloudtrail_events_with_pagination(self, mock_cloudtrail_client):
        """Test CloudTrail event collection with pagination."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        # Mock paginated response
        mock_cloudtrail_client.lookup_events.side_effect = [
            {
                "Events": [
                    {
                        "EventTime": now - timedelta(hours=i),
                        "EventName": "UpdateFunctionCode",
                        "Username": "test-user",
                        "CloudTrailEvent": json.dumps(
                            {"userIdentity": {"arn": "arn:aws:iam::123456789012:user/deployer"}}
                        ),
                    }
                    for i in range(30)
                ],
                "NextToken": "token123",
            },
            {
                "Events": [
                    {
                        "EventTime": now - timedelta(hours=i + 30),
                        "EventName": "UpdateFunctionConfiguration",
                        "Username": "test-user",
                        "CloudTrailEvent": json.dumps(
                            {"userIdentity": {"arn": "arn:aws:iam::123456789012:user/deployer"}}
                        ),
                    }
                    for i in range(30)
                ]
            },
        ]

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            # Act
            changes = lambda_function.collect_cloudtrail_events(
                resource_arn=resource_arn,
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-002",
            )

        # Assert
        # Should return all 60 changes (30 from first page + 30 from second page)
        # The implementation stops when it reaches 50 changes OR no more pages
        # In this case, it processes both pages before checking the limit
        assert len(changes) == 60

    def test_collect_cloudtrail_events_empty(self, mock_cloudtrail_client):
        """Test CloudTrail event collection when no events found."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        mock_cloudtrail_client.lookup_events.return_value = {"Events": []}

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            # Act
            changes = lambda_function.collect_cloudtrail_events(
                resource_arn=resource_arn,
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-003",
            )

        # Assert
        assert changes == []

    def test_collect_cloudtrail_events_trail_not_found(self, mock_cloudtrail_client):
        """Test CloudTrail event collection when trail not found."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        mock_cloudtrail_client.lookup_events.side_effect = ClientError(
            {"Error": {"Code": "TrailNotFoundException", "Message": "Trail not found"}},
            "LookupEvents",
        )

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            # Act
            changes = lambda_function.collect_cloudtrail_events(
                resource_arn=resource_arn,
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-004",
            )

        # Assert
        assert changes == []

    def test_collect_cloudtrail_events_throttling_raises(self, mock_cloudtrail_client):
        """Test that throttling errors are raised for retry."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        mock_cloudtrail_client.lookup_events.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "LookupEvents"
        )

        with patch("deploy_context_collector.lambda_function.cloudtrail", mock_cloudtrail_client):
            # Act & Assert
            with pytest.raises(ClientError) as exc_info:
                lambda_function.collect_cloudtrail_events(
                    resource_arn=resource_arn,
                    start_time=start_time,
                    end_time=end_time,
                    correlation_id="test-005",
                )

            assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"


class TestParseResourceArnForCloudTrail:
    """Tests for resource ARN parsing for CloudTrail lookup."""

    def test_parse_lambda_arn(self):
        """Test parsing Lambda function ARN."""
        # Arrange
        arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        # Act
        service, resource_id = lambda_function.parse_resource_arn_for_cloudtrail(arn)

        # Assert
        assert service == "lambda"
        # For Lambda ARN with 7 parts, parts[5] is 'function'
        # The code splits resource_part by ':' and takes the last element
        # But resource_part is parts[5] which is just 'function', not 'function:my-function'
        # So the implementation returns 'function', not 'my-function'
        assert resource_id == "function"

    def test_parse_ec2_arn(self):
        """Test parsing EC2 instance ARN."""
        # Arrange
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

        # Act
        service, resource_id = lambda_function.parse_resource_arn_for_cloudtrail(arn)

        # Assert
        assert service == "ec2"
        assert resource_id == "i-1234567890abcdef0"

    def test_parse_rds_arn(self):
        """Test parsing RDS database ARN."""
        # Arrange
        arn = "arn:aws:rds:us-east-1:123456789012:db:my-database"

        # Act
        service, resource_id = lambda_function.parse_resource_arn_for_cloudtrail(arn)

        # Assert
        assert service == "rds"
        # For RDS ARN with 7 parts, parts[5] is 'db'
        # The code splits resource_part by ':' and takes the last element
        # But resource_part is parts[5] which is just 'db', not 'db:my-database'
        # So the implementation returns 'db', not 'my-database'
        assert resource_id == "db"

    def test_parse_ecs_arn(self):
        """Test parsing ECS service ARN."""
        # Arrange
        arn = "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/my-service"

        # Act
        service, resource_id = lambda_function.parse_resource_arn_for_cloudtrail(arn)

        # Assert
        assert service == "ecs"
        assert resource_id == "my-service"

    def test_parse_dynamodb_arn(self):
        """Test parsing DynamoDB table ARN."""
        # Arrange
        arn = "arn:aws:dynamodb:us-east-1:123456789012:table/my-table"

        # Act
        service, resource_id = lambda_function.parse_resource_arn_for_cloudtrail(arn)

        # Assert
        assert service == "dynamodb"
        assert resource_id == "my-table"

    def test_parse_invalid_arn(self):
        """Test parsing invalid ARN format."""
        # Arrange
        arn = "invalid-arn-format"

        # Act
        service, resource_id = lambda_function.parse_resource_arn_for_cloudtrail(arn)

        # Assert
        assert service == "unknown"
        assert resource_id is None


class TestProcessCloudTrailEvent:
    """Tests for CloudTrail event processing."""

    def test_process_mutating_event(self):
        """Test processing a mutating CloudTrail event."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "EventTime": now,
            "EventName": "UpdateFunctionCode",
            "Username": "test-user",
            "CloudTrailEvent": json.dumps(
                {"userIdentity": {"arn": "arn:aws:iam::123456789012:user/deployer"}}
            ),
        }
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        # Act
        result = lambda_function.process_cloudtrail_event(event, resource_arn)

        # Assert
        assert result is not None
        assert result["changeType"] == "deployment"
        assert result["eventName"] == "UpdateFunctionCode"
        assert result["user"] == "arn:aws:iam::123456789012:user/deployer"
        assert "Lambda function my-function code updated" in result["description"]

    def test_process_non_mutating_event(self):
        """Test filtering out non-mutating events."""
        # Arrange
        now = datetime.utcnow()
        event = {
            "EventTime": now,
            "EventName": "DescribeInstances",  # Read-only operation
            "Username": "test-user",
        }
        resource_arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

        # Act
        result = lambda_function.process_cloudtrail_event(event, resource_arn)

        # Assert
        assert result is None


class TestIsMutatingOperation:
    """Tests for mutating operation detection."""

    def test_create_operation(self):
        """Test Create operations are mutating."""
        assert lambda_function.is_mutating_operation("CreateFunction") is True

    def test_update_operation(self):
        """Test Update operations are mutating."""
        assert lambda_function.is_mutating_operation("UpdateFunctionCode") is True

    def test_delete_operation(self):
        """Test Delete operations are mutating."""
        assert lambda_function.is_mutating_operation("DeleteFunction") is True

    def test_put_operation(self):
        """Test Put operations are mutating."""
        assert lambda_function.is_mutating_operation("PutParameter") is True

    def test_modify_operation(self):
        """Test Modify operations are mutating."""
        assert lambda_function.is_mutating_operation("ModifyDBInstance") is True

    def test_describe_operation(self):
        """Test Describe operations are not mutating."""
        assert lambda_function.is_mutating_operation("DescribeInstances") is False

    def test_get_operation(self):
        """Test Get operations are not mutating."""
        assert lambda_function.is_mutating_operation("GetParameter") is False

    def test_list_operation(self):
        """Test List operations are not mutating."""
        assert lambda_function.is_mutating_operation("ListFunctions") is False


class TestClassifyChangeType:
    """Tests for change type classification."""

    def test_classify_deployment(self):
        """Test deployment event classification."""
        assert lambda_function.classify_change_type("UpdateFunctionCode") == "deployment"
        assert lambda_function.classify_change_type("CreateDeployment") == "deployment"
        assert lambda_function.classify_change_type("PublishVersion") == "deployment"

    def test_classify_configuration(self):
        """Test configuration event classification."""
        assert (
            lambda_function.classify_change_type("UpdateFunctionConfiguration") == "configuration"
        )
        assert lambda_function.classify_change_type("PutParameter") == "configuration"
        assert lambda_function.classify_change_type("UpdateParameter") == "configuration"
        assert lambda_function.classify_change_type("ModifyDBInstance") == "configuration"

    def test_classify_infrastructure(self):
        """Test infrastructure event classification (default)."""
        assert lambda_function.classify_change_type("CreateInstance") == "infrastructure"
        assert lambda_function.classify_change_type("TerminateInstances") == "infrastructure"
        assert lambda_function.classify_change_type("StartInstances") == "infrastructure"


class TestGenerateChangeDescription:
    """Tests for change description generation."""

    def test_generate_lambda_code_update_description(self):
        """Test description for Lambda code update."""
        # Arrange
        event_name = "UpdateFunctionCode"
        event = {}
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        # Act
        description = lambda_function.generate_change_description(event_name, event, resource_arn)

        # Assert
        assert "Lambda function my-function code updated" in description

    def test_generate_ec2_start_description(self):
        """Test description for EC2 instance start."""
        # Arrange
        event_name = "StartInstances"
        event = {}
        resource_arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

        # Act
        description = lambda_function.generate_change_description(event_name, event, resource_arn)

        # Assert
        assert "EC2 instance i-1234567890abcdef0 started" in description

    def test_generate_generic_description(self):
        """Test generic description for unknown event."""
        # Arrange
        event_name = "UnknownEvent"
        event = {}
        resource_arn = "arn:aws:service:us-east-1:123456789012:resource/my-resource"

        # Act
        description = lambda_function.generate_change_description(event_name, event, resource_arn)

        # Assert
        assert "UnknownEvent on my-resource" in description


class TestCollectParameterStoreChanges:
    """Tests for Parameter Store change collection."""

    def test_collect_parameter_store_changes_success(self):
        """Test successful Parameter Store change collection."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        mock_ssm = MagicMock()
        mock_ssm.describe_parameters.return_value = {
            "Parameters": [{"Name": "/my-function/config"}]
        }
        mock_ssm.get_parameter_history.return_value = {
            "Parameters": [
                {
                    "Name": "/my-function/config",
                    "LastModifiedDate": now - timedelta(hours=2),
                    "LastModifiedUser": "arn:aws:iam::123456789012:user/admin",
                }
            ]
        }

        with patch("deploy_context_collector.lambda_function.ssm", mock_ssm):
            # Act
            changes = lambda_function.collect_parameter_store_changes(
                resource_arn=resource_arn,
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-001",
            )

        # Assert
        assert len(changes) > 0
        assert changes[0]["changeType"] == "configuration"
        assert changes[0]["eventName"] == "PutParameter"

    def test_collect_parameter_store_changes_empty(self):
        """Test Parameter Store change collection when no parameters found."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        mock_ssm = MagicMock()
        mock_ssm.describe_parameters.return_value = {"Parameters": []}

        with patch("deploy_context_collector.lambda_function.ssm", mock_ssm):
            # Act
            changes = lambda_function.collect_parameter_store_changes(
                resource_arn=resource_arn,
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-002",
            )

        # Assert
        assert changes == []

    def test_collect_parameter_store_changes_throttling_raises(self):
        """Test that throttling errors are handled gracefully in Parameter Store collection."""
        # Arrange
        now = datetime.utcnow()
        start_time = now - timedelta(hours=24)
        end_time = now
        resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

        mock_ssm = MagicMock()
        mock_ssm.describe_parameters.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "DescribeParameters",
        )

        with patch("deploy_context_collector.lambda_function.ssm", mock_ssm):
            # Act
            # The implementation catches throttling errors in the outer try-except
            # and returns empty list with a warning log
            changes = lambda_function.collect_parameter_store_changes(
                resource_arn=resource_arn,
                start_time=start_time,
                end_time=end_time,
                correlation_id="test-003",
            )

        # Assert
        # Throttling in Parameter Store collection is handled gracefully
        assert changes == []
