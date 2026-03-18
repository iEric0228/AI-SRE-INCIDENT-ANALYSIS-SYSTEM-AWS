"""
Notification Service Lambda Function

Sends incident analysis reports to Slack and email channels.
Implements graceful degradation - continues with email if Slack fails.
"""

import json
import logging
import os

import time
import traceback
from datetime import datetime
from typing import Any, Dict

import boto3
import requests
from botocore.exceptions import ClientError

from models import (
    AnalysisReport,
    DeliveryStatus,
    NotificationDeliveryStatus,
    NotificationOutput,
    Status,
)
from metrics import put_notification_delivery_metric

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_manager = boto3.client("secretsmanager")
sns_client = boto3.client("sns")

# Environment variables
SLACK_SECRET_NAME = os.environ.get("SLACK_SECRET_NAME", "incident-analysis/slack-webhook")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
INCIDENT_STORE_BASE_URL = os.environ.get(
    "INCIDENT_STORE_BASE_URL", "https://console.aws.amazon.com/dynamodb/incident"
)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for notification service.

    Args:
        event: Analysis report from LLM analyzer
        context: Lambda context

    Returns:
        Notification output with delivery status
    """
    start_time = datetime.utcnow()

    # Extract correlation ID
    correlation_id = event.get("incidentId", "unknown")

    try:
        logger.info(
            json.dumps(
                {
                    "message": "Notification service invoked",
                    "correlationId": correlation_id,
                    "timestamp": start_time.isoformat(),
                }
            )
        )

        # Parse analysis report from Step Functions state
        # The analysis report is nested under 'analysisReport' key in the full state
        report_data = event.get("analysisReport", event)
        analysis_report = AnalysisReport.from_dict(report_data)

        # Initialize delivery status
        delivery_status = NotificationDeliveryStatus(
            slack=DeliveryStatus.SKIPPED.value,
            email=DeliveryStatus.SKIPPED.value,
            slack_error=None,
            email_error=None,
        )

        # GRACEFUL DEGRADATION STRATEGY:
        # Attempt both notification channels independently
        # If Slack fails, still try email (Requirement 8.6)
        # Return partial success if at least one channel succeeds

        # Attempt Slack notification
        slack_start = datetime.utcnow()
        try:
            send_slack_notification(analysis_report)
            slack_duration = (datetime.utcnow() - slack_start).total_seconds()
            delivery_status.slack = DeliveryStatus.DELIVERED.value
            logger.info(
                json.dumps(
                    {"message": "Slack notification delivered", "correlationId": correlation_id}
                )
            )
            # Emit success metric
            put_notification_delivery_metric("slack", True, slack_duration)
        except Exception as e:
            # Slack failure - log error but continue to email
            slack_duration = (datetime.utcnow() - slack_start).total_seconds()
            delivery_status.slack = DeliveryStatus.FAILED.value
            delivery_status.slack_error = str(e)
            logger.error(
                json.dumps(
                    {
                        "message": "Slack notification failed",
                        "correlationId": correlation_id,
                        "error": str(e),
                        "stackTrace": traceback.format_exc(),
                    }
                )
            )
            # Emit failure metric
            put_notification_delivery_metric("slack", False, slack_duration)

        # Attempt email notification (independent of Slack result)
        # This ensures at least one notification channel is attempted
        email_start = datetime.utcnow()
        try:
            send_email_notification(analysis_report)
            email_duration = (datetime.utcnow() - email_start).total_seconds()
            delivery_status.email = DeliveryStatus.DELIVERED.value
            logger.info(
                json.dumps(
                    {"message": "Email notification delivered", "correlationId": correlation_id}
                )
            )
            # Emit success metric
            put_notification_delivery_metric("email", True, email_duration)
        except Exception as e:
            # Email failure - log error
            email_duration = (datetime.utcnow() - email_start).total_seconds()
            delivery_status.email = DeliveryStatus.FAILED.value
            delivery_status.email_error = str(e)
            logger.error(
                json.dumps(
                    {
                        "message": "Email notification failed",
                        "correlationId": correlation_id,
                        "error": str(e),
                        "stackTrace": traceback.format_exc(),
                    }
                )
            )
            # Emit failure metric
            put_notification_delivery_metric("email", False, email_duration)

        # Calculate duration
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Determine overall status
        if (
            delivery_status.slack == DeliveryStatus.DELIVERED.value
            or delivery_status.email == DeliveryStatus.DELIVERED.value
        ):
            if (
                delivery_status.slack == DeliveryStatus.DELIVERED.value
                and delivery_status.email == DeliveryStatus.DELIVERED.value
            ):
                status = Status.SUCCESS.value
            else:
                status = Status.PARTIAL.value
        else:
            status = Status.FAILED.value

        # Create output
        output = NotificationOutput(
            status=status, delivery_status=delivery_status, notification_duration=duration
        )

        logger.info(
            json.dumps(
                {
                    "message": "Notification service completed",
                    "correlationId": correlation_id,
                    "status": status,
                    "duration": duration,
                    "slackStatus": delivery_status.slack,
                    "emailStatus": delivery_status.email,
                }
            )
        )

        return output.to_dict()

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "message": "Notification service failed",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorType": type(e).__name__,
                    "stackTrace": traceback.format_exc(),
                }
            )
        )

        # Return failure response
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        return {
            "status": Status.FAILED.value,
            "deliveryStatus": {
                "slack": DeliveryStatus.FAILED.value,
                "email": DeliveryStatus.FAILED.value,
                "slackError": str(e),
                "emailError": str(e),
            },
            "notificationDuration": duration,
        }


def send_slack_notification(analysis_report: AnalysisReport) -> None:
    """
    Send notification to Slack via webhook.

    Args:
        analysis_report: Analysis report to send

    Raises:
        Exception: If Slack delivery fails after retries
    """
    # RETRY STRATEGY:
    # Max retries: 2 (total 3 attempts)
    # Retry delay: 1 second (simple fixed delay, not exponential)
    # Reason: Slack webhooks may fail due to transient network issues
    # Timeout: 5 seconds per request to prevent hanging

    # Retrieve webhook URL from Secrets Manager (runtime retrieval for security)
    webhook_url = get_slack_webhook_url()

    # Format message
    message = format_slack_message(analysis_report)

    # Send with retry logic
    max_retries = 2
    retry_delay = 1  # seconds

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                webhook_url, json=message, timeout=5  # Prevent hanging on slow connections
            )
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
            return  # Success - exit function
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                # Retry on failure (transient network issues)
                logger.warning(f"Slack webhook attempt {attempt + 1} failed, retrying: {e}")
                time.sleep(retry_delay)
            else:
                # All retries exhausted - raise exception
                raise Exception(f"Slack webhook failed after {max_retries + 1} attempts: {e}")


def send_email_notification(analysis_report: AnalysisReport) -> None:
    """
    Send notification via SNS email.

    Args:
        analysis_report: Analysis report to send

    Raises:
        Exception: If email delivery fails
    """
    if not SNS_TOPIC_ARN:
        raise Exception("SNS_TOPIC_ARN environment variable not set")

    # Format message
    subject = format_email_subject(analysis_report)
    plain_text = format_email_plain_text(analysis_report)
    format_email_html(analysis_report)  # HTML version prepared for future use

    # Publish to SNS
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=plain_text,
            MessageAttributes={
                "incidentId": {"DataType": "String", "StringValue": analysis_report.incident_id},
                "severity": {
                    "DataType": "String",
                    "StringValue": get_severity_from_confidence(
                        analysis_report.analysis.confidence
                    ),
                },
            },
        )
    except ClientError as e:
        raise Exception(f"SNS publish failed: {e}")


def get_slack_webhook_url() -> str:
    """
    Retrieve Slack webhook URL from Secrets Manager.

    Returns:
        Webhook URL

    Raises:
        Exception: If secret retrieval fails
    """
    try:
        response = secrets_manager.get_secret_value(SecretId=SLACK_SECRET_NAME)
        secret = json.loads(response["SecretString"])
        return str(secret["webhook_url"])
    except ClientError as e:
        raise Exception(f"Failed to retrieve Slack webhook URL: {e}")
    except (KeyError, json.JSONDecodeError) as e:
        raise Exception(f"Invalid secret format: {e}")


def format_slack_message(analysis_report: AnalysisReport) -> Dict[str, Any]:
    """
    Format analysis report as Slack message with blocks.

    Args:
        analysis_report: Analysis report

    Returns:
        Slack message payload
    """
    analysis = analysis_report.analysis

    # Determine severity emoji
    confidence = analysis.confidence
    confidence_value = confidence.value if hasattr(confidence, "value") else str(confidence)
    if confidence_value == "high":
        emoji = "🔴"
        severity = "High"
    elif confidence_value == "medium":
        emoji = "🟡"
        severity = "Medium"
    elif confidence_value == "low":
        emoji = "🟢"
        severity = "Low"
    else:
        emoji = "⚪"
        severity = "Unknown"

    # Generate incident store link
    incident_link = f"{INCIDENT_STORE_BASE_URL}/{analysis_report.incident_id}"

    # Build Slack blocks
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} Incident Alert", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Incident ID:*\n{analysis_report.incident_id}"},
                {"type": "mrkdwn", "text": f"*Severity:*\n{severity}"},
                {"type": "mrkdwn", "text": f"*Time:*\n{analysis_report.timestamp}"},
                {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence_value.capitalize()}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Root Cause Hypothesis:*\n{analysis.root_cause_hypothesis}",
            },
        },
    ]

    # Add evidence section if available
    if analysis.evidence:
        evidence_text = "\n".join([f"• {e}" for e in analysis.evidence])
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Evidence:*\n{evidence_text}"}}
        )

    # Add contributing factors if available
    if analysis.contributing_factors:
        factors_text = "\n".join([f"• {f}" for f in analysis.contributing_factors])
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Contributing Factors:*\n{factors_text}"},
            }
        )

    # Add recommended actions
    if analysis.recommended_actions:
        actions_text = "\n".join(
            [f"{i + 1}. {a}" for i, a in enumerate(analysis.recommended_actions)]
        )
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Recommended Actions:*\n{actions_text}"},
            }
        )

    # Add link to full details
    blocks.extend(
        [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"<{incident_link}|View Full Incident Details>"},
            },
        ]
    )

    return {"blocks": blocks}


def format_email_subject(analysis_report: AnalysisReport) -> str:
    """
    Format email subject line.

    Args:
        analysis_report: Analysis report

    Returns:
        Email subject
    """
    confidence = analysis_report.analysis.confidence
    severity = get_severity_from_confidence(confidence)
    return f"[{severity}] Incident Alert: {analysis_report.incident_id}"


def format_email_plain_text(analysis_report: AnalysisReport) -> str:
    """
    Format analysis report as plain text email.

    Args:
        analysis_report: Analysis report

    Returns:
        Plain text email body
    """
    analysis = analysis_report.analysis
    confidence = analysis.confidence
    confidence_value = confidence.value if hasattr(confidence, "value") else str(confidence)
    severity = get_severity_from_confidence(confidence)
    incident_link = f"{INCIDENT_STORE_BASE_URL}/{analysis_report.incident_id}"

    lines = [
        "INCIDENT ALERT",
        "=" * 60,
        "",
        f"Incident ID: {analysis_report.incident_id}",
        f"Severity: {severity}",
        f"Time: {analysis_report.timestamp}",
        f"Confidence: {confidence_value.capitalize()}",
        "",
        "ROOT CAUSE HYPOTHESIS:",
        "-" * 60,
        analysis.root_cause_hypothesis,
        "",
    ]

    if analysis.evidence:
        lines.append("EVIDENCE:")
        lines.append("-" * 60)
        for evidence in analysis.evidence:
            lines.append(f"• {evidence}")
        lines.append("")

    if analysis.contributing_factors:
        lines.append("CONTRIBUTING FACTORS:")
        lines.append("-" * 60)
        for factor in analysis.contributing_factors:
            lines.append(f"• {factor}")
        lines.append("")

    if analysis.recommended_actions:
        lines.append("RECOMMENDED ACTIONS:")
        lines.append("-" * 60)
        for i, action in enumerate(analysis.recommended_actions, 1):
            lines.append(f"{i}. {action}")
        lines.append("")

    lines.extend(["=" * 60, f"View Full Incident Details: {incident_link}", ""])

    return "\n".join(lines)


def format_email_html(analysis_report: AnalysisReport) -> str:
    """
    Format analysis report as HTML email.

    Args:
        analysis_report: Analysis report

    Returns:
        HTML email body
    """
    analysis = analysis_report.analysis
    confidence = analysis.confidence
    confidence_value = confidence.value if hasattr(confidence, "value") else str(confidence)
    severity = get_severity_from_confidence(confidence)
    incident_link = f"{INCIDENT_STORE_BASE_URL}/{analysis_report.incident_id}"

    # Determine color based on severity
    if severity == "High":
        color = "#dc3545"
    elif severity == "Medium":
        color = "#ffc107"
    else:
        color = "#28a745"

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: {color}; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .section {{ margin-bottom: 20px; }}
            .section-title {{ font-weight: bold; color: {color}; margin-bottom: 10px; }}
            .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }}
            .info-item {{ padding: 10px; background-color: #f8f9fa; border-left: 3px solid {color}; }}
            .info-label {{ font-weight: bold; }}
            ul {{ list-style-type: none; padding-left: 0; }}
            li {{ padding: 5px 0; padding-left: 20px; position: relative; }}
            li:before {{ content: "•"; position: absolute; left: 0; color: {color}; font-weight: bold; }}
            .button {{ display: inline-block; padding: 10px 20px; background-color: {color}; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🚨 Incident Alert</h1>
        </div>
        <div class="content">
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">Incident ID</div>
                    <div>{analysis_report.incident_id}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Severity</div>
                    <div>{severity}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Time</div>
                    <div>{analysis_report.timestamp}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Confidence</div>
                    <div>{confidence_value.capitalize()}</div>
                </div>
            </div>

            <div class="section">
                <div class="section-title">Root Cause Hypothesis</div>
                <p>{analysis.root_cause_hypothesis}</p>
            </div>
    """

    if analysis.evidence:
        html += """
            <div class="section">
                <div class="section-title">Evidence</div>
                <ul>
        """
        for evidence in analysis.evidence:
            html += f"<li>{evidence}</li>"
        html += """
                </ul>
            </div>
        """

    if analysis.contributing_factors:
        html += """
            <div class="section">
                <div class="section-title">Contributing Factors</div>
                <ul>
        """
        for factor in analysis.contributing_factors:
            html += f"<li>{factor}</li>"
        html += """
                </ul>
            </div>
        """

    if analysis.recommended_actions:
        html += """
            <div class="section">
                <div class="section-title">Recommended Actions</div>
                <ol>
        """
        for action in analysis.recommended_actions:
            html += f"<li>{action}</li>"
        html += """
                </ol>
            </div>
        """

    html += f"""
            <a href="{incident_link}" class="button">View Full Incident Details</a>

            <div class="footer">
                <p>This is an automated incident notification from the AI-Assisted SRE Incident Analysis System.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return html


def get_severity_from_confidence(confidence) -> str:
    """
    Map confidence level to severity.

    Args:
        confidence: Confidence level (high, medium, low, none) - can be enum or string

    Returns:
        Severity level (High, Medium, Low)
    """
    confidence_value = confidence.value if hasattr(confidence, "value") else str(confidence)
    mapping = {"high": "High", "medium": "Medium", "low": "Low", "none": "Low"}
    return mapping.get(confidence_value.lower(), "Low")
