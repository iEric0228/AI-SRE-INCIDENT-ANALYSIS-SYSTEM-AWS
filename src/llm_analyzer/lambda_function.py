"""
LLM Analyzer Lambda Function

This Lambda function invokes Amazon Bedrock to generate root-cause hypotheses
for infrastructure incidents. It constructs a structured prompt from the
correlation engine's output, invokes Claude with retry logic, and parses
the response into a structured analysis report.

The function implements:
- Bedrock client wrapper with retry logic
- Parameter Store client for prompt template retrieval
- Prompt construction from structured context
- LLM response parsing with fallback handling
- Circuit breaker pattern for Bedrock calls
- Metadata extraction (token usage, model version, latency)
"""

import json
import logging
import traceback
import time
import os
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

import boto3
from botocore.exceptions import ClientError

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker pattern for external service calls.

    Prevents cascading failures by opening the circuit after a threshold
    of consecutive failures, then testing recovery after a timeout.
    """

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Seconds to wait before testing recovery
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result

        Raises:
            Exception: If circuit is open or function fails
        """
        # CIRCUIT BREAKER STATE MACHINE:
        # CLOSED -> OPEN: After failure_threshold consecutive failures
        # OPEN -> HALF_OPEN: After timeout_seconds elapsed
        # HALF_OPEN -> CLOSED: On successful call
        # HALF_OPEN -> OPEN: On failed call

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed to test recovery
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) > self.timeout_seconds
            ):
                # Transition to HALF_OPEN to test if service recovered
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                # Circuit still open - fail fast without calling external service
                # This prevents cascading failures and gives service time to recover
                raise Exception("Circuit breaker is OPEN - rejecting request")

        try:
            # Attempt to call the function
            result = func(*args, **kwargs)
            # Success - reset failure count and close circuit
            self.on_success()
            return result
        except Exception as e:
            # Failure - increment counter and potentially open circuit
            self.on_failure()
            # Re-raise exception for caller to handle
            raise

    def on_success(self):
        """Handle successful call."""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker transitioning to CLOSED")
        self.state = CircuitState.CLOSED

    def on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            logger.warning(f"Circuit breaker opening after {self.failure_count} failures")
            self.state = CircuitState.OPEN


# Global circuit breaker for Bedrock calls
bedrock_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout_seconds=60)

# Import metrics utility
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from metrics import put_llm_invocation_metric


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
        Exception: If parameter retrieval fails
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
        # Construct request body for Claude
        request_body = {
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "temperature": temperature,
            "max_tokens_to_sample": max_tokens,
            "stop_sequences": ["\n\nHuman:"],
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
        completion = response_body.get("completion", "")

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


def parse_llm_response(response_text: str) -> Dict[str, Any]:
    """
    Parse LLM response into structured analysis.

    Attempts to extract JSON from the response. If parsing fails,
    creates a structured response from the text.

    Args:
        response_text: Raw LLM response text

    Returns:
        Structured analysis dict
    """
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

                return analysis

        # Level 2: If JSON parsing failed, create structured response from text
        # This handles cases where LLM provides analysis in natural language
        logger.warning("Failed to parse JSON from LLM response, using text extraction")

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
        logger.error(f"JSON parsing failed: {e}")

        return {
            "rootCauseHypothesis": "Failed to parse LLM response",
            "confidence": "none",
            "evidence": [],
            "contributingFactors": [],
            "recommendedActions": ["Review incident data manually", "Check LLM response format"],
        }


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
            {
                "message": "LLM Analyzer invoked",
                "correlationId": correlation_id,
                "contextSize": len(json.dumps(structured_context)),
            }
        )

        # Initialize clients
        bedrock_client = get_bedrock_client()
        ssm_client = get_ssm_client()

        # Retrieve prompt template
        prompt_info = retrieve_prompt_template(ssm_client)
        template = prompt_info["template"]
        prompt_version = prompt_info["version"]

        # Construct prompt
        prompt = construct_prompt(template, structured_context)
        prompt_length = len(prompt)

        logger.info(
            {
                "message": "Prompt constructed",
                "correlationId": correlation_id,
                "promptLength": prompt_length,
                "promptVersion": prompt_version,
            }
        )

        # Invoke Bedrock with circuit breaker
        try:
            llm_response = bedrock_circuit_breaker.call(invoke_bedrock, bedrock_client, prompt)
        except Exception as e:
            if "Circuit breaker is OPEN" in str(e):
                logger.error(
                    {
                        "message": "Circuit breaker is OPEN, returning fallback",
                        "correlationId": correlation_id,
                    }
                )
                return create_fallback_report(correlation_id, "Circuit breaker open")
            raise

        # Parse LLM response
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
            {
                "message": "Analysis completed successfully",
                "correlationId": correlation_id,
                "confidence": analysis["confidence"],
                "latency": metadata["latency"],
            }
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
            {
                "message": "AWS service error",
                "correlationId": correlation_id,
                "errorCode": error_code,
                "errorMessage": error_message,
                "stackTrace": traceback.format_exc(),
            }
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
            {
                "message": "Unexpected error",
                "correlationId": correlation_id,
                "error": str(e),
                "errorType": type(e).__name__,
                "stackTrace": traceback.format_exc(),
            }
        )

        # Emit failure metric
        put_llm_invocation_metric(latency=0.0, success=False)

        # Return fallback report
        return create_fallback_report(correlation_id, str(e))
