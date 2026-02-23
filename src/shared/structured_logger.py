"""
Structured Logger Utility

Provides structured JSON logging with correlation IDs, function metadata,
and consistent formatting across all Lambda functions.

Requirements: 11.1, 11.2, 11.6
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredLogger:
    """
    Structured logger that ensures all logs are valid JSON with required metadata.

    Requirements:
    - 11.1: All logs are valid JSON
    - 11.2: Include correlation ID in all logs
    - 11.6: Include error details with stack traces on failures
    """

    def __init__(self, function_name: str, function_version: str = "$LATEST"):
        """
        Initialize structured logger.

        Args:
            function_name: Name of the Lambda function
            function_version: Version of the Lambda function
        """
        self.function_name = function_name
        self.function_version = function_version
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)

    def _format_log(
        self, level: str, message: str, correlation_id: str = "unknown", **kwargs
    ) -> Dict[str, Any]:
        """
        Format log entry as structured JSON.

        Args:
            level: Log level (INFO, WARNING, ERROR)
            message: Log message
            correlation_id: Incident ID for correlation
            **kwargs: Additional fields to include in log

        Returns:
            Structured log dictionary
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "correlationId": correlation_id,
            "functionName": self.function_name,
            "functionVersion": self.function_version,
        }

        # Add any additional fields
        log_entry.update(kwargs)

        return log_entry

    def info(self, message: str, correlation_id: str = "unknown", **kwargs):
        """
        Log INFO level message.

        Args:
            message: Log message
            correlation_id: Incident ID for correlation
            **kwargs: Additional fields to include in log
        """
        log_entry = self._format_log("INFO", message, correlation_id, **kwargs)
        self.logger.info(json.dumps(log_entry))

    def warning(self, message: str, correlation_id: str = "unknown", **kwargs):
        """
        Log WARNING level message.

        Args:
            message: Log message
            correlation_id: Incident ID for correlation
            **kwargs: Additional fields to include in log
        """
        log_entry = self._format_log("WARNING", message, correlation_id, **kwargs)
        self.logger.warning(json.dumps(log_entry))

    def error(
        self,
        message: str,
        correlation_id: str = "unknown",
        error: Optional[Exception] = None,
        include_trace: bool = True,
        **kwargs,
    ):
        """
        Log ERROR level message with optional stack trace.

        Args:
            message: Log message
            correlation_id: Incident ID for correlation
            error: Exception object (optional)
            include_trace: Whether to include stack trace
            **kwargs: Additional fields to include in log
        """
        log_entry = self._format_log("ERROR", message, correlation_id, **kwargs)

        # Add error details
        if error:
            log_entry["error"] = str(error)
            log_entry["errorType"] = type(error).__name__

        # Add stack trace if requested
        if include_trace:
            log_entry["stackTrace"] = traceback.format_exc()

        self.logger.error(json.dumps(log_entry))

    def debug(self, message: str, correlation_id: str = "unknown", **kwargs):
        """
        Log DEBUG level message.

        Args:
            message: Log message
            correlation_id: Incident ID for correlation
            **kwargs: Additional fields to include in log
        """
        log_entry = self._format_log("DEBUG", message, correlation_id, **kwargs)
        self.logger.debug(json.dumps(log_entry))


def get_correlation_id(event: Dict[str, Any]) -> str:
    """
    Extract correlation ID (incident ID) from event.

    Tries multiple common locations for the incident ID.

    Args:
        event: Lambda event dictionary

    Returns:
        Correlation ID string, or "unknown" if not found
    """
    # Try direct incidentId field
    if "incidentId" in event:
        return event["incidentId"]

    # Try nested in incident object
    if "incident" in event and isinstance(event["incident"], dict):
        if "incidentId" in event["incident"]:
            return event["incident"]["incidentId"]

    # Try in structuredContext
    if "structuredContext" in event and isinstance(event["structuredContext"], dict):
        if "incidentId" in event["structuredContext"]:
            return event["structuredContext"]["incidentId"]

    # Default to unknown
    return "unknown"
