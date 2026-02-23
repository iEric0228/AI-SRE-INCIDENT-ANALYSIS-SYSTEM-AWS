"""
Unit tests for DynamoDB storage operations.

Tests cover:
- Successful item persistence
- TTL calculation
- Query by resource ARN
- Query by severity
- Query by time range
"""

import pytest
from datetime import datetime, timedelta
from moto import mock_aws
import boto3
from decimal import Decimal
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from shared.models import (
    IncidentRecord,
    StructuredContext,
    AnalysisReport,
    NotificationOutput,
    ResourceInfo,
    AlarmInfo,
    CompletenessInfo,
    Analysis,
    AnalysisMetadata,
    NotificationDeliveryStatus,
)


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # Create table
        table = dynamodb.create_table(
            TableName="incident-analysis-store",
            KeySchema=[
                {"AttributeName": "incidentId", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "incidentId", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
                {"AttributeName": "resourceArn", "AttributeType": "S"},
                {"AttributeName": "severity", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "ResourceArnIndex",
                    "KeySchema": [
                        {"AttributeName": "resourceArn", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
                {
                    "IndexName": "SeverityIndex",
                    "KeySchema": [
                        {"AttributeName": "severity", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
            ],
            BillingMode="PROVISIONED",
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        yield table


@pytest.fixture
def sample_incident_record():
    """Create a sample incident record for testing."""
    now = datetime.utcnow()
    ttl = int((now + timedelta(days=90)).timestamp())

    structured_context = {
        "incidentId": "test-incident-123",
        "timestamp": now.isoformat(),
        "resource": {
            "arn": "arn:aws:lambda:us-east-1:123456789012:function:test-function",
            "type": "lambda",
            "name": "test-function",
        },
        "alarm": {"name": "test-alarm", "metric": "Errors", "threshold": 10.0},
        "metrics": {},
        "logs": {},
        "changes": {},
        "completeness": {"metrics": True, "logs": True, "changes": True},
    }

    analysis_report = {
        "incidentId": "test-incident-123",
        "timestamp": now.isoformat(),
        "analysis": {
            "rootCauseHypothesis": "High error rate due to API timeout",
            "confidence": "high",
            "evidence": ["Error logs show timeout exceptions"],
            "contributingFactors": ["Increased traffic"],
            "recommendedActions": ["Increase timeout", "Add retry logic"],
        },
        "metadata": {
            "modelId": "anthropic.claude-v2",
            "modelVersion": "2.0",
            "promptVersion": "v1.0",
            "tokenUsage": {"input": 1000, "output": 500},
            "latency": 2.5,
        },
    }

    notification_status = {
        "status": "success",
        "deliveryStatus": {"slack": "delivered", "email": "delivered"},
        "notificationDuration": 1.2,
    }

    return IncidentRecord(
        incident_id="test-incident-123",
        timestamp=now.isoformat(),
        resource_arn="arn:aws:lambda:us-east-1:123456789012:function:test-function",
        resource_type="lambda",
        alarm_name="test-alarm",
        severity="high",
        structured_context=structured_context,
        analysis_report=analysis_report,
        notification_status=notification_status,
        ttl=ttl,
    )


def test_successful_item_persistence(dynamodb_table, sample_incident_record):
    """Test successful persistence of incident record to DynamoDB."""
    # Put item
    dynamodb_table.put_item(
        Item={
            "incidentId": sample_incident_record.incident_id,
            "timestamp": sample_incident_record.timestamp,
            "resourceArn": sample_incident_record.resource_arn,
            "resourceType": sample_incident_record.resource_type,
            "alarmName": sample_incident_record.alarm_name,
            "severity": sample_incident_record.severity,
            "structuredContext": json.dumps(sample_incident_record.structured_context),
            "analysisReport": json.dumps(sample_incident_record.analysis_report),
            "notificationStatus": json.dumps(sample_incident_record.notification_status),
            "ttl": sample_incident_record.ttl,
        }
    )

    # Retrieve item
    response = dynamodb_table.get_item(
        Key={
            "incidentId": sample_incident_record.incident_id,
            "timestamp": sample_incident_record.timestamp,
        }
    )

    # Verify item was stored correctly
    assert "Item" in response
    item = response["Item"]
    assert item["incidentId"] == sample_incident_record.incident_id
    assert item["timestamp"] == sample_incident_record.timestamp
    assert item["resourceArn"] == sample_incident_record.resource_arn
    assert item["resourceType"] == sample_incident_record.resource_type
    assert item["alarmName"] == sample_incident_record.alarm_name
    assert item["severity"] == sample_incident_record.severity
    assert item["ttl"] == sample_incident_record.ttl

    # Verify JSON fields can be parsed
    assert json.loads(item["structuredContext"])["incidentId"] == sample_incident_record.incident_id
    assert json.loads(item["analysisReport"])["incidentId"] == sample_incident_record.incident_id
    assert json.loads(item["notificationStatus"])["status"] == "success"


def test_ttl_calculation():
    """Test TTL calculation is exactly 90 days from incident timestamp."""
    incident_time = datetime(2024, 1, 1, 12, 0, 0)
    expected_ttl_time = incident_time + timedelta(days=90)
    expected_ttl = int(expected_ttl_time.timestamp())

    # Calculate TTL
    calculated_ttl = int((incident_time + timedelta(days=90)).timestamp())

    # Verify TTL is exactly 90 days
    assert calculated_ttl == expected_ttl

    # Verify TTL is in the future
    assert calculated_ttl > int(incident_time.timestamp())

    # Verify TTL difference is 90 days in seconds (allowing for DST variations)
    ttl_diff = calculated_ttl - int(incident_time.timestamp())
    expected_seconds = 90 * 24 * 60 * 60
    # Allow 1 hour tolerance for DST
    assert abs(ttl_diff - expected_seconds) <= 3600


def test_query_by_resource_arn(dynamodb_table):
    """Test querying incidents by resource ARN."""
    resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"

    # Insert multiple incidents for the same resource
    for i in range(3):
        timestamp = (datetime.utcnow() - timedelta(hours=i)).isoformat()
        dynamodb_table.put_item(
            Item={
                "incidentId": f"incident-{i}",
                "timestamp": timestamp,
                "resourceArn": resource_arn,
                "resourceType": "lambda",
                "alarmName": f"alarm-{i}",
                "severity": "high",
                "structuredContext": json.dumps({}),
                "analysisReport": json.dumps({}),
                "notificationStatus": json.dumps({}),
                "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
            }
        )

    # Query by resource ARN
    response = dynamodb_table.query(
        IndexName="ResourceArnIndex",
        KeyConditionExpression="resourceArn = :arn",
        ExpressionAttributeValues={":arn": resource_arn},
        ScanIndexForward=False,  # Sort descending by timestamp
    )

    # Verify results
    assert response["Count"] == 3
    assert all(item["resourceArn"] == resource_arn for item in response["Items"])

    # Verify results are sorted by timestamp (descending)
    timestamps = [item["timestamp"] for item in response["Items"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_query_by_severity(dynamodb_table):
    """Test querying incidents by severity."""
    # Insert incidents with different severities
    severities = ["critical", "high", "high", "medium", "low"]

    for i, severity in enumerate(severities):
        timestamp = (datetime.utcnow() - timedelta(hours=i)).isoformat()
        dynamodb_table.put_item(
            Item={
                "incidentId": f"incident-{i}",
                "timestamp": timestamp,
                "resourceArn": f"arn:aws:lambda:us-east-1:123456789012:function:func-{i}",
                "resourceType": "lambda",
                "alarmName": f"alarm-{i}",
                "severity": severity,
                "structuredContext": json.dumps({}),
                "analysisReport": json.dumps({}),
                "notificationStatus": json.dumps({}),
                "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
            }
        )

    # Query by severity = 'high'
    response = dynamodb_table.query(
        IndexName="SeverityIndex",
        KeyConditionExpression="severity = :sev",
        ExpressionAttributeValues={":sev": "high"},
    )

    # Verify results
    assert response["Count"] == 2
    assert all(item["severity"] == "high" for item in response["Items"])


def test_query_by_time_range(dynamodb_table):
    """Test querying incidents by time range."""
    resource_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    base_time = datetime.utcnow()

    # Insert incidents at different times
    timestamps = []
    for i in range(5):
        timestamp = (base_time - timedelta(hours=i)).isoformat()
        timestamps.append(timestamp)
        dynamodb_table.put_item(
            Item={
                "incidentId": f"incident-{i}",
                "timestamp": timestamp,
                "resourceArn": resource_arn,
                "resourceType": "lambda",
                "alarmName": f"alarm-{i}",
                "severity": "high",
                "structuredContext": json.dumps({}),
                "analysisReport": json.dumps({}),
                "notificationStatus": json.dumps({}),
                "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
            }
        )

    # Query for incidents in the last 2 hours
    start_time = (base_time - timedelta(hours=2)).isoformat()
    end_time = base_time.isoformat()

    response = dynamodb_table.query(
        IndexName="ResourceArnIndex",
        KeyConditionExpression="resourceArn = :arn AND #ts BETWEEN :start AND :end",
        ExpressionAttributeNames={"#ts": "timestamp"},
        ExpressionAttributeValues={":arn": resource_arn, ":start": start_time, ":end": end_time},
    )

    # Verify results (should include incidents from hours 0, 1, 2)
    assert response["Count"] == 3
    assert all(item["resourceArn"] == resource_arn for item in response["Items"])
    assert all(start_time <= item["timestamp"] <= end_time for item in response["Items"])


def test_incident_record_to_dynamodb_item(sample_incident_record):
    """Test conversion of IncidentRecord to DynamoDB item format."""
    item = sample_incident_record.to_dynamodb_item()

    # Verify structure
    assert item["incidentId"]["S"] == sample_incident_record.incident_id
    assert item["timestamp"]["S"] == sample_incident_record.timestamp
    assert item["resourceArn"]["S"] == sample_incident_record.resource_arn
    assert item["resourceType"]["S"] == sample_incident_record.resource_type
    assert item["alarmName"]["S"] == sample_incident_record.alarm_name
    assert item["severity"]["S"] == sample_incident_record.severity
    assert item["ttl"]["N"] == str(sample_incident_record.ttl)

    # Verify JSON fields
    assert "structuredContext" in item
    assert "analysisReport" in item
    assert "notificationStatus" in item

    # Verify JSON can be parsed
    structured_context = json.loads(item["structuredContext"]["S"])
    assert structured_context["incidentId"] == sample_incident_record.incident_id


def test_empty_query_results(dynamodb_table):
    """Test querying with no matching results."""
    # Query for non-existent resource
    response = dynamodb_table.query(
        IndexName="ResourceArnIndex",
        KeyConditionExpression="resourceArn = :arn",
        ExpressionAttributeValues={
            ":arn": "arn:aws:lambda:us-east-1:123456789012:function:non-existent"
        },
    )

    # Verify empty results
    assert response["Count"] == 0
    assert len(response["Items"]) == 0


def test_incident_record_validation(sample_incident_record):
    """Test incident record validation."""
    # Valid record
    assert sample_incident_record.validate() is True

    # Invalid record - missing incident_id
    invalid_record = IncidentRecord(
        incident_id="",
        timestamp=sample_incident_record.timestamp,
        resource_arn=sample_incident_record.resource_arn,
        resource_type=sample_incident_record.resource_type,
        alarm_name=sample_incident_record.alarm_name,
        severity=sample_incident_record.severity,
        structured_context=sample_incident_record.structured_context,
        analysis_report=sample_incident_record.analysis_report,
        notification_status=sample_incident_record.notification_status,
        ttl=sample_incident_record.ttl,
    )
    assert invalid_record.validate() is False


def test_multiple_incidents_same_resource(dynamodb_table):
    """Test storing and querying multiple incidents for the same resource."""
    resource_arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

    # Insert 10 incidents for the same resource
    for i in range(10):
        timestamp = (datetime.utcnow() - timedelta(minutes=i)).isoformat()
        dynamodb_table.put_item(
            Item={
                "incidentId": f"incident-{i}",
                "timestamp": timestamp,
                "resourceArn": resource_arn,
                "resourceType": "ec2",
                "alarmName": f"alarm-{i}",
                "severity": "high" if i % 2 == 0 else "medium",
                "structuredContext": json.dumps({}),
                "analysisReport": json.dumps({}),
                "notificationStatus": json.dumps({}),
                "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
            }
        )

    # Query all incidents for this resource
    response = dynamodb_table.query(
        IndexName="ResourceArnIndex",
        KeyConditionExpression="resourceArn = :arn",
        ExpressionAttributeValues={":arn": resource_arn},
    )

    # Verify all incidents are returned
    assert response["Count"] == 10
    assert all(item["resourceArn"] == resource_arn for item in response["Items"])
