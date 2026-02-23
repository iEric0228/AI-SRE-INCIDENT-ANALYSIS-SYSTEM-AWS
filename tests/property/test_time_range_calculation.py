"""
Property-based tests for time range calculation.

This module tests the time range calculation property: for any timestamp,
the metrics time range must be exactly -60 minutes to +5 minutes.

Validates Requirements 3.1
"""

from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from metrics_collector.lambda_function import calculate_time_range

# Strategy generators


@composite
def datetime_strategy(draw):
    """
    Generate arbitrary datetime objects with timezone info.

    Generates timestamps in a reasonable range (2020-2030) to avoid
    edge cases with very old or very future dates.
    """
    # Generate timestamp in range: 2020-01-01 to 2030-12-31
    timestamp = draw(st.integers(min_value=1577836800, max_value=1924905600))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


# Property Tests


@given(datetime_strategy())
def test_time_range_calculation_correctness(incident_timestamp):
    """
    Property 8: Time Range Calculation Correctness

    **Validates: Requirements 3.1**

    For any timestamp, metrics time range must be exactly -60min to +5min.

    This property ensures that:
    1. Start time is exactly 60 minutes before the incident timestamp
    2. End time is exactly 5 minutes after the incident timestamp
    3. The time range is always 65 minutes total
    """
    # Calculate time range using the function under test
    start_time, end_time = calculate_time_range(incident_timestamp)

    # Property 1: Start time must be exactly 60 minutes before incident
    expected_start = incident_timestamp - timedelta(minutes=60)
    assert start_time == expected_start, (
        f"Start time should be exactly 60 minutes before incident. "
        f"Expected: {expected_start}, Got: {start_time}"
    )

    # Property 2: End time must be exactly 5 minutes after incident
    expected_end = incident_timestamp + timedelta(minutes=5)
    assert end_time == expected_end, (
        f"End time should be exactly 5 minutes after incident. "
        f"Expected: {expected_end}, Got: {end_time}"
    )

    # Property 3: Total time range must be exactly 65 minutes
    time_range_duration = end_time - start_time
    expected_duration = timedelta(minutes=65)
    assert time_range_duration == expected_duration, (
        f"Total time range should be exactly 65 minutes. "
        f"Expected: {expected_duration}, Got: {time_range_duration}"
    )

    # Property 4: Start time must be before end time
    assert start_time < end_time, (
        f"Start time must be before end time. " f"Start: {start_time}, End: {end_time}"
    )

    # Property 5: Incident timestamp must be within the range
    assert start_time <= incident_timestamp <= end_time, (
        f"Incident timestamp must be within the calculated range. "
        f"Range: [{start_time}, {end_time}], Incident: {incident_timestamp}"
    )


@given(datetime_strategy())
def test_time_range_preserves_timezone(incident_timestamp):
    """
    Property: Time Range Calculation Preserves Timezone

    **Validates: Requirements 3.1**

    For any timestamp with timezone info, the calculated time range
    must preserve the timezone information.
    """
    start_time, end_time = calculate_time_range(incident_timestamp)

    # If input has timezone, output should have timezone
    if incident_timestamp.tzinfo is not None:
        assert start_time.tzinfo is not None, "Start time should preserve timezone information"
        assert end_time.tzinfo is not None, "End time should preserve timezone information"


@given(st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)))
def test_time_range_handles_naive_datetimes(incident_timestamp):
    """
    Property: Time Range Calculation Handles Naive Datetimes

    **Validates: Requirements 3.1**

    For any naive datetime (without timezone), the function should still
    calculate the correct time range with proper offsets.
    """
    start_time, end_time = calculate_time_range(incident_timestamp)

    # Calculate expected values
    expected_start = incident_timestamp - timedelta(minutes=60)
    expected_end = incident_timestamp + timedelta(minutes=5)

    # Verify correctness regardless of timezone awareness
    assert (start_time - expected_start).total_seconds() == 0, (
        f"Start time calculation incorrect for naive datetime. "
        f"Expected: {expected_start}, Got: {start_time}"
    )

    assert (end_time - expected_end).total_seconds() == 0, (
        f"End time calculation incorrect for naive datetime. "
        f"Expected: {expected_end}, Got: {end_time}"
    )


@given(datetime_strategy())
def test_time_range_idempotent(incident_timestamp):
    """
    Property: Time Range Calculation is Idempotent

    **Validates: Requirements 3.1**

    Calling calculate_time_range multiple times with the same input
    should always produce the same output.
    """
    # Calculate time range twice
    start_time_1, end_time_1 = calculate_time_range(incident_timestamp)
    start_time_2, end_time_2 = calculate_time_range(incident_timestamp)

    # Results should be identical
    assert start_time_1 == start_time_2, "Start time should be consistent across multiple calls"
    assert end_time_1 == end_time_2, "End time should be consistent across multiple calls"


@given(datetime_strategy(), datetime_strategy())
def test_time_range_monotonic(timestamp1, timestamp2):
    """
    Property: Time Range Calculation is Monotonic

    **Validates: Requirements 3.1**

    If timestamp A is before timestamp B, then the time range for A
    should be entirely before the time range for B (or they overlap
    in a predictable way based on the 65-minute window).
    """
    # Ensure timestamp1 is before timestamp2
    if timestamp1 > timestamp2:
        timestamp1, timestamp2 = timestamp2, timestamp1

    start_time_1, end_time_1 = calculate_time_range(timestamp1)
    start_time_2, end_time_2 = calculate_time_range(timestamp2)

    # If timestamps are the same, ranges should be the same
    if timestamp1 == timestamp2:
        assert start_time_1 == start_time_2
        assert end_time_1 == end_time_2
    else:
        # If timestamp1 < timestamp2, then start1 < start2 and end1 < end2
        assert start_time_1 < start_time_2, "Earlier timestamp should produce earlier start time"
        assert end_time_1 < end_time_2, "Earlier timestamp should produce earlier end time"
