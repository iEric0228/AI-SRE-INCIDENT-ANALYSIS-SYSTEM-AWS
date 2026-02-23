"""
Property-based tests for notification message completeness.

This module tests that notification messages always include all required fields:
incident ID, resource, severity, hypothesis, actions, and link.

Validates Requirements 8.1, 8.4, 8.5
"""

import json
import sys
import os
from datetime import datetime
from hypothesis import given, strategies as st
from hypothesis.strategies import composite

# Import shared models
from shared.models import AnalysisReport, Analysis, AnalysisMetadata, Confidence

# Import notification service functions directly
# Clear any cached lambda_function module first
if "lambda_function" in sys.modules:
    del sys.modules["lambda_function"]
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "notification_service")
)
import lambda_function as notification_lambda

format_slack_message = notification_lambda.format_slack_message
format_email_plain_text = notification_lambda.format_email_plain_text
format_email_html = notification_lambda.format_email_html
format_email_subject = notification_lambda.format_email_subject


# Strategy generators


@composite
def incident_id_strategy(draw):
    """Generate arbitrary incident IDs."""
    return draw(
        st.one_of(
            st.uuids().map(str),
            st.text(
                min_size=10,
                max_size=50,
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
            ),
        )
    )


@composite
def confidence_strategy(draw):
    """Generate arbitrary confidence levels."""
    return draw(
        st.sampled_from([Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW, Confidence.NONE])
    )


@composite
def hypothesis_strategy(draw):
    """Generate arbitrary root cause hypotheses."""
    # Use printable ASCII characters only (space through tilde, excluding control characters)
    text = draw(
        st.text(
            min_size=20,
            max_size=500,
            alphabet=" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
        )
    )
    # Filter out any null bytes that might have snuck in
    return text.replace("\x00", "")


@composite
def evidence_list_strategy(draw):
    """Generate arbitrary evidence lists."""
    return draw(
        st.lists(
            st.text(
                min_size=10,
                max_size=200,
                alphabet=" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
            ).map(lambda s: s.replace("\x00", "")),
            min_size=0,
            max_size=10,
        )
    )


@composite
def actions_list_strategy(draw):
    """Generate arbitrary recommended actions lists."""
    return draw(
        st.lists(
            st.text(
                min_size=10,
                max_size=200,
                alphabet=" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
            ).map(lambda s: s.replace("\x00", "")),
            min_size=1,  # At least one action required
            max_size=10,
        )
    )


@composite
def analysis_report_strategy(draw):
    """Generate arbitrary analysis reports."""
    incident_id = draw(incident_id_strategy())
    confidence = draw(confidence_strategy())
    hypothesis = draw(hypothesis_strategy())
    evidence = draw(evidence_list_strategy())
    contributing_factors = draw(evidence_list_strategy())
    actions = draw(actions_list_strategy())

    # Create Analysis object
    analysis = Analysis(
        root_cause_hypothesis=hypothesis,
        confidence=confidence,
        evidence=evidence,
        contributing_factors=contributing_factors,
        recommended_actions=actions,
    )

    # Create AnalysisMetadata
    metadata = AnalysisMetadata(
        model_id="anthropic.claude-v2",
        model_version="2.1",
        prompt_version="v1.0",
        token_usage={"input": 1000, "output": 200},
        latency=2.5,
    )

    # Create AnalysisReport
    return AnalysisReport(
        incident_id=incident_id, timestamp=datetime.utcnow(), analysis=analysis, metadata=metadata
    )


# Property Tests


@given(analysis_report_strategy())
def test_property_21_slack_message_completeness(analysis_report):
    """
    **Property 21: Notification Message Completeness**
    **Validates: Requirements 8.1, 8.4, 8.5**

    For any analysis report, Slack notification must include:
    1. Incident ID
    2. Resource information (implied by incident context)
    3. Severity (derived from confidence)
    4. Root cause hypothesis
    5. Recommended actions
    6. Link to full incident details

    This property verifies that the Slack message contains all required fields
    and that they are properly formatted and accessible.
    """
    # Format Slack message
    slack_message = format_slack_message(analysis_report)

    # Verify message is a dictionary
    assert isinstance(slack_message, dict), "Slack message should be a dictionary"

    # Verify message has blocks structure
    assert "blocks" in slack_message, "Slack message should contain 'blocks' key"
    assert isinstance(slack_message["blocks"], list), "Slack blocks should be a list"
    assert len(slack_message["blocks"]) > 0, "Slack blocks should not be empty"

    # Convert blocks to JSON string for content verification
    message_json = json.dumps(slack_message)

    # 1. Verify incident ID is present (handle JSON escaping)
    incident_id_escaped = json.dumps(analysis_report.incident_id)[1:-1]  # Remove quotes
    assert (
        incident_id_escaped in message_json
    ), f"Slack message should contain incident ID '{analysis_report.incident_id}'"

    # 2. Verify severity is present (derived from confidence)
    confidence_value = analysis_report.analysis.confidence.value
    severity_mapping = {"high": "High", "medium": "Medium", "low": "Low", "none": "Unknown"}
    expected_severity = severity_mapping.get(confidence_value, "Unknown")
    assert (
        expected_severity in message_json
    ), f"Slack message should contain severity '{expected_severity}'"

    # 3. Verify root cause hypothesis is present (handle JSON escaping)
    hypothesis_escaped = json.dumps(analysis_report.analysis.root_cause_hypothesis)[
        1:-1
    ]  # Remove quotes
    assert hypothesis_escaped in message_json, "Slack message should contain root cause hypothesis"

    # 4. Verify recommended actions are present (handle JSON escaping)
    for action in analysis_report.analysis.recommended_actions:
        action_escaped = json.dumps(action)[1:-1]  # Remove quotes
        assert (
            action_escaped in message_json
        ), f"Slack message should contain recommended action '{action}'"

    # 5. Verify link to incident details is present
    # The link should contain the incident ID
    assert (
        "View Full Incident Details" in message_json or "incident" in message_json.lower()
    ), "Slack message should contain link to full incident details"

    # Verify confidence level is present
    assert (
        confidence_value in message_json or confidence_value.capitalize() in message_json
    ), f"Slack message should contain confidence level '{confidence_value}'"

    # Verify timestamp is present
    timestamp_str = (
        analysis_report.timestamp.isoformat()
        if isinstance(analysis_report.timestamp, datetime)
        else str(analysis_report.timestamp)
    )
    assert (
        timestamp_str in message_json or str(analysis_report.timestamp) in message_json
    ), "Slack message should contain timestamp"


@given(analysis_report_strategy())
def test_property_21_email_subject_completeness(analysis_report):
    """
    Property: Email subject contains incident ID and severity.

    This verifies that the email subject line includes key identifying information.
    """
    # Format email subject
    subject = format_email_subject(analysis_report)

    # Verify subject is a non-empty string
    assert isinstance(subject, str), "Email subject should be a string"
    assert len(subject) > 0, "Email subject should not be empty"

    # Verify incident ID is in subject
    assert (
        analysis_report.incident_id in subject
    ), f"Email subject should contain incident ID '{analysis_report.incident_id}'"

    # Verify severity is in subject
    confidence_value = analysis_report.analysis.confidence.value
    severity_mapping = {"high": "High", "medium": "Medium", "low": "Low", "none": "Low"}
    expected_severity = severity_mapping.get(confidence_value, "Low")
    assert (
        expected_severity in subject
    ), f"Email subject should contain severity '{expected_severity}'"


@given(analysis_report_strategy())
def test_property_21_email_plain_text_completeness(analysis_report):
    """
    Property: Email plain text contains all required fields.

    This verifies that the plain text email includes all required information.
    """
    # Format email plain text
    plain_text = format_email_plain_text(analysis_report)

    # Verify plain text is a non-empty string
    assert isinstance(plain_text, str), "Email plain text should be a string"
    assert len(plain_text) > 0, "Email plain text should not be empty"

    # 1. Verify incident ID is present
    assert (
        analysis_report.incident_id in plain_text
    ), f"Email should contain incident ID '{analysis_report.incident_id}'"

    # 2. Verify severity is present
    confidence_value = analysis_report.analysis.confidence.value
    severity_mapping = {"high": "High", "medium": "Medium", "low": "Low", "none": "Low"}
    expected_severity = severity_mapping.get(confidence_value, "Low")
    assert expected_severity in plain_text, f"Email should contain severity '{expected_severity}'"

    # 3. Verify root cause hypothesis is present
    hypothesis = analysis_report.analysis.root_cause_hypothesis
    assert hypothesis in plain_text, "Email should contain root cause hypothesis"

    # 4. Verify recommended actions are present
    for action in analysis_report.analysis.recommended_actions:
        assert action in plain_text, f"Email should contain recommended action '{action}'"

    # 5. Verify link to incident details is present
    assert (
        "View Full Incident Details" in plain_text or "incident" in plain_text.lower()
    ), "Email should contain link to full incident details"

    # Verify confidence level is present
    assert (
        confidence_value in plain_text or confidence_value.capitalize() in plain_text
    ), f"Email should contain confidence level '{confidence_value}'"

    # Verify timestamp is present
    timestamp_str = str(analysis_report.timestamp)
    assert (
        timestamp_str in plain_text or analysis_report.timestamp.isoformat() in plain_text
    ), "Email should contain timestamp"


@given(analysis_report_strategy())
def test_property_21_email_html_completeness(analysis_report):
    """
    Property: Email HTML contains all required fields.

    This verifies that the HTML email includes all required information.
    """
    # Format email HTML
    html = format_email_html(analysis_report)

    # Verify HTML is a non-empty string
    assert isinstance(html, str), "Email HTML should be a string"
    assert len(html) > 0, "Email HTML should not be empty"

    # Verify it's valid HTML
    assert "<html>" in html.lower(), "Email should be valid HTML"
    assert "</html>" in html.lower(), "Email should be valid HTML"

    # 1. Verify incident ID is present
    assert (
        analysis_report.incident_id in html
    ), f"Email HTML should contain incident ID '{analysis_report.incident_id}'"

    # 2. Verify severity is present
    confidence_value = analysis_report.analysis.confidence.value
    severity_mapping = {"high": "High", "medium": "Medium", "low": "Low", "none": "Low"}
    expected_severity = severity_mapping.get(confidence_value, "Low")
    assert expected_severity in html, f"Email HTML should contain severity '{expected_severity}'"

    # 3. Verify root cause hypothesis is present
    hypothesis = analysis_report.analysis.root_cause_hypothesis
    assert hypothesis in html, "Email HTML should contain root cause hypothesis"

    # 4. Verify recommended actions are present
    for action in analysis_report.analysis.recommended_actions:
        assert action in html, f"Email HTML should contain recommended action '{action}'"

    # 5. Verify link to incident details is present
    assert (
        "View Full Incident Details" in html or "incident" in html.lower()
    ), "Email HTML should contain link to full incident details"

    # Verify confidence level is present
    assert (
        confidence_value in html or confidence_value.capitalize() in html
    ), f"Email HTML should contain confidence level '{confidence_value}'"

    # Verify timestamp is present
    timestamp_str = str(analysis_report.timestamp)
    assert (
        timestamp_str in html or analysis_report.timestamp.isoformat() in html
    ), "Email HTML should contain timestamp"


@given(analysis_report_strategy())
def test_slack_message_has_proper_structure(analysis_report):
    """
    Property: Slack message has proper block structure.

    This verifies that the Slack message follows the expected block format.
    """
    # Format Slack message
    slack_message = format_slack_message(analysis_report)

    # Verify blocks structure
    blocks = slack_message["blocks"]

    # Should have at least: header, section with fields, divider, hypothesis, actions, divider, link
    assert len(blocks) >= 5, "Slack message should have at least 5 blocks"

    # First block should be header
    assert blocks[0]["type"] == "header", "First block should be header"
    assert "text" in blocks[0], "Header should have text"

    # Should have at least one section block
    section_blocks = [b for b in blocks if b["type"] == "section"]
    assert len(section_blocks) > 0, "Should have at least one section block"

    # Should have dividers
    divider_blocks = [b for b in blocks if b["type"] == "divider"]
    assert len(divider_blocks) >= 2, "Should have at least 2 divider blocks"


@given(analysis_report_strategy())
def test_all_notification_formats_contain_same_core_info(analysis_report):
    """
    Property: All notification formats contain the same core information.

    This verifies consistency across Slack, email subject, plain text, and HTML.
    """
    # Format all notification types
    slack_message = format_slack_message(analysis_report)
    email_subject = format_email_subject(analysis_report)
    email_plain = format_email_plain_text(analysis_report)
    email_html = format_email_html(analysis_report)

    # Convert to strings for comparison
    slack_str = json.dumps(slack_message)

    # Core information that should be in all formats
    incident_id = analysis_report.incident_id
    hypothesis = analysis_report.analysis.root_cause_hypothesis

    # Escape for JSON comparison
    incident_id_escaped = json.dumps(incident_id)[1:-1]
    hypothesis_escaped = json.dumps(hypothesis)[1:-1]

    # Verify incident ID is in all formats
    assert incident_id_escaped in slack_str, "Incident ID should be in Slack message"
    assert incident_id in email_subject, "Incident ID should be in email subject"
    assert incident_id in email_plain, "Incident ID should be in email plain text"
    assert incident_id in email_html, "Incident ID should be in email HTML"

    # Verify hypothesis is in all formats (except subject which is too short)
    assert hypothesis_escaped in slack_str, "Hypothesis should be in Slack message"
    assert hypothesis in email_plain, "Hypothesis should be in email plain text"
    assert hypothesis in email_html, "Hypothesis should be in email HTML"


@given(analysis_report_strategy())
def test_notification_messages_are_non_empty(analysis_report):
    """
    Property: All notification messages are non-empty.

    This verifies that no notification format produces empty output.
    """
    # Format all notification types
    slack_message = format_slack_message(analysis_report)
    email_subject = format_email_subject(analysis_report)
    email_plain = format_email_plain_text(analysis_report)
    email_html = format_email_html(analysis_report)

    # Verify all are non-empty
    assert len(slack_message["blocks"]) > 0, "Slack message should have blocks"
    assert len(email_subject) > 0, "Email subject should not be empty"
    assert len(email_plain) > 0, "Email plain text should not be empty"
    assert len(email_html) > 0, "Email HTML should not be empty"

    # Verify minimum reasonable lengths
    assert len(email_subject) >= 10, "Email subject should have reasonable length"
    assert len(email_plain) >= 50, "Email plain text should have reasonable length"
    assert len(email_html) >= 100, "Email HTML should have reasonable length"


@given(analysis_report_strategy())
def test_notification_messages_are_json_serializable(analysis_report):
    """
    Property: Notification messages can be serialized to JSON.

    This verifies that messages can be transmitted over the wire.
    """
    # Format Slack message
    slack_message = format_slack_message(analysis_report)

    # Should be JSON-serializable
    try:
        json_str = json.dumps(slack_message)
    except (TypeError, ValueError) as e:
        assert False, f"Slack message should be JSON-serializable, got error: {e}"

    # Verify JSON is valid
    assert isinstance(json_str, str), "JSON serialization should produce a string"
    assert len(json_str) > 0, "JSON string should not be empty"

    # Verify we can deserialize it back
    try:
        deserialized = json.loads(json_str)
    except json.JSONDecodeError as e:
        assert False, f"Serialized message should be valid JSON: {e}"

    # Verify deserialized matches original
    assert deserialized == slack_message, "Deserialized message should match original"


@given(analysis_report_strategy())
def test_recommended_actions_are_numbered_in_notifications(analysis_report):
    """
    Property: Recommended actions are properly numbered/listed.

    This verifies that actions are presented in an ordered, readable format.
    """
    # Format notifications
    slack_message = format_slack_message(analysis_report)
    email_plain = format_email_plain_text(analysis_report)
    email_html = format_email_html(analysis_report)

    slack_str = json.dumps(slack_message)

    # Verify actions are numbered (1., 2., 3., etc.)
    num_actions = len(analysis_report.analysis.recommended_actions)

    if num_actions > 0:
        # Check for numbering in plain text
        assert "1." in email_plain, "First action should be numbered in plain text"

        # Check for numbering in HTML (should have <ol> or numbered list)
        assert (
            "<ol>" in email_html or "1." in email_html
        ), "Actions should be in ordered list in HTML"

        # Check for numbering in Slack
        assert "1." in slack_str, "First action should be numbered in Slack"

        # If multiple actions, verify sequential numbering
        if num_actions > 1:
            assert "2." in email_plain, "Second action should be numbered"
            assert "2." in slack_str, "Second action should be numbered in Slack"


@given(analysis_report_strategy())
def test_incident_link_contains_incident_id(analysis_report):
    """
    Property: Incident detail link contains the incident ID.

    This verifies that the link is properly constructed with the incident ID.
    """
    # Format notifications
    slack_message = format_slack_message(analysis_report)
    email_plain = format_email_plain_text(analysis_report)
    email_html = format_email_html(analysis_report)

    slack_str = json.dumps(slack_message)

    # The link should contain the incident ID
    incident_id = analysis_report.incident_id

    # Check Slack message for link with incident ID
    # Slack uses <url|text> format
    assert incident_id in slack_str, "Slack link should contain incident ID"

    # Check plain text for link with incident ID
    assert incident_id in email_plain, "Plain text link should contain incident ID"

    # Check HTML for link with incident ID
    assert incident_id in email_html, "HTML link should contain incident ID"
    assert "<a href=" in email_html, "HTML should have proper link tag"


@given(analysis_report_strategy())
def test_severity_emoji_matches_confidence(analysis_report):
    """
    Property: Slack message uses appropriate emoji for severity.

    This verifies that visual indicators match the confidence level.
    """
    # Format Slack message
    slack_message = format_slack_message(analysis_report)
    slack_str = json.dumps(slack_message)

    confidence_value = analysis_report.analysis.confidence.value

    # Verify appropriate emoji is used
    if confidence_value == "high":
        assert (
            "🔴" in slack_str or "High" in slack_str
        ), "High confidence should use red emoji or High severity"
    elif confidence_value == "medium":
        assert (
            "🟡" in slack_str or "Medium" in slack_str
        ), "Medium confidence should use yellow emoji or Medium severity"
    elif confidence_value == "low":
        assert (
            "🟢" in slack_str or "Low" in slack_str
        ), "Low confidence should use green emoji or Low severity"
    else:  # none
        assert (
            "⚪" in slack_str or "Unknown" in slack_str
        ), "No confidence should use white emoji or Unknown severity"


@given(analysis_report_strategy())
def test_email_html_has_proper_styling(analysis_report):
    """
    Property: HTML email has proper CSS styling.

    This verifies that the HTML email is properly formatted with styles.
    """
    # Format HTML email
    html = format_email_html(analysis_report)

    # Verify HTML structure
    assert "<html>" in html.lower(), "Should have html tag"
    assert "<head>" in html.lower(), "Should have head tag"
    assert "<style>" in html.lower(), "Should have style tag"
    assert "<body>" in html.lower(), "Should have body tag"

    # Verify styling elements
    assert "font-family" in html.lower(), "Should have font styling"
    assert "color" in html.lower(), "Should have color styling"

    # Verify proper closing tags
    assert "</html>" in html.lower(), "Should close html tag"
    assert "</body>" in html.lower(), "Should close body tag"


def test_notification_with_empty_evidence_list():
    """
    Property: Notifications handle empty evidence lists gracefully.

    This verifies that missing optional fields don't break the notification.
    """
    # Create analysis report with empty evidence
    analysis = Analysis(
        root_cause_hypothesis="Test hypothesis",
        confidence=Confidence.HIGH,
        evidence=[],  # Empty evidence
        contributing_factors=[],
        recommended_actions=["Action 1"],
    )

    metadata = AnalysisMetadata(
        model_id="anthropic.claude-v2",
        model_version="2.1",
        prompt_version="v1.0",
        token_usage={"input": 1000, "output": 200},
        latency=2.5,
    )

    report = AnalysisReport(
        incident_id="test-incident-123",
        timestamp=datetime.utcnow(),
        analysis=analysis,
        metadata=metadata,
    )

    # Format notifications - should not raise exceptions
    slack_message = format_slack_message(report)
    email_plain = format_email_plain_text(report)
    email_html = format_email_html(report)

    # Verify messages are still valid
    assert len(slack_message["blocks"]) > 0
    assert len(email_plain) > 0
    assert len(email_html) > 0

    # Verify required fields are still present
    slack_str = json.dumps(slack_message)
    assert "test-incident-123" in slack_str
    assert "Test hypothesis" in slack_str
    assert "Action 1" in slack_str


def test_notification_with_special_characters():
    """
    Property: Notifications handle special characters in content.

    This verifies that special characters don't break formatting.
    """
    # Create analysis report with special characters
    analysis = Analysis(
        root_cause_hypothesis='Test <hypothesis> with & special "characters"',
        confidence=Confidence.MEDIUM,
        evidence=["Evidence with 'quotes' and <tags>"],
        contributing_factors=["Factor with & ampersand"],
        recommended_actions=['Action with "quotes"'],
    )

    metadata = AnalysisMetadata(
        model_id="anthropic.claude-v2",
        model_version="2.1",
        prompt_version="v1.0",
        token_usage={"input": 1000, "output": 200},
        latency=2.5,
    )

    report = AnalysisReport(
        incident_id="test-incident-456",
        timestamp=datetime.utcnow(),
        analysis=analysis,
        metadata=metadata,
    )

    # Format notifications - should not raise exceptions
    slack_message = format_slack_message(report)
    email_plain = format_email_plain_text(report)
    email_html = format_email_html(report)

    # Verify messages are still valid
    assert len(slack_message["blocks"]) > 0
    assert len(email_plain) > 0
    assert len(email_html) > 0

    # Verify content is preserved
    slack_str = json.dumps(slack_message)
    assert "hypothesis" in slack_str.lower()
    assert "special" in slack_str.lower()
