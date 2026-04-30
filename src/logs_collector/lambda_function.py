"""
Logs Collector Lambda Function

This Lambda function collects CloudWatch Logs for the affected resource
during an incident. It queries logs from 30 minutes before to 5 minutes
after the incident timestamp and filters for ERROR/WARN/CRITICAL levels.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize CloudWatch Logs client
logs_client = boto3.client("logs")

# Import metrics utility
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from metrics import put_collector_success_metric  # noqa: E402

# Initialize log group resolver with SSM-based configuration
from log_group_resolver import LogGroupResolver  # noqa: E402

_ssm_client = boto3.client("ssm")
_LOG_GROUP_MAPPING_PARAM = os.environ.get(
    "LOG_GROUP_MAPPING_PARAM", "/ai-sre-incident-analysis/log-group-mappings"
)
_log_group_resolver = LogGroupResolver(_ssm_client, _LOG_GROUP_MAPPING_PARAM)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for logs collection.

    Args:
        event: Event containing resourceArn, timestamp, and optional logGroupName
        context: Lambda context object

    Returns:
        Dictionary containing status, logs array, total_matches, returned count, and collection_duration
    """
    start_time = datetime.now(timezone.utc)
    correlation_id = event.get("incidentId", event.get("incident", {}).get("incidentId", "unknown"))

    try:
        logger.info(
            json.dumps(
                {
                    "message": "Logs collector invoked",
                    "correlationId": correlation_id,
                    "resourceArn": event.get("resourceArn"),
                    "timestamp": event.get("timestamp"),
                }
            )
        )

        # Extract required fields
        resource_arn = event.get("resourceArn")
        timestamp_str = event.get("timestamp")
        log_group_name = event.get("logGroupName")

        if not resource_arn or not timestamp_str:
            raise ValueError("Missing required fields: resourceArn and timestamp")

        # Parse timestamp
        incident_timestamp = parse_timestamp(timestamp_str)

        # Determine log group names
        event_source = event.get("eventSource", "cloudwatch")

        if not log_group_name:
            resolved_groups = _log_group_resolver.resolve(resource_arn)
            log_group_name = resolved_groups[0] if resolved_groups else map_resource_arn_to_log_group(resource_arn)

        # Build list of log groups to query
        log_groups_to_query = [{"name": log_group_name, "source": "application"}]

        # For security events, add CloudTrail and VPC Flow Log groups
        if event_source == "guardduty":
            log_groups_to_query.extend(_get_security_log_groups(resource_arn))

        logger.info(
            json.dumps(
                {
                    "message": "Resolved log groups",
                    "correlationId": correlation_id,
                    "logGroups": [lg["name"] for lg in log_groups_to_query],
                    "eventSource": event_source,
                }
            )
        )

        # Calculate time range (-30min to +5min)
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

        # Collect logs from all log groups
        all_logs_data = []
        total_matches = 0

        for lg_info in log_groups_to_query:
            filter_pattern = _get_filter_pattern(lg_info["source"])
            lg_logs, lg_matches = collect_logs(
                log_group_name=lg_info["name"],
                start_time=start_time_range,
                end_time=end_time_range,
                correlation_id=correlation_id,
                filter_pattern=filter_pattern,
            )
            # Tag each log entry with its source
            for entry in lg_logs:
                entry["logSource"] = lg_info["source"]
            all_logs_data.extend(lg_logs)
            total_matches += lg_matches

        logs_data = all_logs_data[:100]  # Limit total across all sources

        # Calculate collection duration
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Log warning if no logs found
        if not logs_data:
            logger.warning(
                json.dumps(
                    {
                        "message": "No logs found for resource",
                        "correlationId": correlation_id,
                        "resourceArn": resource_arn,
                        "logGroupName": log_group_name,
                    }
                )
            )

        result = {
            "status": "success",
            "logs": logs_data,
            "totalMatches": total_matches,
            "returned": len(logs_data),
            "collectionDuration": collection_duration,
        }

        logger.info(
            json.dumps(
                {
                    "message": "Logs collection completed",
                    "correlationId": correlation_id,
                    "logsCount": len(logs_data),
                    "totalMatches": total_matches,
                    "duration": collection_duration,
                }
            )
        )

        # Emit CloudWatch metrics
        put_collector_success_metric("logs", True, collection_duration)

        return result

    except ValueError as e:
        # Non-retryable validation error
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
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
        put_collector_success_metric("logs", False, collection_duration)

        return {
            "status": "failed",
            "logs": [],
            "totalMatches": 0,
            "returned": 0,
            "collectionDuration": collection_duration,
            "error": str(e),
        }

    except ClientError as e:
        # ERROR HANDLING STRATEGY: Graceful handling of missing log groups
        # ResourceNotFoundException: Log group doesn't exist (not an error - return empty)
        # Retryable errors: ThrottlingException, TooManyRequestsException
        # Other errors: Return error response
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
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
            put_collector_success_metric("logs", False, collection_duration)
            raise

        # Handle ResourceNotFoundException gracefully (log group doesn't exist)
        # This is not an error - some resources may not have logs configured
        if error_code == "ResourceNotFoundException":
            logger.warning(
                json.dumps(
                    {
                        "message": "Log group not found",
                        "correlationId": correlation_id,
                        "logGroupName": event.get("logGroupName"),
                    }
                )
            )
            # Return success with empty data (graceful degradation)
            put_collector_success_metric("logs", True, collection_duration)
            return {
                "status": "success",
                "logs": [],
                "totalMatches": 0,
                "returned": 0,
                "collectionDuration": collection_duration,
                "error": f"Log group not found: {event.get('logGroupName')}",
            }

        # Other non-retryable errors
        put_collector_success_metric("logs", False, collection_duration)

        return {
            "status": "failed",
            "logs": [],
            "totalMatches": 0,
            "returned": 0,
            "collectionDuration": collection_duration,
            "error": f"{error_code}: {str(e)}",
        }

    except Exception as e:
        # Unexpected error
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
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
        put_collector_success_metric("logs", False, collection_duration)

        return {
            "status": "failed",
            "logs": [],
            "totalMatches": 0,
            "returned": 0,
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
    Calculate time range for logs query.

    Args:
        incident_timestamp: Time of the incident

    Returns:
        Tuple of (start_time, end_time) for logs query

    Requirements: 4.1 - Query logs from 30 minutes before to 5 minutes after
    """
    start_time = incident_timestamp - timedelta(minutes=30)
    end_time = incident_timestamp + timedelta(minutes=5)

    return start_time, end_time


def map_resource_arn_to_log_group(resource_arn: str) -> str:
    """
    Map resource ARN to CloudWatch Logs log group name.

    Args:
        resource_arn: AWS resource ARN

    Returns:
        Log group name

    Examples:
        arn:aws:lambda:us-east-1:123456789012:function:my-function
        -> /aws/lambda/my-function

        arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0
        -> /aws/ec2/instance/i-1234567890abcdef0

    Requirements: 4.1 - Map resource ARN to log group name
    """
    parts = resource_arn.split(":")

    if len(parts) < 6:
        raise ValueError(f"Invalid ARN format: {resource_arn}")

    service = parts[2]
    resource_part = parts[5] if len(parts) > 5 else parts[-1]

    # Map service to log group pattern
    if service == "lambda":
        # arn:aws:lambda:region:account:function:function-name
        function_name = (
            resource_part.split(":")[-1] if ":" in resource_part else resource_part.split("/")[-1]
        )
        return f"/aws/lambda/{function_name}"

    elif service == "ec2":
        # arn:aws:ec2:region:account:instance/instance-id
        instance_id = resource_part.split("/")[-1]
        return f"/aws/ec2/instance/{instance_id}"

    elif service == "rds":
        # arn:aws:rds:region:account:db:db-instance-id
        db_instance_id = resource_part.split(":")[-1]
        return f"/aws/rds/instance/{db_instance_id}/error"

    elif service == "ecs":
        # arn:aws:ecs:region:account:service/cluster-name/service-name
        parts_split = resource_part.split("/")
        if len(parts_split) >= 3:
            cluster_name = parts_split[1]
            service_name = parts_split[2]
            return f"/ecs/{cluster_name}/{service_name}"
        return f"/ecs/{resource_part}"

    elif service == "apigateway":
        # arn:aws:apigateway:region::/restapis/api-id
        api_id = resource_part.split("/")[-1]
        return f"/aws/apigateway/{api_id}"

    elif service == "elasticloadbalancing":
        # arn:aws:elasticloadbalancing:region:account:loadbalancer/app/name/id
        lb_parts = resource_part.split("/")
        if len(lb_parts) >= 3:
            lb_type = lb_parts[1]  # "app" or "net"
            lb_name = lb_parts[2]
            if lb_type == "net":
                return f"/aws/nlb/{lb_name}"
            return f"/aws/alb/{lb_name}"
        return f"/aws/elb/{resource_part}"

    elif service == "eks":
        # arn:aws:eks:region:account:cluster/cluster-name
        cluster_name = resource_part.split("/")[-1]
        return f"/aws/eks/{cluster_name}/cluster"

    elif service == "elasticache":
        # arn:aws:elasticache:region:account:cluster:cluster-id
        cluster_id = resource_part.split(":")[-1] if ":" in resource_part else resource_part.split("/")[-1]
        return f"/aws/elasticache/{cluster_id}"

    elif service == "es":
        # arn:aws:es:region:account:domain/domain-name
        domain_name = resource_part.split("/")[-1]
        return f"/aws/opensearch/domains/{domain_name}"

    # Default pattern
    return f"/aws/{service}/{resource_part}"


def _get_security_log_groups(resource_arn: str) -> List[Dict[str, str]]:
    """
    Get additional security-focused log groups for GuardDuty events.

    Args:
        resource_arn: AWS resource ARN

    Returns:
        List of log group info dicts with 'name' and 'source' keys
    """
    security_groups: List[Dict[str, str]] = []

    # CloudTrail logs (standard log group name)
    security_groups.append({"name": "/aws/cloudtrail", "source": "cloudtrail"})

    # VPC Flow Logs — only for EC2/ENI resources
    parts = resource_arn.split(":")
    if len(parts) >= 3 and parts[2] == "ec2":
        security_groups.append({"name": "/aws/vpc/flowlogs", "source": "vpc_flow"})

    return security_groups


def _get_filter_pattern(log_source: str) -> str:
    """
    Get the appropriate filter pattern based on log source type.

    Args:
        log_source: Type of log source (application, cloudtrail, vpc_flow)

    Returns:
        CloudWatch Logs filter pattern string
    """
    if log_source == "cloudtrail":
        return "?UnauthorizedAccess ?AccessDenied ?ConsoleLogin ?AssumeRole ?PolicyChanged ?CreateUser ?DeleteUser ?AttachPolicy ?DetachPolicy"

    if log_source == "vpc_flow":
        return "REJECT"

    # Default application log filter
    return "?ERROR ?WARN ?CRITICAL ?Error ?Warning ?error ?warn ?critical"


def collect_logs(
    log_group_name: str, start_time: datetime, end_time: datetime, correlation_id: str,
    filter_pattern: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Collect logs from CloudWatch Logs with filtering.

    Args:
        log_group_name: Name of the log group
        start_time: Start of time range
        end_time: End of time range
        correlation_id: Correlation ID for logging

    Returns:
        Tuple of (logs_data, total_matches)

    Requirements:
        4.2 - Filter for ERROR, WARN, CRITICAL level messages
        4.3 - Return up to 100 most relevant log entries in chronological order
        4.4 - Return logs in normalized JSON structure
    """
    # Convert datetime to milliseconds since epoch (CloudWatch Logs API format)
    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

    # Use provided filter pattern or default to error keywords
    if filter_pattern is None:
        filter_pattern = "?ERROR ?WARN ?CRITICAL ?Error ?Warning ?error ?warn ?critical"

    all_logs = []
    next_token = None

    try:
        # PAGINATION STRATEGY:
        # Query logs with pagination to handle large result sets
        # Stop when we have 100+ logs or no more pages
        # Limit: 100 per API call (CloudWatch Logs maximum)
        while True:
            params = {
                "logGroupName": log_group_name,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "filterPattern": filter_pattern,
                "limit": 100,  # Maximum per API call
            }

            if next_token:
                params["nextToken"] = next_token

            response = logs_client.filter_log_events(**params)

            events = response.get("events", [])
            all_logs.extend(events)

            # Check if we have enough logs or if there are more pages
            next_token = response.get("nextToken")

            # Stop if we have 100+ logs or no more pages
            if len(all_logs) >= 100 or not next_token:
                break

        total_matches = len(all_logs)

        # Sort by timestamp (chronological order for incident timeline)
        # CloudWatch Logs may return events out of order
        all_logs.sort(key=lambda x: x.get("timestamp", 0))

        # Limit to top 100 entries (most recent if sorted chronologically)
        limited_logs = all_logs[:100]

        # Normalize log entries to consistent format
        normalized_logs = []
        for log_event in limited_logs:
            normalized_log = normalize_log_entry(log_event)
            if normalized_log:
                normalized_logs.append(normalized_log)

        return normalized_logs, total_matches

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")

        # Handle ResourceNotFoundException gracefully (log group doesn't exist)
        if error_code == "ResourceNotFoundException":
            logger.warning(
                json.dumps(
                    {
                        "message": "Log group not found",
                        "correlationId": correlation_id,
                        "logGroupName": log_group_name,
                    }
                )
            )
            return [], 0

        # Retry on throttling (raise to trigger Step Functions retry)
        if error_code in ["ThrottlingException", "TooManyRequestsException"]:
            raise

        logger.error(
            json.dumps(
                {
                    "message": "Failed to collect logs",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorCode": error_code,
                }
            )
        )

        return [], 0


def normalize_log_entry(log_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize a CloudWatch Logs event into structured format.

    Args:
        log_event: Raw log event from CloudWatch Logs

    Returns:
        Normalized log entry dictionary or None if invalid

    Requirements: 4.4 - Return logs in normalized JSON structure
    """
    try:
        timestamp_ms = log_event.get("timestamp", 0)
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)

        message = log_event.get("message", "")
        log_stream = log_event.get("logStreamName", "")

        # Extract log level from message
        log_level = extract_log_level(message)

        # Format timestamp as ISO-8601 with 'Z' suffix (UTC)
        timestamp_str = timestamp.isoformat().replace("+00:00", "Z")

        return {
            "timestamp": timestamp_str,
            "logLevel": log_level,
            "message": message.strip(),
            "logStream": log_stream,
        }

    except Exception as e:
        logger.warning(f"Failed to normalize log entry: {str(e)}")
        return None


def extract_log_level(message: str) -> str:
    """
    Extract log level from log message.

    Args:
        message: Log message text

    Returns:
        Log level (ERROR, WARN, CRITICAL, or INFO)

    Requirements: 4.2 - Identify log levels
    """
    message_upper = message.upper()

    # Check for log levels in order of severity
    if "CRITICAL" in message_upper or "FATAL" in message_upper:
        return "CRITICAL"
    elif "ERROR" in message_upper:
        return "ERROR"
    elif "WARN" in message_upper or "WARNING" in message_upper:
        return "WARN"
    else:
        # Default to INFO if no level found (shouldn't happen with filter pattern)
        return "INFO"
