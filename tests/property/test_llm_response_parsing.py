"""
Property-based tests for LLM response parsing.

This module tests that the LLM analyzer correctly parses LLM responses into
structured analysis reports, handling both valid and malformed responses gracefully.

Validates Requirements 7.4, 7.5
"""

import json
import sys
import os
from hypothesis import given, strategies as st, assume
from hypothesis.strategies import composite

# Import LLM analyzer functions directly
# Clear any cached lambda_function module first
if "lambda_function" in sys.modules:
    del sys.modules["lambda_function"]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "llm_analyzer"))
import lambda_function as llm_lambda

parse_llm_response = llm_lambda.parse_llm_response


# Strategy generators


@composite
def valid_analysis_json_strategy(draw):
    """Generate valid analysis JSON responses."""
    confidence_levels = ["high", "medium", "low", "none"]

    # Generate valid analysis structure
    analysis = {
        "rootCauseHypothesis": draw(
            st.text(
                min_size=10,
                max_size=500,
                alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            )
        ),
        "confidence": draw(st.sampled_from(confidence_levels)),
        "evidence": draw(
            st.lists(
                st.text(
                    min_size=5,
                    max_size=200,
                    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
                ),
                min_size=0,
                max_size=10,
            )
        ),
        "contributingFactors": draw(
            st.lists(
                st.text(
                    min_size=5,
                    max_size=200,
                    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
                ),
                min_size=0,
                max_size=10,
            )
        ),
        "recommendedActions": draw(
            st.lists(
                st.text(
                    min_size=5,
                    max_size=200,
                    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
                ),
                min_size=0,
                max_size=10,
            )
        ),
    }

    # Convert to JSON string
    json_str = json.dumps(analysis)

    # Optionally wrap with surrounding text (LLM might add preamble/postamble)
    if draw(st.booleans()):
        prefix = draw(
            st.text(
                min_size=0,
                max_size=100,
                alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            )
        )
        suffix = draw(
            st.text(
                min_size=0,
                max_size=100,
                alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            )
        )
        return f"{prefix}\n{json_str}\n{suffix}"

    return json_str


@composite
def malformed_json_strategy(draw):
    """Generate malformed JSON responses."""
    malformed_types = draw(
        st.sampled_from(
            [
                "incomplete_json",
                "invalid_json",
                "missing_fields",
                "wrong_types",
                "empty_response",
                "plain_text",
                "partial_json",
            ]
        )
    )

    if malformed_types == "incomplete_json":
        # JSON with missing closing braces
        return '{"rootCauseHypothesis": "Test", "confidence": "high"'

    elif malformed_types == "invalid_json":
        # Invalid JSON syntax
        return '{"rootCauseHypothesis": "Test", "confidence": high, "evidence": [}'

    elif malformed_types == "missing_fields":
        # Valid JSON but missing required fields
        partial_fields = draw(
            st.sampled_from(
                [
                    {"rootCauseHypothesis": "Test"},
                    {"confidence": "high"},
                    {"evidence": ["Test"]},
                    {"rootCauseHypothesis": "Test", "confidence": "high"},
                    {"rootCauseHypothesis": "Test", "evidence": ["Test"]},
                ]
            )
        )
        return json.dumps(partial_fields)

    elif malformed_types == "wrong_types":
        # Valid JSON but wrong field types
        wrong_type_data = {
            "rootCauseHypothesis": draw(st.integers()),  # Should be string
            "confidence": draw(st.integers()),  # Should be string
            "evidence": "not a list",  # Should be list
            "contributingFactors": 123,  # Should be list
            "recommendedActions": None,  # Should be list
        }
        return json.dumps(wrong_type_data)

    elif malformed_types == "empty_response":
        # Empty or whitespace-only response
        return draw(st.sampled_from(["", "   ", "\n\n", "\t\t"]))

    elif malformed_types == "plain_text":
        # Plain text without JSON
        return draw(
            st.text(
                min_size=10,
                max_size=500,
                alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            )
        )

    elif malformed_types == "partial_json":
        # JSON embedded in text but incomplete
        text = draw(
            st.text(
                min_size=10,
                max_size=100,
                alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            )
        )
        return f'{text}\n{{\n"rootCauseHypothesis": "Test"\n'

    return "malformed response"


@composite
def mixed_case_confidence_strategy(draw):
    """Generate valid JSON with mixed-case confidence levels."""
    confidence_variants = [
        "HIGH",
        "High",
        "HiGh",
        "MEDIUM",
        "Medium",
        "MeDiUm",
        "LOW",
        "Low",
        "LoW",
        "NONE",
        "None",
        "NoNe",
    ]

    analysis = {
        "rootCauseHypothesis": draw(
            st.text(
                min_size=10,
                max_size=200,
                alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            )
        ),
        "confidence": draw(st.sampled_from(confidence_variants)),
        "evidence": draw(
            st.lists(
                st.text(
                    min_size=5,
                    max_size=100,
                    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
                ),
                min_size=0,
                max_size=5,
            )
        ),
        "contributingFactors": draw(
            st.lists(
                st.text(
                    min_size=5,
                    max_size=100,
                    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
                ),
                min_size=0,
                max_size=5,
            )
        ),
        "recommendedActions": draw(
            st.lists(
                st.text(
                    min_size=5,
                    max_size=100,
                    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
                ),
                min_size=0,
                max_size=5,
            )
        ),
    }

    return json.dumps(analysis)


# Property Tests


@given(valid_analysis_json_strategy())
def test_property_19_valid_llm_response_parsing(valid_response):
    """
    **Property 19: LLM Response Parsing (Valid Responses)**
    **Validates: Requirements 7.4, 7.5**

    For any valid LLM response, output must be a structured AnalysisReport.

    This property verifies that:
    1. Valid JSON responses are correctly parsed
    2. All required fields are present in the output
    3. Field types are correct
    4. Confidence levels are normalized to lowercase
    5. The parser handles responses with surrounding text
    """
    # Parse the response
    result = parse_llm_response(valid_response)

    # Verify result is a dictionary
    assert isinstance(result, dict), "Parsed result should be a dictionary"

    # Verify all required fields are present
    required_fields = [
        "rootCauseHypothesis",
        "confidence",
        "evidence",
        "contributingFactors",
        "recommendedActions",
    ]
    for field in required_fields:
        assert field in result, f"Result should contain field '{field}'"

    # Verify field types
    assert isinstance(result["rootCauseHypothesis"], str), "rootCauseHypothesis should be a string"
    assert isinstance(result["confidence"], str), "confidence should be a string"
    assert isinstance(result["evidence"], list), "evidence should be a list"
    assert isinstance(result["contributingFactors"], list), "contributingFactors should be a list"
    assert isinstance(result["recommendedActions"], list), "recommendedActions should be a list"

    # Verify confidence is normalized to lowercase
    valid_confidence_levels = ["high", "medium", "low", "none"]
    assert (
        result["confidence"] in valid_confidence_levels
    ), f"Confidence should be one of {valid_confidence_levels}, got '{result['confidence']}'"

    # Verify hypothesis is not empty
    assert len(result["rootCauseHypothesis"]) > 0, "Root cause hypothesis should not be empty"

    # Verify lists contain strings
    for item in result["evidence"]:
        assert isinstance(item, str), "Evidence items should be strings"
    for item in result["contributingFactors"]:
        assert isinstance(item, str), "Contributing factor items should be strings"
    for item in result["recommendedActions"]:
        assert isinstance(item, str), "Recommended action items should be strings"


@given(malformed_json_strategy())
def test_property_19_malformed_llm_response_parsing(malformed_response):
    """
    **Property 19: LLM Response Parsing (Malformed Responses)**
    **Validates: Requirements 7.4, 7.5**

    For any malformed LLM response, output must be a structured fallback response.

    This property verifies that:
    1. Malformed responses don't cause exceptions
    2. A valid fallback structure is always returned
    3. The fallback contains all required fields
    4. The fallback indicates parsing failure appropriately
    """
    # Parse the malformed response - should not raise exception
    try:
        result = parse_llm_response(malformed_response)
    except Exception as e:
        assert False, f"Parsing should not raise exception, got: {type(e).__name__}: {e}"

    # Verify result is a dictionary
    assert isinstance(result, dict), "Parsed result should be a dictionary"

    # Verify all required fields are present
    required_fields = [
        "rootCauseHypothesis",
        "confidence",
        "evidence",
        "contributingFactors",
        "recommendedActions",
    ]
    for field in required_fields:
        assert field in result, f"Fallback result should contain field '{field}'"

    # Verify field types
    assert isinstance(result["rootCauseHypothesis"], str), "rootCauseHypothesis should be a string"
    assert isinstance(result["confidence"], str), "confidence should be a string"
    assert isinstance(result["evidence"], list), "evidence should be a list"
    assert isinstance(result["contributingFactors"], list), "contributingFactors should be a list"
    assert isinstance(result["recommendedActions"], list), "recommendedActions should be a list"

    # Verify confidence indicates uncertainty
    valid_fallback_confidence = ["low", "none"]
    assert (
        result["confidence"] in valid_fallback_confidence
    ), f"Fallback confidence should be 'low' or 'none', got '{result['confidence']}'"

    # Verify hypothesis is not empty (should have fallback message)
    assert len(result["rootCauseHypothesis"]) > 0, "Fallback hypothesis should not be empty"

    # Verify recommended actions suggest manual review
    assert len(result["recommendedActions"]) > 0, "Fallback should include recommended actions"

    # At least one action should mention manual review or checking
    action_text = " ".join(result["recommendedActions"]).lower()
    assert any(
        keyword in action_text for keyword in ["manual", "review", "check"]
    ), "Fallback actions should suggest manual review"


@given(mixed_case_confidence_strategy())
def test_confidence_normalization(response_with_mixed_case):
    """
    Property: Confidence levels are normalized to lowercase.

    This verifies that the parser handles confidence levels in any case
    and normalizes them to lowercase for consistency.
    """
    result = parse_llm_response(response_with_mixed_case)

    # Verify confidence is lowercase
    assert result[
        "confidence"
    ].islower(), f"Confidence should be lowercase, got '{result['confidence']}'"

    # Verify it's a valid confidence level
    valid_confidence_levels = ["high", "medium", "low", "none"]
    assert (
        result["confidence"] in valid_confidence_levels
    ), f"Confidence should be one of {valid_confidence_levels}"


@given(
    st.text(min_size=0, max_size=1000, alphabet=st.characters(min_codepoint=32, max_codepoint=126))
)
def test_arbitrary_text_produces_valid_fallback(arbitrary_text):
    """
    Property: Any arbitrary text produces a valid fallback structure.

    This is the most general test - any string input should produce
    a valid, structured response without exceptions.
    """
    # Parse arbitrary text - should never raise exception
    try:
        result = parse_llm_response(arbitrary_text)
    except Exception as e:
        assert (
            False
        ), f"Parsing should not raise exception for any input, got: {type(e).__name__}: {e}"

    # Verify result structure
    assert isinstance(result, dict), "Result should be a dictionary"

    # Verify all required fields exist
    required_fields = [
        "rootCauseHypothesis",
        "confidence",
        "evidence",
        "contributingFactors",
        "recommendedActions",
    ]
    for field in required_fields:
        assert field in result, f"Result should contain field '{field}'"

    # Verify types
    assert isinstance(result["rootCauseHypothesis"], str)
    assert isinstance(result["confidence"], str)
    assert isinstance(result["evidence"], list)
    assert isinstance(result["contributingFactors"], list)
    assert isinstance(result["recommendedActions"], list)


@given(valid_analysis_json_strategy())
def test_parsing_is_deterministic(valid_response):
    """
    Property: Parsing the same response multiple times produces identical results.

    This ensures the parser is deterministic and doesn't have side effects.
    """
    # Parse multiple times
    result1 = parse_llm_response(valid_response)
    result2 = parse_llm_response(valid_response)
    result3 = parse_llm_response(valid_response)

    # All results should be identical
    assert result1 == result2, "Multiple parses should produce identical results"
    assert result2 == result3, "Multiple parses should produce identical results"
    assert result1 == result3, "Multiple parses should produce identical results"


@given(
    st.text(min_size=1, max_size=500, alphabet=st.characters(min_codepoint=32, max_codepoint=126))
)
def test_empty_lists_are_valid(text_without_json):
    """
    Property: Fallback responses can have empty lists for evidence, factors, and actions.

    This verifies that the parser doesn't require non-empty lists.
    """
    # Assume the text doesn't contain valid JSON
    assume("{" not in text_without_json or "}" not in text_without_json)

    result = parse_llm_response(text_without_json)

    # Verify lists exist (even if empty)
    assert isinstance(result["evidence"], list)
    assert isinstance(result["contributingFactors"], list)
    assert isinstance(result["recommendedActions"], list)

    # Empty lists are acceptable for evidence and contributing factors
    # But recommended actions should have at least one item in fallback
    if result["confidence"] in ["low", "none"]:
        assert (
            len(result["recommendedActions"]) > 0
        ), "Fallback should include at least one recommended action"


def test_json_with_extra_fields():
    """
    Property: JSON with extra fields is accepted (fields are ignored).

    This verifies the parser is tolerant of additional fields.
    """
    response_with_extra = json.dumps(
        {
            "rootCauseHypothesis": "Test hypothesis",
            "confidence": "high",
            "evidence": ["Test evidence"],
            "contributingFactors": ["Test factor"],
            "recommendedActions": ["Test action"],
            "extraField1": "ignored",
            "extraField2": 123,
            "nested": {"extra": "data"},
        }
    )

    result = parse_llm_response(response_with_extra)

    # Verify required fields are present
    assert result["rootCauseHypothesis"] == "Test hypothesis"
    assert result["confidence"] == "high"
    assert result["evidence"] == ["Test evidence"]
    assert result["contributingFactors"] == ["Test factor"]
    assert result["recommendedActions"] == ["Test action"]


def test_json_with_unicode_characters():
    """
    Property: JSON with unicode characters is handled correctly.

    This verifies the parser handles international characters.
    """
    response_with_unicode = json.dumps(
        {
            "rootCauseHypothesis": "Test with émojis 🚨 and spëcial çharacters",
            "confidence": "medium",
            "evidence": ["Evidence with 中文", "Evidence with العربية"],
            "contributingFactors": ["Factor with Ελληνικά"],
            "recommendedActions": ["Action with 日本語"],
        }
    )

    result = parse_llm_response(response_with_unicode)

    # Verify unicode is preserved
    assert "émojis" in result["rootCauseHypothesis"] or "mojis" in result["rootCauseHypothesis"]
    assert isinstance(result["evidence"], list)
    assert len(result["evidence"]) > 0


def test_json_with_nested_structures():
    """
    Property: JSON with nested structures in string fields is handled.

    This verifies the parser handles complex string content.
    """
    response_with_nested = json.dumps(
        {
            "rootCauseHypothesis": "Test with {nested: 'json-like'} content",
            "confidence": "low",
            "evidence": [
                "Evidence with [array-like] content",
                "Evidence with {object: 'like'} content",
            ],
            "contributingFactors": ["Factor"],
            "recommendedActions": ["Action"],
        }
    )

    result = parse_llm_response(response_with_nested)

    # Verify parsing succeeds
    assert isinstance(result, dict)
    assert result["confidence"] == "low"
    assert len(result["evidence"]) > 0


def test_very_long_response():
    """
    Property: Very long responses are handled without truncation errors.

    This verifies the parser handles large responses.
    """
    long_hypothesis = "A" * 10000
    long_evidence = ["Evidence " + str(i) for i in range(100)]

    response = json.dumps(
        {
            "rootCauseHypothesis": long_hypothesis,
            "confidence": "medium",
            "evidence": long_evidence,
            "contributingFactors": ["Factor"],
            "recommendedActions": ["Action"],
        }
    )

    result = parse_llm_response(response)

    # Verify parsing succeeds
    assert isinstance(result, dict)
    assert len(result["rootCauseHypothesis"]) > 0
    assert len(result["evidence"]) > 0


def test_json_with_null_values():
    """
    Property: JSON with null values is handled gracefully.

    This verifies the parser handles null/None values.
    """
    response_with_nulls = json.dumps(
        {
            "rootCauseHypothesis": None,
            "confidence": "low",
            "evidence": None,
            "contributingFactors": None,
            "recommendedActions": None,
        }
    )

    result = parse_llm_response(response_with_nulls)

    # Verify fallback structure is returned
    assert isinstance(result, dict)
    assert isinstance(result["rootCauseHypothesis"], str)
    assert isinstance(result["evidence"], list)
    assert isinstance(result["contributingFactors"], list)
    assert isinstance(result["recommendedActions"], list)
