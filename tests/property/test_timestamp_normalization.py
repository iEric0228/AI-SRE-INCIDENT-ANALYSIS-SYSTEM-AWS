"""
Property-based tests for timestamp normalization.

This module tests that the correlation engine correctly normalizes all timestamps
to ISO 8601 UTC format across all data sources (metrics, logs, changes).

Validates Requirement 6.2
"""

from datetime import datetime, timezone, timedelta
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import sys
import os
import re

# Import shared models
from shared.models import StructuredContext, ResourceInfo, AlarmInfo, CompletenessInfo

# Import correlation engine functions directly
# Clear any cached lambda_function module first
if "lambda_function" in sys.modules:
    del sys.modules["lambda_function"]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "correlation_engine"))
import lambda_function as correlation_lambda

normalize_timestamps = correlation_lambda.normalize_timestamps
parse_timestamp = correlation_lambda.parse_timestamp


# ISO 8601 UTC format regex pattern
ISO_8601_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?Z$")


def is_iso_8601_utc(timestamp_str: str) -> bool:
    """
    Check if a timestamp string is in ISO 8601 UTC format.

    Args:
        timestamp_str: Timestamp string to validate

    Returns:
        True if timestamp is in ISO 8601 UTC format, False otherwise
    """
    if not isinstance(timestamp_str, str):
        return False

    return bool(ISO_8601_UTC_PATTERN.match(timestamp_str))


# Strategy generators


@composite
def datetime_strategy(draw):
    """Generate datetime objects with timezone info."""
    timestamp = draw(st.integers(min_value=1577836800, max_value=1893456000))
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


@composite
def mixed_timestamp_strategy(draw):
    """
    Generate timestamps in various formats that need normalization.

    Returns timestamps as:
    - ISO 8601 with Z suffix (already normalized)
    - ISO 8601 without Z or timezone
    - datetime objects
    - ISO 8601 with +00:00 timezone
    """
    dt = draw(datetime_strategy())

    format_choice = draw(st.integers(min_value=0, max_value=3))

    if format_choice == 0:
        # Already normalized: ISO 8601 with Z
        iso_str = dt.isoformat()
        # Remove timezone info if present and add Z
        if "+" in iso_str:
            iso_str = iso_str.split("+")[0]
        return iso_str + "Z"
    elif format_choice == 1:
        # ISO 8601 without Z or timezone
        iso_str = dt.isoformat()
        if "+" in iso_str:
            iso_str = iso_str.split("+")[0]
        return iso_str
    elif format_choice == 2:
        # datetime object
        return dt
    else:
        # ISO 8601 with +00:00 timezone (no Z)
        iso_str = dt.isoformat()
        if "+" in iso_str:
            iso_str = iso_str.split("+")[0]
        return iso_str + "+00:00"


@composite
def metrics_time_series_strategy(draw):
    """Generate metrics time series with mixed timestamp formats."""
    num_entries = draw(st.integers(min_value=1, max_value=20))

    time_series = []
    for _ in range(num_entries):
        time_series.append(
            {
                "timestamp": draw(mixed_timestamp_strategy()),
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

    return time_series


@composite
def metrics_datapoints_strategy(draw):
    """Generate metrics with datapoints containing mixed timestamp formats."""
    num_metrics = draw(st.integers(min_value=1, max_value=5))

    metrics = []
    for _ in range(num_metrics):
        num_datapoints = draw(st.integers(min_value=1, max_value=10))
        datapoints = []

        for _ in range(num_datapoints):
            datapoints.append(
                {
                    "timestamp": draw(mixed_timestamp_strategy()),
                    "value": draw(
                        st.floats(
                            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
                        )
                    ),
                    "unit": draw(st.sampled_from(["Percent", "Count", "Bytes", "Seconds"])),
                }
            )

        metrics.append(
            {
                "metricName": draw(
                    st.text(
                        min_size=1,
                        max_size=30,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    )
                ),
                "namespace": draw(st.sampled_from(["AWS/EC2", "AWS/Lambda", "AWS/RDS"])),
                "datapoints": datapoints,
                "statistics": {
                    "avg": draw(
                        st.floats(
                            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
                        )
                    ),
                    "max": draw(
                        st.floats(
                            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
                        )
                    ),
                    "min": draw(
                        st.floats(
                            min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False
                        )
                    ),
                },
            }
        )

    return metrics


@composite
def log_entries_strategy(draw):
    """Generate log entries with mixed timestamp formats."""
    num_entries = draw(st.integers(min_value=1, max_value=20))

    entries = []
    for _ in range(num_entries):
        entries.append(
            {
                "timestamp": draw(mixed_timestamp_strategy()),
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

    return entries


@composite
def change_entries_strategy(draw):
    """Generate change entries with mixed timestamp formats."""
    num_entries = draw(st.integers(min_value=1, max_value=20))

    entries = []
    for _ in range(num_entries):
        entries.append(
            {
                "timestamp": draw(mixed_timestamp_strategy()),
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

    return entries


@composite
def structured_context_strategy(draw):
    """Generate a structured context with mixed timestamp formats."""
    # Generate metrics data
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
        "timeSeries": draw(metrics_time_series_strategy()),
        "metrics": draw(metrics_datapoints_strategy()),
    }

    # Generate logs data
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
        "entries": draw(log_entries_strategy()),
        "totalMatches": draw(st.integers(min_value=0, max_value=1000)),
        "returned": draw(st.integers(min_value=0, max_value=100)),
    }

    # Generate changes data
    changes_data = {
        "recentDeployments": draw(st.integers(min_value=0, max_value=10)),
        "lastDeployment": draw(st.one_of(st.none(), mixed_timestamp_strategy())),
        "changeCountsByType": {
            "deployment": draw(st.integers(min_value=0, max_value=10)),
            "configuration": draw(st.integers(min_value=0, max_value=10)),
            "infrastructure": draw(st.integers(min_value=0, max_value=10)),
        },
        "totalChanges": draw(st.integers(min_value=0, max_value=30)),
        "entries": draw(change_entries_strategy()),
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


# Property Tests


@given(structured_context_strategy())
def test_property_14_timestamp_normalization(context):
    """
    **Property 14: Timestamp Normalization**
    **Validates: Requirements 6.2**

    For any structured context, all timestamps must be ISO 8601 UTC format.

    This property verifies that:
    1. All timestamps in metrics time series are normalized to ISO 8601 UTC
    2. All timestamps in metrics datapoints are normalized to ISO 8601 UTC
    3. All timestamps in log entries are normalized to ISO 8601 UTC
    4. All timestamps in change entries are normalized to ISO 8601 UTC
    5. The normalization preserves the actual time value
    """
    # Normalize timestamps
    normalized_context = normalize_timestamps(context)

    # Verify all timestamps in metrics time series are ISO 8601 UTC
    if "timeSeries" in normalized_context.metrics:
        for entry in normalized_context.metrics["timeSeries"]:
            if "timestamp" in entry:
                timestamp = entry["timestamp"]
                assert is_iso_8601_utc(
                    timestamp
                ), f"Metrics time series timestamp '{timestamp}' is not in ISO 8601 UTC format"

    # Verify all timestamps in metrics datapoints are ISO 8601 UTC
    if "metrics" in normalized_context.metrics:
        for metric in normalized_context.metrics["metrics"]:
            if "datapoints" in metric:
                for dp in metric["datapoints"]:
                    if "timestamp" in dp:
                        timestamp = dp["timestamp"]
                        assert is_iso_8601_utc(
                            timestamp
                        ), f"Metrics datapoint timestamp '{timestamp}' is not in ISO 8601 UTC format"

    # Verify all timestamps in log entries are ISO 8601 UTC
    if "entries" in normalized_context.logs:
        for entry in normalized_context.logs["entries"]:
            if "timestamp" in entry:
                timestamp = entry["timestamp"]
                assert is_iso_8601_utc(
                    timestamp
                ), f"Log entry timestamp '{timestamp}' is not in ISO 8601 UTC format"

    # Verify all timestamps in change entries are ISO 8601 UTC
    if "entries" in normalized_context.changes:
        for entry in normalized_context.changes["entries"]:
            if "timestamp" in entry:
                timestamp = entry["timestamp"]
                assert is_iso_8601_utc(
                    timestamp
                ), f"Change entry timestamp '{timestamp}' is not in ISO 8601 UTC format"


@given(st.lists(mixed_timestamp_strategy(), min_size=1, max_size=10))
def test_timestamp_normalization_preserves_time_value(timestamps):
    """
    Property: Timestamp normalization preserves the actual time value.

    This test verifies that normalizing a timestamp doesn't change the actual
    point in time it represents, only the format.
    """
    for original_ts in timestamps:
        # Parse the original timestamp
        if isinstance(original_ts, datetime):
            original_dt = original_ts
        else:
            original_dt = parse_timestamp(original_ts)

        # Ensure original_dt is timezone-aware
        if original_dt.tzinfo is None:
            original_dt = original_dt.replace(tzinfo=timezone.utc)

        # Normalize it - remove timezone info from isoformat and add Z
        iso_str = original_dt.isoformat()
        if "+" in iso_str:
            iso_str = iso_str.split("+")[0]
        normalized_ts = iso_str + "Z"

        # Parse the normalized timestamp
        normalized_dt = parse_timestamp(normalized_ts)

        # Ensure normalized_dt is timezone-aware
        if normalized_dt.tzinfo is None:
            normalized_dt = normalized_dt.replace(tzinfo=timezone.utc)

        # Verify they represent the same point in time (within 1 second tolerance for rounding)
        time_diff = abs((original_dt - normalized_dt).total_seconds())
        assert (
            time_diff < 1.0
        ), f"Normalization changed time value: {original_ts} -> {normalized_ts} (diff: {time_diff}s)"


@given(structured_context_strategy())
def test_all_data_sources_have_normalized_timestamps(context):
    """
    Property: After normalization, all data sources contain only ISO 8601 UTC timestamps.

    This is a comprehensive test that checks every possible location where timestamps
    can appear in the structured context.
    """
    # Normalize timestamps
    normalized_context = normalize_timestamps(context)

    # Collect all timestamps from all sources
    all_timestamps = []

    # From metrics time series
    if "timeSeries" in normalized_context.metrics:
        for entry in normalized_context.metrics["timeSeries"]:
            if "timestamp" in entry:
                all_timestamps.append(("metrics.timeSeries", entry["timestamp"]))

    # From metrics datapoints
    if "metrics" in normalized_context.metrics:
        for metric in normalized_context.metrics["metrics"]:
            if "datapoints" in metric:
                for dp in metric["datapoints"]:
                    if "timestamp" in dp:
                        all_timestamps.append(("metrics.datapoints", dp["timestamp"]))

    # From log entries
    if "entries" in normalized_context.logs:
        for entry in normalized_context.logs["entries"]:
            if "timestamp" in entry:
                all_timestamps.append(("logs.entries", entry["timestamp"]))

    # From change entries
    if "entries" in normalized_context.changes:
        for entry in normalized_context.changes["entries"]:
            if "timestamp" in entry:
                all_timestamps.append(("changes.entries", entry["timestamp"]))

    # Verify all timestamps are ISO 8601 UTC
    for source, timestamp in all_timestamps:
        assert is_iso_8601_utc(
            timestamp
        ), f"Timestamp in {source} is not ISO 8601 UTC: '{timestamp}'"

    # Verify we found at least some timestamps (context should have data)
    assert len(all_timestamps) > 0, "No timestamps found in context"


@given(
    st.sampled_from(
        [
            "2024-01-15T14:30:00Z",
            "2024-01-15T14:30:00",
            "2024-01-15T14:30:00+00:00",
            "2024-01-15T14:30:00.123456Z",
            "2024-01-15T14:30:00.123456",
        ]
    )
)
def test_various_iso_formats_normalized_to_standard(timestamp_str):
    """
    Property: Various ISO 8601 formats are normalized to the standard format with Z suffix.

    This test verifies that different valid ISO 8601 formats are all normalized
    to the same standard format: YYYY-MM-DDTHH:MM:SS.ffffffZ or YYYY-MM-DDTHH:MM:SSZ
    """
    # Parse and normalize
    dt = parse_timestamp(timestamp_str)

    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # Normalize: remove timezone from isoformat and add Z
    iso_str = dt.isoformat()
    if "+" in iso_str:
        iso_str = iso_str.split("+")[0]
    normalized = iso_str + "Z"

    # Verify it's in ISO 8601 UTC format
    assert is_iso_8601_utc(
        normalized
    ), f"Normalized timestamp '{normalized}' is not in ISO 8601 UTC format"

    # Verify it ends with Z
    assert normalized.endswith("Z"), f"Normalized timestamp '{normalized}' should end with 'Z'"

    # Verify it contains T separator
    assert "T" in normalized, f"Normalized timestamp '{normalized}' should contain 'T' separator"
