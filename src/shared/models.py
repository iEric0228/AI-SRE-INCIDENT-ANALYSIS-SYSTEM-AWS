"""
Data models for AI-Assisted SRE Incident Analysis System.

This module defines all data structures used throughout the incident analysis pipeline,
including incident events, collector outputs, structured context, analysis reports,
and notification outputs.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


def _serialize_timestamp(value: Any, field_name: str) -> str:
    """
    Serialize a timestamp field to an ISO-8601 string for JSON output.

    Accepts ``datetime`` objects or strings that can be parsed as ISO-8601.
    Raises ``ValueError`` for any other type so that callers receive an
    explicit, descriptive error rather than silently producing invalid output.

    Args:
        value: The timestamp value to serialize.
        field_name: Human-readable field identifier used in error messages.

    Returns:
        ISO-8601 string representation of the timestamp.

    Raises:
        ValueError: If ``value`` is neither a ``datetime`` nor a parseable
                    ISO-8601 string.
    """
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, str):
        # Validate that the string is actually parseable as ISO-8601 before
        # returning it verbatim.  fromisoformat raises ValueError on failure.
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"{field_name} contains an unparseable timestamp string: {value!r}"
            )
        return value

    raise ValueError(
        f"{field_name} must be a datetime object or a valid ISO-8601 string, "
        f"got {type(value).__name__!r}: {value!r}"
    )


class AlarmState(Enum):
    """CloudWatch Alarm states."""

    ALARM = "ALARM"
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class LogLevel(Enum):
    """Log severity levels."""

    ERROR = "ERROR"
    WARN = "WARN"
    CRITICAL = "CRITICAL"
    INFO = "INFO"


class ChangeType(Enum):
    """Types of infrastructure changes."""

    DEPLOYMENT = "deployment"
    CONFIGURATION = "configuration"
    INFRASTRUCTURE = "infrastructure"


class Confidence(Enum):
    """Analysis confidence levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class Status(Enum):
    """Operation status."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class DeliveryStatus(Enum):
    """Notification delivery status."""

    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class IncidentEvent:
    """
    Represents a CloudWatch Alarm state change event that triggers incident analysis.

    Attributes:
        incident_id: Unique identifier for the incident (UUID v4)
        alarm_name: Name of the CloudWatch Alarm
        alarm_arn: ARN of the CloudWatch Alarm
        resource_arn: ARN of the affected AWS resource
        timestamp: Time when the alarm triggered
        alarm_state: Current state of the alarm
        metric_name: Name of the metric that triggered the alarm
        namespace: CloudWatch namespace for the metric
        alarm_description: Optional description of the alarm
    """

    incident_id: str
    alarm_name: str
    alarm_arn: str
    resource_arn: str
    timestamp: datetime
    alarm_state: str
    metric_name: str
    namespace: str
    alarm_description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "incidentId": self.incident_id,
            "alarmName": self.alarm_name,
            "alarmArn": self.alarm_arn,
            "resourceArn": self.resource_arn,
            "timestamp": _serialize_timestamp(self.timestamp, "IncidentEvent.timestamp"),
            "alarmState": self.alarm_state,
            "metricName": self.metric_name,
            "namespace": self.namespace,
            "alarmDescription": self.alarm_description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IncidentEvent":
        """Create instance from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(
            incident_id=data["incidentId"],
            alarm_name=data["alarmName"],
            alarm_arn=data["alarmArn"],
            resource_arn=data["resourceArn"],
            timestamp=timestamp,
            alarm_state=data["alarmState"],
            metric_name=data["metricName"],
            namespace=data["namespace"],
            alarm_description=data.get("alarmDescription"),
        )

    def validate(self) -> bool:
        """Validate required fields are present and non-empty."""
        required_fields = [
            self.incident_id,
            self.alarm_name,
            self.alarm_arn,
            self.resource_arn,
            self.timestamp,
            self.alarm_state,
            self.metric_name,
            self.namespace,
        ]
        return all(field is not None and str(field).strip() != "" for field in required_fields)


@dataclass
class MetricDatapoint:
    """
    Represents a single metric datapoint.

    Attributes:
        timestamp: Time of the datapoint
        value: Metric value
        unit: Unit of measurement
    """

    timestamp: datetime
    value: float
    unit: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": _serialize_timestamp(self.timestamp, "MetricDatapoint.timestamp"),
            "value": self.value,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricDatapoint":
        """Create instance from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(timestamp=timestamp, value=float(data["value"]), unit=data["unit"])


@dataclass
class MetricStatistics:
    """
    Summary statistics for a metric.

    Attributes:
        avg: Average value
        max: Maximum value
        min: Minimum value
        p95: 95th percentile (optional)
    """

    avg: float
    max: float
    min: float
    p95: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"avg": self.avg, "max": self.max, "min": self.min}
        if self.p95 is not None:
            result["p95"] = self.p95
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricStatistics":
        """Create instance from dictionary."""
        return cls(
            avg=float(data["avg"]),
            max=float(data["max"]),
            min=float(data["min"]),
            p95=float(data["p95"]) if data.get("p95") is not None else None,
        )


@dataclass
class MetricData:
    """
    Represents metric data for a specific metric.

    Attributes:
        metric_name: Name of the metric
        namespace: CloudWatch namespace
        datapoints: List of metric datapoints
        statistics: Summary statistics
    """

    metric_name: str
    namespace: str
    datapoints: List[MetricDatapoint]
    statistics: MetricStatistics

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metricName": self.metric_name,
            "namespace": self.namespace,
            "datapoints": [dp.to_dict() for dp in self.datapoints],
            "statistics": self.statistics.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricData":
        """Create instance from dictionary."""
        return cls(
            metric_name=data["metricName"],
            namespace=data["namespace"],
            datapoints=[MetricDatapoint.from_dict(dp) for dp in data.get("datapoints", [])],
            statistics=MetricStatistics.from_dict(data["statistics"]),
        )


@dataclass
class MetricsCollectorOutput:
    """
    Output from the Metrics Collector Lambda.

    Attributes:
        status: Operation status
        metrics: List of collected metrics
        collection_duration: Time taken to collect metrics (seconds)
        error: Error message if collection failed
    """

    status: str
    metrics: List[MetricData]
    collection_duration: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "status": self.status,
            "metrics": [m.to_dict() for m in self.metrics],
            "collectionDuration": self.collection_duration,
        }
        if self.error is not None:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricsCollectorOutput":
        """Create instance from dictionary."""
        return cls(
            status=data["status"],
            metrics=[MetricData.from_dict(m) for m in data.get("metrics", [])],
            collection_duration=float(data["collectionDuration"]),
            error=data.get("error"),
        )

    def validate(self) -> bool:
        """Validate required fields are present."""
        return (
            self.status is not None
            and self.metrics is not None
            and self.collection_duration is not None
        )


@dataclass
class LogEntry:
    """
    Represents a single log entry.

    Attributes:
        timestamp: Time of the log entry
        log_level: Severity level
        message: Log message
        log_stream: CloudWatch Logs stream name
    """

    timestamp: datetime
    log_level: str
    message: str
    log_stream: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": _serialize_timestamp(self.timestamp, "LogEntry.timestamp"),
            "logLevel": self.log_level,
            "message": self.message,
            "logStream": self.log_stream,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEntry":
        """Create instance from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(
            timestamp=timestamp,
            log_level=data["logLevel"],
            message=data["message"],
            log_stream=data["logStream"],
        )


@dataclass
class LogsCollectorOutput:
    """
    Output from the Logs Collector Lambda.

    Attributes:
        status: Operation status
        logs: List of collected log entries
        total_matches: Total number of matching log entries
        returned: Number of log entries returned
        collection_duration: Time taken to collect logs (seconds)
        error: Error message if collection failed
    """

    status: str
    logs: List[LogEntry]
    total_matches: int
    returned: int
    collection_duration: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "status": self.status,
            "logs": [log.to_dict() for log in self.logs],
            "totalMatches": self.total_matches,
            "returned": self.returned,
            "collectionDuration": self.collection_duration,
        }
        if self.error is not None:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogsCollectorOutput":
        """Create instance from dictionary."""
        return cls(
            status=data["status"],
            logs=[LogEntry.from_dict(log) for log in data.get("logs", [])],
            total_matches=int(data["totalMatches"]),
            returned=int(data["returned"]),
            collection_duration=float(data["collectionDuration"]),
            error=data.get("error"),
        )

    def validate(self) -> bool:
        """Validate required fields are present."""
        return (
            self.status is not None
            and self.logs is not None
            and self.total_matches is not None
            and self.returned is not None
            and self.collection_duration is not None
        )


@dataclass
class ChangeEvent:
    """
    Represents an infrastructure change event.

    Attributes:
        timestamp: Time of the change
        change_type: Type of change (deployment, configuration, infrastructure)
        event_name: Name of the AWS API event
        user: ARN of the user who made the change
        description: Human-readable description of the change
    """

    timestamp: datetime
    change_type: str
    event_name: str
    user: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": _serialize_timestamp(self.timestamp, "ChangeEvent.timestamp"),
            "changeType": self.change_type,
            "eventName": self.event_name,
            "user": self.user,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeEvent":
        """Create instance from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(
            timestamp=timestamp,
            change_type=data["changeType"],
            event_name=data["eventName"],
            user=data["user"],
            description=data["description"],
        )


@dataclass
class DeployContextCollectorOutput:
    """
    Output from the Deploy Context Collector Lambda.

    Attributes:
        status: Operation status
        changes: List of change events
        collection_duration: Time taken to collect changes (seconds)
        error: Error message if collection failed
    """

    status: str
    changes: List[ChangeEvent]
    collection_duration: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "status": self.status,
            "changes": [change.to_dict() for change in self.changes],
            "collectionDuration": self.collection_duration,
        }
        if self.error is not None:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeployContextCollectorOutput":
        """Create instance from dictionary."""
        return cls(
            status=data["status"],
            changes=[ChangeEvent.from_dict(change) for change in data.get("changes", [])],
            collection_duration=float(data["collectionDuration"]),
            error=data.get("error"),
        )

    def validate(self) -> bool:
        """Validate required fields are present."""
        return (
            self.status is not None
            and self.changes is not None
            and self.collection_duration is not None
        )


@dataclass
class ResourceInfo:
    """
    Information about the affected AWS resource.

    Attributes:
        arn: Resource ARN
        type: Resource type (lambda, ec2, rds, ecs, etc.)
        name: Resource name
    """

    arn: str
    type: str
    name: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {"arn": self.arn, "type": self.type, "name": self.name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceInfo":
        """Create instance from dictionary."""
        return cls(arn=data["arn"], type=data["type"], name=data["name"])


@dataclass
class AlarmInfo:
    """
    Information about the CloudWatch Alarm.

    Attributes:
        name: Alarm name
        metric: Metric name
        threshold: Alarm threshold value
    """

    name: str
    metric: str
    threshold: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {"name": self.name, "metric": self.metric, "threshold": self.threshold}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlarmInfo":
        """Create instance from dictionary."""
        return cls(name=data["name"], metric=data["metric"], threshold=float(data["threshold"]))


@dataclass
class CompletenessInfo:
    """
    Tracks which data sources were successfully collected.

    Attributes:
        metrics: Whether metrics were collected
        logs: Whether logs were collected
        changes: Whether change events were collected
    """

    metrics: bool
    logs: bool
    changes: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {"metrics": self.metrics, "logs": self.logs, "changes": self.changes}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompletenessInfo":
        """Create instance from dictionary."""
        return cls(
            metrics=bool(data["metrics"]), logs=bool(data["logs"]), changes=bool(data["changes"])
        )


@dataclass
class StructuredContext:
    """
    Normalized and merged context from all collectors.

    Attributes:
        incident_id: Unique incident identifier
        timestamp: Incident timestamp
        resource: Resource information
        alarm: Alarm information
        metrics: Metrics data (dict format for flexibility)
        logs: Logs data (dict format for flexibility)
        changes: Changes data (dict format for flexibility)
        completeness: Data source completeness tracking
    """

    incident_id: str
    timestamp: datetime
    resource: ResourceInfo
    alarm: AlarmInfo
    metrics: Dict[str, Any]
    logs: Dict[str, Any]
    changes: Dict[str, Any]
    completeness: CompletenessInfo

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "incidentId": self.incident_id,
            "timestamp": _serialize_timestamp(self.timestamp, "StructuredContext.timestamp"),
            "resource": self.resource.to_dict(),
            "alarm": self.alarm.to_dict(),
            "metrics": self.metrics,
            "logs": self.logs,
            "changes": self.changes,
            "completeness": self.completeness.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredContext":
        """Create instance from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(
            incident_id=data["incidentId"],
            timestamp=timestamp,
            resource=ResourceInfo.from_dict(data["resource"]),
            alarm=AlarmInfo.from_dict(data["alarm"]),
            metrics=data.get("metrics", {}),
            logs=data.get("logs", {}),
            changes=data.get("changes", {}),
            completeness=CompletenessInfo.from_dict(data["completeness"]),
        )

    def size_bytes(self) -> int:
        """Calculate the size of the structured context in bytes."""
        return len(json.dumps(self.to_dict()).encode("utf-8"))

    def validate(self) -> bool:
        """Validate required fields are present."""
        return (
            self.incident_id is not None
            and self.timestamp is not None
            and self.resource is not None
            and self.alarm is not None
            and self.completeness is not None
        )


@dataclass
class AnalysisMetadata:
    """
    Metadata about the LLM analysis.

    Attributes:
        model_id: Bedrock model identifier
        model_version: Model version
        prompt_version: Prompt template version
        token_usage: Token usage statistics
        latency: Analysis latency in seconds
    """

    model_id: str
    model_version: str
    prompt_version: str
    token_usage: Dict[str, int]
    latency: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "modelId": self.model_id,
            "modelVersion": self.model_version,
            "promptVersion": self.prompt_version,
            "tokenUsage": self.token_usage,
            "latency": self.latency,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalysisMetadata":
        """Create instance from dictionary."""
        return cls(
            model_id=data["modelId"],
            model_version=data["modelVersion"],
            prompt_version=data["promptVersion"],
            token_usage=data["tokenUsage"],
            latency=float(data["latency"]),
        )


@dataclass
class Analysis:
    """
    LLM-generated incident analysis.

    Attributes:
        root_cause_hypothesis: Primary hypothesis for root cause
        confidence: Confidence level (high, medium, low, none)
        evidence: List of supporting evidence
        contributing_factors: List of contributing factors
        recommended_actions: List of recommended actions
    """

    root_cause_hypothesis: str
    confidence: str
    evidence: List[str]
    contributing_factors: List[str]
    recommended_actions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "rootCauseHypothesis": self.root_cause_hypothesis,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "contributingFactors": self.contributing_factors,
            "recommendedActions": self.recommended_actions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Analysis":
        """Create instance from dictionary."""
        return cls(
            root_cause_hypothesis=data["rootCauseHypothesis"],
            confidence=data["confidence"],
            evidence=data.get("evidence", []),
            contributing_factors=data.get("contributingFactors", []),
            recommended_actions=data.get("recommendedActions", []),
        )


@dataclass
class AnalysisReport:
    """
    Complete analysis report from LLM Analyzer.

    Attributes:
        incident_id: Unique incident identifier
        timestamp: Analysis timestamp
        analysis: Analysis content
        metadata: Analysis metadata
    """

    incident_id: str
    timestamp: datetime
    analysis: Analysis
    metadata: AnalysisMetadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "incidentId": self.incident_id,
            "timestamp": _serialize_timestamp(self.timestamp, "AnalysisReport.timestamp"),
            "analysis": self.analysis.to_dict(),
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnalysisReport":
        """Create instance from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(
            incident_id=data["incidentId"],
            timestamp=timestamp,
            analysis=Analysis.from_dict(data["analysis"]),
            metadata=AnalysisMetadata.from_dict(data["metadata"]),
        )

    def validate(self) -> bool:
        """Validate required fields are present."""
        return (
            self.incident_id is not None
            and self.timestamp is not None
            and self.analysis is not None
            and self.metadata is not None
        )


@dataclass
class NotificationDeliveryStatus:
    """
    Delivery status for notification channels.

    Attributes:
        slack: Slack delivery status
        email: Email delivery status
        slack_error: Slack error message if delivery failed
        email_error: Email error message if delivery failed
    """

    slack: str
    email: str
    slack_error: Optional[str] = None
    email_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"slack": self.slack, "email": self.email}
        if self.slack_error is not None:
            result["slackError"] = self.slack_error
        if self.email_error is not None:
            result["emailError"] = self.email_error
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationDeliveryStatus":
        """Create instance from dictionary."""
        return cls(
            slack=data["slack"],
            email=data["email"],
            slack_error=data.get("slackError"),
            email_error=data.get("emailError"),
        )


@dataclass
class NotificationOutput:
    """
    Output from the Notification Service Lambda.

    Attributes:
        status: Overall notification status
        delivery_status: Per-channel delivery status
        notification_duration: Time taken to send notifications (seconds)
    """

    status: str
    delivery_status: NotificationDeliveryStatus
    notification_duration: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "deliveryStatus": self.delivery_status.to_dict(),
            "notificationDuration": self.notification_duration,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationOutput":
        """Create instance from dictionary."""
        return cls(
            status=data["status"],
            delivery_status=NotificationDeliveryStatus.from_dict(data["deliveryStatus"]),
            notification_duration=float(data["notificationDuration"]),
        )

    def validate(self) -> bool:
        """Validate required fields are present."""
        return (
            self.status is not None
            and self.delivery_status is not None
            and self.notification_duration is not None
        )


@dataclass
class IncidentRecord:
    """
    Complete incident record for DynamoDB storage.

    Attributes:
        incident_id: Unique incident identifier (partition key)
        timestamp: Incident timestamp (sort key, ISO-8601 string)
        resource_arn: ARN of affected resource
        resource_type: Type of resource
        alarm_name: Name of the alarm
        severity: Incident severity (critical, high, medium, low)
        structured_context: Complete structured context
        analysis_report: Complete analysis report
        notification_status: Notification delivery status
        ttl: TTL for automatic deletion (Unix timestamp)
    """

    incident_id: str
    timestamp: str
    resource_arn: str
    resource_type: str
    alarm_name: str
    severity: str
    structured_context: Dict[str, Any]
    analysis_report: Dict[str, Any]
    notification_status: Dict[str, Any]
    ttl: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "incidentId": self.incident_id,
            "timestamp": self.timestamp,
            "resourceArn": self.resource_arn,
            "resourceType": self.resource_type,
            "alarmName": self.alarm_name,
            "severity": self.severity,
            "structuredContext": self.structured_context,
            "analysisReport": self.analysis_report,
            "notificationStatus": self.notification_status,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IncidentRecord":
        """Create instance from dictionary."""
        return cls(
            incident_id=data["incidentId"],
            timestamp=data["timestamp"],
            resource_arn=data["resourceArn"],
            resource_type=data["resourceType"],
            alarm_name=data["alarmName"],
            severity=data["severity"],
            structured_context=data["structuredContext"],
            analysis_report=data["analysisReport"],
            notification_status=data["notificationStatus"],
            ttl=int(data["ttl"]),
        )

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "incidentId": {"S": self.incident_id},
            "timestamp": {"S": self.timestamp},
            "resourceArn": {"S": self.resource_arn},
            "resourceType": {"S": self.resource_type},
            "alarmName": {"S": self.alarm_name},
            "severity": {"S": self.severity},
            "structuredContext": {"S": json.dumps(self.structured_context)},
            "analysisReport": {"S": json.dumps(self.analysis_report)},
            "notificationStatus": {"S": json.dumps(self.notification_status)},
            "ttl": {"N": str(self.ttl)},
        }

    def validate(self) -> bool:
        """Validate required fields are present."""
        required_fields = [
            self.incident_id,
            self.timestamp,
            self.resource_arn,
            self.resource_type,
            self.alarm_name,
            self.severity,
        ]
        return all(field is not None and str(field).strip() != "" for field in required_fields)
