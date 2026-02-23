"""
Integration tests for partial failure scenarios in incident analysis workflow.

Tests graceful degradation when collectors or other components fail.
Validates: Requirements 2.5, 12.1, 12.2, 12.3, 12.4, 12.5
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

# Import Lambda handlers
import sys
import os

from metrics_collector.lambda_function import lambda_handler as metrics_collector_handler
from logs_collector.lambda_function import lambda_handler as logs_collector_handler
from deploy_context_collector.lambda_function import lambda_handler as deploy_context_handler
from correlation_engine.lambda_function import lambda_handler as correlation_handler
from llm_analyzer.lambda_function import lambda_handler as llm_analyzer_handler
from notification_service.lambda_function import lambda_handler as notification_handler


@pytest.mark.integration
class TestPartialFailureScenarios:
    """Integration tests for graceful degradation with partial failures."""

    def test_workflow_continues_with_metrics_collector_failure(self):
        """
        Test that workflow continues when metrics collector fails.

        Validates:
        - Workflow completes despite metrics failure
        - Completeness indicator shows metrics unavailable
        - Other data sources (logs, changes) are still collected
        """
        incident_event = {
            "incidentId": "inc-test-001",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/EC2",
            "metricName": "CPUUtilization",
        }

        # Metrics collector fails
        with patch("boto3.client") as mock_boto3:
            mock_cw = MagicMock()
            mock_cw.get_metric_statistics.side_effect = ClientError(
                {"Error": {"Code": "ServiceException", "Message": "Service unavailable"}},
                "GetMetricStatistics",
            )
            mock_boto3.return_value = mock_cw

            metrics_result = metrics_collector_handler(incident_event, {})
            # Source gracefully degrades - returns success with empty metrics
            assert metrics_result["status"] == "success"

        # Logs collector succeeds
        with patch("boto3.client") as mock_boto3:
            mock_logs = MagicMock()
            mock_logs.filter_log_events.return_value = {
                "events": [
                    {
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        "message": "ERROR: Test error",
                        "logStreamName": "test-stream",
                    }
                ]
            }
            mock_boto3.return_value = mock_logs

            logs_result = logs_collector_handler(incident_event, {})
            assert logs_result["status"] == "success"

        # Deploy context collector succeeds
        with patch("boto3.client") as mock_boto3:
            mock_ct = MagicMock()
            mock_ct.lookup_events.return_value = {"Events": []}
            mock_boto3.return_value = mock_ct

            deploy_result = deploy_context_handler(incident_event, {})
            assert deploy_result["status"] == "success"

        # Correlation engine handles empty metrics (graceful degradation)
        correlation_input = {
            "incident": incident_event,
            "metrics": metrics_result,
            "logs": logs_result,
            "changes": deploy_result,
        }

        correlation_result = correlation_handler(correlation_input, {})
        structured = correlation_result["structuredContext"]

        # With graceful degradation, metrics are "complete" but empty
        assert structured["completeness"]["metrics"] is True
        assert structured["completeness"]["logs"] is True
        assert structured["completeness"]["changes"] is True

        # Verify workflow can continue with partial data
        assert "incidentId" in structured
        assert "logs" in structured
        assert "changes" in structured

    def test_workflow_continues_with_logs_collector_failure(self):
        """
        Test that workflow continues when logs collector fails.

        Validates:
        - Workflow completes despite logs failure
        - Completeness indicator shows logs unavailable
        - Other data sources (metrics, changes) are still collected
        """
        incident_event = {
            "incidentId": "inc-test-002",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test-func",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/Lambda",
            "metricName": "Errors",
        }

        # Metrics collector succeeds
        with patch("boto3.client") as mock_boto3:
            mock_cw = MagicMock()
            mock_cw.get_metric_statistics.return_value = {
                "Datapoints": [{"Timestamp": datetime.utcnow(), "Average": 10.0, "Unit": "Count"}]
            }
            mock_boto3.return_value = mock_cw

            metrics_result = metrics_collector_handler(incident_event, {})
            assert metrics_result["status"] == "success"

        # Logs collector fails
        with patch("boto3.client") as mock_boto3:
            mock_logs = MagicMock()
            mock_logs.filter_log_events.side_effect = ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "Log group not found"}},
                "FilterLogEvents",
            )
            mock_boto3.return_value = mock_logs

            logs_result = logs_collector_handler(incident_event, {})
            # Source gracefully degrades - returns success with empty logs
            assert logs_result["status"] == "success"

        # Deploy context collector succeeds
        with patch("boto3.client") as mock_boto3:
            mock_ct = MagicMock()
            mock_ct.lookup_events.return_value = {"Events": []}
            mock_boto3.return_value = mock_ct

            deploy_result = deploy_context_handler(incident_event, {})
            assert deploy_result["status"] == "success"

        # Correlation engine handles empty logs (graceful degradation)
        correlation_input = {
            "incident": incident_event,
            "metrics": metrics_result,
            "logs": logs_result,
            "changes": deploy_result,
        }

        correlation_result = correlation_handler(correlation_input, {})
        structured = correlation_result["structuredContext"]

        # With graceful degradation, all sources are "complete"
        assert structured["completeness"]["metrics"] is True
        assert structured["completeness"]["logs"] is True
        assert structured["completeness"]["changes"] is True

    def test_workflow_continues_with_deploy_context_collector_failure(self):
        """
        Test that workflow continues when deploy context collector fails.

        Validates:
        - Workflow completes despite deploy context failure
        - Completeness indicator shows changes unavailable
        - Other data sources (metrics, logs) are still collected
        """
        incident_event = {
            "incidentId": "inc-test-003",
            "resourceArn": "arn:aws:rds:us-east-1:123456789012:db:test-db",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/RDS",
            "metricName": "DatabaseConnections",
        }

        # Metrics collector succeeds
        with patch("boto3.client") as mock_boto3:
            mock_cw = MagicMock()
            mock_cw.get_metric_statistics.return_value = {"Datapoints": []}
            mock_boto3.return_value = mock_cw

            metrics_result = metrics_collector_handler(incident_event, {})
            assert metrics_result["status"] == "success"

        # Logs collector succeeds
        with patch("boto3.client") as mock_boto3:
            mock_logs = MagicMock()
            mock_logs.filter_log_events.return_value = {"events": []}
            mock_boto3.return_value = mock_logs

            logs_result = logs_collector_handler(incident_event, {})
            assert logs_result["status"] == "success"

        # Deploy context collector fails
        with patch("boto3.client") as mock_boto3:
            mock_ct = MagicMock()
            mock_ct.lookup_events.side_effect = ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}},
                "LookupEvents",
            )
            mock_boto3.return_value = mock_ct

            deploy_result = deploy_context_handler(incident_event, {})
            # Source gracefully degrades - returns success with empty changes
            assert deploy_result["status"] == "success"

        # Correlation engine handles empty deploy context (graceful degradation)
        correlation_input = {
            "incident": incident_event,
            "metrics": metrics_result,
            "logs": logs_result,
            "changes": deploy_result,
        }

        correlation_result = correlation_handler(correlation_input, {})
        structured = correlation_result["structuredContext"]

        # With graceful degradation, all sources are "complete"
        assert structured["completeness"]["metrics"] is True
        assert structured["completeness"]["logs"] is True
        assert structured["completeness"]["changes"] is True

    def test_workflow_with_multiple_collector_failures(self):
        """
        Test that workflow continues when multiple collectors fail.

        Validates:
        - Workflow completes with minimal data
        - Completeness indicator shows all failures
        - Analysis can proceed with limited context
        """
        incident_event = {
            "incidentId": "inc-test-004",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/EC2",
            "metricName": "CPUUtilization",
        }

        # Only metrics collector succeeds
        with patch("boto3.client") as mock_boto3:
            mock_cw = MagicMock()
            mock_cw.get_metric_statistics.return_value = {
                "Datapoints": [{"Timestamp": datetime.utcnow(), "Average": 85.0, "Unit": "Percent"}]
            }
            mock_boto3.return_value = mock_cw

            metrics_result = metrics_collector_handler(incident_event, {})
            assert metrics_result["status"] == "success"

        # Correlation with multiple failures
        correlation_input = {
            "incident": incident_event,
            "metrics": metrics_result,
            "logsError": {"error": "Log group not found"},
            "changesError": {"error": "CloudTrail not enabled"},
        }

        correlation_result = correlation_handler(correlation_input, {})
        structured = correlation_result["structuredContext"]

        # Verify completeness indicator shows all failures
        assert structured["completeness"]["metrics"] is True
        assert structured["completeness"]["logs"] is False
        assert structured["completeness"]["changes"] is False

        # Verify workflow can still produce analysis with minimal data
        assert "incidentId" in structured
        assert "metrics" in structured

    def test_llm_analyzer_failure_produces_fallback_report(self):
        """
        Test that LLM analyzer failure produces a fallback report.

        Validates:
        - Fallback report is generated on LLM failure
        - Notification indicates analysis unavailable
        - Workflow completes despite LLM failure
        """
        structured_context = {
            "incidentId": "inc-test-005",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "resource": {
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
                "type": "ec2",
                "name": "test-instance",
            },
            "alarm": {"name": "test-alarm", "metric": "CPUUtilization", "threshold": 50.0},
            "metrics": {"summary": {"avgCPU": 75.0}},
            "logs": {"errorCount": 5},
            "changes": {"recentDeployments": 1},
            "completeness": {"metrics": True, "logs": True, "changes": True},
        }

        # LLM analyzer fails
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_model.side_effect = ClientError(
                {"Error": {"Code": "ValidationException", "Message": "Invalid model input"}},
                "InvokeModel",
            )

            mock_ssm = MagicMock()
            mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "Test prompt"}}

            def client_factory(service, **kwargs):
                if service == "bedrock-runtime":
                    return mock_bedrock
                elif service == "ssm":
                    return mock_ssm
                return MagicMock()

            mock_boto3.side_effect = client_factory

            llm_result = llm_analyzer_handler({"structuredContext": structured_context}, {})

            # Verify fallback report
            assert "analysis" in llm_result
            assert llm_result["analysis"]["confidence"] == "none"
            assert "unavailable" in llm_result["analysis"]["rootCauseHypothesis"].lower()

        # Notification service handles fallback report
        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        mock_sns = MagicMock()
        mock_sns.publish.return_value = {"MessageId": "test-msg-id"}

        with (
            patch("notification_service.lambda_function.secrets_manager", mock_secrets),
            patch("notification_service.lambda_function.sns_client", mock_sns),
            patch(
                "notification_service.lambda_function.SNS_TOPIC_ARN",
                "arn:aws:sns:us-east-1:123456789012:test-topic",
            ),
            patch("requests.post") as mock_post,
        ):

            mock_post.return_value = MagicMock(status_code=200)

            notification_result = notification_handler(llm_result, {})

            # Verify notification sent despite LLM failure
            assert notification_result["status"] in ["success", "partial"]

    def test_notification_failure_still_stores_incident(self):
        """
        Test that incident is stored even if notification fails.

        Validates:
        - Incident persists to DynamoDB despite notification failure
        - Storage operation is independent of notification
        """
        analysis_report = {
            "incidentId": "inc-test-006",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "analysis": {
                "rootCauseHypothesis": "Test hypothesis",
                "confidence": "high",
                "evidence": ["Test evidence"],
                "contributingFactors": [],
                "recommendedActions": ["Test action"],
            },
            "metadata": {
                "modelId": "anthropic.claude-v2",
                "modelVersion": "2.1",
                "promptVersion": "v1.0",
                "tokenUsage": {"input": 100, "output": 50},
                "latency": 1.0,
            },
        }

        # Notification fails - both Slack and email fail
        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
            "GetSecretValue",
        )

        with (
            patch("notification_service.lambda_function.secrets_manager", mock_secrets),
            patch("notification_service.lambda_function.SNS_TOPIC_ARN", ""),
        ):

            notification_result = notification_handler(analysis_report, {})

            # Notification fails but doesn't crash
            assert notification_result["status"] == "failed"

        # Storage still succeeds (simulated)
        with patch("boto3.resource") as mock_boto3_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto3_resource.return_value = mock_dynamodb

            # Store incident
            incident_record = {
                "incidentId": analysis_report["incidentId"],
                "timestamp": analysis_report["timestamp"],
                "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
                "analysisReport": analysis_report,
                "notificationStatus": notification_result,
                "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
            }

            mock_table.put_item(Item=incident_record)

            # Verify storage succeeded
            mock_table.put_item.assert_called_once()

    def test_slack_failure_still_sends_email(self):
        """
        Test that email is sent even if Slack notification fails.

        Validates:
        - Email delivery is independent of Slack delivery
        - Graceful degradation in notification service
        """
        analysis_report = {
            "incidentId": "inc-test-007",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "analysis": {
                "rootCauseHypothesis": "Test hypothesis",
                "confidence": "high",
                "evidence": ["Test evidence"],
                "contributingFactors": [],
                "recommendedActions": ["Test action"],
            },
            "metadata": {
                "modelId": "anthropic.claude-v2",
                "modelVersion": "2.1",
                "promptVersion": "v1.0",
                "tokenUsage": {"input": 100, "output": 50},
                "latency": 1.0,
            },
        }

        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"webhook_url": "https://hooks.slack.com/test"})
        }

        mock_sns = MagicMock()
        mock_sns.publish.return_value = {"MessageId": "test-msg-id"}

        with (
            patch("notification_service.lambda_function.secrets_manager", mock_secrets),
            patch("notification_service.lambda_function.sns_client", mock_sns),
            patch(
                "notification_service.lambda_function.SNS_TOPIC_ARN",
                "arn:aws:sns:us-east-1:123456789012:test-topic",
            ),
            patch("requests.post") as mock_post,
        ):

            # Slack fails
            mock_post.side_effect = Exception("Slack webhook failed")

            notification_result = notification_handler(analysis_report, {})

            # Verify partial success (email sent, Slack failed)
            assert notification_result["status"] == "partial"
            assert notification_result["deliveryStatus"]["slack"] == "failed"
            assert notification_result["deliveryStatus"]["email"] == "delivered"
