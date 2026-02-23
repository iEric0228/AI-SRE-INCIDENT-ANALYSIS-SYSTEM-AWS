"""
Log Metadata Utility

Adds function name and version metadata to existing structured logs.
This is a lightweight wrapper that enhances existing logging without requiring
major refactoring of Lambda functions.

Requirements: 11.1, 11.2, 11.6
"""

import json
import os
from typing import Any, Dict


def add_function_metadata(log_dict: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Add function name and version metadata to a log dictionary.

    Args:
        log_dict: Existing log dictionary
        context: Lambda context object (optional)

    Returns:
        Enhanced log dictionary with function metadata

    Requirements:
    - 11.1: Ensure logs are valid JSON
    - 11.2: Include function name and version
    """
    # Add function name from environment or context
    if context and hasattr(context, "function_name"):
        log_dict["functionName"] = context.function_name
        log_dict["functionVersion"] = context.function_version
    else:
        # Fallback to environment variable
        log_dict["functionName"] = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "unknown")
        log_dict["functionVersion"] = os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "$LATEST")

    return log_dict


def enhance_log_message(message: str, context: Any = None) -> str:
    """
    Enhance a JSON log message with function metadata.

    If the message is already JSON, adds metadata fields.
    If not JSON, wraps it in a JSON structure with metadata.

    Args:
        message: Log message (JSON string or plain text)
        context: Lambda context object (optional)

    Returns:
        Enhanced JSON log message
    """
    try:
        # Try to parse as JSON
        log_dict = json.loads(message)

        # Add metadata
        log_dict = add_function_metadata(log_dict, context)

        return json.dumps(log_dict)
    except (json.JSONDecodeError, TypeError):
        # Not JSON, wrap it
        log_dict = {
            "message": message,
            "functionName": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "unknown"),
            "functionVersion": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "$LATEST"),
        }

        if context and hasattr(context, "function_name"):
            log_dict["functionName"] = context.function_name
            log_dict["functionVersion"] = context.function_version

        return json.dumps(log_dict)
