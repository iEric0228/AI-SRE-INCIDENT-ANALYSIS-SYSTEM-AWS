"""
Prompt Builder for LLM Analyzer

Handles retrieval of the prompt template from SSM Parameter Store and
construction of the final prompt sent to Bedrock.
"""

import json
import logging
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def retrieve_prompt_template(
    ssm_client, parameter_name: str = "/incident-analysis/prompt-template"
) -> Dict[str, str]:
    """
    Retrieve prompt template from Parameter Store.

    Args:
        ssm_client: boto3 SSM client
        parameter_name: Parameter Store parameter name

    Returns:
        Dict with 'template' and 'version' keys

    Raises:
        Exception: If parameter retrieval fails with a non-404 error
    """
    try:
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=False)

        template = response["Parameter"]["Value"]
        version = str(response["Parameter"]["Version"])

        logger.info(f"Retrieved prompt template version {version}")

        return {"template": template, "version": version}
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ParameterNotFound":
            logger.warning(f"Prompt template not found at {parameter_name}, using default")
            return {"template": get_default_prompt_template(), "version": "default"}
        else:
            logger.error(f"Failed to retrieve prompt template: {e}")
            raise


def get_default_prompt_template() -> str:
    """
    Get default prompt template if Parameter Store retrieval fails.

    Returns:
        Default prompt template string
    """
    return """You are an expert Site Reliability Engineer analyzing an infrastructure incident.

TASK: Analyze the provided incident data and generate a root-cause hypothesis with supporting evidence.

INPUT DATA:
{structured_context}

OUTPUT FORMAT (JSON):
{{
  "rootCauseHypothesis": "Single sentence hypothesis",
  "confidence": "high|medium|low",
  "evidence": ["Specific data point 1", "Specific data point 2"],
  "contributingFactors": ["Factor 1", "Factor 2"],
  "recommendedActions": ["Action 1", "Action 2"]
}}

CONSTRAINTS:
- Base hypothesis ONLY on provided data (no speculation)
- Cite specific metrics, logs, or changes as evidence
- Confidence = high if multiple correlated signals, medium if single signal, low if ambiguous
- Recommended actions must be specific and actionable
- Keep response under 500 tokens

ANALYSIS:"""


def construct_prompt(template: str, structured_context: Dict[str, Any]) -> str:
    """
    Construct LLM prompt from template and structured context.

    Args:
        template: Prompt template string
        structured_context: Normalized incident context

    Returns:
        Complete prompt string
    """
    # Format structured context as readable JSON
    context_json = json.dumps(structured_context, indent=2)

    # Inject context into template
    prompt = template.replace("{structured_context}", context_json)

    return prompt
