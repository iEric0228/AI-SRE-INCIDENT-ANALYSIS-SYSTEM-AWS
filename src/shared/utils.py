"""
Shared utility functions for AI-Assisted SRE Incident Analysis System.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse timestamp string to a timezone-aware datetime object.

    Handles ISO 8601 format with 'Z' suffix, '+00:00' offset, and
    bare ISO format. Returns current UTC time if the input is empty
    or unparseable.

    Args:
        timestamp_str: Timestamp string in various formats

    Returns:
        Timezone-aware datetime object
    """
    if not timestamp_str:
        return datetime.now(timezone.utc)

    try:
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"

        return datetime.fromisoformat(timestamp_str)
    except Exception as e:
        logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
        return datetime.now(timezone.utc)
