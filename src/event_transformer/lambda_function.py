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
from datetime import datetime, timezone
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sns_client = boto3.client("sns")
sfn_client = boto3.client("stepfunctions")


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
                # Distinguish EKS from ECS by metric namespace
                metric_namespace = metric_info.get("namespace", "")
                if metric_namespace in ("AWS/ContainerInsights", "ContainerInsights"):
                    return f"arn:aws:eks:{region}:{account}:cluster/{cluster_name}"
                return f"arn:aws:ecs:{region}:{account}:cluster/{cluster_name}"

            if "LoadBalancer" in dimensions:
                lb_value = dimensions["LoadBalancer"]
                region = alarm_event.get("region", "us-east-1")
                account = alarm_event.get("account", "")
                return f"arn:aws:elasticloadbalancing:{region}:{account}:loadbalancer/{lb_value}"

            if "CacheClusterId" in dimensions:
                cluster_id = dimensions["CacheClusterId"]
                region = alarm_event.get("region", "us-east-1")
                account = alarm_event.get("account", "")
                return f"arn:aws:elasticache:{region}:{account}:cluster:{cluster_id}"

            if "DomainName" in dimensions:
                domain_name = dimensions["DomainName"]
                region = alarm_event.get("region", "us-east-1")
                account = alarm_event.get("account", "")
                return f"arn:aws:es:{region}:{account}:domain/{domain_name}"

        # Fallback to alarm ARN if resource ARN not found
        alarm_arn = detail.get("alarmArn", "")
        if alarm_arn:
            return str(alarm_arn)

        # Last resort: construct generic ARN
        alarm_name = detail.get("alarmName", "unknown")
        region = alarm_event.get("region", "us-east-1")
        account = alarm_event.get("account", "")
        return f"arn:aws:cloudwatch:{region}:{account}:alarm:{alarm_name}"

    except Exception as e:
        logger.warning(f"Error extracting resource ARN: {e}")
        # Return alarm ARN as fallback
        return str(alarm_event.get("detail", {}).get("alarmArn", "unknown"))


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

        # Extract metric information from alarm configuration
        configuration = detail.get("configuration", {})
        metric_name = "Unknown"
        namespace = "Unknown"

        # CloudWatch alarm config nests metric info under metrics[].metricStat.metric
        metrics = configuration.get("metrics", [])
        if metrics:
            metric_stat = metrics[0].get("metricStat", {})
            metric_info = metric_stat.get("metric", {})
            metric_name = metric_info.get("name", metric_info.get("metricName", "Unknown"))
            namespace = metric_info.get("namespace", "Unknown")

        # Fallback to flat keys if present (some alarm formats)
        if metric_name == "Unknown":
            metric_name = configuration.get("metricName", "Unknown")
        if namespace == "Unknown":
            namespace = configuration.get("namespace", "Unknown")

        # Extract resource ARN
        resource_arn = extract_resource_arn(alarm_event)

        # Get timestamp (use event time or current time)
        timestamp_str = alarm_event.get(
            "time",
            (
                datetime.now(datetime.UTC).isoformat()
                if hasattr(datetime, "UTC")
                else datetime.now(timezone.utc).isoformat()
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
            ttl = int(datetime.now(timezone.utc).timestamp()) + 7776000

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
            "eventSource": "cloudwatch",
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

        return str(message_id)

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


def transform_guardduty_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform GuardDuty finding event into normalized IncidentEvent structure.

    Args:
        event: GuardDuty finding event from EventBridge

    Returns:
        Normalized IncidentEvent dictionary
    """
    detail = event.get("detail", {})

    incident_id = str(uuid.uuid4())
    finding_id = detail.get("id", "")
    finding_type = detail.get("type", "Unknown")
    severity_value = detail.get("severity", 0)
    description = detail.get("description", "")
    title = detail.get("title", finding_type)

    # Map GuardDuty severity (0-10) to high/medium/low
    if severity_value >= 7.0:
        severity = "high"
    elif severity_value >= 4.0:
        severity = "medium"
    else:
        severity = "low"

    # Extract affected resource ARN
    resource_info = detail.get("resource", {})
    resource_arn = _extract_guardduty_resource_arn(resource_info, event)

    # Get timestamp
    timestamp_str = event.get("time", detail.get("updatedAt", detail.get("createdAt", "")))

    # Calculate TTL (90 days)
    try:
        if timestamp_str.endswith("Z"):
            timestamp_dt = datetime.fromisoformat(timestamp_str[:-1])
        else:
            timestamp_dt = datetime.fromisoformat(timestamp_str)
        ttl = int(timestamp_dt.timestamp()) + 7776000
    except Exception:
        ttl = int(datetime.now(timezone.utc).timestamp()) + 7776000

    incident_event = {
        "incidentId": incident_id,
        "alarmName": title,
        "alarmArn": finding_id,
        "resourceArn": resource_arn,
        "timestamp": timestamp_str,
        "ttl": ttl,
        "alarmState": "ALARM",
        "metricName": finding_type,
        "namespace": "GuardDuty",
        "alarmDescription": description,
        "eventSource": "guardduty",
        "severity": severity,
        "guarddutyDetail": {
            "findingType": finding_type,
            "severity": severity_value,
            "accountId": detail.get("accountId", ""),
            "region": detail.get("region", event.get("region", "")),
        },
    }

    logger.info(
        {
            "message": "Transformed GuardDuty finding to incident event",
            "incidentId": incident_id,
            "findingType": finding_type,
            "severity": severity,
            "resourceArn": resource_arn,
        }
    )

    return incident_event


def _extract_guardduty_resource_arn(resource_info: Dict[str, Any], event: Dict[str, Any]) -> str:
    """Extract the most relevant resource ARN from a GuardDuty finding."""
    region = event.get("region", "us-east-1")
    account = event.get("account", "")

    # Check for EC2 instance
    instance_details = resource_info.get("instanceDetails", {})
    if instance_details:
        instance_id = instance_details.get("instanceId", "")
        if instance_id:
            return f"arn:aws:ec2:{region}:{account}:instance/{instance_id}"

    # Check for IAM access key (user)
    access_key = resource_info.get("accessKeyDetails", {})
    if access_key:
        user_name = access_key.get("userName", "")
        if user_name:
            return f"arn:aws:iam::{account}:user/{user_name}"

    # Check for S3 bucket
    s3_details = resource_info.get("s3BucketDetails", [])
    if s3_details:
        bucket_name = s3_details[0].get("name", "") if s3_details else ""
        if bucket_name:
            return f"arn:aws:s3:::{bucket_name}"

    # Check for EKS cluster
    eks_details = resource_info.get("eksClusterDetails", {})
    if eks_details:
        cluster_name = eks_details.get("name", "")
        if cluster_name:
            return f"arn:aws:eks:{region}:{account}:cluster/{cluster_name}"

    # Check for Lambda function
    lambda_details = resource_info.get("lambdaDetails", {})
    if lambda_details:
        function_arn = lambda_details.get("functionArn", "")
        if function_arn:
            return function_arn

    # Check for ECS cluster
    ecs_details = resource_info.get("ecsClusterDetails", {})
    if ecs_details:
        cluster_arn = ecs_details.get("arn", "")
        if cluster_arn:
            return cluster_arn

    # Check for RDS DB instance
    rds_details = resource_info.get("rdsDbInstanceDetails", {})
    if rds_details:
        db_instance_id = rds_details.get("dbInstanceIdentifier", "")
        if db_instance_id:
            return f"arn:aws:rds:{region}:{account}:db:{db_instance_id}"

    return f"arn:aws:guardduty:{region}:{account}:detector/unknown"


def transform_health_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform AWS Health event into normalized IncidentEvent structure.

    Args:
        event: AWS Health event from EventBridge

    Returns:
        Normalized IncidentEvent dictionary
    """
    detail = event.get("detail", {})

    incident_id = str(uuid.uuid4())
    event_type_code = detail.get("eventTypeCode", "Unknown")
    event_type_category = detail.get("eventTypeCategory", "issue")
    service = detail.get("service", "Unknown")
    description_parts = detail.get("eventDescription", [])
    description = description_parts[0].get("latestDescription", "") if description_parts else ""

    # Map Health event category to severity
    severity = "high" if event_type_category == "issue" else "medium"

    # Extract affected resource ARN from affectedEntities
    affected_entities = detail.get("affectedEntities", [])
    resource_arn = (
        affected_entities[0].get("entityValue", "")
        if affected_entities
        else f"aws.health/{service}"
    )

    # Get timestamp
    timestamp_str = event.get("time", detail.get("startTime", ""))

    # Calculate TTL (90 days)
    try:
        if timestamp_str.endswith("Z"):
            timestamp_dt = datetime.fromisoformat(timestamp_str[:-1])
        else:
            timestamp_dt = datetime.fromisoformat(timestamp_str)
        ttl = int(timestamp_dt.timestamp()) + 7776000
    except Exception:
        ttl = int(datetime.now(timezone.utc).timestamp()) + 7776000

    incident_event = {
        "incidentId": incident_id,
        "alarmName": f"{service}: {event_type_code}",
        "alarmArn": detail.get("eventArn", ""),
        "resourceArn": resource_arn,
        "timestamp": timestamp_str,
        "ttl": ttl,
        "alarmState": "ALARM",
        "metricName": event_type_code,
        "namespace": f"AWS/Health/{service}",
        "alarmDescription": description,
        "eventSource": "health",
        "severity": severity,
        "healthDetail": {
            "eventTypeCode": event_type_code,
            "eventTypeCategory": event_type_category,
            "service": service,
            "statusCode": detail.get("statusCode", ""),
        },
    }

    logger.info(
        {
            "message": "Transformed Health event to incident event",
            "incidentId": incident_id,
            "eventTypeCode": event_type_code,
            "service": service,
            "severity": severity,
            "resourceArn": resource_arn,
        }
    )

    return incident_event


def _unwrap_sns_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unwrap an SNS-delivered event into the EventBridge format expected by
    transform_alarm_event.

    Supports two SNS message formats:
    1. Native CloudWatch Alarm notification (AlarmName, NewStateValue, Trigger)
    2. EventBridge input_transformer flattened format (alarmName, state, configuration)
    """
    record = event["Records"][0]["Sns"]
    message = json.loads(record["Message"])

    # GuardDuty or Health events pass through as full EventBridge events
    if message.get("source") in ("aws.guardduty", "aws.health"):
        return message

    # Detect native CloudWatch alarm notification format
    if "AlarmName" in message or "Trigger" in message:
        trigger = message.get("Trigger", {})
        # Convert native Dimensions list [{name, value}] to dict {name: value}
        dimensions = {}
        for dim in trigger.get("Dimensions", []):
            dimensions[dim.get("name", "")] = dim.get("value", "")

        return {
            "source": "aws.cloudwatch",
            "detail-type": "CloudWatch Alarm State Change",
            "time": message.get("StateChangeTime", record.get("Timestamp", "")),
            "region": message.get("Region", ""),
            "account": message.get("AWSAccountId", ""),
            "detail": {
                "alarmName": message.get("AlarmName", ""),
                "alarmArn": message.get("AlarmArn", ""),
                "alarmDescription": message.get("AlarmDescription", ""),
                "state": {
                    "value": message.get("NewStateValue", "ALARM"),
                    "reason": message.get("NewStateReason", ""),
                },
                "previousState": {
                    "value": message.get("OldStateValue", ""),
                },
                "configuration": {
                    "metrics": [
                        {
                            "metricStat": {
                                "metric": {
                                    "name": trigger.get("MetricName", ""),
                                    "namespace": trigger.get("Namespace", ""),
                                    "dimensions": dimensions,
                                },
                                "stat": trigger.get("Statistic", "Average"),
                                "period": trigger.get("Period", 60),
                            }
                        }
                    ]
                },
            },
        }

    # Fallback: EventBridge input_transformer format
    return {
        "source": "aws.cloudwatch",
        "detail-type": "CloudWatch Alarm State Change",
        "time": message.get("timestamp", record.get("Timestamp", "")),
        "region": message.get("region", ""),
        "account": message.get("account", ""),
        "detail": {
            "alarmName": message.get("alarmName", ""),
            "alarmArn": message.get("alarmArn", ""),
            "alarmDescription": message.get("alarmDescription", ""),
            "state": {
                "value": message.get("state", "ALARM"),
                "reason": message.get("stateReason", ""),
                "reasonData": message.get("stateReasonData", ""),
            },
            "previousState": {
                "value": message.get("previousState", ""),
            },
            "configuration": message.get("configuration", {}),
        },
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for EventBridge event transformer.

    Receives CloudWatch Alarm state change events from EventBridge,
    transforms them into normalized IncidentEvent objects, and publishes
    to SNS for orchestration by Step Functions.

    Supports two delivery paths:
    - Direct EventBridge invocation (event has 'source' and 'detail')
    - SNS delivery (event has 'Records[].Sns.Message')

    Args:
        event: EventBridge event or SNS-wrapped event
        context: Lambda context object

    Returns:
        Response dictionary with status and incident details
    """
    try:
        # Unwrap SNS envelope if present
        if "Records" in event:
            logger.info({"message": "Unwrapping SNS envelope"})
            event = _unwrap_sns_event(event)

        logger.info(
            {
                "message": "Event transformer invoked",
                "eventSource": event.get("source"),
                "detailType": event.get("detail-type"),
            }
        )

        # Route based on event source
        event_source = event.get("source", "")

        if event_source == "aws.guardduty":
            incident_event = transform_guardduty_event(event)
        elif event_source == "aws.health":
            incident_event = transform_health_event(event)
        elif event_source == "aws.cloudwatch":
            incident_event = transform_alarm_event(event)
        else:
            logger.warning(
                {
                    "message": "Unexpected event source, treating as CloudWatch alarm",
                    "source": event_source,
                }
            )
            incident_event = transform_alarm_event(event)

        # Start Step Functions workflow
        state_machine_arn = os.environ.get("STATE_MACHINE_ARN", "")
        if not state_machine_arn:
            raise ValueError("STATE_MACHINE_ARN environment variable not set")

        execution_name = f"incident-{incident_event['incidentId']}"
        sfn_response = sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(incident_event),
        )

        logger.info(
            {
                "message": "Started Step Functions execution",
                "incidentId": incident_event["incidentId"],
                "executionArn": sfn_response["executionArn"],
                "alarmName": incident_event["alarmName"],
            }
        )

        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "incidentId": incident_event["incidentId"],
                    "executionArn": sfn_response["executionArn"],
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
