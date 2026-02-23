"""
Integration tests for performance and timeout requirements.

Tests workflow completion times and individual component timeouts.
Validates: Requirements 2.6, 3.5, 4.6, 5.5, 7.6
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import patch, MagicMock
import json

import pytest

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
@pytest.mark.performance
class TestPerformance:
    """Integration tests for performance and timeout requirements."""

    def test_metrics_collector_completes_within_timeout(self):
        """
        Test that metrics collector completes within 15 seconds.

        Validates: Requirement 3.5
        """
        incident_event = {
            "incidentId": "inc-perf-001",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/EC2",
            "metricName": "CPUUtilization",
        }

        with patch("boto3.client") as mock_boto3:
            mock_cw = MagicMock()
            mock_cw.get_metric_statistics.return_value = {
                "Datapoints": [
                    {
                        "Timestamp": datetime.utcnow() - timedelta(minutes=i),
                        "Average": 50.0 + i,
                        "Unit": "Percent",
                    }
                    for i in range(60)  # 60 data points
                ]
            }
            mock_boto3.return_value = mock_cw

            start_time = time.time()
            result = metrics_collector_handler(incident_event, {})
            duration = time.time() - start_time

            # Verify completes within 15 seconds
            assert duration < 15.0, f"Metrics collector took {duration}s, expected < 15s"
            assert result["status"] == "success"
            assert "collectionDuration" in result
            assert result["collectionDuration"] < 15.0

    def test_logs_collector_completes_within_timeout(self):
        """
        Test that logs collector completes within 20 seconds.

        Validates: Requirement 4.6
        """
        incident_event = {
            "incidentId": "inc-perf-002",
            "resourceArn": "arn:aws:lambda:us-east-1:123456789012:function:test-func",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/Lambda",
            "metricName": "Errors",
        }

        with patch("boto3.client") as mock_boto3:
            mock_logs = MagicMock()
            mock_logs.filter_log_events.return_value = {
                "events": [
                    {
                        "timestamp": int(
                            (datetime.utcnow() - timedelta(minutes=i)).timestamp() * 1000
                        ),
                        "message": f"ERROR: Test error message {i}",
                        "logStreamName": "test-stream",
                    }
                    for i in range(100)  # 100 log entries
                ]
            }
            mock_boto3.return_value = mock_logs

            start_time = time.time()
            result = logs_collector_handler(incident_event, {})
            duration = time.time() - start_time

            # Verify completes within 20 seconds
            assert duration < 20.0, f"Logs collector took {duration}s, expected < 20s"
            assert result["status"] == "success"
            assert "collectionDuration" in result
            assert result["collectionDuration"] < 20.0

    def test_deploy_context_collector_completes_within_timeout(self):
        """
        Test that deploy context collector completes within 15 seconds.

        Validates: Requirement 5.5
        """
        incident_event = {
            "incidentId": "inc-perf-003",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/EC2",
            "metricName": "CPUUtilization",
        }

        with patch("boto3.client") as mock_boto3:
            mock_ct = MagicMock()
            mock_ct.lookup_events.return_value = {
                "Events": [
                    {
                        "EventTime": datetime.utcnow() - timedelta(hours=i),
                        "EventName": "StartInstances",
                        "Username": "test-user",
                        "Resources": [{"ResourceName": "i-test"}],
                    }
                    for i in range(24)  # 24 hours of events
                ]
            }
            mock_boto3.return_value = mock_ct

            start_time = time.time()
            result = deploy_context_handler(incident_event, {})
            duration = time.time() - start_time

            # Verify completes within 15 seconds
            assert duration < 15.0, f"Deploy context collector took {duration}s, expected < 15s"
            assert result["status"] == "success"
            assert "collectionDuration" in result
            assert result["collectionDuration"] < 15.0

    def test_correlation_engine_completes_within_timeout(self):
        """
        Test that correlation engine completes within 5 seconds.

        Validates: Requirement 6.5
        """
        incident_event = {
            "incidentId": "inc-perf-004",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
        }

        # Create large datasets
        metrics_data = {
            "status": "success",
            "metrics": [
                {
                    "metricName": "CPUUtilization",
                    "namespace": "AWS/EC2",
                    "datapoints": [
                        {
                            "timestamp": (datetime.utcnow() - timedelta(minutes=i)).isoformat()
                            + "Z",
                            "value": 50.0 + i,
                            "unit": "Percent",
                        }
                        for i in range(60)
                    ],
                    "statistics": {"avg": 75.0, "max": 95.0, "min": 50.0},
                }
            ],
            "collectionDuration": 1.2,
        }

        logs_data = {
            "status": "success",
            "logs": [
                {
                    "timestamp": (datetime.utcnow() - timedelta(minutes=i)).isoformat() + "Z",
                    "logLevel": "ERROR",
                    "message": f"Test error {i}",
                    "logStream": "test-stream",
                }
                for i in range(100)
            ],
            "totalMatches": 100,
            "returned": 100,
            "collectionDuration": 2.5,
        }

        deploy_data = {
            "status": "success",
            "changes": [
                {
                    "timestamp": (datetime.utcnow() - timedelta(hours=i)).isoformat() + "Z",
                    "changeType": "deployment",
                    "eventName": "UpdateFunctionCode",
                    "user": "test-user",
                    "description": f"Change {i}",
                }
                for i in range(50)
            ],
            "collectionDuration": 3.1,
        }

        correlation_input = {
            "incident": incident_event,
            "metrics": metrics_data,
            "logs": logs_data,
            "changes": deploy_data,
        }

        start_time = time.time()
        result = correlation_handler(correlation_input, {})
        duration = time.time() - start_time

        # Verify completes within 5 seconds
        assert duration < 5.0, f"Correlation engine took {duration}s, expected < 5s"
        # Correlation engine wraps result in structuredContext
        assert "structuredContext" in result
        assert "incidentId" in result["structuredContext"]
        assert "completeness" in result["structuredContext"]

    def test_llm_analyzer_completes_within_timeout(self):
        """
        Test that LLM analyzer completes within 30 seconds.

        Validates: Requirement 7.6
        """
        structured_context = {
            "incidentId": "inc-perf-005",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "resource": {
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
                "type": "ec2",
                "name": "test-instance",
            },
            "alarm": {"name": "test-alarm", "metric": "CPUUtilization", "threshold": 50.0},
            "metrics": {"summary": {"avgCPU": 75.0, "maxCPU": 95.0}},
            "logs": {"errorCount": 10, "topErrors": ["Error 1", "Error 2"]},
            "changes": {"recentDeployments": 2},
            "completeness": {"metrics": True, "logs": True, "changes": True},
        }

        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()

            # Simulate LLM processing time
            def slow_invoke_model(**kwargs):
                time.sleep(0.5)  # Simulate network latency
                return {
                    "body": MagicMock(
                        read=lambda: json.dumps(
                            {
                                "completion": json.dumps(
                                    {
                                        "rootCauseHypothesis": "High CPU due to process",
                                        "confidence": "high",
                                        "evidence": ["CPU spike"],
                                        "contributingFactors": ["Undersized"],
                                        "recommendedActions": ["Upgrade"],
                                    }
                                )
                            }
                        ).encode()
                    )
                }

            mock_bedrock.invoke_model = slow_invoke_model

            mock_ssm = MagicMock()
            mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "Test prompt: {context}"}}

            def client_factory(service, **kwargs):
                if service == "bedrock-runtime":
                    return mock_bedrock
                elif service == "ssm":
                    return mock_ssm
                return MagicMock()

            mock_boto3.side_effect = client_factory

            start_time = time.time()
            result = llm_analyzer_handler({"structuredContext": structured_context}, {})
            duration = time.time() - start_time

            # Verify completes within 30 seconds
            assert duration < 30.0, f"LLM analyzer took {duration}s, expected < 30s"
            assert "analysis" in result
            assert "metadata" in result
            assert "latency" in result["metadata"]

    def test_notification_service_completes_within_timeout(self):
        """
        Test that notification service completes within 10 seconds.

        Validates: Requirement 8.7
        """
        analysis_report = {
            "incidentId": "inc-perf-006",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "analysis": {
                "rootCauseHypothesis": "Test hypothesis",
                "confidence": "high",
                "evidence": ["Evidence 1", "Evidence 2"],
                "contributingFactors": ["Factor 1"],
                "recommendedActions": ["Action 1", "Action 2"],
            },
            "metadata": {
                "modelId": "anthropic.claude-v2",
                "modelVersion": "2.1",
                "promptVersion": "v1.0",
                "tokenUsage": {"input": 1000, "output": 200},
                "latency": 2.5,
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

            mock_post.return_value = MagicMock(status_code=200)

            start_time = time.time()
            result = notification_handler(analysis_report, {})
            duration = time.time() - start_time

            # Verify completes within 10 seconds
            assert duration < 10.0, f"Notification service took {duration}s, expected < 10s"
            assert result["status"] in ["success", "partial"]
            assert "notificationDuration" in result

    def test_complete_workflow_completes_within_120_seconds(self):
        """
        Test that complete workflow completes within 120 seconds.

        Validates: Requirement 2.6
        """
        incident_event = {
            "incidentId": "inc-perf-007",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/EC2",
            "metricName": "CPUUtilization",
        }

        start_time = time.time()

        # Step 1: Parallel data collection
        with patch("boto3.client") as mock_boto3:
            # Metrics collector
            mock_cw = MagicMock()
            mock_cw.get_metric_statistics.return_value = {
                "Datapoints": [{"Timestamp": datetime.utcnow(), "Average": 75.0, "Unit": "Percent"}]
            }
            mock_boto3.return_value = mock_cw
            metrics_result = metrics_collector_handler(incident_event, {})

        with patch("boto3.client") as mock_boto3:
            # Logs collector
            mock_logs = MagicMock()
            mock_logs.filter_log_events.return_value = {
                "events": [
                    {
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        "message": "ERROR: Test",
                        "logStreamName": "test-stream",
                    }
                ]
            }
            mock_boto3.return_value = mock_logs
            logs_result = logs_collector_handler(incident_event, {})

        with patch("boto3.client") as mock_boto3:
            # Deploy context collector
            mock_ct = MagicMock()
            mock_ct.lookup_events.return_value = {"Events": []}
            mock_boto3.return_value = mock_ct
            deploy_result = deploy_context_handler(incident_event, {})

        # Step 2: Correlation
        correlation_input = {
            "incident": incident_event,
            "metrics": metrics_result,
            "logs": logs_result,
            "changes": deploy_result,
        }
        correlation_result = correlation_handler(correlation_input, {})

        # Step 3: LLM Analysis
        with patch("boto3.client") as mock_boto3:
            mock_bedrock = MagicMock()
            mock_bedrock.invoke_model.return_value = {
                "body": MagicMock(
                    read=lambda: json.dumps(
                        {
                            "completion": json.dumps(
                                {
                                    "rootCauseHypothesis": "Test",
                                    "confidence": "high",
                                    "evidence": ["Test"],
                                    "contributingFactors": [],
                                    "recommendedActions": ["Test"],
                                }
                            )
                        }
                    ).encode()
                )
            }

            mock_ssm = MagicMock()
            mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "Test prompt"}}

            def client_factory(service, **kwargs):
                if service == "bedrock-runtime":
                    return mock_bedrock
                elif service == "ssm":
                    return mock_ssm
                return MagicMock()

            mock_boto3.side_effect = client_factory
            llm_result = llm_analyzer_handler({"structuredContext": correlation_result}, {})

        # Step 4: Notification
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

        total_duration = time.time() - start_time

        # Verify complete workflow within 120 seconds
        assert total_duration < 120.0, f"Complete workflow took {total_duration}s, expected < 120s"

        # Verify all steps completed successfully
        assert metrics_result["status"] == "success"
        assert logs_result["status"] == "success"
        assert deploy_result["status"] == "success"
        assert "structuredContext" in correlation_result
        assert "incidentId" in correlation_result["structuredContext"]
        assert "analysis" in llm_result
        assert notification_result["status"] in ["success", "partial"]

    def test_collector_timeout_handling(self):
        """
        Test that collectors handle timeouts gracefully.

        Validates: Timeout handling for all collectors
        """
        incident_event = {
            "incidentId": "inc-perf-008",
            "resourceArn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alarmName": "test-alarm",
            "namespace": "AWS/EC2",
            "metricName": "CPUUtilization",
        }

        # Simulate slow API response
        with patch("boto3.client") as mock_boto3:
            mock_cw = MagicMock()

            def slow_api_call(**kwargs):
                time.sleep(0.1)  # Simulate slow response
                return {"Datapoints": []}

            mock_cw.get_metric_statistics = slow_api_call
            mock_boto3.return_value = mock_cw

            start_time = time.time()
            result = metrics_collector_handler(incident_event, {})
            duration = time.time() - start_time

            # Verify function completes (doesn't hang indefinitely)
            assert duration < 15.0
            assert result["status"] in ["success", "failed"]
