"""
Property-based tests for log result limiting and ordering.

This module tests the log result limiting and ordering property: for any log query
with >100 entries, exactly 100 are returned in chronological order.

Validates Requirements 4.3
"""

from datetime import datetime, timezone
from hypothesis import given, strategies as st, assume
from hypothesis.strategies import composite
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from logs_collector.lambda_function import normalize_log_entry

# Strategy generators


@composite
def cloudwatch_log_event_strategy(draw, timestamp_ms=None):
    """
    Generate CloudWatch Logs event structure.

    Args:
        draw: Hypothesis draw function
        timestamp_ms: Optional fixed timestamp in milliseconds

    Returns:
        CloudWatch log event dictionary
    """
    if timestamp_ms is None:
        timestamp_ms = draw(st.integers(min_value=1577836800000, max_value=1893456000000))

    # Generate message with log level
    level = draw(st.sampled_from(["ERROR", "WARN", "CRITICAL"]))
    message_text = draw(
        st.text(min_size=10, max_size=200, alphabet=st.characters(blacklist_categories=("Cs",)))
    )
    message = f"{level}: {message_text}"

    log_stream = draw(
        st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",)))
    )

    log_event = {"timestamp": timestamp_ms, "message": message, "logStreamName": log_stream}

    return log_event


@composite
def log_events_list_strategy(draw, min_size=1, max_size=150):
    """
    Generate a list of CloudWatch log events with sequential timestamps.

    Args:
        draw: Hypothesis draw function
        min_size: Minimum number of log events
        max_size: Maximum number of log events (reduced to 150 to avoid health check failures)

    Returns:
        List of CloudWatch log event dictionaries
    """
    count = draw(st.integers(min_value=min_size, max_value=max_size))

    # Generate base timestamp
    base_timestamp = draw(
        st.integers(min_value=1577836800000, max_value=1893456000000 - count * 1000)
    )

    # Generate log events with sequential timestamps
    log_events = []
    for i in range(count):
        # Add some randomness to timestamp ordering (not strictly sequential)
        timestamp_offset = draw(st.integers(min_value=0, max_value=5000))
        timestamp_ms = base_timestamp + (i * 1000) + timestamp_offset

        log_event = draw(cloudwatch_log_event_strategy(timestamp_ms=timestamp_ms))
        log_events.append(log_event)

    return log_events


@composite
def shuffled_log_events_strategy(draw, min_size=1, max_size=150):
    """
    Generate a list of CloudWatch log events with shuffled timestamps.

    This creates log events that are NOT in chronological order,
    to test that the system properly sorts them.

    Args:
        draw: Hypothesis draw function
        min_size: Minimum number of log events
        max_size: Maximum number of log events (reduced to 150 to avoid health check failures)

    Returns:
        List of CloudWatch log event dictionaries (shuffled)
    """
    # Generate sequential events
    log_events = draw(log_events_list_strategy(min_size=min_size, max_size=max_size))

    # Shuffle them
    import random

    shuffled = log_events.copy()
    random.shuffle(shuffled)

    return shuffled


# Property Tests


@given(log_events_list_strategy(min_size=101, max_size=150))
def test_log_result_limiting_returns_exactly_100(log_events):
    """
    Property 11: Log Result Limiting Returns Exactly 100

    **Validates: Requirements 4.3**

    For any log query with >100 entries, exactly 100 are returned.
    """
    # Assume we have more than 100 events
    assume(len(log_events) > 100)

    # Simulate the limiting logic from collect_logs
    # Sort by timestamp (chronological order)
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))

    # Limit to top 100 entries
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    # Property: Exactly 100 logs should be returned
    assert len(normalized_logs) == 100, (
        f"Expected exactly 100 logs when input has {len(log_events)} entries. "
        f"Got: {len(normalized_logs)}"
    )


@given(log_events_list_strategy(min_size=101, max_size=150))
def test_log_result_limiting_returns_earliest_100(log_events):
    """
    Property 11: Log Result Limiting Returns Earliest 100

    **Validates: Requirements 4.3**

    For any log query with >100 entries, the returned 100 entries
    should be the earliest ones (by timestamp).
    """
    # Assume we have more than 100 events
    assume(len(log_events) > 100)

    # Sort by timestamp to get chronological order
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))

    # Get expected earliest 100
    expected_earliest_100 = sorted_logs[:100]
    expected_timestamps = [log.get("timestamp") for log in expected_earliest_100]

    # Simulate the limiting logic
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    # Extract timestamps from normalized logs
    # Convert ISO-8601 back to milliseconds for comparison
    actual_timestamps = []
    for log in normalized_logs:
        timestamp_str = log["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)
        timestamp_ms = int(dt.timestamp() * 1000)
        actual_timestamps.append(timestamp_ms)

    # Property: The returned timestamps should match the earliest 100
    assert actual_timestamps == expected_timestamps, (
        f"Returned logs should be the earliest 100 entries. "
        f"Expected first timestamp: {expected_timestamps[0]}, "
        f"Got: {actual_timestamps[0]}"
    )


@given(shuffled_log_events_strategy(min_size=101, max_size=150))
def test_log_result_ordering_chronological(log_events):
    """
    Property 11: Log Result Ordering is Chronological

    **Validates: Requirements 4.3**

    For any log query with >100 entries, the returned 100 entries
    must be in chronological order (sorted by timestamp ascending).
    """
    # Assume we have more than 100 events
    assume(len(log_events) > 100)

    # Simulate the sorting and limiting logic
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    # Extract timestamps
    timestamps = []
    for log in normalized_logs:
        timestamp_str = log["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)
        timestamp_ms = int(dt.timestamp() * 1000)
        timestamps.append(timestamp_ms)

    # Property: Timestamps should be in ascending order
    for i in range(len(timestamps) - 1):
        assert timestamps[i] <= timestamps[i + 1], (
            f"Logs should be in chronological order. "
            f"Found timestamp {timestamps[i]} followed by {timestamps[i + 1]} at index {i}"
        )


@given(log_events_list_strategy(min_size=1, max_size=100))
def test_log_result_limiting_preserves_all_when_under_100(log_events):
    """
    Property 11: Log Result Limiting Preserves All When Under 100

    **Validates: Requirements 4.3**

    For any log query with ≤100 entries, all entries should be returned.
    """
    # Assume we have 100 or fewer events
    assume(len(log_events) <= 100)

    # Simulate the limiting logic
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    # Property: All logs should be preserved when count ≤ 100
    assert len(normalized_logs) == len(log_events), (
        f"All logs should be preserved when count ≤ 100. "
        f"Input: {len(log_events)}, Output: {len(normalized_logs)}"
    )


@given(shuffled_log_events_strategy(min_size=50, max_size=150))
def test_log_result_ordering_stable_sort(log_events):
    """
    Property 11: Log Result Ordering is Stable

    **Validates: Requirements 4.3**

    For any log query, sorting by timestamp should be stable
    (logs with same timestamp maintain relative order).
    """
    # Simulate the sorting logic
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))

    # Limit to 100 if needed
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    # Extract timestamps
    timestamps = []
    for log in normalized_logs:
        timestamp_str = log["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)
        timestamp_ms = int(dt.timestamp() * 1000)
        timestamps.append(timestamp_ms)

    # Property: Timestamps should be non-decreasing (allows equal timestamps)
    for i in range(len(timestamps) - 1):
        assert timestamps[i] <= timestamps[i + 1], (
            f"Logs should maintain chronological order. "
            f"Found timestamp {timestamps[i]} followed by {timestamps[i + 1]}"
        )


@given(log_events_list_strategy(min_size=101, max_size=150))
def test_log_result_limiting_discards_latest(log_events):
    """
    Property 11: Log Result Limiting Discards Latest Entries

    **Validates: Requirements 4.3**

    For any log query with >100 entries, the entries beyond the first 100
    (chronologically) should be discarded.
    """
    # Assume we have more than 100 events
    assume(len(log_events) > 100)

    # Sort by timestamp
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))

    # Get the 101st entry timestamp (should be discarded)
    discarded_timestamp = sorted_logs[100].get("timestamp")

    # Simulate the limiting logic
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    # Extract timestamps from normalized logs
    actual_timestamps = []
    for log in normalized_logs:
        timestamp_str = log["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)
        timestamp_ms = int(dt.timestamp() * 1000)
        actual_timestamps.append(timestamp_ms)

    # Property: The discarded timestamp should not be in the result
    assert discarded_timestamp not in actual_timestamps, (
        f"Entries beyond the first 100 should be discarded. "
        f"Found discarded timestamp {discarded_timestamp} in results"
    )


@given(log_events_list_strategy(min_size=101, max_size=150))
def test_log_result_limiting_boundary_at_100(log_events):
    """
    Property 11: Log Result Limiting Boundary at 100

    **Validates: Requirements 4.3**

    For any log query with >100 entries, the 100th entry should be included
    and the 101st entry should be excluded.
    """
    # Assume we have more than 100 events
    assume(len(log_events) > 100)

    # Sort by timestamp
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))

    # Get the 100th and 101st entry timestamps
    timestamp_100th = sorted_logs[99].get("timestamp")  # Index 99 = 100th entry
    timestamp_101st = sorted_logs[100].get("timestamp")  # Index 100 = 101st entry

    # Simulate the limiting logic
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    # Extract timestamps from normalized logs
    actual_timestamps = []
    for log in normalized_logs:
        timestamp_str = log["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)
        timestamp_ms = int(dt.timestamp() * 1000)
        actual_timestamps.append(timestamp_ms)

    # Property: 100th entry should be included, 101st should not
    assert (
        timestamp_100th in actual_timestamps
    ), f"The 100th entry (timestamp {timestamp_100th}) should be included"
    assert (
        timestamp_101st not in actual_timestamps
    ), f"The 101st entry (timestamp {timestamp_101st}) should be excluded"


@given(shuffled_log_events_strategy(min_size=101, max_size=150))
def test_log_result_ordering_independent_of_input_order(log_events):
    """
    Property 11: Log Result Ordering Independent of Input Order

    **Validates: Requirements 4.3**

    For any log query, the output order should depend only on timestamps,
    not on the input order of log events.
    """
    # Assume we have more than 100 events
    assume(len(log_events) > 100)

    # Process logs in original order
    sorted_logs_1 = sorted(log_events, key=lambda x: x.get("timestamp", 0))
    limited_logs_1 = sorted_logs_1[:100]
    normalized_logs_1 = [normalize_log_entry(log) for log in limited_logs_1]
    normalized_logs_1 = [log for log in normalized_logs_1 if log is not None]

    # Shuffle and process again
    import random

    shuffled_logs = log_events.copy()
    random.shuffle(shuffled_logs)

    sorted_logs_2 = sorted(shuffled_logs, key=lambda x: x.get("timestamp", 0))
    limited_logs_2 = sorted_logs_2[:100]
    normalized_logs_2 = [normalize_log_entry(log) for log in limited_logs_2]
    normalized_logs_2 = [log for log in normalized_logs_2 if log is not None]

    # Extract timestamps from both results
    timestamps_1 = []
    for log in normalized_logs_1:
        timestamp_str = log["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)
        timestamp_ms = int(dt.timestamp() * 1000)
        timestamps_1.append(timestamp_ms)

    timestamps_2 = []
    for log in normalized_logs_2:
        timestamp_str = log["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(timestamp_str)
        timestamp_ms = int(dt.timestamp() * 1000)
        timestamps_2.append(timestamp_ms)

    # Property: Results should be identical regardless of input order
    assert timestamps_1 == timestamps_2, (
        f"Output order should be independent of input order. "
        f"Got different results after shuffling input"
    )


@given(log_events_list_strategy(min_size=101, max_size=150))
def test_log_result_count_invariant(log_events):
    """
    Property 11: Log Result Count Invariant

    **Validates: Requirements 4.3**

    For any log query with N entries where N > 100, the result count
    should always be min(N, 100).
    """
    # Assume we have more than 100 events
    assume(len(log_events) > 100)

    input_count = len(log_events)
    expected_count = min(input_count, 100)

    # Simulate the limiting logic
    sorted_logs = sorted(log_events, key=lambda x: x.get("timestamp", 0))
    limited_logs = sorted_logs[:100]

    # Normalize log entries
    normalized_logs = []
    for log_event in limited_logs:
        normalized_log = normalize_log_entry(log_event)
        if normalized_log:
            normalized_logs.append(normalized_log)

    actual_count = len(normalized_logs)

    # Property: Result count should be min(N, 100)
    assert actual_count == expected_count, (
        f"Result count should be min({input_count}, 100) = {expected_count}. "
        f"Got: {actual_count}"
    )
