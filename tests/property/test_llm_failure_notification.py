"""
Property Test: LLM Failure Notification

Property 27: For any incident where the LLM analyzer fails, the notification
service must send a notification indicating analysis is unavailable.

Validates: Requirements 12.4
"""

import json
import pytest
from hypothesis import given, strategies as st
from datetime import datetime
from typing import Dict, Any

# Import notification service
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from notification_service.lambda_function import format_slack_message, format_email_plain_text


# Strategy for generating fallback analysis reports (LLM failures)
@st.composite
def fallback_analysis_reports(draw):
    """
    Generate analysis reports that indicate LLM failure.

    These reports have:
    - rootCauseHypothesis indicating analysis unavailable
    - confidence = 'none'
    - empty evidence and contributing factors
    - recommended actions include manual review
    """
    incident_id = draw(
        st.text(
            min_size=10,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pd")),
        )
    )
    timestamp = draw(st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2025, 12, 31)))

    # Generate error message
    error_messages = [
        "Analysis unavailable due to LLM service error",
        "Failed to parse LLM response",
        "Circuit breaker open",
        "Bedrock invocation failed",
        "LLM timeout",
    ]
    error_msg = draw(st.sampled_from(error_messages))

    return {
        "incidentId": incident_id,
        "timestamp": timestamp.isoformat() + "Z",
        "analysis": {
            "rootCauseHypothesis": error_msg,
            "confidence": "none",
            "evidence": [],
            "contributingFactors": [],
            "recommendedActions": [
                "Review incident data manually",
                "Check LLM service status",
                draw(st.text(min_size=10, max_size=100)),
            ],
        },
        "metadata": {
            "modelId": "fallback",
            "modelVersion": "N/A",
            "promptVersion": "N/A",
            "tokenUsage": {"input": 0, "output": 0},
            "latency": 0.0,
            "error": draw(st.text(min_size=10, max_size=200)),
        },
    }


@given(report=fallback_analysis_reports())
@pytest.mark.property_test
@pytest.mark.tag("Feature: ai-sre-incident-analysis, Property 27: LLM Failure Notification")
def test_llm_failure_notification_slack(report):
    """
    Property 27: For any incident where the LLM analyzer fails, the notification
    service must send a notification indicating analysis is unavailable.

    Tests Slack notification format.

    Validates: Requirements 12.4
    """
    # Import AnalysisReport model
    from shared.models import AnalysisReport

    # Convert dict to AnalysisReport object
    analysis_report = AnalysisReport.from_dict(report)

    # Format Slack message
    slack_message = format_slack_message(analysis_report)

    # PROPERTY ASSERTIONS:
    # 1. Notification must be generated (not raise exception)
    assert slack_message is not None, "Slack message must be generated even for LLM failure"

    # 2. Message must contain blocks
    assert "blocks" in slack_message, "Slack message must contain blocks"

    # 3. Message must include incident ID (check in the actual data structure, not JSON string)
    message_text = str(slack_message)
    assert report["incidentId"] in message_text, "Notification must include incident ID"

    # 4. Message must indicate analysis unavailable
    # Check for keywords that indicate LLM failure
    failure_indicators = ["unavailable", "failed", "error", "manual", "review", "service"]

    message_lower = message_text.lower()
    has_failure_indicator = any(indicator in message_lower for indicator in failure_indicators)

    assert (
        has_failure_indicator
    ), "Notification must indicate analysis is unavailable or requires manual review"

    # 5. Message must include recommended actions (manual review)
    assert (
        "recommendedActions" in message_text or "Recommended Actions" in message_text
    ), "Notification must include recommended actions section"

    # 6. Confidence must be 'none' or indicate low confidence
    assert (
        "none" in message_lower or "unknown" in message_lower or "low" in message_lower
    ), "Notification must indicate low/no confidence when LLM fails"


@given(report=fallback_analysis_reports())
@pytest.mark.property_test
def test_llm_failure_notification_email(report):
    """
    Test that email notification properly indicates LLM failure.
    """
    from shared.models import AnalysisReport

    # Convert dict to AnalysisReport object
    analysis_report = AnalysisReport.from_dict(report)

    # Format email message
    email_text = format_email_plain_text(analysis_report)

    # PROPERTY ASSERTIONS:
    # 1. Email must be generated
    assert email_text is not None, "Email message must be generated even for LLM failure"

    assert len(email_text) > 0, "Email message must not be empty"

    # 2. Email must include incident ID
    assert report["incidentId"] in email_text, "Email must include incident ID"

    # 3. Email must indicate analysis unavailable
    email_lower = email_text.lower()
    failure_indicators = ["unavailable", "failed", "error", "manual", "review"]

    has_failure_indicator = any(indicator in email_lower for indicator in failure_indicators)

    assert has_failure_indicator, "Email must indicate analysis is unavailable"

    # 4. Email must include recommended actions
    assert (
        "RECOMMENDED ACTIONS" in email_text or "recommended actions" in email_lower
    ), "Email must include recommended actions section"

    # 5. Email must include manual review recommendation
    assert (
        "manual" in email_lower and "review" in email_lower
    ), "Email must recommend manual review when LLM fails"


@given(
    incident_id=st.text(min_size=10, max_size=50),
    error_type=st.sampled_from(
        [
            "Circuit breaker open",
            "Bedrock throttling",
            "Timeout",
            "Invalid response",
            "Service unavailable",
        ]
    ),
)
@pytest.mark.property_test
def test_notification_includes_error_context(incident_id, error_type):
    """
    Test that notification includes context about the LLM failure.
    """
    from shared.models import AnalysisReport

    # Create fallback report with specific error
    report = {
        "incidentId": incident_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "analysis": {
            "rootCauseHypothesis": f"Analysis unavailable due to {error_type}",
            "confidence": "none",
            "evidence": [],
            "contributingFactors": [],
            "recommendedActions": [
                "Review incident data manually",
                "Check LLM service status",
                f"Error: {error_type}",
            ],
        },
        "metadata": {
            "modelId": "fallback",
            "modelVersion": "N/A",
            "promptVersion": "N/A",
            "tokenUsage": {"input": 0, "output": 0},
            "latency": 0.0,
            "error": error_type,
        },
    }

    analysis_report = AnalysisReport.from_dict(report)

    # Format both notification types
    slack_message = format_slack_message(analysis_report)
    email_text = format_email_plain_text(analysis_report)

    # Both must include error context
    slack_text = json.dumps(slack_message).lower()
    email_lower = email_text.lower()

    # Check that error type or related keywords appear in notifications
    error_keywords = error_type.lower().split()

    # At least one keyword from error type should appear
    slack_has_context = any(keyword in slack_text for keyword in error_keywords)
    email_has_context = any(keyword in email_lower for keyword in error_keywords)

    assert (
        slack_has_context or "error" in slack_text
    ), "Slack notification should include error context"

    assert (
        email_has_context or "error" in email_lower
    ), "Email notification should include error context"


@given(report=fallback_analysis_reports())
@pytest.mark.property_test
def test_fallback_report_structure_valid(report):
    """
    Test that fallback reports have valid structure for notification formatting.
    """
    from shared.models import AnalysisReport

    # Must be parseable as AnalysisReport
    try:
        analysis_report = AnalysisReport.from_dict(report)
    except Exception as e:
        pytest.fail(f"Fallback report must be parseable as AnalysisReport: {e}")

    # Must have all required fields
    assert hasattr(analysis_report, "incident_id"), "Fallback report must have incident_id"

    assert hasattr(analysis_report, "analysis"), "Fallback report must have analysis"

    assert hasattr(
        analysis_report.analysis, "root_cause_hypothesis"
    ), "Fallback report must have root_cause_hypothesis"

    assert hasattr(analysis_report.analysis, "confidence"), "Fallback report must have confidence"

    assert hasattr(
        analysis_report.analysis, "recommended_actions"
    ), "Fallback report must have recommended_actions"

    # Confidence must be 'none' for fallback
    confidence_value = analysis_report.analysis.confidence
    if hasattr(confidence_value, "value"):
        confidence_value = confidence_value.value

    assert str(confidence_value).lower() == "none", "Fallback report confidence must be 'none'"

    # Must have at least one recommended action
    assert (
        len(analysis_report.analysis.recommended_actions) > 0
    ), "Fallback report must have recommended actions"
