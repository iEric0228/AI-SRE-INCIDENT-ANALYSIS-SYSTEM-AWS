"""
Deploy Context Collector Lambda Function

This Lambda function collects deployment and configuration change history for
the affected resource during an incident. It queries CloudTrail and Systems Manager
Parameter Store for changes in the past 24 hours.

Requirements: 5.1, 5.2, 5.3, 5.4
"""

import json
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
cloudtrail = boto3.client("cloudtrail")
ssm = boto3.client("ssm")

# Import metrics utility
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from metrics import put_collector_success_metric


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for deploy context collection.

    Args:
        event: Event containing resourceArn and timestamp
        context: Lambda context object

    Returns:
        Dictionary containing status, changes array, and collection_duration
    """
    start_time = datetime.utcnow()
    correlation_id = event.get("incidentId", event.get("incident", {}).get("incidentId", "unknown"))

    try:
        logger.info(
            json.dumps(
                {
                    "message": "Deploy context collector invoked",
                    "correlationId": correlation_id,
                    "resourceArn": event.get("resourceArn"),
                    "timestamp": event.get("timestamp"),
                }
            )
        )

        # Extract required fields
        resource_arn = event.get("resourceArn")
        timestamp_str = event.get("timestamp")

        if not resource_arn or not timestamp_str:
            raise ValueError("Missing required fields: resourceArn and timestamp")

        # Parse timestamp
        incident_timestamp = parse_timestamp(timestamp_str)

        # Calculate time range (-24h to incident time)
        start_time_range, end_time_range = calculate_time_range(incident_timestamp)

        logger.info(
            json.dumps(
                {
                    "message": "Calculated time range",
                    "correlationId": correlation_id,
                    "startTime": start_time_range.isoformat(),
                    "endTime": end_time_range.isoformat(),
                }
            )
        )

        # Collect CloudTrail events
        cloudtrail_changes = collect_cloudtrail_events(
            resource_arn=resource_arn,
            start_time=start_time_range,
            end_time=end_time_range,
            correlation_id=correlation_id,
        )

        # Collect Parameter Store changes
        parameter_changes = collect_parameter_store_changes(
            resource_arn=resource_arn,
            start_time=start_time_range,
            end_time=end_time_range,
            correlation_id=correlation_id,
        )

        # Merge and sort all changes
        all_changes = cloudtrail_changes + parameter_changes
        all_changes.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Limit to top 50 changes
        limited_changes = all_changes[:50]

        # Calculate collection duration
        collection_duration = (datetime.utcnow() - start_time).total_seconds()

        # Log warning if no changes found
        if not limited_changes:
            logger.warning(
                json.dumps(
                    {
                        "message": "No changes found for resource",
                        "correlationId": correlation_id,
                        "resourceArn": resource_arn,
                    }
                )
            )

        result = {
            "status": "success",
            "changes": limited_changes,
            "collectionDuration": collection_duration,
        }

        logger.info(
            json.dumps(
                {
                    "message": "Deploy context collection completed",
                    "correlationId": correlation_id,
                    "changesCount": len(limited_changes),
                    "duration": collection_duration,
                }
            )
        )

        # Emit CloudWatch metrics
        put_collector_success_metric("deploy_context", True, collection_duration)

        return result

    except ValueError as e:
        # Non-retryable validation error
        collection_duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(
            json.dumps(
                {
                    "message": "Validation error",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorType": "ValidationException",
                }
            )
        )

        # Emit failure metric
        put_collector_success_metric("deploy_context", False, collection_duration)

        return {
            "status": "failed",
            "changes": [],
            "collectionDuration": collection_duration,
            "error": str(e),
        }

    except ClientError as e:
        # ERROR HANDLING STRATEGY: Graceful handling of CloudTrail not enabled
        # TrailNotFoundException: CloudTrail not configured (not an error - return empty)
        # Retryable errors: ThrottlingException, TooManyRequestsException
        # Other errors: Return error response
        collection_duration = (datetime.utcnow() - start_time).total_seconds()
        error_code = e.response.get("Error", {}).get("Code", "Unknown")

        logger.error(
            json.dumps(
                {
                    "message": "AWS API error",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorCode": error_code,
                    "errorType": "ClientError",
                }
            )
        )

        # Raise retryable errors for Step Functions retry
        if error_code in ["ThrottlingException", "ServiceException", "TooManyRequestsException"]:
            put_collector_success_metric("deploy_context", False, collection_duration)
            raise

        # Non-retryable errors - return error response
        put_collector_success_metric("deploy_context", False, collection_duration)

        return {
            "status": "failed",
            "changes": [],
            "collectionDuration": collection_duration,
            "error": f"{error_code}: {str(e)}",
        }

    except Exception as e:
        # Unexpected error
        collection_duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(
            json.dumps(
                {
                    "message": "Unexpected error",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorType": type(e).__name__,
                    "stackTrace": traceback.format_exc(),
                }
            )
        )

        # Emit failure metric
        put_collector_success_metric("deploy_context", False, collection_duration)

        return {
            "status": "failed",
            "changes": [],
            "collectionDuration": collection_duration,
            "error": str(e),
        }


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse timestamp string to datetime object.

    Args:
        timestamp_str: ISO-8601 timestamp string

    Returns:
        datetime object
    """
    # Handle both with and without 'Z' suffix
    if timestamp_str.endswith("Z"):
        timestamp_str = timestamp_str[:-1] + "+00:00"

    return datetime.fromisoformat(timestamp_str)


def calculate_time_range(incident_timestamp: datetime) -> Tuple[datetime, datetime]:
    """
    Calculate time range for change events query.

    Args:
        incident_timestamp: Time of the incident

    Returns:
        Tuple of (start_time, end_time) for changes query

    Requirements: 5.1 - Query changes from 24 hours before to incident time
    """
    start_time = incident_timestamp - timedelta(hours=24)
    end_time = incident_timestamp

    return start_time, end_time


def collect_cloudtrail_events(
    resource_arn: str, start_time: datetime, end_time: datetime, correlation_id: str
) -> List[Dict[str, Any]]:
    """
    Collect CloudTrail events for the resource.

    Args:
        resource_arn: AWS resource ARN
        start_time: Start of time range
        end_time: End of time range
        correlation_id: Correlation ID for logging

    Returns:
        List of change events

    Requirements:
        5.1 - Query CloudTrail for changes
        5.2 - Identify deployments, configuration updates, and infrastructure changes
        5.3 - Return changes in normalized JSON structure
    """
    changes = []

    try:
        # Extract resource information from ARN for CloudTrail lookup
        resource_type, resource_id = parse_resource_arn_for_cloudtrail(resource_arn)

        # PAGINATION STRATEGY:
        # Query CloudTrail with pagination to handle large result sets
        # Stop when we have 50+ changes or no more pages
        # MaxResults: 50 per API call (CloudTrail limit)
        next_token = None
        max_results = 50

        while True:
            params = {"StartTime": start_time, "EndTime": end_time, "MaxResults": max_results}

            # Add resource lookup if we have a specific resource ID
            # This filters CloudTrail events to only those affecting this resource
            if resource_id:
                params["LookupAttributes"] = [
                    {"AttributeKey": "ResourceName", "AttributeValue": resource_id}
                ]

            if next_token:
                params["NextToken"] = next_token

            response = cloudtrail.lookup_events(**params)

            events = response.get("Events", [])

            # Filter and normalize events
            # Only include mutating operations (Create, Update, Delete, etc.)
            for event in events:
                change_event = process_cloudtrail_event(event, resource_arn)
                if change_event:
                    changes.append(change_event)

            # Check for more pages
            next_token = response.get("NextToken")

            # Stop if we have enough changes or no more pages
            if len(changes) >= 50 or not next_token:
                break

        logger.info(
            json.dumps(
                {
                    "message": "CloudTrail events collected",
                    "correlationId": correlation_id,
                    "eventsCount": len(changes),
                }
            )
        )

        return changes

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")

        # Handle CloudTrail not enabled gracefully
        # This is not an error - some accounts may not have CloudTrail configured
        if error_code in ["TrailNotFoundException", "InvalidTrailNameException"]:
            logger.warning(
                json.dumps(
                    {
                        "message": "CloudTrail not enabled or trail not found",
                        "correlationId": correlation_id,
                        "error": str(e),
                    }
                )
            )
            return []  # Return empty list (graceful degradation)

        # Retry on throttling
        if error_code in ["ThrottlingException", "TooManyRequestsException"]:
            raise

        logger.error(
            json.dumps(
                {
                    "message": "Failed to collect CloudTrail events",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorCode": error_code,
                }
            )
        )

        return []


def parse_resource_arn_for_cloudtrail(resource_arn: str) -> Tuple[str, Optional[str]]:
    """
    Parse resource ARN to extract resource type and ID for CloudTrail lookup.

    Args:
        resource_arn: AWS resource ARN

    Returns:
        Tuple of (resource_type, resource_id)

    Examples:
        arn:aws:lambda:us-east-1:123456789012:function:my-function
        -> ("lambda", "my-function")

        arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0
        -> ("ec2", "i-1234567890abcdef0")
    """
    parts = resource_arn.split(":")

    if len(parts) < 6:
        return "unknown", None

    service = parts[2]
    resource_part = parts[5] if len(parts) > 5 else parts[-1]

    # Extract resource ID based on service
    if service == "lambda":
        # arn:aws:lambda:region:account:function:function-name
        resource_id = (
            resource_part.split(":")[-1] if ":" in resource_part else resource_part.split("/")[-1]
        )
        return service, resource_id

    elif service == "ec2":
        # arn:aws:ec2:region:account:instance/instance-id
        resource_id = resource_part.split("/")[-1]
        return service, resource_id

    elif service == "rds":
        # arn:aws:rds:region:account:db:db-instance-id
        resource_id = resource_part.split(":")[-1]
        return service, resource_id

    elif service == "ecs":
        # arn:aws:ecs:region:account:service/cluster-name/service-name
        parts_split = resource_part.split("/")
        if len(parts_split) >= 3:
            resource_id = parts_split[2]  # service name
            return service, resource_id
        return service, None

    elif service == "dynamodb":
        # arn:aws:dynamodb:region:account:table/table-name
        resource_id = resource_part.split("/")[-1]
        return service, resource_id

    return service, None


def process_cloudtrail_event(event: Dict[str, Any], resource_arn: str) -> Optional[Dict[str, Any]]:
    """
    Process and normalize a CloudTrail event.

    Args:
        event: Raw CloudTrail event
        resource_arn: Resource ARN for context

    Returns:
        Normalized change event or None if event should be filtered out

    Requirements:
        5.2 - Filter for mutating operations and classify change type
        5.3 - Return changes in normalized JSON structure
    """
    try:
        event_name = event.get("EventName", "")
        event_time = event.get("EventTime")
        username = event.get("Username", "unknown")

        # Filter for mutating operations only
        if not is_mutating_operation(event_name):
            return None

        # Classify change type
        change_type = classify_change_type(event_name)

        # Extract user ARN from CloudTrailEvent if available
        user_arn = username
        try:
            cloud_trail_event = json.loads(event.get("CloudTrailEvent", "{}"))
            user_identity = cloud_trail_event.get("userIdentity", {})
            user_arn = user_identity.get("arn", username)
        except:
            pass

        # Generate description
        description = generate_change_description(event_name, event, resource_arn)

        # Format timestamp as ISO-8601 with 'Z' suffix (UTC)
        if isinstance(event_time, datetime):
            timestamp_str = event_time.isoformat().replace("+00:00", "Z")
        else:
            timestamp_str = event_time

        return {
            "timestamp": timestamp_str,
            "changeType": change_type,
            "eventName": event_name,
            "user": user_arn,
            "description": description,
        }

    except Exception as e:
        logger.warning(f"Failed to process CloudTrail event: {str(e)}")
        return None


def is_mutating_operation(event_name: str) -> bool:
    """
    Determine if an event represents a mutating operation.

    Args:
        event_name: CloudTrail event name

    Returns:
        True if the operation mutates infrastructure

    Requirements: 5.2 - Filter for mutating operations
    """
    # Mutating operation prefixes
    mutating_prefixes = [
        "Create",
        "Update",
        "Delete",
        "Put",
        "Modify",
        "Deploy",
        "Publish",
        "Start",
        "Stop",
        "Reboot",
        "Terminate",
        "Launch",
        "Register",
        "Deregister",
        "Attach",
        "Detach",
        "Associate",
        "Disassociate",
        "Enable",
        "Disable",
        "Set",
        "Add",
        "Remove",
    ]

    return any(event_name.startswith(prefix) for prefix in mutating_prefixes)


def classify_change_type(event_name: str) -> str:
    """
    Classify a change event into deployment, configuration, or infrastructure.

    Args:
        event_name: CloudTrail event name

    Returns:
        Change type: "deployment", "configuration", or "infrastructure"

    Requirements: 5.2 - Classify change events
    """
    # CHANGE CLASSIFICATION ALGORITHM:
    # Strategy: Keyword-based classification with priority ordering
    # Priority: deployment > configuration > infrastructure (default)
    # Reason: Deployments are most likely to cause incidents, followed by config changes

    event_name_lower = event_name.lower()

    # Deployment-related events (highest priority)
    # These events indicate code or container image changes
    deployment_keywords = [
        "deploy",
        "publish",
        "updatefunctioncode",
        "updateservice",
        "createdeployment",
        "updateapplication",
        "putimage",
    ]

    if any(keyword in event_name_lower for keyword in deployment_keywords):
        return "deployment"

    # Configuration-related events (medium priority)
    # These events indicate settings or parameter changes
    configuration_keywords = [
        "updatefunctionconfiguration",
        "putparameter",
        "updateparameter",
        "modifydbinstance",
        "updatestack",
        "putrule",
        "updatealarm",
        "putmetricfilter",
        "updateloggroup",
    ]

    if any(keyword in event_name_lower for keyword in configuration_keywords):
        return "configuration"

    # Infrastructure-related events (default/lowest priority)
    # All other mutating operations (Create, Update, Delete, etc.)
    return "infrastructure"


def generate_change_description(event_name: str, event: Dict[str, Any], resource_arn: str) -> str:
    """
    Generate a human-readable description of the change.

    Args:
        event_name: CloudTrail event name
        event: Full CloudTrail event
        resource_arn: Resource ARN

    Returns:
        Human-readable description
    """
    # Extract resource name from ARN
    resource_name = resource_arn.split("/")[-1].split(":")[-1]

    # Generate description based on event name
    descriptions = {
        "UpdateFunctionCode": f"Lambda function {resource_name} code updated",
        "UpdateFunctionConfiguration": f"Lambda function {resource_name} configuration updated",
        "CreateDeployment": f"Deployment created for {resource_name}",
        "UpdateService": f"ECS service {resource_name} updated",
        "ModifyDBInstance": f"RDS instance {resource_name} modified",
        "PutParameter": f"Parameter Store parameter updated",
        "UpdateStack": f"CloudFormation stack {resource_name} updated",
        "RunInstances": f"EC2 instance {resource_name} launched",
        "TerminateInstances": f"EC2 instance {resource_name} terminated",
        "RebootInstances": f"EC2 instance {resource_name} rebooted",
        "StartInstances": f"EC2 instance {resource_name} started",
        "StopInstances": f"EC2 instance {resource_name} stopped",
    }

    return descriptions.get(event_name, f"{event_name} on {resource_name}")


def collect_parameter_store_changes(
    resource_arn: str, start_time: datetime, end_time: datetime, correlation_id: str
) -> List[Dict[str, Any]]:
    """
    Collect Parameter Store changes related to the resource.

    Args:
        resource_arn: AWS resource ARN
        start_time: Start of time range
        end_time: End of time range
        correlation_id: Correlation ID for logging

    Returns:
        List of parameter change events

    Requirements: 5.1 - Query Systems Manager Parameter Store for configuration changes
    """
    changes = []

    try:
        # Extract resource name to construct parameter name pattern
        resource_name = resource_arn.split("/")[-1].split(":")[-1]

        # Common parameter name patterns
        parameter_patterns = [
            f"/{resource_name}/",
            f"/config/{resource_name}",
            f"/app/{resource_name}",
            f"/service/{resource_name}",
        ]

        # Query parameters for each pattern
        for pattern in parameter_patterns:
            try:
                # Get parameters by path
                response = ssm.describe_parameters(
                    ParameterFilters=[{"Key": "Name", "Option": "BeginsWith", "Values": [pattern]}],
                    MaxResults=10,
                )

                parameters = response.get("Parameters", [])

                # Get history for each parameter
                for param in parameters:
                    param_name = param.get("Name")

                    try:
                        history_response = ssm.get_parameter_history(Name=param_name, MaxResults=10)

                        history = history_response.get("Parameters", [])

                        # Filter history by time range
                        for hist_entry in history:
                            last_modified = hist_entry.get("LastModifiedDate")

                            if last_modified and start_time <= last_modified <= end_time:
                                # Format timestamp as ISO-8601 with 'Z' suffix (UTC)
                                if isinstance(last_modified, datetime):
                                    timestamp_str = last_modified.isoformat().replace("+00:00", "Z")
                                else:
                                    timestamp_str = last_modified

                                change_event = {
                                    "timestamp": timestamp_str,
                                    "changeType": "configuration",
                                    "eventName": "PutParameter",
                                    "user": hist_entry.get("LastModifiedUser", "unknown"),
                                    "description": f"Parameter {param_name} updated",
                                }

                                changes.append(change_event)

                    except ClientError as e:
                        # Skip parameters we can't access
                        logger.debug(f"Could not get history for parameter {param_name}: {str(e)}")
                        continue

            except ClientError as e:
                # Skip patterns that don't match
                logger.debug(f"No parameters found for pattern {pattern}: {str(e)}")
                continue

        logger.info(
            json.dumps(
                {
                    "message": "Parameter Store changes collected",
                    "correlationId": correlation_id,
                    "changesCount": len(changes),
                }
            )
        )

        return changes

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")

        # Retry on throttling
        if error_code in ["ThrottlingException", "TooManyRequestsException"]:
            raise

        logger.warning(
            json.dumps(
                {
                    "message": "Failed to collect Parameter Store changes",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorCode": error_code,
                }
            )
        )

        return []
