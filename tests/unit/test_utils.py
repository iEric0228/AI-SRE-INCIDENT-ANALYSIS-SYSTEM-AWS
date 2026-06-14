"""Unit tests for shared.utils."""

from datetime import datetime, timezone

from shared.utils import parse_timestamp


class TestParseTimestamp:
    """Tests for parse_timestamp covering all branches."""

    def test_empty_string_returns_now_utc(self):
        result = parse_timestamp("")
        assert result.tzinfo == timezone.utc

    def test_z_suffix_parsed_as_utc(self):
        result = parse_timestamp("2026-06-14T12:00:00Z")
        assert result == datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)

    def test_explicit_offset_parsed(self):
        result = parse_timestamp("2026-06-14T12:00:00+00:00")
        assert result == datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)

    def test_non_utc_offset_preserved(self):
        result = parse_timestamp("2026-06-14T12:00:00+02:00")
        assert result.utcoffset().total_seconds() == 2 * 3600

    def test_bare_iso_without_tz_parsed(self):
        result = parse_timestamp("2026-06-14T12:00:00")
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 14

    def test_unparseable_returns_now_utc(self):
        result = parse_timestamp("not-a-timestamp")
        assert result.tzinfo == timezone.utc
