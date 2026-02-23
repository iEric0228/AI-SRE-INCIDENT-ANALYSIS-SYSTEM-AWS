"""
Unit tests for the LLM prompt template structure and content.

These tests verify that the prompt template meets all requirements without
requiring AWS credentials or Parameter Store access.

Requirements: 16.1, 16.2, 16.3, 16.4, 16.5
"""

import sys
import os
import json

# Add scripts directory to path to import the template
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from create_prompt_template import PROMPT_TEMPLATE, PROMPT_VERSION, PARAMETER_NAME


class TestPromptTemplateStructure:
    """Test the structure and content of the prompt template."""

    def test_template_has_role_definition(self):
        """Requirement 16.1: Template includes role definition."""
        assert "ROLE:" in PROMPT_TEMPLATE
        assert "Site Reliability Engineer" in PROMPT_TEMPLATE
        assert "expert" in PROMPT_TEMPLATE.lower()

    def test_template_has_task_description(self):
        """Requirement 16.1: Template includes task description."""
        assert "TASK:" in PROMPT_TEMPLATE
        assert "analyze" in PROMPT_TEMPLATE.lower()
        assert "root-cause hypothesis" in PROMPT_TEMPLATE.lower()

    def test_template_has_input_format(self):
        """Requirement 16.1: Template includes input format specification."""
        assert "INPUT DATA:" in PROMPT_TEMPLATE
        assert "{structured_context}" in PROMPT_TEMPLATE

    def test_template_has_output_format(self):
        """Requirement 16.1: Template includes output format specification."""
        assert "OUTPUT FORMAT" in PROMPT_TEMPLATE
        assert "rootCauseHypothesis" in PROMPT_TEMPLATE
        assert "confidence" in PROMPT_TEMPLATE
        assert "evidence" in PROMPT_TEMPLATE
        assert "contributingFactors" in PROMPT_TEMPLATE
        assert "recommendedActions" in PROMPT_TEMPLATE

    def test_template_has_instructions_section(self):
        """Requirement 16.1: Template includes detailed instructions."""
        assert "INSTRUCTIONS:" in PROMPT_TEMPLATE

    def test_template_has_confidence_level_instructions(self):
        """Requirement 16.3: Template includes confidence level instructions."""
        assert "CONFIDENCE LEVELS:" in PROMPT_TEMPLATE
        assert "HIGH:" in PROMPT_TEMPLATE
        assert "MEDIUM:" in PROMPT_TEMPLATE
        assert "LOW:" in PROMPT_TEMPLATE
        assert "multiple correlated signals" in PROMPT_TEMPLATE.lower()

    def test_template_has_evidence_citation_instructions(self):
        """Requirement 16.4: Template includes evidence citation instructions."""
        assert "EVIDENCE:" in PROMPT_TEMPLATE
        assert "cite specific" in PROMPT_TEMPLATE.lower()
        assert "exact values" in PROMPT_TEMPLATE.lower()
        assert "timestamps" in PROMPT_TEMPLATE.lower()

    def test_template_has_constraints(self):
        """Requirement 16.1: Template includes constraints."""
        assert "CONSTRAINTS:" in PROMPT_TEMPLATE
        assert "500 tokens" in PROMPT_TEMPLATE
        assert "provided data" in PROMPT_TEMPLATE.lower()
        assert "no speculation" in PROMPT_TEMPLATE.lower()

    def test_template_version_format(self):
        """Requirement 16.5: Template is versioned."""
        assert PROMPT_VERSION.startswith("v")
        assert "." in PROMPT_VERSION
        # Should be in format v1.0, v1.1, v2.0, etc.
        version_parts = PROMPT_VERSION[1:].split(".")
        assert len(version_parts) == 2
        assert all(part.isdigit() for part in version_parts)

    def test_parameter_name_format(self):
        """Verify Parameter Store path follows convention."""
        assert PARAMETER_NAME.startswith("/")
        assert "incident-analysis" in PARAMETER_NAME
        assert "prompt-template" in PARAMETER_NAME

    def test_template_size_reasonable(self):
        """Template should be large enough to be useful but not excessive."""
        # Should be at least 1000 characters for comprehensive instructions
        assert len(PROMPT_TEMPLATE) >= 1000
        # Should be under 10KB to avoid Parameter Store issues
        assert len(PROMPT_TEMPLATE) < 10000

    def test_template_has_context_placeholder(self):
        """Template must have placeholder for structured context injection."""
        assert "{structured_context}" in PROMPT_TEMPLATE
        # Should only appear once
        assert PROMPT_TEMPLATE.count("{structured_context}") == 1

    def test_template_output_format_is_valid_json_structure(self):
        """Output format should show valid JSON structure."""
        # Extract the JSON structure from the template
        assert "{{" in PROMPT_TEMPLATE  # Escaped braces for format string
        assert "}}" in PROMPT_TEMPLATE

        # Verify all required fields are in the output format
        required_fields = [
            "rootCauseHypothesis",
            "confidence",
            "evidence",
            "contributingFactors",
            "recommendedActions",
        ]
        for field in required_fields:
            assert field in PROMPT_TEMPLATE

    def test_template_specifies_confidence_values(self):
        """Template should specify valid confidence values."""
        assert "high|medium|low" in PROMPT_TEMPLATE

    def test_template_has_recommended_actions_guidance(self):
        """Template should guide LLM on recommended actions."""
        assert "RECOMMENDED ACTIONS:" in PROMPT_TEMPLATE or "recommendedActions" in PROMPT_TEMPLATE
        assert "specific" in PROMPT_TEMPLATE.lower()
        assert "actionable" in PROMPT_TEMPLATE.lower()

    def test_template_emphasizes_data_only_analysis(self):
        """Template should emphasize using only provided data."""
        assert (
            "ONLY on provided data" in PROMPT_TEMPLATE
            or "only on the provided data" in PROMPT_TEMPLATE.lower()
        )
        assert (
            "no speculation" in PROMPT_TEMPLATE.lower()
            or "do not make assumptions" in PROMPT_TEMPLATE.lower()
        )

    def test_template_has_token_limit(self):
        """Template should specify token limit for response."""
        assert "500 tokens" in PROMPT_TEMPLATE or "token" in PROMPT_TEMPLATE.lower()

    def test_template_requests_temporal_correlation(self):
        """Template should ask for temporal correlation in evidence."""
        assert "temporal" in PROMPT_TEMPLATE.lower() or "time" in PROMPT_TEMPLATE.lower()
        assert "correlation" in PROMPT_TEMPLATE.lower() or "aligned" in PROMPT_TEMPLATE.lower()


class TestPromptTemplateContent:
    """Test the quality and completeness of prompt template content."""

    def test_role_establishes_expertise(self):
        """Role should establish high level of expertise."""
        role_section = PROMPT_TEMPLATE.split("TASK:")[0]
        expertise_keywords = ["expert", "senior", "deep", "expertise"]
        assert any(keyword in role_section.lower() for keyword in expertise_keywords)

    def test_instructions_are_numbered_or_structured(self):
        """Instructions should be well-structured for clarity."""
        instructions_section = PROMPT_TEMPLATE.split("INSTRUCTIONS:")[1].split("CONSTRAINTS:")[0]
        # Should have numbered sections or clear structure
        assert "1." in instructions_section or "ROOT CAUSE" in instructions_section

    def test_confidence_levels_have_clear_criteria(self):
        """Each confidence level should have clear criteria."""
        confidence_section = PROMPT_TEMPLATE.split("CONFIDENCE LEVELS:")[1].split("EVIDENCE:")[0]
        assert "HIGH:" in confidence_section
        assert "MEDIUM:" in confidence_section
        assert "LOW:" in confidence_section
        # Each should have explanation
        assert confidence_section.count(":") >= 3

    def test_evidence_section_provides_examples(self):
        """Evidence section should provide examples or clear guidance."""
        evidence_section = PROMPT_TEMPLATE.split("EVIDENCE:")[1].split("CONTRIBUTING FACTORS:")[0]
        # Should mention specific types of evidence
        assert "metrics" in evidence_section.lower() or "logs" in evidence_section.lower()
        assert "timestamp" in evidence_section.lower()

    def test_recommended_actions_prioritize_mitigation(self):
        """Recommended actions should prioritize immediate mitigation."""
        actions_section = PROMPT_TEMPLATE.split("RECOMMENDED ACTIONS:")[1].split("CONSTRAINTS:")[0]
        assert "immediate" in actions_section.lower() or "mitigation" in actions_section.lower()
        assert "specific" in actions_section.lower()

    def test_constraints_prevent_hallucination(self):
        """Constraints should prevent LLM hallucination."""
        constraints_section = PROMPT_TEMPLATE.split("CONSTRAINTS:")[1]
        hallucination_prevention = [
            "provided data",
            "no speculation",
            "no assumptions",
            "only information",
        ]
        assert any(phrase in constraints_section.lower() for phrase in hallucination_prevention)


class TestPromptTemplateIntegration:
    """Test how the template integrates with the system."""

    def test_template_can_be_formatted_with_context(self):
        """Template should be formattable with structured context."""
        sample_context = {
            "incidentId": "test-123",
            "timestamp": "2024-01-15T14:30:00Z",
            "resource": {"arn": "arn:aws:lambda:us-east-1:123456789012:function:test"},
        }

        # Should be able to replace placeholder
        formatted = PROMPT_TEMPLATE.replace(
            "{structured_context}", json.dumps(sample_context, indent=2)
        )

        assert "{structured_context}" not in formatted
        assert "test-123" in formatted
        assert "2024-01-15T14:30:00Z" in formatted

    def test_template_preserves_json_structure_after_formatting(self):
        """After formatting, JSON structure should still be valid."""
        sample_context = {"test": "data"}
        formatted = PROMPT_TEMPLATE.replace(
            "{structured_context}", json.dumps(sample_context, indent=2)
        )

        # Output format should still be present
        assert "rootCauseHypothesis" in formatted
        assert "confidence" in formatted
        assert "evidence" in formatted

    def test_version_can_be_extracted_from_template(self):
        """Version should be accessible for metadata."""
        assert PROMPT_VERSION is not None
        assert len(PROMPT_VERSION) > 0
        # Should be semantic version
        assert PROMPT_VERSION[0] == "v"
        assert "." in PROMPT_VERSION


class TestPromptTemplateRequirements:
    """Test that template meets all specified requirements."""

    def test_requirement_16_1_structured_prompt(self):
        """Requirement 16.1: Structured prompt with role, task, input/output formats."""
        assert "ROLE:" in PROMPT_TEMPLATE
        assert "TASK:" in PROMPT_TEMPLATE
        assert "INPUT DATA:" in PROMPT_TEMPLATE
        assert "OUTPUT FORMAT" in PROMPT_TEMPLATE

    def test_requirement_16_2_confidence_levels(self):
        """Requirement 16.2: Instructions for confidence levels."""
        assert "CONFIDENCE LEVELS:" in PROMPT_TEMPLATE
        assert "high" in PROMPT_TEMPLATE.lower()
        assert "medium" in PROMPT_TEMPLATE.lower()
        assert "low" in PROMPT_TEMPLATE.lower()

    def test_requirement_16_3_evidence_citation(self):
        """Requirement 16.3: Instructions to cite specific evidence."""
        assert "EVIDENCE:" in PROMPT_TEMPLATE
        assert "cite" in PROMPT_TEMPLATE.lower() or "specific" in PROMPT_TEMPLATE.lower()

    def test_requirement_16_4_versioning(self):
        """Requirement 16.4: Template is versioned."""
        assert PROMPT_VERSION is not None
        assert PROMPT_VERSION.startswith("v")
        assert "." in PROMPT_VERSION

    def test_requirement_16_5_parameter_store_ready(self):
        """Requirement 16.5: Template ready for Parameter Store."""
        # Should be a string
        assert isinstance(PROMPT_TEMPLATE, str)
        # Should be under Parameter Store size limit (4KB for standard, 8KB for advanced)
        assert len(PROMPT_TEMPLATE.encode("utf-8")) < 8192
        # Should have valid parameter name
        assert PARAMETER_NAME.startswith("/")
