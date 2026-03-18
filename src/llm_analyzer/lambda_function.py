"""
LLM Analyzer Lambda Function

This Lambda function invokes Amazon Bedrock to generate root-cause hypotheses
for infrastructure incidents. It constructs a structured prompt from the
correlation engine's output, invokes Claude with retry logic, and parses
the response into a structured analysis report.

Sub-module responsibilities
----------------------------
circuit_breaker.py  – CircuitBreaker class + Lambda-global instance
prompt_builder.py   – SSM template retrieval + prompt construction
response_parser.py  – 3-level fallback parsing + LLMParseLevel metric

This file is the orchestrating entry point only; all domain logic lives in
the sub-modules listed above.
"""

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Sub-module imports
# ---------------------------------------------------------------------------
# circuit_breaker, prompt_builder, and response_parser live alongside this
# file in the same package directory.
sys.path.insert(0, os.path.dirname(__file__))

from circuit_breaker import CircuitBreaker, CircuitState, bedrock_circuit_breaker  # noqa: E402
from prompt_builder import (  # noqa: E402
    construct_prompt,
    get_default_prompt_template,
    retrieve_prompt_template,
)
from response_parser import parse_llm_response  # noqa: E402

# Shared metrics utility
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from metrics import put_llm_invocation_metric  # noqa: E402

# Re-export sub-module symbols that are directly referenced by existing tests
# so that ``from llm_analyzer import lambda_function`` continues to expose
# the same public API that was present before the refactor.
__all__ = [
    "lambda_handler",
    "invoke_bedrock",
    "create_fallback_report",
    "extract_metadata",
    # Sub-module re-exports
    "CircuitBreaker",
    "CircuitState",
    "bedrock_circuit_breaker",
    "construct_prompt",
    "get_default_prompt_template",
    "retrieve_prompt_template",
    "parse_llm_response",
]


def get_bedrock_client():
    """
    Create Bedrock Runtime client with retry configuration.

    Returns:
        boto3 Bedrock Runtime client
    """
    return boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def get_ssm_client():
    """
    Create Systems Manager client.

    Returns:
        boto3 SSM client
    """
    return boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def invoke_bedrock(
    bedrock_client,
    prompt: str,
    model_id: str = "anthropic.claude-v2",
    temperature: float = 0.3,
    max_tokens: int = 1000,
) -> Dict[str, Any]:
    """
    Invoke Bedrock with Claude model.

    Args:
        bedrock_client: boto3 Bedrock Runtime client
        prompt: Complete prompt string
        model_id: Bedrock model identifier
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate

    Returns:
        Dict with 'response' and 'metadata' keys

    Raises:
        Exception: If Bedrock invocation fails
    """
    start_time = time.time()

    try:
        # Construct request body for Claude Messages API (Claude 3+)
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }

        # Invoke model
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body),
            contentType="application/json",
            accept="application/json",
        )

        # Parse response
        response_body = json.loads(response["body"].read())
        completion = response_body.get("content", [{}])[0].get("text", "")

        latency = time.time() - start_time

        # Extract metadata
        metadata = {
            "modelId": model_id,
            "latency": latency,
            "stopReason": response_body.get("stop_reason", "unknown"),
        }

        logger.info(f"Bedrock invocation completed in {latency:.2f}s")

        return {"response": completion, "metadata": metadata}

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        latency = time.time() - start_time

        logger.error(f"Bedrock invocation failed after {latency:.2f}s: {error_code}")

        # Re-raise retryable errors for Step Functions retry
        if error_code in [
            "ThrottlingException",
            "TooManyRequestsException",
            "ServiceUnavailableException",
        ]:
            raise
        else:
            # Non-retryable error
            raise Exception(f"Bedrock invocation failed: {error_code}")


def create_fallback_report(incident_id: str, error_message: str) -> Dict[str, Any]:
    """
    Create fallback analysis report when LLM invocation fails.

    Args:
        incident_id: Incident identifier
        error_message: Error description

    Returns:
        Fallback analysis report dict
    """
    return {
        "incidentId": incident_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "analysis": {
            "rootCauseHypothesis": "Analysis unavailable due to LLM service error",
            "confidence": "none",
            "evidence": [],
            "contributingFactors": [],
            "recommendedActions": [
                "Review incident data manually",
                "Check LLM service status",
                f"Error: {error_message}",
            ],
        },
        "metadata": {
            "modelId": "fallback",
            "modelVersion": "N/A",
            "promptVersion": "N/A",
            "tokenUsage": {"input": 0, "output": 0},
            "latency": 0.0,
            "error": error_message,
        },
    }


def extract_metadata(
    llm_response: Dict[str, Any], prompt_version: str, prompt_length: int
) -> Dict[str, Any]:
    """
    Extract metadata from LLM response.

    Args:
        llm_response: Response from invoke_bedrock
        prompt_version: Prompt template version
        prompt_length: Length of prompt in characters

    Returns:
        Metadata dict
    """
    metadata = llm_response.get("metadata", {})
    response_text = llm_response.get("response", "")

    # Estimate token usage (rough approximation: 1 token ≈ 4 characters)
    input_tokens = prompt_length // 4
    output_tokens = len(response_text) // 4

    return {
        "modelId": metadata.get("modelId", "anthropic.claude-v2"),
        "modelVersion": "2.1",  # Claude v2.1
        "promptVersion": prompt_version,
        "tokenUsage": {"input": input_tokens, "output": output_tokens},
        "latency": metadata.get("latency", 0.0),
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for LLM Analyzer.

    Receives structured context from correlation engine, invokes Bedrock
    to generate root-cause analysis, and returns structured analysis report.

    Args:
        event: Lambda event containing structuredContext
        context: Lambda context

    Returns:
        Analysis report dict
    """
    # Extract correlation ID
    structured_context = event.get("structuredContext", {})
    correlation_id = structured_context.get("incidentId", "unknown")

    try:
        logger.info(
            json.dumps(
                {
                    "message": "LLM Analyzer invoked",
                    "correlationId": correlation_id,
                    "contextSize": len(json.dumps(structured_context)),
                }
            )
        )

        # Initialize clients
        bedrock_client = get_bedrock_client()
        ssm_client = get_ssm_client()

        # Retrieve prompt template (delegated to prompt_builder)
        param_name = os.environ.get("PROMPT_TEMPLATE_PARAM", "/incident-analysis/prompt-template")
        prompt_info = retrieve_prompt_template(ssm_client, parameter_name=param_name)
        template = prompt_info["template"]
        prompt_version = prompt_info["version"]

        # Construct prompt (delegated to prompt_builder)
        prompt = construct_prompt(template, structured_context)
        prompt_length = len(prompt)

        logger.info(
            json.dumps(
                {
                    "message": "Prompt constructed",
                    "correlationId": correlation_id,
                    "promptLength": prompt_length,
                    "promptVersion": prompt_version,
                }
            )
        )

        # Invoke Bedrock with circuit breaker (bedrock_circuit_breaker is Lambda-global)
        model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
        try:
            llm_response = bedrock_circuit_breaker.call(invoke_bedrock, bedrock_client, prompt, model_id)
        except Exception as e:
            if "Circuit breaker is OPEN" in str(e):
                logger.error(
                    json.dumps(
                        {
                            "message": "Circuit breaker is OPEN, returning fallback",
                            "correlationId": correlation_id,
                        }
                    )
                )
                return create_fallback_report(correlation_id, "Circuit breaker open")
            raise

        # Parse LLM response (delegated to response_parser; logs raw response at DEBUG)
        analysis = parse_llm_response(llm_response["response"])

        # Extract metadata
        metadata = extract_metadata(llm_response, prompt_version, prompt_length)

        # Construct analysis report
        analysis_report = {
            "incidentId": correlation_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "analysis": analysis,
            "metadata": metadata,
        }

        logger.info(
            json.dumps(
                {
                    "message": "Analysis completed successfully",
                    "correlationId": correlation_id,
                    "confidence": analysis["confidence"],
                    "latency": metadata["latency"],
                }
            )
        )

        # Emit LLM invocation metrics
        put_llm_invocation_metric(
            latency=metadata["latency"], success=True, model_id=metadata["modelId"]
        )

        return analysis_report

    except ClientError as e:
        # ERROR HANDLING STRATEGY: Distinguish retryable from non-retryable errors
        # Retryable: ThrottlingException, TooManyRequestsException, ServiceUnavailableException
        # Non-retryable: All others (return fallback report)
        # Step Functions will retry retryable errors with exponential backoff
        error_code = e.response["Error"]["Code"]
        error_message = e.response["Error"]["Message"]

        logger.error(
            json.dumps(
                {
                    "message": "AWS service error",
                    "correlationId": correlation_id,
                    "errorCode": error_code,
                    "errorMessage": error_message,
                    "stackTrace": traceback.format_exc(),
                }
            )
        )

        # Re-raise retryable errors for Step Functions retry mechanism
        # Step Functions configured with exponential backoff: 2s, 4s, 8s (max 3 attempts)
        if error_code in [
            "ThrottlingException",
            "TooManyRequestsException",
            "ServiceUnavailableException",
        ]:
            # Emit failure metric before raising
            put_llm_invocation_metric(latency=0.0, success=False)
            raise  # Let Step Functions handle retry

        # Emit failure metric for non-retryable errors
        put_llm_invocation_metric(latency=0.0, success=False)

        # Return fallback for non-retryable errors (graceful degradation)
        return create_fallback_report(correlation_id, f"{error_code}: {error_message}")

    except Exception as e:
        logger.error(
            json.dumps(
                {
                    "message": "Unexpected error",
                    "correlationId": correlation_id,
                    "error": str(e),
                    "errorType": type(e).__name__,
                    "stackTrace": traceback.format_exc(),
                }
            )
        )

        # Emit failure metric
        put_llm_invocation_metric(latency=0.0, success=False)

        # Return fallback report
        return create_fallback_report(correlation_id, str(e))
