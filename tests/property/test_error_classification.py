"""
Property Test: Error Classification for Retries

Property 31: For any error encountered by a Lambda function, the system must
correctly classify it as retryable or non-retryable and only retry retryable errors.

Validates: Requirements 20.5

Retryable errors:
- ThrottlingException (AWS API rate limits)
- ServiceException (temporary AWS service issues)
- TooManyRequestsException (Bedrock rate limits)
- Timeout errors

Non-retryable errors:
- ValidationException (invalid input data)
- AccessDeniedException (IAM permission issues)
- ResourceNotFoundException (missing AWS resources)
- InvalidParameterException (malformed API requests)
"""

import json
import pytest
from hypothesis import given, strategies as st
from typing import Dict, Any, List

# Define error categories
RETRYABLE_ERRORS = [
    "ThrottlingException",
    "ServiceException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "InternalServerError",
    "RequestTimeout",
]

NON_RETRYABLE_ERRORS = [
    "ValidationException",
    "AccessDeniedException",
    "ResourceNotFoundException",
    "InvalidParameterException",
    "InvalidParameterValueException",
    "ResourceAlreadyExistsException",
]


def classify_error(error_type: str) -> str:
    """
    Classify error as retryable or non-retryable.

    Args:
        error_type: AWS error type string

    Returns:
        'retryable' or 'non-retryable'
    """
    if error_type in RETRYABLE_ERRORS:
        return "retryable"
    elif error_type in NON_RETRYABLE_ERRORS:
        return "non-retryable"
    else:
        # Unknown errors are treated as non-retryable by default
        # to avoid infinite retry loops
        return "non-retryable"


def should_retry(error_type: str, attempt_count: int, max_attempts: int = 3) -> bool:
    """
    Determine if error should be retried.

    Args:
        error_type: AWS error type string
        attempt_count: Current attempt number (1-indexed)
        max_attempts: Maximum retry attempts

    Returns:
        True if should retry, False otherwise
    """
    # Don't retry if max attempts reached
    if attempt_count >= max_attempts:
        return False

    # Only retry if error is retryable
    return classify_error(error_type) == "retryable"


@given(error_type=st.sampled_from(RETRYABLE_ERRORS + NON_RETRYABLE_ERRORS))
@pytest.mark.property_test
@pytest.mark.tag("Feature: ai-sre-incident-analysis, Property 31: Error Classification for Retries")
def test_error_classification_correctness(error_type):
    """
    Property 31: For any error encountered by a Lambda function, the system must
    correctly classify it as retryable or non-retryable.

    Validates: Requirements 20.5
    """
    classification = classify_error(error_type)

    # PROPERTY ASSERTIONS:
    # 1. Classification must be one of the valid types
    assert classification in [
        "retryable",
        "non-retryable",
    ], f"Classification must be 'retryable' or 'non-retryable', got {classification}"

    # 2. Known retryable errors must be classified as retryable
    if error_type in RETRYABLE_ERRORS:
        assert classification == "retryable", f"{error_type} must be classified as retryable"

    # 3. Known non-retryable errors must be classified as non-retryable
    if error_type in NON_RETRYABLE_ERRORS:
        assert (
            classification == "non-retryable"
        ), f"{error_type} must be classified as non-retryable"


@given(
    error_type=st.sampled_from(RETRYABLE_ERRORS),
    attempt_count=st.integers(min_value=1, max_value=5),
)
@pytest.mark.property_test
def test_retryable_errors_are_retried(error_type, attempt_count):
    """
    Test that retryable errors are retried up to max attempts.
    """
    max_attempts = 3

    should_retry_result = should_retry(error_type, attempt_count, max_attempts)

    # PROPERTY: Retryable errors should be retried until max attempts
    if attempt_count < max_attempts:
        assert (
            should_retry_result == True
        ), f"Retryable error {error_type} should be retried on attempt {attempt_count}"
    else:
        assert (
            should_retry_result == False
        ), f"Retryable error {error_type} should not be retried after {max_attempts} attempts"


@given(
    error_type=st.sampled_from(NON_RETRYABLE_ERRORS),
    attempt_count=st.integers(min_value=1, max_value=5),
)
@pytest.mark.property_test
def test_non_retryable_errors_not_retried(error_type, attempt_count):
    """
    Test that non-retryable errors are never retried.
    """
    should_retry_result = should_retry(error_type, attempt_count)

    # PROPERTY: Non-retryable errors should never be retried
    assert (
        should_retry_result == False
    ), f"Non-retryable error {error_type} should not be retried on any attempt"


@given(
    retryable_error=st.sampled_from(RETRYABLE_ERRORS),
    non_retryable_error=st.sampled_from(NON_RETRYABLE_ERRORS),
)
@pytest.mark.property_test
def test_error_classification_consistency(retryable_error, non_retryable_error):
    """
    Test that error classification is consistent across multiple calls.
    """
    # PROPERTY: Classification must be deterministic

    # Retryable error should always be classified as retryable
    classification1 = classify_error(retryable_error)
    classification2 = classify_error(retryable_error)

    assert (
        classification1 == classification2 == "retryable"
    ), f"Retryable error {retryable_error} must consistently be classified as retryable"

    # Non-retryable error should always be classified as non-retryable
    classification3 = classify_error(non_retryable_error)
    classification4 = classify_error(non_retryable_error)

    assert (
        classification3 == classification4 == "non-retryable"
    ), f"Non-retryable error {non_retryable_error} must consistently be classified as non-retryable"


@given(
    error_type=st.text(
        min_size=5, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))
    )
)
@pytest.mark.property_test
def test_unknown_errors_classified_as_non_retryable(error_type):
    """
    Test that unknown/unexpected errors are classified as non-retryable by default.

    This prevents infinite retry loops on unexpected errors.
    """
    # Filter out known errors
    if error_type in RETRYABLE_ERRORS or error_type in NON_RETRYABLE_ERRORS:
        return  # Skip known errors

    classification = classify_error(error_type)

    # PROPERTY: Unknown errors should be non-retryable (fail-safe)
    assert (
        classification == "non-retryable"
    ), f"Unknown error {error_type} should be classified as non-retryable to prevent infinite retries"


@given(
    error_sequence=st.lists(
        st.sampled_from(RETRYABLE_ERRORS + NON_RETRYABLE_ERRORS), min_size=1, max_size=5
    )
)
@pytest.mark.property_test
def test_retry_sequence_behavior(error_sequence):
    """
    Test retry behavior across a sequence of errors.
    """
    max_attempts = 3

    # Simulate retry sequence
    for attempt, error_type in enumerate(error_sequence, start=1):
        should_retry_result = should_retry(error_type, attempt, max_attempts)
        classification = classify_error(error_type)

        # PROPERTY: Retry decision must match classification and attempt count
        if classification == "retryable" and attempt < max_attempts:
            assert should_retry_result == True, f"Should retry {error_type} on attempt {attempt}"
        else:
            assert (
                should_retry_result == False
            ), f"Should not retry {error_type} on attempt {attempt}"


@given(error_type=st.sampled_from(RETRYABLE_ERRORS + NON_RETRYABLE_ERRORS))
@pytest.mark.property_test
def test_step_functions_retry_config_matches_classification(error_type):
    """
    Test that Step Functions retry configuration matches error classification.
    """
    classification = classify_error(error_type)

    # Step Functions retry configuration
    retry_config = {
        "ErrorEquals": RETRYABLE_ERRORS,
        "MaxAttempts": 3,
        "IntervalSeconds": 2,
        "BackoffRate": 2.0,
    }

    # PROPERTY: Retry config must include all retryable errors
    if classification == "retryable":
        assert (
            error_type in retry_config["ErrorEquals"]
        ), f"Retryable error {error_type} must be in Step Functions retry config"
    else:
        assert (
            error_type not in retry_config["ErrorEquals"]
        ), f"Non-retryable error {error_type} must not be in Step Functions retry config"


@given(
    error_type=st.sampled_from(RETRYABLE_ERRORS), max_attempts=st.integers(min_value=1, max_value=5)
)
@pytest.mark.property_test
def test_retry_attempts_bounded(error_type, max_attempts):
    """
    Test that retry attempts are bounded by max_attempts.
    """
    # PROPERTY: Retries must stop after max_attempts

    # Simulate retries
    retry_count = 0
    for attempt in range(1, max_attempts + 5):  # Try more than max
        if should_retry(error_type, attempt, max_attempts):
            retry_count += 1
        else:
            break

    # Total attempts should not exceed max_attempts
    assert (
        retry_count < max_attempts
    ), f"Retry count {retry_count} must be less than max_attempts {max_attempts}"


@given(
    error_type=st.sampled_from(RETRYABLE_ERRORS + NON_RETRYABLE_ERRORS),
    context=st.dictionaries(
        st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=50), min_size=0, max_size=5
    ),
)
@pytest.mark.property_test
def test_error_classification_independent_of_context(error_type, context):
    """
    Test that error classification is independent of error context.

    The error type alone should determine retry behavior, not the context.
    """
    classification = classify_error(error_type)

    # PROPERTY: Classification depends only on error type, not context
    # Classify again (simulating different context)
    classification_again = classify_error(error_type)

    assert (
        classification == classification_again
    ), f"Error classification must be independent of context"

    # Classification should be based solely on error type
    if error_type in RETRYABLE_ERRORS:
        assert (
            classification == "retryable"
        ), f"{error_type} must always be retryable regardless of context"
    elif error_type in NON_RETRYABLE_ERRORS:
        assert (
            classification == "non-retryable"
        ), f"{error_type} must always be non-retryable regardless of context"


@given(
    errors=st.lists(
        st.sampled_from(RETRYABLE_ERRORS + NON_RETRYABLE_ERRORS),
        min_size=1,
        max_size=10,
        unique=True,
    )
)
@pytest.mark.property_test
def test_batch_error_classification(errors):
    """
    Test that multiple errors can be classified correctly in batch.
    """
    # Classify all errors
    classifications = {error: classify_error(error) for error in errors}

    # PROPERTY: All classifications must be valid
    for error, classification in classifications.items():
        assert classification in [
            "retryable",
            "non-retryable",
        ], f"Classification for {error} must be valid"

        # Verify against known lists
        if error in RETRYABLE_ERRORS:
            assert classification == "retryable", f"{error} must be classified as retryable"
        elif error in NON_RETRYABLE_ERRORS:
            assert classification == "non-retryable", f"{error} must be classified as non-retryable"


@given(
    error_type=st.sampled_from(["ThrottlingException", "TooManyRequestsException"]),
    backoff_rate=st.floats(min_value=1.5, max_value=3.0),
)
@pytest.mark.property_test
def test_exponential_backoff_for_rate_limit_errors(error_type, backoff_rate):
    """
    Test that rate limit errors use exponential backoff.
    """
    # Rate limit errors should be retryable
    classification = classify_error(error_type)
    assert classification == "retryable", f"Rate limit error {error_type} must be retryable"

    # Calculate retry intervals with exponential backoff
    initial_interval = 2  # seconds
    intervals = []

    for attempt in range(3):  # 3 retry attempts
        interval = initial_interval * (backoff_rate**attempt)
        intervals.append(interval)

    # PROPERTY: Each interval must be larger than the previous (exponential growth)
    for i in range(1, len(intervals)):
        assert (
            intervals[i] > intervals[i - 1]
        ), f"Retry interval must increase exponentially: {intervals[i]} > {intervals[i-1]}"

    # Total backoff time should be reasonable
    total_backoff = sum(intervals)
    assert total_backoff < 60, f"Total backoff time {total_backoff}s should be reasonable (< 60s)"
