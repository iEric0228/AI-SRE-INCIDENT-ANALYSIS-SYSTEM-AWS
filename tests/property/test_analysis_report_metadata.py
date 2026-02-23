"""
Property-based tests for analysis report metadata completeness.

This module tests that analysis reports always include complete metadata
with all required fields: model ID, version, prompt version, token usage, and latency.

Validates Requirements 7.7, 16.5
"""

import json
import sys
import os
from hypothesis import given, strategies as st
from hypothesis.strategies import composite

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Import LLM analyzer functions
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "llm_analyzer"))
from lambda_function import extract_metadata, create_fallback_report

# Import shared models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "shared"))
from models import AnalysisReport

# Strategy generators


@composite
def llm_response_strategy(draw):
    """Generate arbitrary LLM response with metadata."""
    model_ids = ["anthropic.claude-v2", "anthropic.claude-v2:1", "anthropic.claude-instant-v1"]

    stop_reasons = ["stop_sequence", "max_tokens", "end_turn"]

    response_text = draw(
        st.text(
            min_size=10, max_size=1000, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    latency = draw(st.floats(min_value=0.1, max_value=60.0, allow_nan=False, allow_infinity=False))

    return {
        "response": response_text,
        "metadata": {
            "modelId": draw(st.sampled_from(model_ids)),
            "latency": latency,
            "stopReason": draw(st.sampled_from(stop_reasons)),
        },
    }


@composite
def prompt_version_strategy(draw):
    """Generate arbitrary prompt versions."""
    version_formats = [
        f"v{draw(st.integers(min_value=1, max_value=10))}.{draw(st.integers(min_value=0, max_value=20))}",
        f"{draw(st.integers(min_value=1, max_value=100))}",
        "default",
        draw(
            st.text(
                min_size=1, max_size=20, alphabet=st.characters(min_codepoint=48, max_codepoint=122)
            )
        ),
    ]
    return draw(st.sampled_from(version_formats))


@composite
def prompt_length_strategy(draw):
    """Generate arbitrary prompt lengths."""
    return draw(st.integers(min_value=100, max_value=50000))


@composite
def incident_id_strategy(draw):
    """Generate arbitrary incident IDs."""
    return draw(
        st.one_of(
            st.uuids().map(lambda u: u.hex),
            st.text(
                min_size=10,
                max_size=50,
                alphabet=st.characters(min_codepoint=48, max_codepoint=122),
            ),
        )
    )


@composite
def error_message_strategy(draw):
    """Generate arbitrary error messages."""
    error_types = [
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelTimeoutException",
        "InvalidRequestException",
        "Circuit breaker open",
        "Connection timeout",
        "Unknown error",
    ]
    return draw(st.sampled_from(error_types))


# Property Tests


@given(llm_response_strategy(), prompt_version_strategy(), prompt_length_strategy())
def test_property_20_analysis_report_metadata_completeness(
    llm_response, prompt_version, prompt_length
):
    """
    **Property 20: Analysis Report Metadata Completeness**
    **Validates: Requirements 7.7, 16.5**

    For any analysis report, metadata must include model ID, version, prompt version,
    token usage, and latency.

    This property verifies that:
    1. Metadata contains all required fields
    2. Model ID is present and non-empty
    3. Model version is present and non-empty
    4. Prompt version is present and non-empty
    5. Token usage contains input and output counts
    6. Latency is a non-negative number
    """
    # Extract metadata from LLM response
    metadata = extract_metadata(llm_response, prompt_version, prompt_length)

    # Verify metadata is a dictionary
    assert isinstance(metadata, dict), "Metadata should be a dictionary"

    # Verify all required fields are present
    required_fields = ["modelId", "modelVersion", "promptVersion", "tokenUsage", "latency"]
    for field in required_fields:
        assert field in metadata, f"Metadata should contain field '{field}'"

    # Verify modelId is a non-empty string
    assert isinstance(metadata["modelId"], str), "modelId should be a string"
    assert len(metadata["modelId"]) > 0, "modelId should not be empty"

    # Verify modelVersion is a non-empty string
    assert isinstance(metadata["modelVersion"], str), "modelVersion should be a string"
    assert len(metadata["modelVersion"]) > 0, "modelVersion should not be empty"

    # Verify promptVersion is a non-empty string
    assert isinstance(metadata["promptVersion"], str), "promptVersion should be a string"
    assert len(metadata["promptVersion"]) > 0, "promptVersion should not be empty"
    assert (
        metadata["promptVersion"] == prompt_version
    ), f"promptVersion should match input ({prompt_version}), got {metadata['promptVersion']}"

    # Verify tokenUsage is a dictionary
    assert isinstance(metadata["tokenUsage"], dict), "tokenUsage should be a dictionary"

    # Verify tokenUsage contains input and output keys
    assert "input" in metadata["tokenUsage"], "tokenUsage should contain 'input' key"
    assert "output" in metadata["tokenUsage"], "tokenUsage should contain 'output' key"

    # Verify token counts are non-negative integers
    assert isinstance(
        metadata["tokenUsage"]["input"], int
    ), "input token count should be an integer"
    assert isinstance(
        metadata["tokenUsage"]["output"], int
    ), "output token count should be an integer"
    assert metadata["tokenUsage"]["input"] >= 0, "input token count should be non-negative"
    assert metadata["tokenUsage"]["output"] >= 0, "output token count should be non-negative"

    # Verify latency is a non-negative number
    assert isinstance(metadata["latency"], (int, float)), "latency should be a number"
    assert metadata["latency"] >= 0, "latency should be non-negative"

    # Verify token usage is reasonable based on prompt length
    # Rough approximation: 1 token ≈ 4 characters
    expected_input_tokens = prompt_length // 4
    # Allow some tolerance (within 50% of expected)
    assert (
        metadata["tokenUsage"]["input"] > 0
    ), "input token count should be positive for non-empty prompt"
    assert (
        metadata["tokenUsage"]["input"] >= expected_input_tokens * 0.5
    ), f"input token count ({metadata['tokenUsage']['input']}) should be reasonable for prompt length ({prompt_length})"
    assert (
        metadata["tokenUsage"]["input"] <= expected_input_tokens * 1.5
    ), f"input token count ({metadata['tokenUsage']['input']}) should be reasonable for prompt length ({prompt_length})"

    # Verify output token count is reasonable based on response length
    response_length = len(llm_response["response"])
    expected_output_tokens = response_length // 4
    if response_length > 0:
        assert (
            metadata["tokenUsage"]["output"] > 0
        ), "output token count should be positive for non-empty response"
        assert (
            metadata["tokenUsage"]["output"] >= expected_output_tokens * 0.5
        ), f"output token count ({metadata['tokenUsage']['output']}) should be reasonable for response length ({response_length})"
        assert (
            metadata["tokenUsage"]["output"] <= expected_output_tokens * 1.5
        ), f"output token count ({metadata['tokenUsage']['output']}) should be reasonable for response length ({response_length})"


@given(incident_id_strategy(), error_message_strategy())
def test_fallback_report_metadata_completeness(incident_id, error_message):
    """
    Property: Fallback reports also contain complete metadata.

    This verifies that even when LLM invocation fails, the fallback report
    includes all required metadata fields.
    """
    # Create fallback report
    fallback = create_fallback_report(incident_id, error_message)

    # Verify fallback is a dictionary
    assert isinstance(fallback, dict), "Fallback report should be a dictionary"

    # Verify top-level structure
    assert "incidentId" in fallback, "Fallback should contain incidentId"
    assert "timestamp" in fallback, "Fallback should contain timestamp"
    assert "analysis" in fallback, "Fallback should contain analysis"
    assert "metadata" in fallback, "Fallback should contain metadata"

    # Verify incident ID matches
    assert fallback["incidentId"] == incident_id, "Fallback incidentId should match input"

    # Extract metadata
    metadata = fallback["metadata"]

    # Verify metadata is a dictionary
    assert isinstance(metadata, dict), "Metadata should be a dictionary"

    # Verify all required fields are present
    required_fields = ["modelId", "modelVersion", "promptVersion", "tokenUsage", "latency"]
    for field in required_fields:
        assert field in metadata, f"Fallback metadata should contain field '{field}'"

    # Verify field types
    assert isinstance(metadata["modelId"], str), "modelId should be a string"
    assert isinstance(metadata["modelVersion"], str), "modelVersion should be a string"
    assert isinstance(metadata["promptVersion"], str), "promptVersion should be a string"
    assert isinstance(metadata["tokenUsage"], dict), "tokenUsage should be a dictionary"
    assert isinstance(metadata["latency"], (int, float)), "latency should be a number"

    # Verify token usage structure
    assert "input" in metadata["tokenUsage"], "tokenUsage should contain 'input'"
    assert "output" in metadata["tokenUsage"], "tokenUsage should contain 'output'"
    assert isinstance(metadata["tokenUsage"]["input"], int), "input tokens should be an integer"
    assert isinstance(metadata["tokenUsage"]["output"], int), "output tokens should be an integer"

    # Verify fallback-specific values
    assert metadata["modelId"] == "fallback", "Fallback modelId should be 'fallback'"
    assert metadata["modelVersion"] == "N/A", "Fallback modelVersion should be 'N/A'"
    assert metadata["promptVersion"] == "N/A", "Fallback promptVersion should be 'N/A'"
    assert metadata["tokenUsage"]["input"] == 0, "Fallback input tokens should be 0"
    assert metadata["tokenUsage"]["output"] == 0, "Fallback output tokens should be 0"
    assert metadata["latency"] == 0.0, "Fallback latency should be 0.0"

    # Verify error is included in metadata
    assert "error" in metadata, "Fallback metadata should contain error field"
    assert metadata["error"] == error_message, "Error message should match input"


@given(llm_response_strategy(), prompt_version_strategy(), prompt_length_strategy())
def test_metadata_extraction_is_deterministic(llm_response, prompt_version, prompt_length):
    """
    Property: Extracting metadata multiple times produces identical results.

    This ensures the metadata extraction function is deterministic.
    """
    # Extract metadata multiple times
    metadata1 = extract_metadata(llm_response, prompt_version, prompt_length)
    metadata2 = extract_metadata(llm_response, prompt_version, prompt_length)
    metadata3 = extract_metadata(llm_response, prompt_version, prompt_length)

    # All should be identical
    assert metadata1 == metadata2, "Multiple extractions should produce identical metadata"
    assert metadata2 == metadata3, "Multiple extractions should produce identical metadata"
    assert metadata1 == metadata3, "Multiple extractions should produce identical metadata"


@given(
    st.lists(
        st.tuples(llm_response_strategy(), prompt_version_strategy(), prompt_length_strategy()),
        min_size=2,
        max_size=5,
    )
)
def test_different_inputs_produce_different_metadata(input_combinations):
    """
    Property: Significantly different inputs produce different metadata.

    This ensures metadata extraction is input-specific for meaningfully different inputs.
    """
    # Extract metadata for all inputs
    metadata_list = [
        extract_metadata(llm_resp, prompt_ver, prompt_len)
        for llm_resp, prompt_ver, prompt_len in input_combinations
    ]

    # Compare each pair
    for i in range(len(metadata_list)):
        for j in range(i + 1, len(metadata_list)):
            input1 = input_combinations[i]
            input2 = input_combinations[j]

            llm_resp1, prompt_ver1, prompt_len1 = input1
            llm_resp2, prompt_ver2, prompt_len2 = input2

            # If inputs are significantly different, metadata should differ
            # Check for significant differences in inputs
            prompt_version_differs = prompt_ver1 != prompt_ver2
            model_id_differs = llm_resp1["metadata"]["modelId"] != llm_resp2["metadata"]["modelId"]
            latency_differs = llm_resp1["metadata"]["latency"] != llm_resp2["metadata"]["latency"]

            # Significant difference in prompt length (>20% difference)
            prompt_length_significantly_differs = (
                abs(prompt_len1 - prompt_len2) > max(prompt_len1, prompt_len2) * 0.2
            )

            # Significant difference in response length (>20% difference)
            resp_len1 = len(llm_resp1["response"])
            resp_len2 = len(llm_resp2["response"])
            response_length_significantly_differs = (
                resp_len1 > 0
                and resp_len2 > 0
                and abs(resp_len1 - resp_len2) > max(resp_len1, resp_len2) * 0.2
            )

            # If there are significant differences, metadata should reflect them
            if (
                prompt_version_differs
                or model_id_differs
                or latency_differs
                or prompt_length_significantly_differs
                or response_length_significantly_differs
            ):

                metadata1 = metadata_list[i]
                metadata2 = metadata_list[j]

                # Check if at least one field differs
                differs = (
                    metadata1["promptVersion"] != metadata2["promptVersion"]
                    or metadata1["tokenUsage"] != metadata2["tokenUsage"]
                    or metadata1["latency"] != metadata2["latency"]
                    or metadata1["modelId"] != metadata2["modelId"]
                )

                assert differs, (
                    f"Significantly different inputs should produce different metadata. "
                    f"Input1: prompt_ver={prompt_ver1}, model={llm_resp1['metadata']['modelId']}, "
                    f"latency={llm_resp1['metadata']['latency']}, prompt_len={prompt_len1}, resp_len={resp_len1}. "
                    f"Input2: prompt_ver={prompt_ver2}, model={llm_resp2['metadata']['modelId']}, "
                    f"latency={llm_resp2['metadata']['latency']}, prompt_len={prompt_len2}, resp_len={resp_len2}"
                )


@given(llm_response_strategy(), prompt_version_strategy(), prompt_length_strategy())
def test_metadata_can_be_serialized_to_json(llm_response, prompt_version, prompt_length):
    """
    Property: Metadata can be serialized to JSON without errors.

    This ensures metadata is JSON-serializable for storage and transmission.
    """
    # Extract metadata
    metadata = extract_metadata(llm_response, prompt_version, prompt_length)

    # Serialize to JSON - should not raise exception
    try:
        json_str = json.dumps(metadata)
    except (TypeError, ValueError) as e:
        assert False, f"Metadata should be JSON-serializable, got error: {e}"

    # Verify JSON is valid
    assert isinstance(json_str, str), "JSON serialization should produce a string"
    assert len(json_str) > 0, "JSON string should not be empty"

    # Verify we can deserialize it back
    try:
        deserialized = json.loads(json_str)
    except json.JSONDecodeError as e:
        assert False, f"Serialized metadata should be valid JSON: {e}"

    # Verify deserialized matches original
    assert deserialized == metadata, "Deserialized metadata should match original"


@given(incident_id_strategy(), error_message_strategy())
def test_fallback_report_can_be_serialized_to_json(incident_id, error_message):
    """
    Property: Fallback reports can be serialized to JSON without errors.

    This ensures fallback reports are JSON-serializable.
    """
    # Create fallback report
    fallback = create_fallback_report(incident_id, error_message)

    # Serialize to JSON - should not raise exception
    try:
        json_str = json.dumps(fallback)
    except (TypeError, ValueError) as e:
        assert False, f"Fallback report should be JSON-serializable, got error: {e}"

    # Verify JSON is valid
    assert isinstance(json_str, str), "JSON serialization should produce a string"
    assert len(json_str) > 0, "JSON string should not be empty"

    # Verify we can deserialize it back
    try:
        deserialized = json.loads(json_str)
    except json.JSONDecodeError as e:
        assert False, f"Serialized fallback should be valid JSON: {e}"

    # Verify deserialized matches original
    assert deserialized == fallback, "Deserialized fallback should match original"


@given(llm_response_strategy(), prompt_version_strategy(), prompt_length_strategy())
def test_metadata_latency_matches_llm_response(llm_response, prompt_version, prompt_length):
    """
    Property: Metadata latency matches the latency from LLM response.

    This ensures latency is correctly extracted from the LLM response.
    """
    # Extract metadata
    metadata = extract_metadata(llm_response, prompt_version, prompt_length)

    # Verify latency matches
    expected_latency = llm_response["metadata"]["latency"]
    assert (
        metadata["latency"] == expected_latency
    ), f"Metadata latency ({metadata['latency']}) should match LLM response latency ({expected_latency})"


@given(llm_response_strategy(), prompt_version_strategy(), prompt_length_strategy())
def test_metadata_model_id_matches_llm_response(llm_response, prompt_version, prompt_length):
    """
    Property: Metadata model ID matches the model ID from LLM response.

    This ensures model ID is correctly extracted from the LLM response.
    """
    # Extract metadata
    metadata = extract_metadata(llm_response, prompt_version, prompt_length)

    # Verify model ID matches
    expected_model_id = llm_response["metadata"]["modelId"]
    assert (
        metadata["modelId"] == expected_model_id
    ), f"Metadata modelId ({metadata['modelId']}) should match LLM response modelId ({expected_model_id})"


def test_metadata_with_missing_llm_metadata_fields():
    """
    Property: Metadata extraction handles missing LLM metadata fields gracefully.

    This verifies the function provides defaults when LLM response is incomplete.
    """
    # Create LLM response with missing metadata fields
    incomplete_response = {"response": "Test response", "metadata": {}}  # Empty metadata

    # Extract metadata - should not raise exception
    try:
        metadata = extract_metadata(incomplete_response, "v1.0", 1000)
    except Exception as e:
        assert False, f"Metadata extraction should handle missing fields, got error: {e}"

    # Verify all required fields are present with defaults
    assert "modelId" in metadata
    assert "modelVersion" in metadata
    assert "promptVersion" in metadata
    assert "tokenUsage" in metadata
    assert "latency" in metadata

    # Verify defaults are reasonable
    assert metadata["modelId"] == "anthropic.claude-v2", "Should use default model ID"
    assert metadata["latency"] == 0.0, "Should use default latency"


def test_metadata_with_zero_length_prompt():
    """
    Property: Metadata extraction handles zero-length prompts.

    This verifies the function handles edge case of empty prompts.
    """
    llm_response = {
        "response": "Test response",
        "metadata": {"modelId": "anthropic.claude-v2", "latency": 1.5, "stopReason": "end_turn"},
    }

    # Extract metadata with zero-length prompt
    metadata = extract_metadata(llm_response, "v1.0", 0)

    # Verify metadata is valid
    assert isinstance(metadata, dict)
    assert "tokenUsage" in metadata
    assert metadata["tokenUsage"]["input"] == 0, "Zero-length prompt should have 0 input tokens"


def test_metadata_with_very_long_prompt():
    """
    Property: Metadata extraction handles very long prompts.

    This verifies the function handles large token counts.
    """
    llm_response = {
        "response": "A" * 10000,  # Very long response
        "metadata": {"modelId": "anthropic.claude-v2", "latency": 5.0, "stopReason": "max_tokens"},
    }

    # Extract metadata with very long prompt
    metadata = extract_metadata(llm_response, "v1.0", 100000)

    # Verify metadata is valid
    assert isinstance(metadata, dict)
    assert "tokenUsage" in metadata
    assert metadata["tokenUsage"]["input"] > 0, "Long prompt should have positive input tokens"
    assert metadata["tokenUsage"]["output"] > 0, "Long response should have positive output tokens"

    # Verify token counts are reasonable (not negative or absurdly large)
    assert metadata["tokenUsage"]["input"] < 1000000, "Input token count should be reasonable"
    assert metadata["tokenUsage"]["output"] < 1000000, "Output token count should be reasonable"
