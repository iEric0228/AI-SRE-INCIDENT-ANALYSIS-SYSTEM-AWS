"""
Response Parser for LLM Analyzer

Implements the 3-level fallback parsing strategy for raw Bedrock responses:

  Level 1 – Extract and parse JSON that is embedded anywhere in the response.
  Level 2 – Create a structured stub from the first 200 characters of raw text
             when the JSON is absent or malformed.
  Level 3 – Return a minimal sentinel dict when everything else fails.

Observability additions
-----------------------
* The full raw LLM response string is logged at DEBUG level *before* any
  parsing attempt.  This makes it possible to diagnose format regressions
  without having to reproduce the exact prompt.
* A ``LLMParseLevel`` custom CloudWatch metric is emitted (value 1, 2, or 3)
  after each parse so that ops teams can detect fallback-level trends via
  dashboards or alarms without grepping logs.
"""

import json
import logging
import os
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Resolve the shared utilities directory so this module can be used both as
# part of a Lambda deployment package and from the test harness.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from metrics import put_metric  # noqa: E402


def _emit_parse_level_metric(level: int) -> None:
    """
    Emit a custom metric recording which fallback level was used.

    Args:
        level: 1 = JSON parsed successfully, 2 = text extraction,
               3 = minimal fallback.
    """
    put_metric(
        metric_name="LLMParseLevel",
        value=float(level),
        unit="None",
        dimensions=[{"Name": "Level", "Value": str(level)}],
    )


def parse_llm_response(response_text: str) -> Dict[str, Any]:
    """
    Parse LLM response into structured analysis.

    Attempts to extract JSON from the response. If parsing fails,
    creates a structured response from the text.

    The full raw response string is logged at DEBUG level before any parsing
    attempt so that format issues can be diagnosed in production without
    needing to reproduce the exact request.

    After parsing, a ``LLMParseLevel`` CloudWatch metric is emitted:
      * 1 – JSON successfully extracted and validated
      * 2 – JSON absent or invalid; text extraction fallback used
      * 3 – Complete parsing failure; minimal sentinel dict returned

    Args:
        response_text: Raw LLM response text

    Returns:
        Structured analysis dict
    """
    # Log the full raw response at DEBUG before any parsing attempt.
    # This is intentionally verbose (full response body) so that engineers
    # can replay exact LLM output when debugging format regressions in prod.
    logger.debug(
        json.dumps(
            {
                "message": "Raw LLM response before parsing",
                "rawResponse": response_text,
                "rawResponseLength": len(response_text) if response_text else 0,
            }
        )
    )

    # LLM RESPONSE PARSING ALGORITHM:
    # Strategy: Robust parsing with multiple fallback levels
    # Level 1: Extract and parse JSON from response
    # Level 2: Create structured response from text if JSON invalid
    # Level 3: Return minimal fallback if all parsing fails
    # Reason: LLMs may return valid analysis in non-JSON format

    try:
        # Level 1: Try to find JSON in response
        # Look for content between first { and last }
        # This handles cases where LLM adds explanatory text before/after JSON
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}")

        if start_idx != -1 and end_idx != -1:
            json_str = response_text[start_idx : end_idx + 1]
            analysis = json.loads(json_str)

            # Validate required fields exist
            required_fields = [
                "rootCauseHypothesis",
                "confidence",
                "evidence",
                "contributingFactors",
                "recommendedActions",
            ]

            if all(field in analysis for field in required_fields):
                # FIELD VALIDATION AND NORMALIZATION:
                # Ensure all fields have correct types to prevent downstream errors
                # Convert None values and normalize data types

                # rootCauseHypothesis must be a non-null string
                if (
                    not isinstance(analysis["rootCauseHypothesis"], str)
                    or analysis["rootCauseHypothesis"] is None
                ):
                    raise ValueError("rootCauseHypothesis must be a string")

                # confidence must be a non-null string
                if not isinstance(analysis["confidence"], str) or analysis["confidence"] is None:
                    raise ValueError("confidence must be a string")

                # Normalize confidence to lowercase for consistency
                analysis["confidence"] = analysis["confidence"].lower()

                # evidence must be a list
                if not isinstance(analysis["evidence"], list) or analysis["evidence"] is None:
                    raise ValueError("evidence must be a list")

                # contributingFactors must be a list
                if (
                    not isinstance(analysis["contributingFactors"], list)
                    or analysis["contributingFactors"] is None
                ):
                    raise ValueError("contributingFactors must be a list")

                # recommendedActions must be a list
                if (
                    not isinstance(analysis["recommendedActions"], list)
                    or analysis["recommendedActions"] is None
                ):
                    raise ValueError("recommendedActions must be a list")

                # Ensure all list items are strings (filter out None and convert to string)
                analysis["evidence"] = [
                    str(item) for item in analysis["evidence"] if item is not None
                ]
                analysis["contributingFactors"] = [
                    str(item) for item in analysis["contributingFactors"] if item is not None
                ]
                analysis["recommendedActions"] = [
                    str(item) for item in analysis["recommendedActions"] if item is not None
                ]

                _emit_parse_level_metric(1)
                return dict(analysis)

        # Level 2: If JSON parsing failed, create structured response from text
        # This handles cases where LLM provides analysis in natural language
        logger.warning(
            json.dumps(
                {
                    "message": "Failed to parse JSON from LLM response, using text extraction",
                    "parseLevel": 2,
                    "responsePreview": response_text[:200] if response_text else "",
                }
            )
        )

        _emit_parse_level_metric(2)
        return {
            "rootCauseHypothesis": (
                response_text[:200] if response_text else "Unable to parse analysis"
            ),
            "confidence": "low",
            "evidence": [],
            "contributingFactors": [],
            "recommendedActions": ["Review incident data manually", "Check LLM response format"],
        }

    except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
        # Level 3: Complete parsing failure - return minimal fallback
        logger.error(
            json.dumps(
                {
                    "message": "JSON parsing failed, using minimal fallback",
                    "parseLevel": 3,
                    "error": str(e),
                }
            )
        )

        _emit_parse_level_metric(3)
        return {
            "rootCauseHypothesis": "Failed to parse LLM response",
            "confidence": "none",
            "evidence": [],
            "contributingFactors": [],
            "recommendedActions": ["Review incident data manually", "Check LLM response format"],
        }
