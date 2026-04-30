"""
Metrics Collector Lambda Function

This Lambda function collects CloudWatch metrics for the affected resource
during an incident. It queries metrics from 60 minutes before to 5 minutes
after the incident timestamp and calculates summary statistics.

Requirements: 3.1, 3.2, 3.3, 3.4
"""

import json
import logging
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize CloudWatch client
cloudwatch = boto3.client("cloudwatch")

# Import metrics utility
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from metrics import put_collector_success_metric  # noqa: E402

# ---------------------------------------------------------------------------
# SSM-backed time-window configuration (module-level cache for warm reuse).
# Parameters are read once on cold start. Defaults apply when SSM is
# unavailable or the parameters have not been created yet.
# ---------------------------------------------------------------------------
_DEFAULT_LOOKBACK_MINUTES: int = 60
_DEFAULT_LOOKAHEAD_MINUTES: int = 5

_SSM_PARAM_LOOKBACK = os.environ.get(
    "METRICS_LOOKBACK_PARAM", "/incident-analysis/metrics-lookback-minutes"
)
_SSM_PARAM_LOOKAHEAD = os.environ.get(
    "METRICS_LOOKAHEAD_PARAM", "/incident-analysis/metrics-lookahead-minutes"
)


def _load_time_window_from_ssm() -> Tuple[int, int]:
    """
    Load metric time-window parameters from SSM Parameter Store.

    Returns:
        Tuple of (lookback_minutes, lookahead_minutes).
        Falls back to module defaults when parameters are absent or SSM
        is unreachable, so a cold start never fails due to missing params.
    """
    ssm = boto3.client("ssm")
    lookback = _DEFAULT_LOOKBACK_MINUTES
    lookahead = _DEFAULT_LOOKAHEAD_MINUTES

    try:
        response = ssm.get_parameters(
            Names=[_SSM_PARAM_LOOKBACK, _SSM_PARAM_LOOKAHEAD],
            WithDecryption=False,
        )
        params = {p["Name"]: p["Value"] for p in response.get("Parameters", [])}

        lookback = int(params.get(_SSM_PARAM_LOOKBACK, _DEFAULT_LOOKBACK_MINUTES))
        lookahead = int(params.get(_SSM_PARAM_LOOKAHEAD, _DEFAULT_LOOKAHEAD_MINUTES))

        logger.info(
            json.dumps(
                {
                    "message": "Loaded time window from SSM",
                    "lookbackMinutes": lookback,
                    "lookaheadMinutes": lookahead,
                }
            )
        )
    except Exception as exc:
        logger.warning(
            json.dumps(
                {
                    "message": "Failed to load time window from SSM; using defaults",
                    "lookbackMinutes": lookback,
                    "lookaheadMinutes": lookahead,
                    "error": str(exc),
                }
            )
        )

    return lookback, lookahead


# Populated at cold-start; reused across warm invocations.
_LOOKBACK_MINUTES, _LOOKAHEAD_MINUTES = _load_time_window_from_ssm()


def _log(level: str, message: str, correlation_id: str, context: Any = None, **kwargs) -> None:
    """
    Helper function for structured logging with function metadata.

    Args:
        level: Log level (info, warning, error)
        message: Log message
        correlation_id: Incident ID for correlation
        context: Lambda context object
        **kwargs: Additional fields to include in log
    """
    function_name = (
        context.function_name
        if context and hasattr(context, "function_name")
        else os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "metrics-collector")
    )
    function_version = (
        context.function_version
        if context and hasattr(context, "function_version")
        else os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "$LATEST")
    )

    log_entry = {
        "message": message,
        "correlationId": correlation_id,
        "functionName": function_name,
        "functionVersion": function_version,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }
    log_entry.update(kwargs)

    log_method = getattr(logger, level)
    log_method(json.dumps(log_entry))


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:  # noqa: C901
    """
    Lambda handler for metrics collection.

    Args:
        event: Event containing resourceArn, timestamp, namespace, and optional metricNames
        context: Lambda context object

    Returns:
        Dictionary containing status, metrics array, and collection_duration
    """
    start_time = datetime.now(timezone.utc)
    correlation_id = event.get("incidentId", event.get("incident", {}).get("incidentId", "unknown"))

    try:
        _log(
            "info",
            "Metrics collector invoked",
            correlation_id,
            context,
            resourceArn=event.get("resourceArn"),
            incidentTimestamp=event.get("timestamp"),
        )

        # Extract required fields
        resource_arn = event.get("resourceArn")
        timestamp_str = event.get("timestamp")
        namespace = event.get("namespace")

        if not resource_arn or not timestamp_str:
            raise ValueError("Missing required fields: resourceArn and timestamp")

        # Parse timestamp
        incident_timestamp = parse_timestamp(timestamp_str)

        # Parse resource ARN to determine namespace and dimensions if not provided
        if not namespace:
            namespace, dimensions = parse_resource_arn(resource_arn)
        else:
            _, dimensions = parse_resource_arn(resource_arn)

        # Calculate time range (-60min to +5min)
        start_time_range, end_time_range = calculate_time_range(incident_timestamp)

        _log(
            "info",
            "Calculated time range",
            correlation_id,
            context,
            startTime=start_time_range.isoformat(),
            endTime=end_time_range.isoformat(),
            namespace=namespace,
        )

        # Determine which metrics to collect based on namespace
        metric_names = event.get("metricNames") or get_default_metrics_for_namespace(namespace)

        # Collect metrics in parallel using ThreadPoolExecutor.
        # Max workers capped at 10 to avoid CloudWatch API throttling.
        # Each GetMetricStatistics call is independent, so parallelism is safe.
        metrics_data = []
        # Keep max_workers <= 10 to avoid CloudWatch throttling.
        max_workers = min(10, len(metric_names)) if metric_names else 1

        def _collect_single(metric_name: str) -> Optional[Dict[str, Any]]:
            return collect_metric(
                namespace=namespace,
                metric_name=metric_name,
                dimensions=dimensions,
                start_time=start_time_range,
                end_time=end_time_range,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_metric = {
                executor.submit(_collect_single, mn): mn for mn in metric_names
            }
            for future in as_completed(future_to_metric):
                metric_name = future_to_metric[future]
                try:
                    metric_data = future.result()
                    if metric_data:
                        metrics_data.append(metric_data)
                except Exception as e:
                    _log(
                        "warning",
                        f"Failed to collect metric {metric_name}",
                        correlation_id,
                        context,
                        metricName=metric_name,
                        error=str(e),
                    )

        # Calculate collection duration
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Log warning if no metrics found
        if not metrics_data:
            _log(
                "warning",
                "No metrics found for resource",
                correlation_id,
                context,
                resourceArn=resource_arn,
                namespace=namespace,
            )

        result = {
            "status": "success",
            "metrics": metrics_data,
            "collectionDuration": collection_duration,
        }

        _log(
            "info",
            "Metrics collection completed",
            correlation_id,
            context,
            metricsCount=len(metrics_data),
            duration=collection_duration,
        )

        # Emit CloudWatch metrics
        put_collector_success_metric("metrics", True, collection_duration)

        return result

    except ValueError as e:
        # Non-retryable validation error
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        _log(
            "error",
            "Validation error",
            correlation_id,
            context,
            error=str(e),
            errorType="ValidationException",
        )

        # Emit failure metric
        put_collector_success_metric("metrics", False, collection_duration)

        return {
            "status": "failed",
            "metrics": [],
            "collectionDuration": collection_duration,
            "error": str(e),
        }

    except ClientError as e:
        # ERROR HANDLING STRATEGY: Classify AWS API errors
        # Retryable: ThrottlingException, ServiceException, TooManyRequestsException
        # Non-retryable: All others (return error response with empty data)
        # AWS SDK has built-in retry logic, but Step Functions adds another layer
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        error_code = e.response.get("Error", {}).get("Code", "Unknown")

        _log(
            "error",
            "AWS API error",
            correlation_id,
            context,
            error=str(e),
            errorCode=error_code,
            errorType="ClientError",
            stackTrace=traceback.format_exc(),
        )

        # Raise retryable errors for Step Functions retry mechanism
        # Step Functions will retry with exponential backoff (2s, 4s, 8s)
        if error_code in ["ThrottlingException", "ServiceException", "TooManyRequestsException"]:
            put_collector_success_metric("metrics", False, collection_duration)
            raise  # Let Step Functions handle retry with backoff

        # Non-retryable error - return error response (graceful degradation)
        put_collector_success_metric("metrics", False, collection_duration)

        return {
            "status": "failed",
            "metrics": [],
            "collectionDuration": collection_duration,
            "error": f"{error_code}: {str(e)}",
        }

    except Exception as e:
        # Unexpected error
        collection_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        _log(
            "error",
            "Unexpected error",
            correlation_id,
            context,
            error=str(e),
            errorType=type(e).__name__,
            stackTrace=traceback.format_exc(),
        )

        # Emit failure metric
        put_collector_success_metric("metrics", False, collection_duration)

        return {
            "status": "failed",
            "metrics": [],
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


def calculate_time_range(
    incident_timestamp: datetime,
    lookback_minutes: int = _LOOKBACK_MINUTES,
    lookahead_minutes: int = _LOOKAHEAD_MINUTES,
) -> Tuple[datetime, datetime]:
    """
    Calculate time range for metrics query.

    The window defaults are sourced from SSM Parameter Store at cold-start
    (see _load_time_window_from_ssm). Callers can override the window by
    supplying explicit values, which is useful for testing.

    Args:
        incident_timestamp: Time of the incident
        lookback_minutes: Minutes before incident to include (default from SSM or 60)
        lookahead_minutes: Minutes after incident to include (default from SSM or 5)

    Returns:
        Tuple of (start_time, end_time) for metrics query

    Requirements: 3.1 - Query metrics from lookback_minutes before to
                         lookahead_minutes after the incident timestamp
    """
    start_time = incident_timestamp - timedelta(minutes=lookback_minutes)
    end_time = incident_timestamp + timedelta(minutes=lookahead_minutes)

    return start_time, end_time


def parse_resource_arn(resource_arn: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    Parse resource ARN to determine CloudWatch namespace and dimensions.

    Args:
        resource_arn: AWS resource ARN

    Returns:
        Tuple of (namespace, dimensions)

    Examples:
        arn:aws:lambda:us-east-1:123456789012:function:my-function
        -> ("AWS/Lambda", [{"Name": "FunctionName", "Value": "my-function"}])

        arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0
        -> ("AWS/EC2", [{"Name": "InstanceId", "Value": "i-1234567890abcdef0"}])
    """
    parts = resource_arn.split(":")

    if len(parts) < 6:
        raise ValueError(f"Invalid ARN format: {resource_arn}")

    service = parts[2]
    resource_part = parts[5] if len(parts) > 5 else parts[-1]

    # Map service to CloudWatch namespace
    namespace_map = {
        "lambda": "AWS/Lambda",
        "ec2": "AWS/EC2",
        "rds": "AWS/RDS",
        "ecs": "AWS/ECS",
        "dynamodb": "AWS/DynamoDB",
        "sqs": "AWS/SQS",
        "sns": "AWS/SNS",
        "apigateway": "AWS/ApiGateway",
        "s3": "AWS/S3",
        "eks": "AWS/ContainerInsights",
        "elasticache": "AWS/ElastiCache",
        "es": "AWS/ES",
    }

    # Distinguish ALB vs NLB based on ARN path
    if service == "elasticloadbalancing":
        if "/net/" in resource_part:
            namespace = "AWS/NetworkELB"
        else:
            namespace = "AWS/ApplicationELB"
    else:
        namespace = namespace_map.get(service, f"AWS/{service.upper()}")

    # Extract resource name/ID and create dimensions
    dimensions = []

    if service == "lambda":
        # arn:aws:lambda:region:account:function:function-name
        function_name = (
            resource_part.split(":")[-1] if ":" in resource_part else resource_part.split("/")[-1]
        )
        dimensions = [{"Name": "FunctionName", "Value": function_name}]

    elif service == "ec2":
        # arn:aws:ec2:region:account:instance/instance-id
        instance_id = resource_part.split("/")[-1]
        dimensions = [{"Name": "InstanceId", "Value": instance_id}]

    elif service == "rds":
        # arn:aws:rds:region:account:db:db-instance-id
        db_instance_id = resource_part.split(":")[-1]
        dimensions = [{"Name": "DBInstanceIdentifier", "Value": db_instance_id}]

    elif service == "ecs":
        # arn:aws:ecs:region:account:service/cluster-name/service-name
        parts_split = resource_part.split("/")
        if len(parts_split) >= 3:
            cluster_name = parts_split[1]
            service_name = parts_split[2]
            dimensions = [
                {"Name": "ClusterName", "Value": cluster_name},
                {"Name": "ServiceName", "Value": service_name},
            ]

    elif service == "dynamodb":
        # arn:aws:dynamodb:region:account:table/table-name
        table_name = resource_part.split("/")[-1]
        dimensions = [{"Name": "TableName", "Value": table_name}]

    elif service == "elasticloadbalancing":
        # arn:aws:elasticloadbalancing:region:account:loadbalancer/app/name/id
        # or loadbalancer/net/name/id
        lb_parts = resource_part.split("/", 1)
        if len(lb_parts) >= 2:
            lb_value = lb_parts[1]  # e.g. "app/name/id" or "net/name/id"
            dimensions = [{"Name": "LoadBalancer", "Value": lb_value}]

    elif service == "eks":
        # arn:aws:eks:region:account:cluster/cluster-name
        cluster_name = resource_part.split("/")[-1]
        dimensions = [{"Name": "ClusterName", "Value": cluster_name}]

    elif service == "elasticache":
        # arn:aws:elasticache:region:account:cluster:cluster-id
        cluster_id = resource_part.split(":")[-1] if ":" in resource_part else resource_part.split("/")[-1]
        dimensions = [{"Name": "CacheClusterId", "Value": cluster_id}]

    elif service == "es":
        # arn:aws:es:region:account:domain/domain-name
        domain_name = resource_part.split("/")[-1]
        dimensions = [{"Name": "DomainName", "Value": domain_name}]

    return namespace, dimensions


def get_default_metrics_for_namespace(namespace: str) -> List[str]:
    """
    Get default metrics to collect for a given namespace.

    Args:
        namespace: CloudWatch namespace

    Returns:
        List of metric names

    Requirements: 3.2 - Retrieve relevant metrics based on service
    """
    metric_map = {
        "AWS/Lambda": ["Invocations", "Errors", "Duration", "Throttles", "ConcurrentExecutions"],
        "AWS/EC2": ["CPUUtilization", "NetworkIn", "NetworkOut", "DiskReadBytes", "DiskWriteBytes"],
        "AWS/RDS": [
            "CPUUtilization",
            "DatabaseConnections",
            "FreeableMemory",
            "ReadLatency",
            "WriteLatency",
        ],
        "AWS/ECS": ["CPUUtilization", "MemoryUtilization"],
        "AWS/DynamoDB": [
            "ConsumedReadCapacityUnits",
            "ConsumedWriteCapacityUnits",
            "UserErrors",
            "SystemErrors",
        ],
        "AWS/SQS": [
            "NumberOfMessagesSent",
            "NumberOfMessagesReceived",
            "ApproximateNumberOfMessagesVisible",
        ],
        "AWS/ApiGateway": ["Count", "4XXError", "5XXError", "Latency"],
        "AWS/ApplicationELB": [
            "RequestCount",
            "TargetResponseTime",
            "HTTPCode_ELB_5XX_Count",
            "HTTPCode_Target_5XX_Count",
            "HealthyHostCount",
            "UnHealthyHostCount",
        ],
        "AWS/NetworkELB": [
            "ActiveFlowCount",
            "NewFlowCount",
            "ProcessedBytes",
            "TCP_Target_Reset_Count",
            "UnHealthyHostCount",
        ],
        "AWS/ContainerInsights": [
            "cluster_failed_node_count",
            "node_cpu_utilization",
            "node_memory_utilization",
            "pod_cpu_utilization",
        ],
        "AWS/ElastiCache": [
            "CPUUtilization",
            "FreeableMemory",
            "CurrConnections",
            "Evictions",
            "CacheHitRate",
        ],
        "AWS/ES": [
            "ClusterStatus.red",
            "FreeStorageSpace",
            "CPUUtilization",
            "JVMMemoryPressure",
            "SearchLatency",
        ],
    }

    return metric_map.get(namespace, ["CPUUtilization", "NetworkIn", "NetworkOut"])


def collect_metric(
    namespace: str,
    metric_name: str,
    dimensions: List[Dict[str, str]],
    start_time: datetime,
    end_time: datetime,
) -> Optional[Dict[str, Any]]:
    """
    Collect a single metric from CloudWatch.

    Args:
        namespace: CloudWatch namespace
        metric_name: Name of the metric
        dimensions: Metric dimensions
        start_time: Start of time range
        end_time: End of time range

    Returns:
        Dictionary containing metric data and statistics, or None if no data

    Requirements: 3.2, 3.3 - Retrieve and normalize metric data
    """
    try:
        # Query CloudWatch for metric statistics
        # Period: 60 seconds (1-minute granularity for detailed view)
        # Statistics: Average, Maximum, Minimum, SampleCount
        # AWS SDK has built-in retry logic with exponential backoff
        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=60,  # 1-minute granularity
            Statistics=["Average", "Maximum", "Minimum", "SampleCount"],
        )

        datapoints = response.get("Datapoints", [])

        # Return None if no data available (not an error condition)
        if not datapoints:
            return None

        # Sort datapoints by timestamp (CloudWatch may return unsorted)
        datapoints.sort(key=lambda x: x["Timestamp"])

        # Normalize datapoints to consistent format
        normalized_datapoints = []
        for dp in datapoints:
            normalized_datapoints.append(
                {
                    "timestamp": dp["Timestamp"].isoformat(),
                    "value": dp.get("Average", 0.0),
                    "unit": dp.get("Unit", "None"),
                }
            )

        # Calculate summary statistics
        statistics = calculate_statistics(datapoints)

        return {
            "metricName": metric_name,
            "namespace": namespace,
            "datapoints": normalized_datapoints,
            "statistics": statistics,
        }

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")

        # Retry on throttling (raise to trigger AWS SDK retry or Step Functions retry)
        if error_code in ["ThrottlingException", "TooManyRequestsException"]:
            raise

        # Log warning for other errors but don't fail entire collection
        logger.warning(f"Failed to collect metric {metric_name}: {str(e)}")
        return None


def calculate_statistics(datapoints: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate summary statistics from datapoints.

    Args:
        datapoints: List of CloudWatch datapoints

    Returns:
        Dictionary containing avg, max, min, and p95 statistics

    Requirements: 3.2 - Calculate summary statistics (avg, max, min, p95)
    """
    if not datapoints:
        return {"avg": 0.0, "max": 0.0, "min": 0.0, "p95": 0.0}

    # Extract average values
    values = [dp.get("Average", 0.0) for dp in datapoints]

    # Calculate statistics
    avg = sum(values) / len(values)
    max_val = max(values)
    min_val = min(values)

    # Calculate 95th percentile
    sorted_values = sorted(values)
    p95_index = int(len(sorted_values) * 0.95)
    p95 = sorted_values[p95_index] if p95_index < len(sorted_values) else sorted_values[-1]

    return {
        "avg": round(avg, 2),
        "max": round(max_val, 2),
        "min": round(min_val, 2),
        "p95": round(p95, 2),
    }
