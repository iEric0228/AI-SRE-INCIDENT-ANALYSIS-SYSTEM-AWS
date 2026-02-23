"""
EventBridge Event Transformer Lambda Function

This function transforms CloudWatch Alarm state change events from EventBridge
into normalized IncidentEvent objects and publishes them to SNS for orchestration.

Requirements: 1.1, 1.2, 1.3
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sns_client = boto3.client("sns")


def extract_resource_arn(alarm_event: Dict[str, Any]) -> str:
    """
    Extract resource ARN from CloudWatch Alarm event.

    CloudWatch Alarms may include resource ARN in different locations:
    - detail.configuration.metrics[].metricStat.metric.dimensions
    - detail.alarmArn (for the alarm itself)

    Args:
        alarm_event: CloudWatch Alarm state change event from EventBridge

    Returns:
        Resource ARN string, or alarm ARN if resource ARN not found
    """
    try:
        # Try to extract from alarm configuration
        detail = alarm_event.get("detail", {})
        configuration = detail.get("configuration", {})

        # Check for resource dimensions in metrics
        metrics = configuration.get("metrics", [])
        for metric in metrics:
            metric_stat = metric.get("metricStat", {})
            metric_info = metric_stat.get("metric", {})
            dimensions = metric_info.get("dimensions", {})

            # Common dimension names that contain resource identifiers
            if "InstanceId" in dimensions:
                instance_id = dimensions["InstanceId"]
                region = alarm_event.get("region", "us-east-1")
                account = alarm_event.get("account", "")
                return f"arn:aws:ec2:{region}:{account}:instance/{instance_id}"

            if "FunctionName" in dimensions:
                function_name = dimensions["FunctionName"]
                region = alarm_event.get("region", "us-east-1")
                account = alarm_event.get("account", "")
                return f"arn:aws:lambda:{region}:{account}:function:{function_name}"

            if "DBInstanceIdentifier" in dimensions:
                db_instance = dimensions["DBInstanceIdentifier"]
                region = alarm_event.get("region", "us-east-1")
                account = alarm_event.get("account", "")
                return f"arn:aws:rds:{region}:{account}:db:{db_instance}"

            if "ClusterName" in dimensions:
                cluster_name = dimensions["ClusterName"]
                region = alarm_event.get("region", "us-east-1")
                account = alarm_event.get("account", "")
                return f"arn:aws:ecs:{region}:{account}:cluster/{cluster_name}"

        # Fallback to alarm ARN if resource ARN not found
        alarm_arn = detail.get("alarmArn", "")
        if alarm_arn:
            return alarm_arn

        # Last resort: construct generic ARN
        alarm_name = detail.get("alarmName", "unknown")
        region = alarm_event.get("region", "us-east-1")
        account = alarm_event.get("account", "")
        return f"arn:aws:cloudwatch:{region}:{account}:alarm:{alarm_name}"

    except Exception as e:
        logger.warning(f"Error extracting resource ARN: {e}")
        # Return alarm ARN as fallback
        return alarm_event.get("detail", {}).get("alarmArn", "unknown")


def transform_alarm_event(alarm_event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform CloudWatch Alarm event into normalized IncidentEvent structure.

    Args:
        alarm_event: CloudWatch Alarm state change event from EventBridge

    Returns:
        Normalized IncidentEvent dictionary

    Raises:
        ValueError: If required fields are missing from alarm event
    """
    try:
        detail = alarm_event.get("detail", {})

        # Validate required fields
        if not detail:
            raise ValueError("Missing 'detail' field in alarm event")

        alarm_name = detail.get("alarmName")
        if not alarm_name:
            raise ValueError("Missing 'alarmName' in alarm event detail")

        # Generate unique incident ID
        incident_id = str(uuid.uuid4())

        # Extract alarm details
        alarm_arn = detail.get("alarmArn", "")
        alarm_state = detail.get("state", {}).get("value", "ALARM")
        alarm_description = detail.get("alarmDescription", "")

        # Extract metric information
        configuration = detail.get("configuration", {})
        metric_name = configuration.get("metricName", "Unknown")
        namespace = configuration.get("namespace", "Unknown")

        # Extract resource ARN
        resource_arn = extract_resource_arn(alarm_event)

        # Get timestamp (use event time or current time)
        timestamp_str = alarm_event.get(
            "time",
            (
                datetime.now(datetime.UTC).isoformat()
                if hasattr(datetime, "UTC")
                else datetime.utcnow().isoformat()
            ),
        )

        # Parse timestamp to calculate TTL (90 days from incident)
        try:
            # Parse ISO-8601 timestamp
            if timestamp_str.endswith("Z"):
                timestamp_dt = datetime.fromisoformat(timestamp_str[:-1])
            else:
                timestamp_dt = datetime.fromisoformat(timestamp_str)

            # Calculate Unix timestamp
            unix_timestamp = int(timestamp_dt.timestamp())

            # Add 90 days (7,776,000 seconds)
            ttl = unix_timestamp + 7776000
        except Exception as e:
            logger.warning(f"Error calculating TTL: {e}, using default")
            # Fallback: current time + 90 days
            ttl = int(datetime.utcnow().timestamp()) + 7776000

        # Create normalized incident event
        incident_event = {
            "incidentId": incident_id,
            "alarmName": alarm_name,
            "alarmArn": alarm_arn,
            "resourceArn": resource_arn,
            "timestamp": timestamp_str,
            "ttl": ttl,
            "alarmState": alarm_state,
            "metricName": metric_name,
            "namespace": namespace,
            "alarmDescription": alarm_description if alarm_description else None,
        }

        logger.info(
            {
                "message": "Transformed alarm event to incident event",
                "incidentId": incident_id,
                "alarmName": alarm_name,
                "resourceArn": resource_arn,
                "alarmState": alarm_state,
            }
        )

        return incident_event

    except Exception as e:
        logger.error(
            {
                "message": "Error transforming alarm event",
                "error": str(e),
                "errorType": type(e).__name__,
                "alarmEvent": alarm_event,
            }
        )
        raise


def publish_to_sns(incident_event: Dict[str, Any]) -> str:
    """
    Publish incident event to SNS topic for orchestration.

    Args:
        incident_event: Normalized incident event dictionary

    Returns:
        SNS message ID

    Raises:
        ClientError: If SNS publish fails
    """
    try:
        # Get SNS topic ARN from environment
        sns_topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
        if not sns_topic_arn:
            raise ValueError("SNS_TOPIC_ARN environment variable not set")

        # Publish to SNS
        response = sns_client.publish(
            TopicArn=sns_topic_arn,
            Message=json.dumps(incident_event),
            Subject=f"Incident: {incident_event['alarmName']}",
            MessageAttributes={
                "incidentId": {"DataType": "String", "StringValue": incident_event["incidentId"]},
                "alarmState": {"DataType": "String", "StringValue": incident_event["alarmState"]},
            },
        )

        message_id = response["MessageId"]

        logger.info(
            {
                "message": "Published incident event to SNS",
                "incidentId": incident_event["incidentId"],
                "messageId": message_id,
                "topicArn": sns_topic_arn,
            }
        )

        return message_id

    except ClientError as e:
        logger.error(
            {
                "message": "Failed to publish to SNS",
                "incidentId": incident_event.get("incidentId", "unknown"),
                "error": str(e),
                "errorCode": e.response["Error"]["Code"],
            }
        )
        raise
    except Exception as e:
        logger.error(
            {
                "message": "Unexpected error publishing to SNS",
                "incidentId": incident_event.get("incidentId", "unknown"),
                "error": str(e),
                "errorType": type(e).__name__,
            }
        )
        raise


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for EventBridge event transformer.

    Receives CloudWatch Alarm state change events from EventBridge,
    transforms them into normalized IncidentEvent objects, and publishes
    to SNS for orchestration by Step Functions.

    Args:
        event: EventBridge event containing CloudWatch Alarm state change
        context: Lambda context object

    Returns:
        Response dictionary with status and incident details
    """
    try:
        logger.info(
            {
                "message": "Event transformer invoked",
                "eventSource": event.get("source"),
                "detailType": event.get("detail-type"),
            }
        )

        # Validate event source
        if event.get("source") != "aws.cloudwatch":
            logger.warning(
                {
                    "message": "Unexpected event source",
                    "source": event.get("source"),
                    "expected": "aws.cloudwatch",
                }
            )

        # Transform alarm event to incident event
        incident_event = transform_alarm_event(event)

        # Publish to SNS
        message_id = publish_to_sns(incident_event)

        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "incidentId": incident_event["incidentId"],
                    "messageId": message_id,
                    "alarmName": incident_event["alarmName"],
                    "resourceArn": incident_event["resourceArn"],
                }
            ),
        }

    except ValueError as e:
        # Non-retryable validation error
        logger.error(
            {"message": "Validation error", "error": str(e), "errorType": "ValidationException"}
        )
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"status": "failed", "error": str(e), "errorType": "ValidationException"}
            ),
        }

    except ClientError as e:
        # AWS service error - may be retryable
        error_code = e.response["Error"]["Code"]
        if error_code in ["Throttling", "ServiceUnavailable", "InternalError"]:
            # Retryable error - raise to trigger Lambda retry
            logger.warning(
                {"message": "Retryable AWS error", "errorCode": error_code, "error": str(e)}
            )
            raise
        else:
            # Non-retryable error
            logger.error(
                {"message": "Non-retryable AWS error", "errorCode": error_code, "error": str(e)}
            )
            return {
                "statusCode": 500,
                "body": json.dumps({"status": "failed", "error": str(e), "errorType": error_code}),
            }

    except Exception as e:
        # Unexpected error
        logger.error(
            {
                "message": "Unexpected error in event transformer",
                "error": str(e),
                "errorType": type(e).__name__,
            }
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"status": "failed", "error": str(e), "errorType": "UnexpectedError"}
            ),
        }
