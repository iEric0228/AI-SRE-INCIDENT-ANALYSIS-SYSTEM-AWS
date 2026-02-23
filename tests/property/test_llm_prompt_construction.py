"""
Property-based tests for LLM prompt construction.

This module tests that the LLM analyzer correctly constructs prompts that include
the complete structured context and follow the template format.

Validates Requirements 7.1, 16.1
"""

import json
import sys
import os
from hypothesis import given, strategies as st
from hypothesis.strategies import composite

# Import LLM analyzer functions directly
# Clear any cached lambda_function module first
if "lambda_function" in sys.modules:
    del sys.modules["lambda_function"]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "llm_analyzer"))
import lambda_function as llm_lambda

construct_prompt = llm_lambda.construct_prompt
get_default_prompt_template = llm_lambda.get_default_prompt_template


# Strategy generators


@composite
def structured_context_strategy(draw):
    """Generate arbitrary structured context instances."""
    # Generate resource info
    resource_type = draw(st.sampled_from(["ec2", "lambda", "rds", "ecs"]))
    resource_name = draw(
        st.text(
            min_size=1, max_size=50, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
        )
    )

    # Generate alarm info
    alarm_name = draw(
        st.text(
            min_size=1, max_size=50, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
        )
    )
    metric_name = draw(
        st.text(
            min_size=1, max_size=30, alphabet=st.characters(min_codepoint=65, max_codepoint=122)
        )
    )

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
            "count": draw(st.integers(min_value=0, max_value=1000)),
        },
        "metrics": draw(
            st.lists(
                st.dictionaries(
                    keys=st.sampled_from(["metricName", "namespace", "statistics"]),
                    values=st.one_of(
                        st.text(
                            min_size=1,
                            max_size=30,
                            alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                        ),
                        st.dictionaries(
                            keys=st.sampled_from(["avg", "max", "min"]),
                            values=st.floats(
                                min_value=0.0,
                                max_value=100.0,
                                allow_nan=False,
                                allow_infinity=False,
                            ),
                        ),
                    ),
                ),
                min_size=0,
                max_size=5,
            )
        ),
        "timeSeries": draw(
            st.lists(
                st.dictionaries(
                    keys=st.sampled_from(["timestamp", "metricName", "value", "unit"]),
                    values=st.one_of(
                        st.text(
                            min_size=1,
                            max_size=30,
                            alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                        ),
                        st.floats(
                            min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False
                        ),
                    ),
                ),
                min_size=0,
                max_size=10,
            )
        ),
    }

    # Generate logs data
    logs_data = {
        "errorCount": draw(st.integers(min_value=0, max_value=100)),
        "errorCountsByLevel": {
            "ERROR": draw(st.integers(min_value=0, max_value=50)),
            "WARN": draw(st.integers(min_value=0, max_value=50)),
            "CRITICAL": draw(st.integers(min_value=0, max_value=50)),
        },
        "topErrors": draw(
            st.lists(
                st.text(
                    min_size=1,
                    max_size=100,
                    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                ),
                min_size=0,
                max_size=5,
            )
        ),
        "entries": draw(
            st.lists(
                st.dictionaries(
                    keys=st.sampled_from(["timestamp", "logLevel", "message", "logStream"]),
                    values=st.text(
                        min_size=1,
                        max_size=50,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    ),
                ),
                min_size=0,
                max_size=10,
            )
        ),
        "totalMatches": draw(st.integers(min_value=0, max_value=1000)),
        "returned": draw(st.integers(min_value=0, max_value=100)),
    }

    # Generate changes data
    changes_data = {
        "recentDeployments": draw(st.integers(min_value=0, max_value=10)),
        "changeCountsByType": {
            "deployment": draw(st.integers(min_value=0, max_value=10)),
            "configuration": draw(st.integers(min_value=0, max_value=10)),
            "infrastructure": draw(st.integers(min_value=0, max_value=10)),
        },
        "totalChanges": draw(st.integers(min_value=0, max_value=50)),
        "entries": draw(
            st.lists(
                st.dictionaries(
                    keys=st.sampled_from(
                        ["timestamp", "changeType", "eventName", "user", "description"]
                    ),
                    values=st.text(
                        min_size=1,
                        max_size=50,
                        alphabet=st.characters(min_codepoint=65, max_codepoint=122),
                    ),
                ),
                min_size=0,
                max_size=10,
            )
        ),
    }

    # Generate completeness info
    completeness = {
        "metrics": draw(st.booleans()),
        "logs": draw(st.booleans()),
        "changes": draw(st.booleans()),
    }

    # Construct structured context
    return {
        "incidentId": draw(st.uuids()).hex,
        "timestamp": "2024-01-15T14:30:00Z",
        "resource": {
            "arn": f"arn:aws:{resource_type}:us-east-1:123456789012:instance/{resource_name}",
            "type": resource_type,
            "name": resource_name,
        },
        "alarm": {
            "name": alarm_name,
            "metric": metric_name,
            "threshold": draw(
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
            ),
        },
        "metrics": metrics_data,
        "logs": logs_data,
        "changes": changes_data,
        "completeness": completeness,
    }


@composite
def prompt_template_strategy(draw):
    """Generate arbitrary prompt templates with placeholder."""
    # Templates must contain {structured_context} placeholder
    prefix = draw(
        st.text(
            min_size=10, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )
    suffix = draw(
        st.text(
            min_size=10, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126)
        )
    )

    return f"{prefix}\n{{structured_context}}\n{suffix}"


# Property Tests


@given(structured_context_strategy())
def test_property_18_llm_prompt_construction(structured_context):
    """
    **Property 18: LLM Prompt Construction**
    **Validates: Requirements 7.1, 16.1**

    For any structured context, prompt must include complete context and follow template format.

    This property verifies that:
    1. The prompt includes the complete structured context as JSON
    2. The prompt follows the template format
    3. All fields from the structured context are present in the prompt
    4. The context is properly formatted as JSON
    """
    # Get default template
    template = get_default_prompt_template()

    # Construct prompt
    prompt = construct_prompt(template, structured_context)

    # Verify prompt is not empty
    assert prompt, "Prompt should not be empty"
    assert len(prompt) > 0, "Prompt should have content"

    # Verify template structure is preserved
    # The template should have sections before and after the context
    assert (
        "You are an expert Site Reliability Engineer" in prompt
    ), "Prompt should contain role definition from template"
    assert "TASK:" in prompt, "Prompt should contain task description from template"
    assert "OUTPUT FORMAT" in prompt, "Prompt should contain output format from template"
    assert "CONSTRAINTS:" in prompt, "Prompt should contain constraints from template"

    # Verify structured context is included in the prompt
    # The context should be formatted as JSON
    context_json = json.dumps(structured_context, indent=2)
    assert context_json in prompt, "Prompt should contain the complete structured context as JSON"

    # Verify all top-level keys from structured context are in the prompt
    required_keys = [
        "incidentId",
        "timestamp",
        "resource",
        "alarm",
        "metrics",
        "logs",
        "changes",
        "completeness",
    ]
    for key in required_keys:
        assert f'"{key}"' in prompt, f"Prompt should contain key '{key}' from structured context"

    # Verify specific values from structured context are in the prompt
    # Note: Values may be JSON-escaped, so we check for their presence in the JSON representation
    assert structured_context["incidentId"] in prompt, "Prompt should contain incident ID"
    assert structured_context["timestamp"] in prompt, "Prompt should contain timestamp"
    assert structured_context["resource"]["type"] in prompt, "Prompt should contain resource type"

    # For string values that might contain special characters, check they're in the JSON
    # The JSON serialization will escape them properly
    resource_name_json = json.dumps(structured_context["resource"]["name"])
    assert (
        resource_name_json in prompt or structured_context["resource"]["name"] in prompt
    ), "Prompt should contain resource name (possibly JSON-escaped)"

    alarm_name_json = json.dumps(structured_context["alarm"]["name"])
    assert (
        alarm_name_json in prompt or structured_context["alarm"]["name"] in prompt
    ), "Prompt should contain alarm name (possibly JSON-escaped)"

    metric_name_json = json.dumps(structured_context["alarm"]["metric"])
    assert (
        metric_name_json in prompt or structured_context["alarm"]["metric"] in prompt
    ), "Prompt should contain metric name (possibly JSON-escaped)"

    # Verify completeness information is included
    # Python's json.dumps uses lowercase for booleans, so check for that
    assert '"completeness"' in prompt, "Prompt should contain completeness key"

    # Verify the prompt is valid (can be used for LLM invocation)
    # Should not contain placeholder markers
    assert "{structured_context}" not in prompt, "Prompt should not contain unreplaced placeholder"

    # Verify prompt length is reasonable (not truncated)
    # The prompt should be at least as long as the template plus context
    min_expected_length = len(template) + len(context_json) - len("{structured_context}")
    assert (
        len(prompt) >= min_expected_length
    ), f"Prompt length ({len(prompt)}) should be at least {min_expected_length}"


@given(structured_context_strategy(), prompt_template_strategy())
def test_prompt_construction_with_custom_template(structured_context, custom_template):
    """
    Property: Prompt construction works with any valid template containing placeholder.

    This verifies that the construct_prompt function correctly handles different
    template formats as long as they contain the {structured_context} placeholder.
    """
    # Construct prompt with custom template
    prompt = construct_prompt(custom_template, structured_context)

    # Verify prompt is not empty
    assert prompt, "Prompt should not be empty"

    # Verify placeholder was replaced
    assert "{structured_context}" not in prompt, "Placeholder should be replaced"

    # Verify structured context is in the prompt
    context_json = json.dumps(structured_context, indent=2)
    assert context_json in prompt, "Prompt should contain structured context JSON"

    # Verify template structure is preserved (parts before and after placeholder)
    template_parts = custom_template.split("{structured_context}")
    if len(template_parts) == 2:
        prefix, suffix = template_parts
        if prefix.strip():
            assert prefix in prompt, "Template prefix should be in prompt"
        if suffix.strip():
            assert suffix in prompt, "Template suffix should be in prompt"


@given(structured_context_strategy())
def test_prompt_contains_all_context_fields(structured_context):
    """
    Property: Prompt contains all fields from structured context.

    This is a focused test ensuring no data is lost during prompt construction.
    """
    template = get_default_prompt_template()
    prompt = construct_prompt(template, structured_context)

    # Verify all nested fields are present
    # Resource fields - check for JSON-escaped versions for strings with special chars
    resource_arn_json = json.dumps(structured_context["resource"]["arn"])
    assert (
        resource_arn_json in prompt or structured_context["resource"]["arn"] in prompt
    ), "Resource ARN should be in prompt"
    assert structured_context["resource"]["type"] in prompt, "Resource type should be in prompt"

    resource_name_json = json.dumps(structured_context["resource"]["name"])
    assert (
        resource_name_json in prompt or structured_context["resource"]["name"] in prompt
    ), "Resource name should be in prompt"

    # Alarm fields - check for JSON-escaped versions
    alarm_name_json = json.dumps(structured_context["alarm"]["name"])
    assert (
        alarm_name_json in prompt or structured_context["alarm"]["name"] in prompt
    ), "Alarm name should be in prompt"

    alarm_metric_json = json.dumps(structured_context["alarm"]["metric"])
    assert (
        alarm_metric_json in prompt or structured_context["alarm"]["metric"] in prompt
    ), "Alarm metric should be in prompt"

    assert (
        str(structured_context["alarm"]["threshold"]) in prompt
    ), "Alarm threshold should be in prompt"

    # Metrics summary
    if structured_context["completeness"]["metrics"]:
        metrics_summary = structured_context["metrics"]["summary"]
        # At least one summary statistic should be present
        assert (
            str(metrics_summary["avg"]) in prompt
            or str(metrics_summary["max"]) in prompt
            or str(metrics_summary["min"]) in prompt
        ), "Metrics summary statistics should be in prompt"

    # Logs data
    if structured_context["completeness"]["logs"]:
        assert (
            str(structured_context["logs"]["errorCount"]) in prompt
        ), "Log error count should be in prompt"
        assert (
            str(structured_context["logs"]["totalMatches"]) in prompt
        ), "Log total matches should be in prompt"

    # Changes data
    if structured_context["completeness"]["changes"]:
        assert (
            str(structured_context["changes"]["recentDeployments"]) in prompt
        ), "Recent deployments count should be in prompt"
        assert (
            str(structured_context["changes"]["totalChanges"]) in prompt
        ), "Total changes count should be in prompt"


@given(structured_context_strategy())
def test_prompt_json_is_valid(structured_context):
    """
    Property: The structured context in the prompt is valid JSON.

    This ensures the context can be parsed if needed and is properly formatted.
    """
    template = get_default_prompt_template()
    prompt = construct_prompt(template, structured_context)

    # Extract the JSON portion from the prompt
    # The context should be formatted as indented JSON
    context_json = json.dumps(structured_context, indent=2)

    # Verify the JSON is in the prompt
    assert context_json in prompt, "Prompt should contain valid JSON"

    # Verify we can parse it back
    try:
        # Find the JSON in the prompt and parse it
        start_idx = prompt.find(context_json)
        assert start_idx != -1, "JSON should be found in prompt"

        extracted_json = prompt[start_idx : start_idx + len(context_json)]
        parsed = json.loads(extracted_json)

        # Verify parsed matches original
        assert parsed == structured_context, "Parsed JSON should match original context"
    except json.JSONDecodeError as e:
        assert False, f"JSON in prompt should be valid: {e}"


@given(st.lists(structured_context_strategy(), min_size=2, max_size=5))
def test_different_contexts_produce_different_prompts(contexts):
    """
    Property: Different structured contexts produce different prompts.

    This ensures the prompt construction is deterministic and context-specific.
    """
    template = get_default_prompt_template()

    # Construct prompts for all contexts
    prompts = [construct_prompt(template, ctx) for ctx in contexts]

    # Verify each prompt is unique (unless contexts are identical)
    for i in range(len(prompts)):
        for j in range(i + 1, len(prompts)):
            if contexts[i] != contexts[j]:
                assert (
                    prompts[i] != prompts[j]
                ), "Different contexts should produce different prompts"


@given(structured_context_strategy())
def test_prompt_construction_is_deterministic(structured_context):
    """
    Property: Constructing a prompt multiple times with the same input produces identical results.

    This ensures the function is pure and deterministic.
    """
    template = get_default_prompt_template()

    # Construct prompt multiple times
    prompt1 = construct_prompt(template, structured_context)
    prompt2 = construct_prompt(template, structured_context)
    prompt3 = construct_prompt(template, structured_context)

    # All should be identical
    assert prompt1 == prompt2, "Multiple constructions should produce identical prompts"
    assert prompt2 == prompt3, "Multiple constructions should produce identical prompts"
    assert prompt1 == prompt3, "Multiple constructions should produce identical prompts"
