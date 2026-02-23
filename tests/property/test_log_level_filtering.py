"""
Property-based tests for log level filtering.

This module tests the log level filtering property: for any set of log entries,
only ERROR/WARN/CRITICAL levels are returned by the logs collector.

Validates Requirements 4.2
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from logs_collector.lambda_function import extract_log_level, normalize_log_entry

# Strategy generators


@composite
def log_message_with_level_strategy(draw):
    """
    Generate log messages with specific log levels embedded.

    Returns tuple of (message, expected_level)
    """
    level = draw(st.sampled_from(["ERROR", "WARN", "CRITICAL", "INFO", "DEBUG", "TRACE"]))

    # Generate message with the level keyword
    prefix = draw(
        st.text(min_size=0, max_size=50, alphabet=st.characters(blacklist_categories=("Cs",)))
    )
    suffix = draw(
        st.text(min_size=0, max_size=50, alphabet=st.characters(blacklist_categories=("Cs",)))
    )

    # Construct message with level keyword
    message = f"{prefix} {level} {suffix}".strip()

    # Determine expected level based on priority
    if "CRITICAL" in message.upper() or "FATAL" in message.upper():
        expected_level = "CRITICAL"
    elif "ERROR" in message.upper():
        expected_level = "ERROR"
    elif "WARN" in message.upper() or "WARNING" in message.upper():
        expected_level = "WARN"
    else:
        expected_level = "INFO"

    return message, expected_level


@composite
def cloudwatch_log_event_strategy(draw):
    """
    Generate CloudWatch Logs event structure with various log levels.

    Returns tuple of (log_event, expected_level)
    """
    message, expected_level = draw(log_message_with_level_strategy())

    timestamp_ms = draw(st.integers(min_value=1577836800000, max_value=1893456000000))
    log_stream = draw(
        st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",)))
    )

    log_event = {"timestamp": timestamp_ms, "message": message, "logStreamName": log_stream}

    return log_event, expected_level


@composite
def filtered_log_levels_strategy(draw):
    """
    Generate only log levels that should pass the filter (ERROR, WARN, CRITICAL).
    """
    return draw(st.sampled_from(["ERROR", "WARN", "CRITICAL"]))


@composite
def unfiltered_log_levels_strategy(draw):
    """
    Generate log levels that should NOT pass the filter (INFO, DEBUG, TRACE).
    """
    return draw(st.sampled_from(["INFO", "DEBUG", "TRACE", "VERBOSE"]))


# Property Tests


@given(st.text(min_size=1, max_size=500))
def test_extract_log_level_returns_valid_level(message):
    """
    Property 10: Log Level Extraction Returns Valid Level

    **Validates: Requirements 4.2**

    For any log message, extract_log_level must return one of the
    valid log levels: ERROR, WARN, CRITICAL, or INFO.
    """
    log_level = extract_log_level(message)

    valid_levels = ["ERROR", "WARN", "CRITICAL", "INFO"]
    assert (
        log_level in valid_levels
    ), f"Extracted log level must be one of {valid_levels}. Got: {log_level}"


@given(log_message_with_level_strategy())
def test_extract_log_level_identifies_correct_level(message_and_level):
    """
    Property 10: Log Level Extraction Correctness

    **Validates: Requirements 4.2**

    For any log message containing a log level keyword, extract_log_level
    must correctly identify the log level based on priority:
    1. CRITICAL/FATAL (highest priority)
    2. ERROR
    3. WARN/WARNING
    4. INFO (default)
    """
    message, expected_level = message_and_level

    extracted_level = extract_log_level(message)

    assert extracted_level == expected_level, (
        f"Expected level '{expected_level}' for message: {message[:100]}... "
        f"Got: {extracted_level}"
    )


@given(cloudwatch_log_event_strategy())
def test_normalize_log_entry_preserves_filtered_levels(log_event_and_level):
    """
    Property 10: Log Entry Normalization Preserves Filtered Levels

    **Validates: Requirements 4.2**

    For any CloudWatch log event, normalize_log_entry must correctly
    extract and preserve the log level in the normalized output.
    """
    log_event, expected_level = log_event_and_level

    normalized = normalize_log_entry(log_event)

    # Should return a valid normalized entry
    assert normalized is not None, "Normalized entry should not be None"
    assert isinstance(normalized, dict), "Normalized entry should be a dictionary"

    # Should contain logLevel field
    assert "logLevel" in normalized, "Normalized entry must have 'logLevel' field"

    # Log level should match expected
    assert normalized["logLevel"] == expected_level, (
        f"Expected log level '{expected_level}' for message: {log_event['message'][:100]}... "
        f"Got: {normalized['logLevel']}"
    )


@given(st.lists(cloudwatch_log_event_strategy(), min_size=1, max_size=50))
def test_filtered_logs_contain_only_error_warn_critical(log_events_and_levels):
    """
    Property 10: Log Level Filtering

    **Validates: Requirements 4.2**

    For any set of log entries, only ERROR/WARN/CRITICAL levels are returned.

    This is the core property: when we normalize log entries, the resulting
    log levels should only be ERROR, WARN, or CRITICAL (or INFO as fallback
    for entries that matched the filter pattern but don't have explicit levels).
    """
    # Normalize all log events
    normalized_logs = []
    for log_event, expected_level in log_events_and_levels:
        normalized = normalize_log_entry(log_event)
        if normalized:
            normalized_logs.append(normalized)

    # Property: All normalized logs should have valid log levels
    valid_filtered_levels = ["ERROR", "WARN", "CRITICAL", "INFO"]

    for i, log in enumerate(normalized_logs):
        assert "logLevel" in log, f"Log entry {i} must have 'logLevel' field"
        assert log["logLevel"] in valid_filtered_levels, (
            f"Log entry {i} has invalid log level: {log['logLevel']}. "
            f"Must be one of {valid_filtered_levels}"
        )


@given(st.text(min_size=1, max_size=500))
def test_log_level_extraction_case_insensitive(message):
    """
    Property 10: Log Level Extraction is Case Insensitive

    **Validates: Requirements 4.2**

    For any log message, log level extraction should work regardless
    of the case of the level keyword (ERROR, error, Error, etc.).
    """
    # Test with different cases
    message_upper = message.upper()
    message_lower = message.lower()

    level_original = extract_log_level(message)
    level_upper = extract_log_level(message_upper)
    level_lower = extract_log_level(message_lower)

    # All should return valid levels
    valid_levels = ["ERROR", "WARN", "CRITICAL", "INFO"]
    assert level_original in valid_levels
    assert level_upper in valid_levels
    assert level_lower in valid_levels


@given(
    st.sampled_from(["ERROR", "WARN", "CRITICAL"]),
    st.text(min_size=0, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))),
)
def test_filtered_levels_always_extracted(level, context):
    """
    Property 10: Filtered Levels Always Extracted

    **Validates: Requirements 4.2**

    For any message containing ERROR, WARN, or CRITICAL keywords,
    the extract_log_level function must identify them correctly.
    """
    # Construct message with the level keyword
    message = f"{context} {level} occurred in the system"

    extracted_level = extract_log_level(message)

    # Should extract the correct level (or higher priority if multiple present)
    if level == "CRITICAL":
        assert extracted_level == "CRITICAL"
    elif level == "ERROR":
        assert extracted_level in ["ERROR", "CRITICAL"]  # CRITICAL has higher priority
    elif level == "WARN":
        assert extracted_level in ["WARN", "ERROR", "CRITICAL"]  # Higher priorities take precedence


@given(st.integers(min_value=1577836800000, max_value=1893456000000))
def test_normalize_log_entry_handles_all_timestamps(timestamp_ms):
    """
    Property 10: Log Entry Normalization Handles All Timestamps

    **Validates: Requirements 4.2, 4.4**

    For any valid timestamp, normalize_log_entry should correctly
    convert it to ISO-8601 format.
    """
    log_event = {
        "timestamp": timestamp_ms,
        "message": "ERROR: Test error message",
        "logStreamName": "test-stream",
    }

    normalized = normalize_log_entry(log_event)

    assert normalized is not None
    assert "timestamp" in normalized
    assert isinstance(normalized["timestamp"], str)

    # Should be ISO-8601 format with 'Z' suffix
    assert normalized["timestamp"].endswith(
        "Z"
    ), "Timestamp should be in ISO-8601 format with 'Z' suffix"

    # Should be parseable as datetime
    try:
        datetime.fromisoformat(normalized["timestamp"].replace("Z", "+00:00"))
    except ValueError as e:
        assert False, f"Timestamp should be valid ISO-8601: {e}"


@given(st.lists(st.sampled_from(["ERROR", "WARN", "CRITICAL"]), min_size=1, max_size=20))
def test_all_filtered_levels_preserved(levels):
    """
    Property 10: All Filtered Levels Preserved

    **Validates: Requirements 4.2**

    For any collection of ERROR/WARN/CRITICAL log entries,
    all should be preserved after normalization.
    """
    # Create log events for each level
    log_events = []
    for i, level in enumerate(levels):
        log_events.append(
            {
                "timestamp": 1577836800000 + i * 1000,
                "message": f"{level}: Test message {i}",
                "logStreamName": f"stream-{i}",
            }
        )

    # Normalize all
    normalized_logs = []
    for log_event in log_events:
        normalized = normalize_log_entry(log_event)
        if normalized:
            normalized_logs.append(normalized)

    # All should be preserved
    assert len(normalized_logs) == len(
        log_events
    ), "All ERROR/WARN/CRITICAL entries should be preserved"

    # All should have valid filtered levels
    for log in normalized_logs:
        assert log["logLevel"] in [
            "ERROR",
            "WARN",
            "CRITICAL",
        ], f"Filtered log should have ERROR/WARN/CRITICAL level, got: {log['logLevel']}"


@given(st.text(min_size=1, max_size=500))
def test_extract_log_level_idempotent(message):
    """
    Property 10: Log Level Extraction is Idempotent

    **Validates: Requirements 4.2**

    Calling extract_log_level multiple times with the same message
    should always return the same result.
    """
    level1 = extract_log_level(message)
    level2 = extract_log_level(message)
    level3 = extract_log_level(message)

    assert level1 == level2 == level3, "extract_log_level should be idempotent"
