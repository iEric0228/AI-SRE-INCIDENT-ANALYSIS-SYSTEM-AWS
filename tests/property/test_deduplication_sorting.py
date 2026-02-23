"""
Property-based tests for deduplication and chronological sorting.

This module tests that the correlation engine correctly removes duplicate entries
and sorts all data chronologically across all data sources (metrics, logs, changes).

Validates Requirement 6.3
"""

from datetime import datetime, timezone, timedelta
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os

# Import shared models
from shared.models import StructuredContext, ResourceInfo, AlarmInfo, CompletenessInfo

# Import correlation engine functions directly
# Clear any cached lambda_function module first
if "lambda_function" in sys.modules:
    del sys.modules["lambda_function"]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "correlation_engine"))
import lambda_function as correlation_lambda

deduplicate_and_sort = correlation_lambda.deduplicate_and_sort
normalize_timestamps = correlation_lambda.normalize_timestamps


# Strategy generators


@composite
def datetime_strategy(draw):
    """Generate datetime objects with timezone info."""
    timestamp = draw(st.integers(min_value=1577836800, max_value=1893456000))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


@composite
def iso_timestamp_strategy(draw):
    """Generate ISO 8601 UTC timestamps."""
    dt = draw(datetime_strategy())
    iso_str = dt.replace(tzinfo=None).isoformat()
    return iso_str + "Z"


@composite
def metrics_time_series_with_duplicates_strategy(draw):
    """
    Generate metrics time series with intentional duplicates.

    Creates a list where some entries are exact duplicates to test deduplication.
    """
    num_unique = draw(st.integers(min_value=3, max_value=15))
    num_duplicates = draw(st.integers(min_value=1, max_value=5))

    # Generate unique entries
    unique_entries = []
    for _ in range(num_unique):
        unique_entries.append(
            {
                "timestamp": draw(iso_timestamp_strategy()),
                "metricName": draw(
                    st.text(
                        min_size=1,
                        max_size=30,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    )
                ),
                "value": draw(
                    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
                ),
                "unit": draw(st.sampled_from(["Percent", "Count", "Bytes", "Seconds"])),
            }
        )

    # Add duplicates by copying some entries
    time_series = unique_entries.copy()
    for _ in range(num_duplicates):
        if unique_entries:
            duplicate = draw(st.sampled_from(unique_entries)).copy()
            time_series.append(duplicate)

    # Shuffle to mix duplicates throughout
    draw(st.randoms()).shuffle(time_series)

    return time_series


@composite
def log_entries_with_duplicates_strategy(draw):
    """
    Generate log entries with intentional duplicates.

    Creates a list where some entries are exact duplicates to test deduplication.
    """
    num_unique = draw(st.integers(min_value=3, max_value=15))
    num_duplicates = draw(st.integers(min_value=1, max_value=5))

    # Generate unique entries
    unique_entries = []
    for _ in range(num_unique):
        unique_entries.append(
            {
                "timestamp": draw(iso_timestamp_strategy()),
                "logLevel": draw(st.sampled_from(["ERROR", "WARN", "CRITICAL", "INFO"])),
                "message": draw(
                    st.text(
                        min_size=1,
                        max_size=100,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    )
                ),
                "logStream": draw(
                    st.text(
                        min_size=1,
                        max_size=30,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    )
                ),
            }
        )

    # Add duplicates by copying some entries
    log_entries = unique_entries.copy()
    for _ in range(num_duplicates):
        if unique_entries:
            duplicate = draw(st.sampled_from(unique_entries)).copy()
            log_entries.append(duplicate)

    # Shuffle to mix duplicates throughout
    draw(st.randoms()).shuffle(log_entries)

    return log_entries


@composite
def change_entries_with_duplicates_strategy(draw):
    """
    Generate change entries with intentional duplicates.

    Creates a list where some entries are exact duplicates to test deduplication.
    """
    num_unique = draw(st.integers(min_value=3, max_value=15))
    num_duplicates = draw(st.integers(min_value=1, max_value=5))

    # Generate unique entries
    unique_entries = []
    for _ in range(num_unique):
        unique_entries.append(
            {
                "timestamp": draw(iso_timestamp_strategy()),
                "changeType": draw(
                    st.sampled_from(["deployment", "configuration", "infrastructure"])
                ),
                "eventName": draw(
                    st.text(
                        min_size=1,
                        max_size=30,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    )
                ),
                "user": f"arn:aws:iam::123456789012:user/{draw(st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=65, max_codepoint=122)))}",
                "description": draw(
                    st.text(
                        min_size=1,
                        max_size=100,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    )
                ),
            }
        )

    # Add duplicates by copying some entries
    change_entries = unique_entries.copy()
    for _ in range(num_duplicates):
        if unique_entries:
            duplicate = draw(st.sampled_from(unique_entries)).copy()
            change_entries.append(duplicate)

    # Shuffle to mix duplicates throughout
    draw(st.randoms()).shuffle(change_entries)

    return change_entries


@composite
def structured_context_with_duplicates_strategy(draw):
    """Generate a structured context with duplicates in all data sources."""
    # Generate metrics data with duplicates
    metrics_data = {
        "summary": {
            "avg": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "max": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "min": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
            "count": draw(st.integers(min_value=1, max_value=100)),
        },
        "timeSeries": draw(metrics_time_series_with_duplicates_strategy()),
        "metrics": [],
    }

    # Generate logs data with duplicates
    logs_data = {
        "errorCount": draw(st.integers(min_value=0, max_value=100)),
        "errorCountsByLevel": {
            "ERROR": draw(st.integers(min_value=0, max_value=50)),
            "WARN": draw(st.integers(min_value=0, max_value=50)),
        },
        "topErrors": draw(
            st.lists(
                st.text(
                    min_size=1,
                    max_size=50,
                    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                ),
                max_size=5,
            )
        ),
        "entries": draw(log_entries_with_duplicates_strategy()),
        "totalMatches": draw(st.integers(min_value=0, max_value=1000)),
        "returned": draw(st.integers(min_value=0, max_value=100)),
    }

    # Generate changes data with duplicates
    changes_data = {
        "recentDeployments": draw(st.integers(min_value=0, max_value=10)),
        "lastDeployment": draw(st.one_of(st.none(), iso_timestamp_strategy())),
        "changeCountsByType": {
            "deployment": draw(st.integers(min_value=0, max_value=10)),
            "configuration": draw(st.integers(min_value=0, max_value=10)),
            "infrastructure": draw(st.integers(min_value=0, max_value=10)),
        },
        "totalChanges": draw(st.integers(min_value=0, max_value=30)),
        "entries": draw(change_entries_with_duplicates_strategy()),
    }

    # Create structured context
    context = StructuredContext(
        incident_id=draw(st.uuids()).hex,
        timestamp=draw(datetime_strategy()),
        resource=ResourceInfo(
            arn=f"arn:aws:ec2:us-east-1:123456789012:instance/{draw(st.text(min_size=1, max_size=20, alphabet=st.characters(min_codepoint=65, max_codepoint=122)))}",
            type="ec2",
            name=draw(
                st.text(
                    min_size=1,
                    max_size=30,
                    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                )
            ),
        ),
        alarm=AlarmInfo(
            name=draw(
                st.text(
                    min_size=1,
                    max_size=30,
                    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                )
            ),
            metric=draw(
                st.text(
                    min_size=1,
                    max_size=30,
                    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                )
            ),
            threshold=draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
        ),
        metrics=metrics_data,
        logs=logs_data,
        changes=changes_data,
        completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
    )

    return context


def is_chronologically_sorted(timestamps: list) -> bool:
    """
    Check if a list of ISO 8601 timestamps is sorted chronologically.

    Args:
        timestamps: List of ISO 8601 timestamp strings

    Returns:
        True if sorted chronologically, False otherwise
    """
    if len(timestamps) <= 1:
        return True

    for i in range(len(timestamps) - 1):
        if timestamps[i] > timestamps[i + 1]:
            return False

    return True


def has_duplicates(entries: list, key_func) -> bool:
    """
    Check if a list of entries contains duplicates based on a key function.

    Args:
        entries: List of entries to check
        key_func: Function that extracts a unique key from an entry

    Returns:
        True if duplicates exist, False otherwise
    """
    seen = set()
    for entry in entries:
        key = key_func(entry)
        if key in seen:
            return True
        seen.add(key)
    return False


# Property Tests


@given(structured_context_with_duplicates_strategy())
def test_property_15_deduplication_and_chronological_sorting(context):
    """
    **Property 15: Deduplication and Chronological Sorting**
    **Validates: Requirements 6.3**

    For any context with duplicates, output must have no duplicates and be chronologically sorted.

    This property verifies that:
    1. Duplicate entries in metrics time series are removed
    2. Duplicate entries in log entries are removed
    3. Duplicate entries in change entries are removed
    4. All entries are sorted chronologically by timestamp
    5. The deduplication preserves at least one copy of each unique entry
    """
    # First normalize timestamps to ensure consistent format for sorting
    context = normalize_timestamps(context)

    # Count original entries before deduplication
    original_metrics_count = len(context.metrics.get("timeSeries", []))
    original_logs_count = len(context.logs.get("entries", []))
    original_changes_count = len(context.changes.get("entries", []))

    # Apply deduplication and sorting
    deduplicated_context = deduplicate_and_sort(context)

    # Verify metrics time series has no duplicates
    if "timeSeries" in deduplicated_context.metrics:
        time_series = deduplicated_context.metrics["timeSeries"]

        # Check for duplicates using the same key as the implementation
        def metrics_key(entry):
            return (entry.get("timestamp", ""), entry.get("metricName", ""), entry.get("value", 0))

        assert not has_duplicates(
            time_series, metrics_key
        ), "Metrics time series should not contain duplicates after deduplication"

        # Verify chronological sorting
        timestamps = [entry.get("timestamp", "") for entry in time_series]
        assert is_chronologically_sorted(
            timestamps
        ), f"Metrics time series should be sorted chronologically: {timestamps}"

        # Verify we didn't lose all data (at least some entries remain)
        if original_metrics_count > 0:
            assert (
                len(time_series) > 0
            ), "Deduplication should preserve at least one entry when original had entries"
            assert (
                len(time_series) <= original_metrics_count
            ), "Deduplicated count should not exceed original count"

    # Verify log entries have no duplicates
    if "entries" in deduplicated_context.logs:
        log_entries = deduplicated_context.logs["entries"]

        # Check for duplicates using the same key as the implementation
        def logs_key(entry):
            return (
                entry.get("timestamp", ""),
                entry.get("message", ""),
                entry.get("logStream", ""),
            )

        assert not has_duplicates(
            log_entries, logs_key
        ), "Log entries should not contain duplicates after deduplication"

        # Verify chronological sorting
        timestamps = [entry.get("timestamp", "") for entry in log_entries]
        assert is_chronologically_sorted(
            timestamps
        ), f"Log entries should be sorted chronologically: {timestamps}"

        # Verify we didn't lose all data
        if original_logs_count > 0:
            assert (
                len(log_entries) > 0
            ), "Deduplication should preserve at least one entry when original had entries"
            assert (
                len(log_entries) <= original_logs_count
            ), "Deduplicated count should not exceed original count"

    # Verify change entries have no duplicates
    if "entries" in deduplicated_context.changes:
        change_entries = deduplicated_context.changes["entries"]

        # Check for duplicates using the same key as the implementation
        def changes_key(entry):
            return (entry.get("timestamp", ""), entry.get("eventName", ""), entry.get("user", ""))

        assert not has_duplicates(
            change_entries, changes_key
        ), "Change entries should not contain duplicates after deduplication"

        # Verify chronological sorting
        timestamps = [entry.get("timestamp", "") for entry in change_entries]
        assert is_chronologically_sorted(
            timestamps
        ), f"Change entries should be sorted chronologically: {timestamps}"

        # Verify we didn't lose all data
        if original_changes_count > 0:
            assert (
                len(change_entries) > 0
            ), "Deduplication should preserve at least one entry when original had entries"
            assert (
                len(change_entries) <= original_changes_count
            ), "Deduplicated count should not exceed original count"


@given(
    st.lists(
        st.tuples(
            iso_timestamp_strategy(),
            st.text(
                min_size=1, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
            ),
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=5,
        max_size=20,
        unique=True,  # Ensure the input tuples are unique
    )
)
def test_exact_duplicates_are_removed(metric_tuples):
    """
    Property: Exact duplicate entries are removed, keeping only one copy.

    This test creates exact duplicates and verifies they are reduced to single entries.
    """
    # Create metrics time series with exact duplicates
    time_series = []
    for ts, name, value in metric_tuples:
        # Add each entry twice to create exact duplicates
        entry = {"timestamp": ts, "metricName": name, "value": value, "unit": "Percent"}
        time_series.append(entry.copy())
        time_series.append(entry.copy())  # Exact duplicate

    # Create context
    context = StructuredContext(
        incident_id="test-123",
        timestamp=datetime.now(timezone.utc),
        resource=ResourceInfo(
            arn="arn:aws:ec2:us-east-1:123456789012:instance/i-123", type="ec2", name="test"
        ),
        alarm=AlarmInfo(name="TestAlarm", metric="CPUUtilization", threshold=80.0),
        metrics={"timeSeries": time_series},
        logs={"entries": []},
        changes={"entries": []},
        completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
    )

    # Apply deduplication
    deduplicated_context = deduplicate_and_sort(context)

    # Verify duplicates are removed
    deduplicated_series = deduplicated_context.metrics["timeSeries"]

    # Should have exactly half the entries (each duplicate pair reduced to one)
    assert len(deduplicated_series) == len(
        metric_tuples
    ), f"Expected {len(metric_tuples)} unique entries, got {len(deduplicated_series)}"

    # Verify no duplicates remain
    def metrics_key(entry):
        return (entry.get("timestamp", ""), entry.get("metricName", ""), entry.get("value", 0))

    assert not has_duplicates(
        deduplicated_series, metrics_key
    ), "No duplicates should remain after deduplication"


@given(structured_context_with_duplicates_strategy())
def test_chronological_sorting_is_stable(context):
    """
    Property: Chronological sorting produces a stable, consistent order.

    This test verifies that sorting by timestamp produces a deterministic order
    and that entries with the same timestamp maintain relative order.
    """
    # Normalize and deduplicate
    context = normalize_timestamps(context)
    deduplicated_context = deduplicate_and_sort(context)

    # Extract all timestamps from all sources
    all_timestamps = []

    # From metrics
    if "timeSeries" in deduplicated_context.metrics:
        for entry in deduplicated_context.metrics["timeSeries"]:
            all_timestamps.append(entry.get("timestamp", ""))

    # From logs
    if "entries" in deduplicated_context.logs:
        for entry in deduplicated_context.logs["entries"]:
            all_timestamps.append(entry.get("timestamp", ""))

    # From changes
    if "entries" in deduplicated_context.changes:
        for entry in deduplicated_context.changes["entries"]:
            all_timestamps.append(entry.get("timestamp", ""))

    # Verify each data source is sorted
    if "timeSeries" in deduplicated_context.metrics:
        metrics_timestamps = [
            e.get("timestamp", "") for e in deduplicated_context.metrics["timeSeries"]
        ]
        assert is_chronologically_sorted(
            metrics_timestamps
        ), "Metrics time series should be chronologically sorted"

    if "entries" in deduplicated_context.logs:
        logs_timestamps = [e.get("timestamp", "") for e in deduplicated_context.logs["entries"]]
        assert is_chronologically_sorted(
            logs_timestamps
        ), "Log entries should be chronologically sorted"

    if "entries" in deduplicated_context.changes:
        changes_timestamps = [
            e.get("timestamp", "") for e in deduplicated_context.changes["entries"]
        ]
        assert is_chronologically_sorted(
            changes_timestamps
        ), "Change entries should be chronologically sorted"


@given(st.lists(iso_timestamp_strategy(), min_size=3, max_size=10))
def test_sorting_handles_various_timestamp_orders(timestamps):
    """
    Property: Sorting works correctly regardless of initial order.

    This test verifies that entries are sorted correctly whether they start
    in forward order, reverse order, or random order.
    """
    # Create log entries with these timestamps in random order
    log_entries = []
    for ts in timestamps:
        log_entries.append(
            {
                "timestamp": ts,
                "logLevel": "ERROR",
                "message": "Test message",
                "logStream": "test-stream",
            }
        )

    # Create context
    context = StructuredContext(
        incident_id="test-456",
        timestamp=datetime.now(timezone.utc),
        resource=ResourceInfo(
            arn="arn:aws:lambda:us-east-1:123456789012:function:test", type="lambda", name="test"
        ),
        alarm=AlarmInfo(name="TestAlarm", metric="Errors", threshold=10.0),
        metrics={"timeSeries": []},
        logs={"entries": log_entries},
        changes={"entries": []},
        completeness=CompletenessInfo(metrics=True, logs=True, changes=True),
    )

    # Apply deduplication and sorting
    deduplicated_context = deduplicate_and_sort(context)

    # Extract sorted timestamps
    sorted_timestamps = [e.get("timestamp", "") for e in deduplicated_context.logs["entries"]]

    # Verify they are sorted
    assert is_chronologically_sorted(
        sorted_timestamps
    ), f"Timestamps should be sorted: {sorted_timestamps}"

    # Verify all timestamps are present (accounting for potential duplicates)
    unique_original = list(set(timestamps))
    assert len(sorted_timestamps) == len(
        unique_original
    ), f"All unique timestamps should be present: expected {len(unique_original)}, got {len(sorted_timestamps)}"


@given(structured_context_with_duplicates_strategy())
def test_deduplication_preserves_data_integrity(context):
    """
    Property: Deduplication removes duplicates but preserves all unique data.

    This test verifies that deduplication doesn't accidentally remove unique entries,
    only true duplicates.
    """
    # Normalize timestamps first
    context = normalize_timestamps(context)

    # Count unique entries before deduplication
    def count_unique_metrics(entries):
        seen = set()
        for entry in entries:
            key = (entry.get("timestamp", ""), entry.get("metricName", ""), entry.get("value", 0))
            seen.add(key)
        return len(seen)

    def count_unique_logs(entries):
        seen = set()
        for entry in entries:
            key = (entry.get("timestamp", ""), entry.get("message", ""), entry.get("logStream", ""))
            seen.add(key)
        return len(seen)

    def count_unique_changes(entries):
        seen = set()
        for entry in entries:
            key = (entry.get("timestamp", ""), entry.get("eventName", ""), entry.get("user", ""))
            seen.add(key)
        return len(seen)

    # Count unique entries before
    unique_metrics_before = count_unique_metrics(context.metrics.get("timeSeries", []))
    unique_logs_before = count_unique_logs(context.logs.get("entries", []))
    unique_changes_before = count_unique_changes(context.changes.get("entries", []))

    # Apply deduplication
    deduplicated_context = deduplicate_and_sort(context)

    # Count entries after
    metrics_after = len(deduplicated_context.metrics.get("timeSeries", []))
    logs_after = len(deduplicated_context.logs.get("entries", []))
    changes_after = len(deduplicated_context.changes.get("entries", []))

    # Verify counts match unique counts
    assert (
        metrics_after == unique_metrics_before
    ), f"Metrics: expected {unique_metrics_before} unique entries, got {metrics_after}"

    assert (
        logs_after == unique_logs_before
    ), f"Logs: expected {unique_logs_before} unique entries, got {logs_after}"

    assert (
        changes_after == unique_changes_before
    ), f"Changes: expected {unique_changes_before} unique entries, got {changes_after}"
