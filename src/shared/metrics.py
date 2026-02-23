"""
CloudWatch Metrics Utility Module

Provides helper functions for emitting custom CloudWatch metrics
from Lambda functions.

Requirements: 11.3 - Custom CloudWatch metrics for observability
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

# Initialize CloudWatch client
cloudwatch = boto3.client("cloudwatch")

# Metric namespace
METRIC_NAMESPACE = "AI-SRE-IncidentAnalysis"


def put_metric(
    metric_name: str,
    value: float,
    unit: str = "None",
    dimensions: Optional[List[Dict[str, str]]] = None,
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Emit a custom CloudWatch metric.

    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Metric unit (Seconds, Count, Percent, etc.)
        dimensions: List of dimension dicts with Name and Value keys
        timestamp: Metric timestamp (defaults to current time)
    """
    try:
        metric_data = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": timestamp or datetime.utcnow(),
        }

        if dimensions:
            metric_data["Dimensions"] = dimensions

        cloudwatch.put_metric_data(Namespace=METRIC_NAMESPACE, MetricData=[metric_data])

        logger.debug(f"Emitted metric: {metric_name}={value} {unit}")

    except ClientError as e:
        # Log error but don't fail the function
        logger.warning(f"Failed to emit metric {metric_name}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error emitting metric {metric_name}: {e}")


def put_collector_success_metric(collector_name: str, success: bool, duration: float) -> None:
    """
    Emit collector success rate and duration metrics.

    Args:
        collector_name: Name of the collector (metrics, logs, deploy_context)
        success: Whether the collection succeeded
        duration: Collection duration in seconds
    """
    dimensions = [{"Name": "Collector", "Value": collector_name}]

    # Emit success/failure count
    put_metric(
        metric_name="CollectorInvocations",
        value=1.0,
        unit="Count",
        dimensions=dimensions + [{"Name": "Status", "Value": "Success" if success else "Failure"}],
    )

    # Emit duration
    put_metric(
        metric_name="CollectorDuration", value=duration, unit="Seconds", dimensions=dimensions
    )


def put_llm_invocation_metric(
    latency: float, success: bool, model_id: str = "anthropic.claude-v2"
) -> None:
    """
    Emit LLM invocation latency and success metrics.

    Args:
        latency: Invocation latency in seconds
        success: Whether the invocation succeeded
        model_id: Bedrock model identifier
    """
    dimensions = [{"Name": "ModelId", "Value": model_id}]

    # Emit latency
    put_metric(
        metric_name="LLMInvocationLatency", value=latency, unit="Seconds", dimensions=dimensions
    )

    # Emit success/failure count
    put_metric(
        metric_name="LLMInvocations",
        value=1.0,
        unit="Count",
        dimensions=dimensions + [{"Name": "Status", "Value": "Success" if success else "Failure"}],
    )


def put_notification_delivery_metric(channel: str, success: bool, duration: float) -> None:
    """
    Emit notification delivery status and duration metrics.

    Args:
        channel: Notification channel (slack, email)
        success: Whether delivery succeeded
        duration: Delivery duration in seconds
    """
    dimensions = [{"Name": "Channel", "Value": channel}]

    # Emit delivery count
    put_metric(
        metric_name="NotificationDeliveries",
        value=1.0,
        unit="Count",
        dimensions=dimensions + [{"Name": "Status", "Value": "Success" if success else "Failure"}],
    )

    # Emit duration
    put_metric(
        metric_name="NotificationDuration", value=duration, unit="Seconds", dimensions=dimensions
    )


def put_workflow_duration_metric(duration: float, success: bool) -> None:
    """
    Emit workflow duration metric.

    Args:
        duration: Workflow duration in seconds
        success: Whether the workflow completed successfully
    """
    # Emit duration
    put_metric(
        metric_name="WorkflowDuration",
        value=duration,
        unit="Seconds",
        dimensions=[{"Name": "Status", "Value": "Success" if success else "Failure"}],
    )

    # Emit completion count
    put_metric(
        metric_name="WorkflowCompletions",
        value=1.0,
        unit="Count",
        dimensions=[{"Name": "Status", "Value": "Success" if success else "Failure"}],
    )
