"""
Property-based tests for incident query capability.

Property 24: Incident Query Capability
For any stored incident, it must be retrievable by resource ARN, time range, or severity.

Validates Requirements: 9.3

NOTE: This test creates a single DynamoDB table and stores multiple incidents in it.
The table is shared across all hypothesis examples within a single test run.
"""

from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings, HealthCheck
import pytest
from moto import mock_aws
import boto3
from shared.models import IncidentRecord


# Strategy for generating valid incident IDs (UUIDs)
@st.composite
def incident_id_strategy(draw):
    """Generate valid UUID v4 incident IDs."""
    import uuid

    return str(uuid.uuid4())


# Strategy for generating resource ARNs
@st.composite
def resource_arn_strategy(draw):
    """Generate valid AWS resource ARNs."""
    service = draw(st.sampled_from(["lambda", "ec2", "rds", "ecs", "dynamodb"]))
    region = draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]))
    account = draw(st.integers(min_value=100000000000, max_value=999999999999))
    resource_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"
            ),
            min_size=1,
            max_size=50,
        )
    )

    return f"arn:aws:{service}:{region}:{account}:function/{resource_name}"


@mock_aws
def test_incident_query_capability_wrapper():
    """
    Wrapper function to set up DynamoDB table once for all hypothesis examples.
    """
    # Setup: Create DynamoDB table with GSIs
    dynamodb = boto3.client("dynamodb", region_name="us-east-1")
    table_name = "incident-analysis-store"

    # Create table with primary key and GSIs
    dynamodb.create_table(
        TableName=table_name,
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
                "IndexName": "ResourceIndex",
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

    # Run the actual property test
    _incident_query_capability_inner(dynamodb, table_name)


@given(
    incident_id=incident_id_strategy(),
    timestamp=st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)),
    resource_arn=resource_arn_strategy(),
    severity=st.sampled_from(["critical", "high", "medium", "low"]),
)
@settings(deadline=2000)  # 2 second deadline for DynamoDB operations
@pytest.mark.property_test
@pytest.mark.tag("Feature: ai-sre-incident-analysis, Property 24: Incident Query Capability")
def _incident_query_capability_inner(
    dynamodb, table_name, incident_id, timestamp, resource_arn, severity
):
    """
    Property 24: For any stored incident, it must be retrievable by resource ARN,
    time range, or severity.

    Validates Requirements: 9.3

    PROPERTY ASSERTIONS:
    1. Incident must be retrievable by incident ID (primary key)
    2. Incident must be retrievable by resource ARN (GSI)
    3. Incident must be retrievable by severity (GSI)
    4. Incident must be retrievable by time range
    5. Query results must match stored incident data
    """

    # Calculate TTL (90 days from incident timestamp)
    ttl_timestamp = int((timestamp + timedelta(days=90)).timestamp())

    # Create incident record
    record = IncidentRecord(
        incident_id=incident_id,
        timestamp=timestamp.isoformat(),
        resource_arn=resource_arn,
        resource_type="lambda",
        alarm_name="HighErrorRate",
        severity=severity,
        structured_context={
            "incidentId": incident_id,
            "timestamp": timestamp.isoformat(),
            "resource": {"arn": resource_arn, "type": "lambda", "name": "test"},
            "alarm": {"name": "HighErrorRate", "metric": "Errors", "threshold": 10.0},
            "metrics": {},
            "logs": {},
            "changes": {},
            "completeness": {"metrics": True, "logs": True, "changes": True},
        },
        analysis_report={
            "incidentId": incident_id,
            "timestamp": timestamp.isoformat(),
            "analysis": {
                "rootCauseHypothesis": "Test hypothesis",
                "confidence": "high",
                "evidence": [],
                "contributingFactors": [],
                "recommendedActions": [],
            },
            "metadata": {
                "modelId": "anthropic.claude-v2",
                "modelVersion": "2.1",
                "promptVersion": "v1.0",
                "tokenUsage": {"input": 100, "output": 50},
                "latency": 2.5,
            },
        },
        notification_status={
            "status": "success",
            "deliveryStatus": {
                "slack": "delivered",
                "email": "delivered",
                "slackError": None,
                "emailError": None,
            },
            "notificationDuration": 1.5,
        },
        ttl=ttl_timestamp,
    )

    # Store incident in DynamoDB
    dynamodb_item = record.to_dynamodb_item()
    dynamodb.put_item(TableName=table_name, Item=dynamodb_item)

    # PROPERTY ASSERTION 1: Incident must be retrievable by incident ID (primary key)
    response = dynamodb.get_item(
        TableName=table_name,
        Key={"incidentId": {"S": incident_id}, "timestamp": {"S": timestamp.isoformat()}},
    )

    assert "Item" in response, "Incident must be retrievable by incident ID"
    assert (
        response["Item"]["incidentId"]["S"] == incident_id
    ), "Retrieved incident ID must match stored incident ID"
    assert (
        response["Item"]["timestamp"]["S"] == timestamp.isoformat()
    ), "Retrieved timestamp must match stored timestamp"

    # PROPERTY ASSERTION 2: Incident must be retrievable by resource ARN (GSI)
    response = dynamodb.query(
        TableName=table_name,
        IndexName="ResourceIndex",
        KeyConditionExpression="resourceArn = :arn",
        ExpressionAttributeValues={":arn": {"S": resource_arn}},
    )

    assert "Items" in response, "Query by resource ARN must return results"
    assert response["Count"] >= 1, "Query by resource ARN must find at least one incident"

    # Find our incident in the results
    found = False
    for item in response["Items"]:
        if item["incidentId"]["S"] == incident_id:
            found = True
            assert (
                item["resourceArn"]["S"] == resource_arn
            ), "Retrieved resource ARN must match stored resource ARN"
            break

    assert found, "Incident must be found when querying by resource ARN"

    # PROPERTY ASSERTION 3: Incident must be retrievable by severity (GSI)
    response = dynamodb.query(
        TableName=table_name,
        IndexName="SeverityIndex",
        KeyConditionExpression="severity = :sev",
        ExpressionAttributeValues={":sev": {"S": severity}},
    )

    assert "Items" in response, "Query by severity must return results"
    assert response["Count"] >= 1, "Query by severity must find at least one incident"

    # Find our incident in the results
    found = False
    for item in response["Items"]:
        if item["incidentId"]["S"] == incident_id:
            found = True
            assert (
                item["severity"]["S"] == severity
            ), "Retrieved severity must match stored severity"
            break

    assert found, "Incident must be found when querying by severity"

    # PROPERTY ASSERTION 4: Incident must be retrievable by time range
    # Query for incidents within a time range that includes our incident
    start_time = (timestamp - timedelta(hours=1)).isoformat()
    end_time = (timestamp + timedelta(hours=1)).isoformat()

    response = dynamodb.query(
        TableName=table_name,
        IndexName="ResourceIndex",
        KeyConditionExpression="resourceArn = :arn AND #ts BETWEEN :start AND :end",
        ExpressionAttributeNames={"#ts": "timestamp"},
        ExpressionAttributeValues={
            ":arn": {"S": resource_arn},
            ":start": {"S": start_time},
            ":end": {"S": end_time},
        },
    )

    assert "Items" in response, "Query by time range must return results"
    assert response["Count"] >= 1, "Query by time range must find at least one incident"

    # Find our incident in the results
    found = False
    for item in response["Items"]:
        if item["incidentId"]["S"] == incident_id:
            found = True
            item_timestamp = item["timestamp"]["S"]
            assert (
                start_time <= item_timestamp <= end_time
            ), "Retrieved incident timestamp must be within query time range"
            break

    assert found, "Incident must be found when querying by time range"

    # PROPERTY ASSERTION 5: Query results must match stored incident data
    # Verify that all query methods return the same incident data
    response = dynamodb.get_item(
        TableName=table_name,
        Key={"incidentId": {"S": incident_id}, "timestamp": {"S": timestamp.isoformat()}},
    )

    retrieved_item = response["Item"]

    # Verify all required fields are present and match
    assert retrieved_item["incidentId"]["S"] == incident_id
    assert retrieved_item["timestamp"]["S"] == timestamp.isoformat()
    assert retrieved_item["resourceArn"]["S"] == resource_arn
    assert retrieved_item["resourceType"]["S"] == "lambda"
    assert retrieved_item["alarmName"]["S"] == "HighErrorRate"
    assert retrieved_item["severity"]["S"] == severity
    assert "structuredContext" in retrieved_item
    assert "analysisReport" in retrieved_item
    assert "notificationStatus" in retrieved_item
    assert "ttl" in retrieved_item
