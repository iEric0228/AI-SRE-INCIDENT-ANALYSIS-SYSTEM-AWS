"""
Correlation Engine Lambda Function

This Lambda function merges and normalizes data from all three collectors
(metrics, logs, deploy context) into a single structured context object.

Responsibilities:
- Merge outputs from all collectors
- Track completeness for failed collectors
- Normalize timestamps to ISO 8601 UTC
- Remove duplicates and sort chronologically
- Calculate summary statistics
- Enforce size constraint (50KB limit with truncation)

Requirements: 6.1, 6.2, 6.3, 6.4, 6.6
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict

# Add shared module to path
sys.path.insert(0, "/opt/python")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from metrics import put_metric, put_workflow_duration_metric  # noqa: E402
from models import (  # noqa: E402
    AlarmInfo,
    CompletenessInfo,
    ResourceInfo,
    StructuredContext,
)

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for correlation engine.

    Args:
        event: Event containing incident data and collector outputs
        context: Lambda context object

    Returns:
        Structured context with merged and normalized data
    """
    correlation_id = event.get("incident", {}).get("incidentId", "unknown")

    try:
        logger.info(
            json.dumps(
                {
                    "message": "Correlation engine invoked",
                    "correlationId": correlation_id,
                    "eventKeys": list(event.keys()),
                }
            )
        )

        # Extract incident information
        incident = event.get("incident", {})

        # Check which collectors succeeded
        completeness = track_completeness(event)

        logger.info(
            json.dumps(
                {
                    "message": "Data completeness tracked",
                    "correlationId": correlation_id,
                    "completeness": completeness,
                }
            )
        )

        # Extract collector outputs
        metrics_data = extract_metrics_data(event) if completeness["metrics"] else {}
        logs_data = extract_logs_data(event) if completeness["logs"] else {}
        changes_data = extract_changes_data(event) if completeness["changes"] else {}

        # Parse resource ARN
        resource_info = parse_resource_arn(incident.get("resourceArn", ""))

        # Extract alarm information
        alarm_info = extract_alarm_info(incident)

        # Create structured context
        structured_context = StructuredContext(
            incident_id=incident.get("incidentId", ""),
            timestamp=parse_timestamp(incident.get("timestamp", "")),
            resource=resource_info,
            alarm=alarm_info,
            metrics=metrics_data,
            logs=logs_data,
            changes=changes_data,
            completeness=CompletenessInfo(
                metrics=completeness["metrics"],
                logs=completeness["logs"],
                changes=completeness["changes"],
            ),
        )

        # Normalize timestamps
        structured_context = normalize_timestamps(structured_context)

        # Remove duplicates and sort chronologically
        structured_context = deduplicate_and_sort(structured_context)

        # Calculate summary statistics
        structured_context = calculate_summary_statistics(structured_context)

        # Enforce size constraint (50KB)
        structured_context = enforce_size_constraint(structured_context)

        result = structured_context.to_dict()

        # Calculate workflow duration from incident timestamp to now
        incident_time = parse_timestamp(incident.get("timestamp", ""))
        workflow_duration = (datetime.now(timezone.utc) - incident_time).total_seconds()

        logger.info(
            json.dumps(
                {
                    "message": "Correlation completed successfully",
                    "correlationId": correlation_id,
                    "contextSize": structured_context.size_bytes(),
                    "completeness": completeness,
                    "workflowDuration": workflow_duration,
                }
            )
        )

        # Emit workflow duration metric (partial - up to correlation)
        # Full workflow duration will be tracked by Step Functions
        put_workflow_duration_metric(workflow_duration, True)

        return {"status": "success", "structuredContext": result, "correlationId": correlation_id}

    except Exception as e:
        # ERROR HANDLING STRATEGY: Non-retryable error with graceful degradation
        # Log full context for debugging, emit failure metrics, return error response
        # Allows Step Functions to continue with partial data from other collectors
        logger.error(
            json.dumps(
                {
                    "message": "Correlation engine error",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorType": type(e).__name__,
                    "stackTrace": traceback.format_exc(),
                }
            )
        )

        # Emit failure metric for observability
        incident = event.get("incident", {})
        if incident.get("timestamp"):
            incident_time = parse_timestamp(incident.get("timestamp", ""))
            workflow_duration = (datetime.now(timezone.utc) - incident_time).total_seconds()
            put_workflow_duration_metric(workflow_duration, False)

        # Return error response (not raising exception allows workflow to continue)
        return {
            "status": "failed",
            "error": str(e),
            "errorType": type(e).__name__,
            "correlationId": correlation_id,
        }


def track_completeness(event: Dict[str, Any]) -> Dict[str, bool]:
    """
    Track which collectors succeeded.

    Args:
        event: Event containing collector outputs

    Returns:
        Dictionary with completeness flags for each collector
    """
    return {
        "metrics": "metricsError" not in event
        and event.get("metrics", {}).get("status") == "success",
        "logs": "logsError" not in event and event.get("logs", {}).get("status") == "success",
        "changes": "changesError" not in event
        and event.get("changes", {}).get("status") == "success",
    }


def extract_metrics_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and structure metrics data from collector output.

    Args:
        event: Event containing metrics collector output

    Returns:
        Structured metrics data
    """
    metrics_output = event.get("metrics", {})
    metrics_list = metrics_output.get("metrics", [])

    # Calculate summary statistics across all metrics
    all_values = []
    time_series = []

    for metric in metrics_list:
        datapoints = metric.get("datapoints", [])
        for dp in datapoints:
            all_values.append(dp.get("value", 0))
            time_series.append(
                {
                    "timestamp": dp.get("timestamp", ""),
                    "metricName": metric.get("metricName", ""),
                    "value": dp.get("value", 0),
                    "unit": dp.get("unit", ""),
                }
            )

    # Calculate aggregate statistics
    summary = {}
    if all_values:
        summary = {
            "avg": sum(all_values) / len(all_values),
            "max": max(all_values),
            "min": min(all_values),
            "count": len(all_values),
        }

    return {"summary": summary, "timeSeries": time_series, "metrics": metrics_list}


def extract_logs_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and structure logs data from collector output.

    Args:
        event: Event containing logs collector output

    Returns:
        Structured logs data
    """
    logs_output = event.get("logs", {})
    logs_list = logs_output.get("logs", [])

    # Count errors by level
    error_counts: Dict[str, int] = {}
    top_errors: list[Dict[str, Any]] = []

    for log in logs_list:
        level = log.get("logLevel", "UNKNOWN")
        error_counts[level] = error_counts.get(level, 0) + 1

        # Collect unique error messages (first 10)
        message = log.get("message", "")
        if message and message not in top_errors and len(top_errors) < 10:
            top_errors.append(message)

    return {
        "errorCount": sum(error_counts.values()),
        "errorCountsByLevel": error_counts,
        "topErrors": top_errors,
        "entries": logs_list,
        "totalMatches": logs_output.get("totalMatches", 0),
        "returned": logs_output.get("returned", 0),
    }


def extract_changes_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and structure changes data from collector output.

    Args:
        event: Event containing deploy context collector output

    Returns:
        Structured changes data
    """
    changes_output = event.get("changes", {})
    changes_list = changes_output.get("changes", [])

    # Count changes by type
    change_counts: Dict[str, int] = {}
    recent_deployments = 0
    last_deployment_time = None

    for change in changes_list:
        change_type = change.get("changeType", "unknown")
        change_counts[change_type] = change_counts.get(change_type, 0) + 1

        # Track deployments
        if change_type == "deployment":
            recent_deployments += 1
            change_time = change.get("timestamp", "")
            if not last_deployment_time or change_time > last_deployment_time:
                last_deployment_time = change_time

    return {
        "recentDeployments": recent_deployments,
        "lastDeployment": last_deployment_time,
        "changeCountsByType": change_counts,
        "totalChanges": len(changes_list),
        "entries": changes_list,
    }


def parse_resource_arn(arn: str) -> ResourceInfo:
    """
    Parse AWS resource ARN to extract resource information.

    Args:
        arn: AWS resource ARN

    Returns:
        ResourceInfo object
    """
    if not arn:
        return ResourceInfo(arn="", type="unknown", name="unknown")

    try:
        # ARN format: arn:aws:service:region:account:resource-type/resource-name
        parts = arn.split(":")

        if len(parts) < 6:
            return ResourceInfo(arn=arn, type="unknown", name="unknown")

        service = parts[2]
        resource_part = ":".join(parts[5:])

        # Extract resource type and name
        if "/" in resource_part:
            resource_type, resource_name = resource_part.split("/", 1)
        else:
            resource_type = service
            resource_name = resource_part

        return ResourceInfo(arn=arn, type=resource_type, name=resource_name)
    except Exception as e:
        logger.warning(f"Failed to parse ARN {arn}: {e}")
        return ResourceInfo(arn=arn, type="unknown", name="unknown")


def extract_alarm_info(incident: Dict[str, Any]) -> AlarmInfo:
    """
    Extract alarm information from incident event.

    Args:
        incident: Incident event data

    Returns:
        AlarmInfo object
    """
    return AlarmInfo(
        name=incident.get("alarmName", ""),
        metric=incident.get("metricName", ""),
        threshold=0.0,  # Threshold not available in current incident format
    )


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse timestamp string to datetime object.

    Args:
        timestamp_str: Timestamp string in various formats

    Returns:
        datetime object (timezone-aware)
    """
    if not timestamp_str:
        return datetime.now(timezone.utc)

    try:
        # Handle ISO 8601 format with Z suffix
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"

        return datetime.fromisoformat(timestamp_str)
    except Exception as e:
        logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
        return datetime.now(timezone.utc)


def normalize_timestamps(context: StructuredContext) -> StructuredContext:  # noqa: C901
    """
    Normalize all timestamps to ISO 8601 UTC format.

    Args:
        context: Structured context with potentially mixed timestamp formats

    Returns:
        Structured context with normalized timestamps
    """

    def to_iso_utc(ts) -> str:
        """Convert timestamp to ISO 8601 UTC format with Z suffix."""
        if isinstance(ts, str):
            dt = parse_timestamp(ts)
        elif isinstance(ts, datetime):
            dt = ts
        else:
            return str(ts)

        # Remove timezone info from isoformat to avoid +00:00, then add Z
        iso_str = dt.replace(tzinfo=None).isoformat()
        return iso_str + "Z"

    # Normalize timestamps in metrics time series
    if "timeSeries" in context.metrics:
        for entry in context.metrics["timeSeries"]:
            if "timestamp" in entry:
                entry["timestamp"] = to_iso_utc(entry["timestamp"])

    # Normalize timestamps in metrics datapoints
    if "metrics" in context.metrics:
        for metric in context.metrics["metrics"]:
            if "datapoints" in metric:
                for dp in metric["datapoints"]:
                    if "timestamp" in dp:
                        dp["timestamp"] = to_iso_utc(dp["timestamp"])

    # Normalize timestamps in log entries
    if "entries" in context.logs:
        for entry in context.logs["entries"]:
            if "timestamp" in entry:
                entry["timestamp"] = to_iso_utc(entry["timestamp"])

    # Normalize timestamps in change entries
    if "entries" in context.changes:
        for entry in context.changes["entries"]:
            if "timestamp" in entry:
                entry["timestamp"] = to_iso_utc(entry["timestamp"])

    return context


def deduplicate_and_sort(context: StructuredContext) -> StructuredContext:
    """
    Remove duplicate entries and sort chronologically.

    Args:
        context: Structured context with potential duplicates

    Returns:
        Structured context with deduplicated and sorted data
    """
    # DEDUPLICATION ALGORITHM:
    # Strategy: Use composite keys to identify unique entries
    # Approach: Track seen entries with set of tuples (fast O(1) lookup)
    # Reason: Collectors may return overlapping data from different sources

    # Deduplicate and sort metrics time series
    if "timeSeries" in context.metrics:
        time_series = context.metrics["timeSeries"]
        # Create unique key: (timestamp, metric_name, value)
        # This ensures same metric at same time with same value is only counted once
        seen = set()
        unique_series = []
        for entry in time_series:
            key = (entry.get("timestamp", ""), entry.get("metricName", ""), entry.get("value", 0))
            if key not in seen:
                seen.add(key)
                unique_series.append(entry)

        # Sort by timestamp (chronological order for time-series analysis)
        unique_series.sort(key=lambda x: x.get("timestamp", ""))
        context.metrics["timeSeries"] = unique_series

    # Deduplicate and sort log entries
    if "entries" in context.logs:
        logs = context.logs["entries"]
        # Create unique key: (timestamp, message, log_stream)
        # Same message at same time from same stream = duplicate
        seen = set()
        unique_logs = []
        for entry in logs:
            key = (entry.get("timestamp", ""), entry.get("message", ""), entry.get("logStream", ""))
            if key not in seen:
                seen.add(key)
                unique_logs.append(entry)

        # Sort by timestamp (chronological order for incident timeline)
        unique_logs.sort(key=lambda x: x.get("timestamp", ""))
        context.logs["entries"] = unique_logs

    # Deduplicate and sort change entries
    if "entries" in context.changes:
        changes = context.changes["entries"]
        # Create unique key: (timestamp, event_name, user)
        # Same event at same time by same user = duplicate
        seen = set()
        unique_changes = []
        for entry in changes:
            key = (entry.get("timestamp", ""), entry.get("eventName", ""), entry.get("user", ""))
            if key not in seen:
                seen.add(key)
                unique_changes.append(entry)

        # Sort by timestamp (chronological order for change timeline)
        unique_changes.sort(key=lambda x: x.get("timestamp", ""))
        context.changes["entries"] = unique_changes

    return context


def calculate_summary_statistics(context: StructuredContext) -> StructuredContext:
    """
    Calculate summary statistics for all data sources.

    Args:
        context: Structured context

    Returns:
        Structured context with calculated summary statistics
    """
    # Metrics summary already calculated in extract_metrics_data

    # Update logs summary with final counts
    if "entries" in context.logs:
        context.logs["errorCount"] = len(context.logs["entries"])

    # Update changes summary with final counts
    if "entries" in context.changes:
        context.changes["totalChanges"] = len(context.changes["entries"])

    return context


def enforce_size_constraint(  # noqa: C901
    context: StructuredContext, max_size_kb: int = 50
) -> StructuredContext:
    """
    Enforce size constraint by truncating data if necessary.
    Prioritizes recent entries when truncating.

    Args:
        context: Structured context
        max_size_kb: Maximum size in kilobytes (default: 50KB)

    Returns:
        Structured context within size constraint
    """
    max_size_bytes = max_size_kb * 1024
    current_size = context.size_bytes()

    # Early return if already within size limit
    if current_size <= max_size_bytes:
        return context

    # Record the original counts so we can report exactly what was dropped.
    original_metrics_ts_count = len(context.metrics.get("timeSeries", []))
    original_logs_count = len(context.logs.get("entries", []))
    original_changes_count = len(context.changes.get("entries", []))

    # Emit a structured WARNING before any data is discarded so ops teams can
    # observe truncation events without having to infer them from size deltas.
    logger.warning(
        json.dumps(
            {
                "message": "Context exceeds size limit, truncating",
                "correlationId": context.incident_id,
                "originalSizeBytes": current_size,
                "maxSizeBytes": max_size_bytes,
                "originalMetricsTimeSeriesCount": original_metrics_ts_count,
                "originalLogsCount": original_logs_count,
                "originalChangesCount": original_changes_count,
            }
        )
    )

    # Emit a custom CloudWatch metric so this event is visible in dashboards and
    # alarms without requiring log-metric filters.
    put_metric(
        metric_name="ContextTruncated",
        value=1.0,
        unit="Count",
        dimensions=[{"Name": "IncidentId", "Value": context.incident_id}],
    )
    # Also record the original payload size for trend analysis.
    put_metric(
        metric_name="ContextTruncatedOriginalSizeBytes",
        value=float(current_size),
        unit="Bytes",
    )

    # TRUNCATION ALGORITHM:
    # Strategy: Progressive truncation in order of data importance
    # Priority: Keep recent data (most relevant to incident)
    # Approach: Remove older 50% of data in each category until size constraint met
    # Order: metrics time series → logs → changes (least to most critical)

    # Phase 1: Truncate metrics time series (keep last 50%)
    # Metrics are least critical since summary statistics are preserved
    if "timeSeries" in context.metrics and len(context.metrics["timeSeries"]) > 10:
        half_point = len(context.metrics["timeSeries"]) // 2
        dropped = half_point
        logger.warning(
            json.dumps(
                {
                    "message": "Truncating metrics timeSeries",
                    "correlationId": context.incident_id,
                    "droppedCount": dropped,
                    "retainedCount": len(context.metrics["timeSeries"]) - half_point,
                }
            )
        )
        # Keep second half (most recent data) since list is chronologically sorted
        context.metrics["timeSeries"] = context.metrics["timeSeries"][half_point:]

        # Check if truncation was sufficient
        if context.size_bytes() <= max_size_bytes:
            _log_truncation_complete(context, max_size_bytes)
            return context

    # Phase 2: Truncate log entries (keep last 50%)
    # Logs are moderately critical - recent errors most relevant
    if "entries" in context.logs and len(context.logs["entries"]) > 10:
        half_point = len(context.logs["entries"]) // 2
        dropped = half_point
        logger.warning(
            json.dumps(
                {
                    "message": "Truncating log entries",
                    "correlationId": context.incident_id,
                    "droppedCount": dropped,
                    "retainedCount": len(context.logs["entries"]) - half_point,
                }
            )
        )
        # Keep second half (most recent logs)
        context.logs["entries"] = context.logs["entries"][half_point:]

        if context.size_bytes() <= max_size_bytes:
            _log_truncation_complete(context, max_size_bytes)
            return context

    # Phase 3: Truncate change entries (keep last 50%)
    # Changes are most critical - recent deployments often cause incidents
    if "entries" in context.changes and len(context.changes["entries"]) > 5:
        half_point = len(context.changes["entries"]) // 2
        dropped = half_point
        logger.warning(
            json.dumps(
                {
                    "message": "Truncating change entries",
                    "correlationId": context.incident_id,
                    "droppedCount": dropped,
                    "retainedCount": len(context.changes["entries"]) - half_point,
                }
            )
        )
        # Keep second half (most recent changes)
        context.changes["entries"] = context.changes["entries"][half_point:]

        if context.size_bytes() <= max_size_bytes:
            _log_truncation_complete(context, max_size_bytes)
            return context

    # Phase 4: Aggressive truncation if still over limit
    # Last resort: Keep only minimal data (10 metrics, 10 logs, 5 changes)
    if context.size_bytes() > max_size_bytes:
        logger.warning(
            json.dumps(
                {
                    "message": "Applying aggressive truncation (phase 4)",
                    "correlationId": context.incident_id,
                    "sizeBeforePhase4": context.size_bytes(),
                }
            )
        )
        # Use negative indexing to get last N entries
        if "timeSeries" in context.metrics:
            context.metrics["timeSeries"] = context.metrics["timeSeries"][-10:]
        if "entries" in context.logs:
            context.logs["entries"] = context.logs["entries"][-10:]
        if "entries" in context.changes:
            context.changes["entries"] = context.changes["entries"][-5:]

    _log_truncation_complete(context, max_size_bytes)
    return context


def _log_truncation_complete(context: Any, max_size_bytes: int) -> None:
    """Emit a final INFO log after truncation completes."""
    final_size = context.size_bytes()
    logger.info(
        json.dumps(
            {
                "message": "Context truncated to meet size constraint",
                "correlationId": context.incident_id,
                "finalSizeBytes": final_size,
                "maxSizeBytes": max_size_bytes,
                "remainingMetricsTimeSeriesCount": len(context.metrics.get("timeSeries", [])),
                "remainingLogsCount": len(context.logs.get("entries", [])),
                "remainingChangesCount": len(context.changes.get("entries", [])),
            }
        )
    )
