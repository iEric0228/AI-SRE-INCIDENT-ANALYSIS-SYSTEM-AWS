"""
Unit tests for data models.

Tests serialization, deserialization, and validation of all data models.
"""

from datetime import datetime

import pytest

from shared.models import (
    AlarmInfo,
    Analysis,
    AnalysisMetadata,
    AnalysisReport,
    ChangeEvent,
    CompletenessInfo,
    DeployContextCollectorOutput,
    IncidentEvent,
    IncidentRecord,
    LogEntry,
    LogsCollectorOutput,
    MetricData,
    MetricDatapoint,
    MetricsCollectorOutput,
    MetricStatistics,
    NotificationDeliveryStatus,
    NotificationOutput,
    ResourceInfo,
    StructuredContext,
    _serialize_timestamp,
)


class TestIncidentEvent:
    """Test IncidentEvent model."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            alarm_description="CPU above 80%",
        )

        result = event.to_dict()

        assert result["incidentId"] == "test-123"
        assert result["alarmName"] == "HighCPU"
        assert result["alarmState"] == "ALARM"
        assert "2024-01-15" in result["timestamp"]

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "incidentId": "test-123",
            "alarmName": "HighCPU",
            "alarmArn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "timestamp": "2024-01-15T14:30:00Z",
            "alarmState": "ALARM",
            "metricName": "CPUUtilization",
            "namespace": "AWS/EC2",
            "alarmDescription": "CPU above 80%",
        }

        event = IncidentEvent.from_dict(data)

        assert event.incident_id == "test-123"
        assert event.alarm_name == "HighCPU"
        assert isinstance(event.timestamp, datetime)

    def test_validate_success(self):
        """Test validation with valid data."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )

        assert event.validate() is True

    def test_validate_failure(self):
        """Test validation with missing required field."""
        event = IncidentEvent(
            incident_id="",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )

        assert event.validate() is False


class TestMetricsCollectorOutput:
    """Test MetricsCollectorOutput model."""

    def test_serialization_round_trip(self):
        """Test that serialization and deserialization produce equivalent object."""
        statistics = MetricStatistics(avg=75.5, max=95.0, min=60.0, p95=90.0)
        datapoint = MetricDatapoint(
            timestamp=datetime(2024, 1, 15, 14, 30, 0), value=85.5, unit="Percent"
        )
        metric = MetricData(
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            datapoints=[datapoint],
            statistics=statistics,
        )
        output = MetricsCollectorOutput(status="success", metrics=[metric], collection_duration=1.5)

        # Serialize and deserialize
        data = output.to_dict()
        restored = MetricsCollectorOutput.from_dict(data)

        assert restored.status == output.status
        assert restored.collection_duration == output.collection_duration
        assert len(restored.metrics) == len(output.metrics)
        assert restored.metrics[0].metric_name == output.metrics[0].metric_name

    def test_validate(self):
        """Test validation method."""
        output = MetricsCollectorOutput(status="success", metrics=[], collection_duration=1.5)

        assert output.validate() is True


class TestStructuredContext:
    """Test StructuredContext model."""

    def test_size_bytes(self):
        """Test size calculation."""
        context = StructuredContext(
            incident_id="test-123",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            resource=ResourceInfo(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                type="ec2",
                name="web-server-1",
            ),
            alarm=AlarmInfo(name="HighCPU", metric="CPUUtilization", threshold=80.0),
            metrics={"summary": {"avg": 75.5}},
            logs={"errorCount": 10},
            changes={"recentDeployments": 1},
            completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
        )

        size = context.size_bytes()

        assert size > 0
        assert isinstance(size, int)

    def test_serialization_round_trip(self):
        """Test that serialization and deserialization produce equivalent object."""
        context = StructuredContext(
            incident_id="test-123",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            resource=ResourceInfo(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                type="ec2",
                name="web-server-1",
            ),
            alarm=AlarmInfo(name="HighCPU", metric="CPUUtilization", threshold=80.0),
            metrics={"summary": {"avg": 75.5}},
            logs={"errorCount": 10},
            changes={"recentDeployments": 1},
            completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
        )

        # Serialize and deserialize
        data = context.to_dict()
        restored = StructuredContext.from_dict(data)

        assert restored.incident_id == context.incident_id
        assert restored.resource.arn == context.resource.arn
        assert restored.alarm.name == context.alarm.name
        assert restored.completeness.metrics == context.completeness.metrics


class TestAnalysisReport:
    """Test AnalysisReport model."""

    def test_serialization_round_trip(self):
        """Test that serialization and deserialization produce equivalent object."""
        report = AnalysisReport(
            incident_id="test-123",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            analysis=Analysis(
                root_cause_hypothesis="High CPU due to memory leak",
                confidence="high",
                evidence=["CPU increased after deployment", "Memory usage at 95%"],
                contributing_factors=["Peak traffic hours"],
                recommended_actions=["Rollback deployment", "Increase memory"],
            ),
            metadata=AnalysisMetadata(
                model_id="anthropic.claude-v2",
                model_version="2.1",
                prompt_version="v1.0",
                token_usage={"input": 1500, "output": 300},
                latency=2.5,
            ),
        )

        # Serialize and deserialize
        data = report.to_dict()
        restored = AnalysisReport.from_dict(data)

        assert restored.incident_id == report.incident_id
        assert restored.analysis.root_cause_hypothesis == report.analysis.root_cause_hypothesis
        assert restored.analysis.confidence == report.analysis.confidence
        assert restored.metadata.model_id == report.metadata.model_id

    def test_validate(self):
        """Test validation method."""
        report = AnalysisReport(
            incident_id="test-123",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            analysis=Analysis(
                root_cause_hypothesis="Test hypothesis",
                confidence="high",
                evidence=[],
                contributing_factors=[],
                recommended_actions=[],
            ),
            metadata=AnalysisMetadata(
                model_id="anthropic.claude-v2",
                model_version="2.1",
                prompt_version="v1.0",
                token_usage={"input": 1500, "output": 300},
                latency=2.5,
            ),
        )

        assert report.validate() is True


class TestNotificationOutput:
    """Test NotificationOutput model."""

    def test_serialization_round_trip(self):
        """Test that serialization and deserialization produce equivalent object."""
        output = NotificationOutput(
            status="success",
            delivery_status=NotificationDeliveryStatus(slack="delivered", email="delivered"),
            notification_duration=1.8,
        )

        # Serialize and deserialize
        data = output.to_dict()
        restored = NotificationOutput.from_dict(data)

        assert restored.status == output.status
        assert restored.delivery_status.slack == output.delivery_status.slack
        assert restored.delivery_status.email == output.delivery_status.email
        assert restored.notification_duration == output.notification_duration

    def test_validate(self):
        """Test validation method."""
        output = NotificationOutput(
            status="success",
            delivery_status=NotificationDeliveryStatus(slack="delivered", email="delivered"),
            notification_duration=1.8,
        )

        assert output.validate() is True


class TestIncidentRecord:
    """Test IncidentRecord model."""

    def test_to_dynamodb_item(self):
        """Test conversion to DynamoDB item format."""
        record = IncidentRecord(
            incident_id="test-123",
            timestamp="2024-01-15T14:30:00Z",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="ec2",
            alarm_name="HighCPU",
            severity="high",
            structured_context={"test": "data"},
            analysis_report={"test": "report"},
            notification_status={"test": "status"},
            ttl=1705334400,
        )

        item = record.to_dynamodb_item()

        assert item["incidentId"]["S"] == "test-123"
        assert item["timestamp"]["S"] == "2024-01-15T14:30:00Z"
        assert (
            item["resourceArn"]["S"]
            == "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        )
        assert item["severity"]["S"] == "high"
        assert item["ttl"]["N"] == "1705334400"

    def test_validate(self):
        """Test validation method."""
        record = IncidentRecord(
            incident_id="test-123",
            timestamp="2024-01-15T14:30:00Z",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="ec2",
            alarm_name="HighCPU",
            severity="high",
            structured_context={},
            analysis_report={},
            notification_status={},
            ttl=1705334400,
        )

        assert record.validate() is True


# ============================================================================
# Validation Tests - Required Field Validation
# ============================================================================


class TestRequiredFieldValidation:
    """Test required field validation for all models."""

    def test_incident_event_missing_incident_id(self):
        """Test IncidentEvent validation fails with empty incident_id."""
        event = IncidentEvent(
            incident_id="",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        assert event.validate() is False

    def test_incident_event_missing_alarm_name(self):
        """Test IncidentEvent validation fails with empty alarm_name."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        assert event.validate() is False

    def test_incident_event_missing_resource_arn(self):
        """Test IncidentEvent validation fails with empty resource_arn."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        assert event.validate() is False

    def test_incident_event_none_timestamp(self):
        """Test IncidentEvent validation fails with None timestamp."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=None,
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        assert event.validate() is False

    def test_incident_record_missing_incident_id(self):
        """Test IncidentRecord validation fails with empty incident_id."""
        record = IncidentRecord(
            incident_id="",
            timestamp="2024-01-15T14:30:00Z",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="ec2",
            alarm_name="HighCPU",
            severity="high",
            structured_context={},
            analysis_report={},
            notification_status={},
            ttl=1705334400,
        )
        assert record.validate() is False

    def test_incident_record_missing_timestamp(self):
        """Test IncidentRecord validation fails with empty timestamp."""
        record = IncidentRecord(
            incident_id="test-123",
            timestamp="",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="ec2",
            alarm_name="HighCPU",
            severity="high",
            structured_context={},
            analysis_report={},
            notification_status={},
            ttl=1705334400,
        )
        assert record.validate() is False

    def test_incident_record_missing_severity(self):
        """Test IncidentRecord validation fails with empty severity."""
        record = IncidentRecord(
            incident_id="test-123",
            timestamp="2024-01-15T14:30:00Z",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="ec2",
            alarm_name="HighCPU",
            severity="",
            structured_context={},
            analysis_report={},
            notification_status={},
            ttl=1705334400,
        )
        assert record.validate() is False

    def test_structured_context_none_incident_id(self):
        """Test StructuredContext validation fails with None incident_id."""
        context = StructuredContext(
            incident_id=None,
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            resource=ResourceInfo(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                type="ec2",
                name="web-server-1",
            ),
            alarm=AlarmInfo(name="HighCPU", metric="CPUUtilization", threshold=80.0),
            metrics={},
            logs={},
            changes={},
            completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
        )
        assert context.validate() is False

    def test_structured_context_none_resource(self):
        """Test StructuredContext validation fails with None resource."""
        context = StructuredContext(
            incident_id="test-123",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            resource=None,
            alarm=AlarmInfo(name="HighCPU", metric="CPUUtilization", threshold=80.0),
            metrics={},
            logs={},
            changes={},
            completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
        )
        assert context.validate() is False

    def test_analysis_report_none_incident_id(self):
        """Test AnalysisReport validation fails with None incident_id."""
        report = AnalysisReport(
            incident_id=None,
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            analysis=Analysis(
                root_cause_hypothesis="Test hypothesis",
                confidence="high",
                evidence=[],
                contributing_factors=[],
                recommended_actions=[],
            ),
            metadata=AnalysisMetadata(
                model_id="anthropic.claude-v2",
                model_version="2.1",
                prompt_version="v1.0",
                token_usage={"input": 1500, "output": 300},
                latency=2.5,
            ),
        )
        assert report.validate() is False

    def test_analysis_report_none_analysis(self):
        """Test AnalysisReport validation fails with None analysis."""
        report = AnalysisReport(
            incident_id="test-123",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            analysis=None,
            metadata=AnalysisMetadata(
                model_id="anthropic.claude-v2",
                model_version="2.1",
                prompt_version="v1.0",
                token_usage={"input": 1500, "output": 300},
                latency=2.5,
            ),
        )
        assert report.validate() is False


# ============================================================================
# Validation Tests - Invalid Field Types
# ============================================================================


class TestInvalidFieldTypes:
    """Test handling of invalid field types."""

    def test_metric_statistics_invalid_avg_type(self):
        """Test MetricStatistics handles non-numeric avg value."""
        with pytest.raises((ValueError, TypeError)):
            MetricStatistics.from_dict({"avg": "not-a-number", "max": 95.0, "min": 60.0})

    def test_metric_statistics_invalid_max_type(self):
        """Test MetricStatistics handles non-numeric max value."""
        with pytest.raises((ValueError, TypeError)):
            MetricStatistics.from_dict({"avg": 75.5, "max": "not-a-number", "min": 60.0})

    def test_metrics_collector_output_invalid_duration_type(self):
        """Test MetricsCollectorOutput handles non-numeric duration."""
        with pytest.raises((ValueError, TypeError)):
            MetricsCollectorOutput.from_dict(
                {"status": "success", "metrics": [], "collectionDuration": "not-a-number"}
            )

    def test_logs_collector_output_invalid_total_matches_type(self):
        """Test LogsCollectorOutput handles non-integer total_matches."""
        with pytest.raises((ValueError, TypeError)):
            LogsCollectorOutput.from_dict(
                {
                    "status": "success",
                    "logs": [],
                    "totalMatches": "not-a-number",
                    "returned": 0,
                    "collectionDuration": 1.5,
                }
            )

    def test_alarm_info_invalid_threshold_type(self):
        """Test AlarmInfo handles non-numeric threshold."""
        with pytest.raises((ValueError, TypeError)):
            AlarmInfo.from_dict(
                {"name": "HighCPU", "metric": "CPUUtilization", "threshold": "not-a-number"}
            )

    def test_analysis_metadata_invalid_latency_type(self):
        """Test AnalysisMetadata handles non-numeric latency."""
        with pytest.raises((ValueError, TypeError)):
            AnalysisMetadata.from_dict(
                {
                    "modelId": "anthropic.claude-v2",
                    "modelVersion": "2.1",
                    "promptVersion": "v1.0",
                    "tokenUsage": {"input": 1500, "output": 300},
                    "latency": "not-a-number",
                }
            )

    def test_notification_output_invalid_duration_type(self):
        """Test NotificationOutput handles non-numeric duration."""
        with pytest.raises((ValueError, TypeError)):
            NotificationOutput.from_dict(
                {
                    "status": "success",
                    "deliveryStatus": {"slack": "delivered", "email": "delivered"},
                    "notificationDuration": "not-a-number",
                }
            )

    def test_incident_record_invalid_ttl_type(self):
        """Test IncidentRecord handles non-integer ttl."""
        with pytest.raises((ValueError, TypeError)):
            IncidentRecord.from_dict(
                {
                    "incidentId": "test-123",
                    "timestamp": "2024-01-15T14:30:00Z",
                    "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                    "resourceType": "ec2",
                    "alarmName": "HighCPU",
                    "severity": "high",
                    "structuredContext": {},
                    "analysisReport": {},
                    "notificationStatus": {},
                    "ttl": "not-a-number",
                }
            )


# ============================================================================
# Validation Tests - Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases for data models."""

    def test_incident_event_whitespace_only_incident_id(self):
        """Test IncidentEvent validation fails with whitespace-only incident_id."""
        event = IncidentEvent(
            incident_id="   ",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        assert event.validate() is False

    def test_incident_event_whitespace_only_alarm_name(self):
        """Test IncidentEvent validation fails with whitespace-only alarm_name."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="   ",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        assert event.validate() is False

    def test_metrics_collector_output_empty_metrics_list(self):
        """Test MetricsCollectorOutput with empty metrics list is valid."""
        output = MetricsCollectorOutput(status="success", metrics=[], collection_duration=1.5)
        assert output.validate() is True

    def test_logs_collector_output_empty_logs_list(self):
        """Test LogsCollectorOutput with empty logs list is valid."""
        output = LogsCollectorOutput(
            status="success", logs=[], total_matches=0, returned=0, collection_duration=1.5
        )
        assert output.validate() is True

    def test_deploy_context_collector_output_empty_changes_list(self):
        """Test DeployContextCollectorOutput with empty changes list is valid."""
        output = DeployContextCollectorOutput(status="success", changes=[], collection_duration=1.5)
        assert output.validate() is True

    def test_structured_context_empty_metrics_dict(self):
        """Test StructuredContext with empty metrics dict is valid."""
        context = StructuredContext(
            incident_id="test-123",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            resource=ResourceInfo(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                type="ec2",
                name="web-server-1",
            ),
            alarm=AlarmInfo(name="HighCPU", metric="CPUUtilization", threshold=80.0),
            metrics={},
            logs={},
            changes={},
            completeness=CompletenessInfo(metrics=False, logs=False, changes=False),
        )
        assert context.validate() is True

    def test_analysis_empty_evidence_list(self):
        """Test Analysis with empty evidence list is valid."""
        analysis = Analysis(
            root_cause_hypothesis="Test hypothesis",
            confidence="low",
            evidence=[],
            contributing_factors=[],
            recommended_actions=[],
        )
        # Analysis doesn't have validate method, but should serialize correctly
        data = analysis.to_dict()
        assert data["evidence"] == []
        assert data["contributingFactors"] == []
        assert data["recommendedActions"] == []

    def test_metrics_collector_output_none_error(self):
        """Test MetricsCollectorOutput with None error is valid."""
        output = MetricsCollectorOutput(
            status="success", metrics=[], collection_duration=1.5, error=None
        )
        assert output.validate() is True
        data = output.to_dict()
        assert "error" not in data

    def test_logs_collector_output_with_error(self):
        """Test LogsCollectorOutput with error message."""
        output = LogsCollectorOutput(
            status="failed",
            logs=[],
            total_matches=0,
            returned=0,
            collection_duration=1.5,
            error="Log group not found",
        )
        assert output.validate() is True
        data = output.to_dict()
        assert data["error"] == "Log group not found"

    def test_deploy_context_collector_output_with_error(self):
        """Test DeployContextCollectorOutput with error message."""
        output = DeployContextCollectorOutput(
            status="failed", changes=[], collection_duration=1.5, error="CloudTrail not enabled"
        )
        assert output.validate() is True
        data = output.to_dict()
        assert data["error"] == "CloudTrail not enabled"

    def test_notification_delivery_status_none_errors(self):
        """Test NotificationDeliveryStatus with None error fields."""
        status = NotificationDeliveryStatus(
            slack="delivered", email="delivered", slack_error=None, email_error=None
        )
        data = status.to_dict()
        assert "slackError" not in data
        assert "emailError" not in data

    def test_notification_delivery_status_with_errors(self):
        """Test NotificationDeliveryStatus with error messages."""
        status = NotificationDeliveryStatus(
            slack="failed", email="delivered", slack_error="Webhook timeout", email_error=None
        )
        data = status.to_dict()
        assert data["slackError"] == "Webhook timeout"
        assert "emailError" not in data

    def test_metric_statistics_none_p95(self):
        """Test MetricStatistics with None p95 value."""
        stats = MetricStatistics(avg=75.5, max=95.0, min=60.0, p95=None)
        data = stats.to_dict()
        assert "p95" not in data

    def test_metric_statistics_with_p95(self):
        """Test MetricStatistics with p95 value."""
        stats = MetricStatistics(avg=75.5, max=95.0, min=60.0, p95=90.0)
        data = stats.to_dict()
        assert data["p95"] == 90.0

    def test_incident_event_none_alarm_description(self):
        """Test IncidentEvent with None alarm_description is valid."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=datetime(2024, 1, 15, 14, 30, 0),
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            alarm_description=None,
        )
        assert event.validate() is True
        data = event.to_dict()
        assert data["alarmDescription"] is None

    def test_incident_record_whitespace_only_severity(self):
        """Test IncidentRecord validation fails with whitespace-only severity."""
        record = IncidentRecord(
            incident_id="test-123",
            timestamp="2024-01-15T14:30:00Z",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="ec2",
            alarm_name="HighCPU",
            severity="   ",
            structured_context={},
            analysis_report={},
            notification_status={},
            ttl=1705334400,
        )
        assert record.validate() is False


# ============================================================================
# Timestamp Type Guard Tests
# ============================================================================


class TestSerializeTimestamp:
    """Tests for the _serialize_timestamp helper (Fix 6: timestamp type guards)."""

    def test_datetime_object_serialized_to_isoformat(self):
        """datetime objects should be converted to ISO-8601 strings."""
        ts = datetime(2024, 1, 15, 14, 30, 0)
        result = _serialize_timestamp(ts, "test.field")
        assert result == "2024-01-15T14:30:00"

    def test_valid_iso_string_returned_unchanged(self):
        """Valid ISO-8601 strings should pass through unchanged."""
        iso = "2024-01-15T14:30:00Z"
        result = _serialize_timestamp(iso, "test.field")
        assert result == iso

    def test_valid_iso_string_with_offset_returned_unchanged(self):
        """Valid ISO-8601 string with UTC offset should pass through."""
        iso = "2024-01-15T14:30:00+00:00"
        result = _serialize_timestamp(iso, "test.field")
        assert result == iso

    def test_invalid_string_raises_value_error(self):
        """Non-ISO string should raise ValueError with the field name in the message."""
        with pytest.raises(ValueError) as exc_info:
            _serialize_timestamp("not-a-timestamp", "IncidentEvent.timestamp")
        assert "IncidentEvent.timestamp" in str(exc_info.value)
        assert "not-a-timestamp" in str(exc_info.value)

    def test_integer_raises_value_error(self):
        """An integer (Unix epoch) should raise ValueError rather than silently coercing."""
        with pytest.raises(ValueError) as exc_info:
            _serialize_timestamp(1705334400, "MetricDatapoint.timestamp")
        assert "MetricDatapoint.timestamp" in str(exc_info.value)
        assert "int" in str(exc_info.value)

    def test_none_raises_value_error(self):
        """None should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _serialize_timestamp(None, "ChangeEvent.timestamp")
        assert "ChangeEvent.timestamp" in str(exc_info.value)

    def test_dict_raises_value_error(self):
        """A dict should raise ValueError."""
        with pytest.raises(ValueError):
            _serialize_timestamp({"ts": "2024-01-15"}, "LogEntry.timestamp")


class TestTimestampTypeGuardsInModels:
    """Integration tests: to_dict() raises ValueError for invalid timestamp types."""

    def test_incident_event_to_dict_invalid_timestamp_raises(self):
        """IncidentEvent.to_dict() should raise ValueError for non-datetime/string timestamp."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=99999,  # invalid type
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        with pytest.raises(ValueError) as exc_info:
            event.to_dict()
        assert "IncidentEvent.timestamp" in str(exc_info.value)

    def test_metric_datapoint_to_dict_invalid_timestamp_raises(self):
        """MetricDatapoint.to_dict() should raise ValueError for invalid timestamp type."""
        dp = MetricDatapoint(timestamp={"bad": "value"}, value=75.0, unit="Percent")
        with pytest.raises(ValueError) as exc_info:
            dp.to_dict()
        assert "MetricDatapoint.timestamp" in str(exc_info.value)

    def test_log_entry_to_dict_invalid_timestamp_raises(self):
        """LogEntry.to_dict() should raise ValueError for invalid timestamp type."""
        entry = LogEntry(
            timestamp=None, log_level="ERROR", message="test", log_stream="stream"
        )
        with pytest.raises(ValueError) as exc_info:
            entry.to_dict()
        assert "LogEntry.timestamp" in str(exc_info.value)

    def test_change_event_to_dict_invalid_timestamp_raises(self):
        """ChangeEvent.to_dict() should raise ValueError for invalid timestamp type."""
        change = ChangeEvent(
            timestamp=3.14,
            change_type="deployment",
            event_name="UpdateFunctionCode",
            user="deployer",
            description="test",
        )
        with pytest.raises(ValueError) as exc_info:
            change.to_dict()
        assert "ChangeEvent.timestamp" in str(exc_info.value)

    def test_incident_event_to_dict_valid_string_timestamp(self):
        """IncidentEvent.to_dict() should accept a valid ISO string timestamp."""
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp="2024-01-15T14:30:00Z",  # valid ISO string
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        result = event.to_dict()
        assert result["timestamp"] == "2024-01-15T14:30:00Z"

    def test_incident_event_to_dict_valid_datetime_timestamp(self):
        """IncidentEvent.to_dict() should accept a datetime timestamp."""
        ts = datetime(2024, 1, 15, 14, 30, 0)
        event = IncidentEvent(
            incident_id="test-123",
            alarm_name="HighCPU",
            alarm_arn="arn:aws:cloudwatch:us-east-1:123456789012:alarm:HighCPU",
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            timestamp=ts,
            alarm_state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
        )
        result = event.to_dict()
        assert "2024-01-15" in result["timestamp"]
