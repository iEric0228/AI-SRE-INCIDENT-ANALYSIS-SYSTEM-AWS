"""
Unit tests for LLM Analyzer Lambda function.

Tests cover:
- Successful Bedrock invocation
- LLM response parsing
- Fallback report on Bedrock failure
- Prompt template retrieval from Parameter Store
- Circuit breaker behavior

Requirements: 7.1, 7.2, 7.4, 7.5, 7.7
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from botocore.exceptions import ClientError

# Import the lambda function
from llm_analyzer import lambda_function


@pytest.fixture
def sample_structured_context():
    """Sample structured context for testing."""
    return {
        "incidentId": "inc-test-001",
        "timestamp": "2024-01-15T14:30:00Z",
        "resource": {
            "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "type": "lambda",
            "name": "my-function",
        },
        "alarm": {"name": "HighErrorRate", "metric": "Errors", "threshold": 10},
        "metrics": {"summary": {"errorRate": 15.5, "avgDuration": 250}, "timeSeries": []},
        "logs": {
            "errorCount": 45,
            "topErrors": ["Connection timeout", "Memory exceeded"],
            "entries": [],
        },
        "changes": {
            "recentDeployments": 2,
            "lastDeployment": "2024-01-15T14:23:00Z",
            "entries": [],
        },
        "completeness": {"metrics": True, "logs": True, "changes": True},
    }


@pytest.fixture
def sample_llm_response():
    """Sample LLM response for testing."""
    return {
        "rootCauseHypothesis": "Lambda function exhausted memory due to memory leak in recent deployment",
        "confidence": "high",
        "evidence": [
            "Memory utilization increased from 60% to 95% after deployment at 14:23",
            "Error logs show 'MemoryError' starting at 14:25",
            "Deployment occurred 2 minutes before incident",
        ],
        "contributingFactors": [
            "Increased traffic during peak hours",
            "Memory limit not adjusted after code changes",
        ],
        "recommendedActions": [
            "Rollback deployment to previous version",
            "Increase Lambda memory limit to 2048 MB",
            "Investigate memory leak in new code",
        ],
    }


@pytest.fixture
def mock_bedrock_client():
    """Mock Bedrock Runtime client."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_ssm_client():
    """Mock SSM client."""
    client = MagicMock()
    return client


class TestLambdaHandler:
    """Tests for the main lambda_handler function."""

    def test_successful_bedrock_invocation(
        self, sample_structured_context, sample_llm_response, mock_bedrock_client, mock_ssm_client
    ):
        """Test successful end-to-end Bedrock invocation."""
        # Arrange
        event = {"structuredContext": sample_structured_context}

        # Mock SSM response
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": lambda_function.get_default_prompt_template(), "Version": 1}
        }

        # Mock Bedrock response
        bedrock_response = {"body": MagicMock()}
        bedrock_response["body"].read.return_value = json.dumps(
            {"completion": json.dumps(sample_llm_response), "stop_reason": "stop_sequence"}
        ).encode("utf-8")

        mock_bedrock_client.invoke_model.return_value = bedrock_response

        # Reset circuit breaker
        lambda_function.bedrock_circuit_breaker.state = lambda_function.CircuitState.CLOSED
        lambda_function.bedrock_circuit_breaker.failure_count = 0

        with (
            patch(
                "llm_analyzer.lambda_function.get_bedrock_client", return_value=mock_bedrock_client
            ),
            patch("llm_analyzer.lambda_function.get_ssm_client", return_value=mock_ssm_client),
        ):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert
        assert result["incidentId"] == "inc-test-001"
        assert "timestamp" in result
        assert "analysis" in result
        assert "metadata" in result

        # Verify analysis structure
        analysis = result["analysis"]
        assert analysis["rootCauseHypothesis"] == sample_llm_response["rootCauseHypothesis"]
        assert analysis["confidence"] == "high"
        assert len(analysis["evidence"]) == 3
        assert len(analysis["contributingFactors"]) == 2
        assert len(analysis["recommendedActions"]) == 3

        # Verify metadata
        metadata = result["metadata"]
        assert "modelId" in metadata
        assert "modelVersion" in metadata
        assert "promptVersion" in metadata
        assert "tokenUsage" in metadata
        assert "latency" in metadata
        assert metadata["tokenUsage"]["input"] > 0
        assert metadata["tokenUsage"]["output"] > 0

    def test_fallback_on_bedrock_failure(
        self, sample_structured_context, mock_bedrock_client, mock_ssm_client
    ):
        """Test fallback report generation when Bedrock fails."""
        # Arrange
        event = {"structuredContext": sample_structured_context}

        # Mock SSM response
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": lambda_function.get_default_prompt_template(), "Version": 1}
        }

        # Mock Bedrock failure (non-retryable error)
        mock_bedrock_client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid request"}}, "InvokeModel"
        )

        # Reset circuit breaker
        lambda_function.bedrock_circuit_breaker.state = lambda_function.CircuitState.CLOSED
        lambda_function.bedrock_circuit_breaker.failure_count = 0

        with (
            patch(
                "llm_analyzer.lambda_function.get_bedrock_client", return_value=mock_bedrock_client
            ),
            patch("llm_analyzer.lambda_function.get_ssm_client", return_value=mock_ssm_client),
        ):
            # Act
            result = lambda_function.lambda_handler(event, None)

        # Assert - should return fallback report
        assert result["incidentId"] == "inc-test-001"
        assert (
            result["analysis"]["rootCauseHypothesis"]
            == "Analysis unavailable due to LLM service error"
        )
        assert result["analysis"]["confidence"] == "none"
        assert result["metadata"]["modelId"] == "fallback"
        assert "error" in result["metadata"]

    def test_retryable_error_propagation(
        self, sample_structured_context, mock_bedrock_client, mock_ssm_client
    ):
        """Test that retryable errors are propagated for Step Functions retry."""
        # Arrange
        event = {"structuredContext": sample_structured_context}

        # Mock SSM response
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": lambda_function.get_default_prompt_template(), "Version": 1}
        }

        # Mock Bedrock throttling (retryable error)
        mock_bedrock_client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "InvokeModel"
        )

        # Reset circuit breaker
        lambda_function.bedrock_circuit_breaker.state = lambda_function.CircuitState.CLOSED
        lambda_function.bedrock_circuit_breaker.failure_count = 0

        with (
            patch(
                "llm_analyzer.lambda_function.get_bedrock_client", return_value=mock_bedrock_client
            ),
            patch("llm_analyzer.lambda_function.get_ssm_client", return_value=mock_ssm_client),
        ):
            # Act & Assert - should raise the error for Step Functions to retry
            with pytest.raises(ClientError) as exc_info:
                lambda_function.lambda_handler(event, None)

            assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"

    def test_missing_structured_context(self):
        """Test handling when structuredContext is missing from event."""
        # Arrange
        event = {}  # Missing structuredContext

        # Act
        result = lambda_function.lambda_handler(event, None)

        # Assert - should return fallback report
        assert result["incidentId"] == "unknown"
        assert result["analysis"]["confidence"] == "none"
        assert result["metadata"]["modelId"] == "fallback"


class TestPromptTemplateRetrieval:
    """Tests for prompt template retrieval from Parameter Store."""

    def test_successful_template_retrieval(self, mock_ssm_client):
        """Test successful retrieval of prompt template."""
        # Arrange
        template_content = "Test prompt template with {structured_context}"
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": template_content, "Version": 5}
        }

        # Act
        result = lambda_function.retrieve_prompt_template(mock_ssm_client)

        # Assert
        assert result["template"] == template_content
        assert result["version"] == "5"
        mock_ssm_client.get_parameter.assert_called_once_with(
            Name="/incident-analysis/prompt-template", WithDecryption=False
        )

    def test_parameter_not_found_uses_default(self, mock_ssm_client):
        """Test fallback to default template when parameter not found."""
        # Arrange
        mock_ssm_client.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "ParameterNotFound", "Message": "Parameter not found"}},
            "GetParameter",
        )

        # Act
        result = lambda_function.retrieve_prompt_template(mock_ssm_client)

        # Assert
        assert result["version"] == "default"
        assert "{structured_context}" in result["template"]
        assert "Site Reliability Engineer" in result["template"]

    def test_ssm_access_denied_raises(self, mock_ssm_client):
        """Test that access denied errors are raised."""
        # Arrange
        mock_ssm_client.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}}, "GetParameter"
        )

        # Act & Assert
        with pytest.raises(ClientError) as exc_info:
            lambda_function.retrieve_prompt_template(mock_ssm_client)

        assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"

    def test_custom_parameter_name(self, mock_ssm_client):
        """Test retrieval with custom parameter name."""
        # Arrange
        custom_name = "/custom/prompt/path"
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": "Custom template", "Version": 1}
        }

        # Act
        result = lambda_function.retrieve_prompt_template(mock_ssm_client, custom_name)

        # Assert
        assert result["template"] == "Custom template"
        mock_ssm_client.get_parameter.assert_called_once_with(
            Name=custom_name, WithDecryption=False
        )


class TestPromptConstruction:
    """Tests for prompt construction."""

    def test_construct_prompt_with_context(self, sample_structured_context):
        """Test prompt construction injects context correctly."""
        # Arrange
        template = "Analyze this incident:\n{structured_context}\nProvide analysis:"

        # Act
        result = lambda_function.construct_prompt(template, sample_structured_context)

        # Assert
        assert "Analyze this incident:" in result
        assert "Provide analysis:" in result
        assert "inc-test-001" in result
        assert "my-function" in result
        assert "HighErrorRate" in result

    def test_construct_prompt_preserves_template_structure(self):
        """Test that prompt construction preserves template structure."""
        # Arrange
        template = lambda_function.get_default_prompt_template()
        context = {"incidentId": "test-123", "resource": {"name": "test-resource"}}

        # Act
        result = lambda_function.construct_prompt(template, context)

        # Assert
        assert "Site Reliability Engineer" in result
        assert "OUTPUT FORMAT" in result
        assert "CONSTRAINTS" in result
        assert "test-123" in result


class TestBedrockInvocation:
    """Tests for Bedrock invocation."""

    def test_successful_invocation(self, mock_bedrock_client, sample_llm_response):
        """Test successful Bedrock model invocation."""
        # Arrange
        prompt = "Test prompt"
        bedrock_response = {"body": MagicMock()}
        bedrock_response["body"].read.return_value = json.dumps(
            {"completion": json.dumps(sample_llm_response), "stop_reason": "stop_sequence"}
        ).encode("utf-8")

        mock_bedrock_client.invoke_model.return_value = bedrock_response

        # Act
        result = lambda_function.invoke_bedrock(mock_bedrock_client, prompt)

        # Assert
        assert "response" in result
        assert "metadata" in result
        assert result["metadata"]["latency"] >= 0
        assert result["metadata"]["stopReason"] == "stop_sequence"

        # Verify invoke_model was called with correct parameters
        call_args = mock_bedrock_client.invoke_model.call_args
        assert call_args[1]["modelId"] == "anthropic.claude-v2"
        assert call_args[1]["contentType"] == "application/json"

        # Verify request body structure
        request_body = json.loads(call_args[1]["body"])
        assert "prompt" in request_body
        assert request_body["temperature"] == 0.3
        assert request_body["max_tokens_to_sample"] == 1000

    def test_throttling_exception_raised(self, mock_bedrock_client):
        """Test that throttling exceptions are raised for retry."""
        # Arrange
        prompt = "Test prompt"
        mock_bedrock_client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "InvokeModel"
        )

        # Act & Assert
        with pytest.raises(ClientError) as exc_info:
            lambda_function.invoke_bedrock(mock_bedrock_client, prompt)

        assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"

    def test_service_unavailable_raised(self, mock_bedrock_client):
        """Test that service unavailable exceptions are raised for retry."""
        # Arrange
        prompt = "Test prompt"
        mock_bedrock_client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "Service unavailable"}},
            "InvokeModel",
        )

        # Act & Assert
        with pytest.raises(ClientError) as exc_info:
            lambda_function.invoke_bedrock(mock_bedrock_client, prompt)

        assert exc_info.value.response["Error"]["Code"] == "ServiceUnavailableException"

    def test_non_retryable_error_wrapped(self, mock_bedrock_client):
        """Test that non-retryable errors are wrapped in Exception."""
        # Arrange
        prompt = "Test prompt"
        mock_bedrock_client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid request"}}, "InvokeModel"
        )

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            lambda_function.invoke_bedrock(mock_bedrock_client, prompt)

        assert "Bedrock invocation failed" in str(exc_info.value)

    def test_custom_model_parameters(self, mock_bedrock_client):
        """Test invocation with custom model parameters."""
        # Arrange
        prompt = "Test prompt"
        bedrock_response = {"body": MagicMock()}
        bedrock_response["body"].read.return_value = json.dumps(
            {"completion": "Test response", "stop_reason": "max_tokens"}
        ).encode("utf-8")

        mock_bedrock_client.invoke_model.return_value = bedrock_response

        # Act
        result = lambda_function.invoke_bedrock(
            mock_bedrock_client,
            prompt,
            model_id="anthropic.claude-v3",
            temperature=0.5,
            max_tokens=500,
        )

        # Assert
        call_args = mock_bedrock_client.invoke_model.call_args
        assert call_args[1]["modelId"] == "anthropic.claude-v3"

        request_body = json.loads(call_args[1]["body"])
        assert request_body["temperature"] == 0.5
        assert request_body["max_tokens_to_sample"] == 500


class TestLLMResponseParsing:
    """Tests for LLM response parsing."""

    def test_parse_valid_json_response(self, sample_llm_response):
        """Test parsing valid JSON response."""
        # Arrange
        response_text = json.dumps(sample_llm_response)

        # Act
        result = lambda_function.parse_llm_response(response_text)

        # Assert
        assert result["rootCauseHypothesis"] == sample_llm_response["rootCauseHypothesis"]
        assert result["confidence"] == "high"
        assert len(result["evidence"]) == 3
        assert len(result["contributingFactors"]) == 2
        assert len(result["recommendedActions"]) == 3

    def test_parse_json_with_surrounding_text(self, sample_llm_response):
        """Test parsing JSON embedded in surrounding text."""
        # Arrange
        response_text = f"Here is my analysis:\n{json.dumps(sample_llm_response)}\nEnd of analysis."

        # Act
        result = lambda_function.parse_llm_response(response_text)

        # Assert
        assert result["rootCauseHypothesis"] == sample_llm_response["rootCauseHypothesis"]
        assert result["confidence"] == "high"

    def test_parse_malformed_json_returns_fallback(self):
        """Test that malformed JSON returns fallback structure."""
        # Arrange
        response_text = "This is not valid JSON {incomplete"

        # Act
        result = lambda_function.parse_llm_response(response_text)

        # Assert
        assert result["confidence"] == "low"
        assert "This is not valid JSON" in result["rootCauseHypothesis"]
        assert result["evidence"] == []
        assert "Review incident data manually" in result["recommendedActions"]

    def test_parse_missing_required_fields(self):
        """Test parsing JSON with missing required fields."""
        # Arrange
        incomplete_response = {
            "rootCauseHypothesis": "Test hypothesis",
            "confidence": "high",
            # Missing evidence, contributingFactors, recommendedActions
        }
        response_text = json.dumps(incomplete_response)

        # Act
        result = lambda_function.parse_llm_response(response_text)

        # Assert - should return fallback due to missing fields
        assert result["confidence"] == "low"
        assert "Test hypothesis" in result["rootCauseHypothesis"]

    def test_parse_empty_response(self):
        """Test parsing empty response."""
        # Arrange
        response_text = ""

        # Act
        result = lambda_function.parse_llm_response(response_text)

        # Assert
        assert result["confidence"] == "low"
        assert result["rootCauseHypothesis"] == "Unable to parse analysis"

    def test_parse_normalizes_confidence_to_lowercase(self):
        """Test that confidence values are normalized to lowercase."""
        # Arrange
        response = {
            "rootCauseHypothesis": "Test",
            "confidence": "HIGH",
            "evidence": ["test"],
            "contributingFactors": [],
            "recommendedActions": [],
        }
        response_text = json.dumps(response)

        # Act
        result = lambda_function.parse_llm_response(response_text)

        # Assert
        assert result["confidence"] == "high"

    def test_parse_filters_null_list_items(self):
        """Test that null items are filtered from lists."""
        # Arrange
        response = {
            "rootCauseHypothesis": "Test",
            "confidence": "medium",
            "evidence": ["Valid evidence", None, "Another evidence"],
            "contributingFactors": [None, "Factor 1"],
            "recommendedActions": ["Action 1", None, None, "Action 2"],
        }
        response_text = json.dumps(response)

        # Act
        result = lambda_function.parse_llm_response(response_text)

        # Assert
        assert len(result["evidence"]) == 2
        assert None not in result["evidence"]
        assert len(result["contributingFactors"]) == 1
        assert len(result["recommendedActions"]) == 2


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    def test_circuit_breaker_closed_allows_calls(self):
        """Test that closed circuit allows function calls."""
        # Arrange
        circuit = lambda_function.CircuitBreaker(failure_threshold=3, timeout_seconds=5)
        mock_func = Mock(return_value="success")

        # Act
        result = circuit.call(mock_func, "arg1", kwarg1="value1")

        # Assert
        assert result == "success"
        assert circuit.state == lambda_function.CircuitState.CLOSED
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    def test_circuit_breaker_opens_after_threshold(self):
        """Test that circuit opens after failure threshold."""
        # Arrange
        circuit = lambda_function.CircuitBreaker(failure_threshold=3, timeout_seconds=5)
        mock_func = Mock(side_effect=Exception("Service error"))

        # Act - trigger failures
        for i in range(3):
            with pytest.raises(Exception):
                circuit.call(mock_func)

        # Assert
        assert circuit.state == lambda_function.CircuitState.OPEN
        assert circuit.failure_count == 3

    def test_circuit_breaker_open_rejects_calls(self):
        """Test that open circuit rejects calls."""
        # Arrange
        circuit = lambda_function.CircuitBreaker(failure_threshold=2, timeout_seconds=5)
        mock_func = Mock(side_effect=Exception("Service error"))

        # Trigger failures to open circuit
        for i in range(2):
            with pytest.raises(Exception):
                circuit.call(mock_func)

        # Act & Assert - next call should be rejected
        with pytest.raises(Exception) as exc_info:
            circuit.call(mock_func)

        assert "Circuit breaker is OPEN" in str(exc_info.value)

    def test_circuit_breaker_transitions_to_half_open(self):
        """Test that circuit transitions to half-open after timeout."""
        # Arrange
        circuit = lambda_function.CircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        mock_func = Mock(side_effect=Exception("Service error"))

        # Open the circuit
        for i in range(2):
            with pytest.raises(Exception):
                circuit.call(mock_func)

        assert circuit.state == lambda_function.CircuitState.OPEN

        # Wait for timeout
        import time

        time.sleep(0.2)

        # Act - next call should transition to half-open
        mock_func.side_effect = None
        mock_func.return_value = "success"
        result = circuit.call(mock_func)

        # Assert
        assert result == "success"
        assert circuit.state == lambda_function.CircuitState.CLOSED

    def test_circuit_breaker_resets_on_success(self):
        """Test that circuit resets failure count on success."""
        # Arrange
        circuit = lambda_function.CircuitBreaker(failure_threshold=3, timeout_seconds=5)
        mock_func = Mock()

        # Trigger some failures
        mock_func.side_effect = Exception("Error")
        with pytest.raises(Exception):
            circuit.call(mock_func)

        assert circuit.failure_count == 1

        # Successful call
        mock_func.side_effect = None
        mock_func.return_value = "success"
        circuit.call(mock_func)

        # Assert
        assert circuit.failure_count == 0
        assert circuit.state == lambda_function.CircuitState.CLOSED

    def test_global_circuit_breaker_exists(self):
        """Test that global circuit breaker is initialized."""
        # Assert
        assert hasattr(lambda_function, "bedrock_circuit_breaker")
        assert isinstance(lambda_function.bedrock_circuit_breaker, lambda_function.CircuitBreaker)
        assert lambda_function.bedrock_circuit_breaker.failure_threshold == 5
        assert lambda_function.bedrock_circuit_breaker.timeout_seconds == 60


class TestFallbackReport:
    """Tests for fallback report generation."""

    def test_create_fallback_report_structure(self):
        """Test fallback report has correct structure."""
        # Arrange
        incident_id = "inc-test-123"
        error_message = "Bedrock service unavailable"

        # Act
        result = lambda_function.create_fallback_report(incident_id, error_message)

        # Assert
        assert result["incidentId"] == incident_id
        assert "timestamp" in result
        assert "analysis" in result
        assert "metadata" in result

        # Verify analysis
        assert (
            result["analysis"]["rootCauseHypothesis"]
            == "Analysis unavailable due to LLM service error"
        )
        assert result["analysis"]["confidence"] == "none"
        assert result["analysis"]["evidence"] == []
        assert len(result["analysis"]["recommendedActions"]) > 0
        assert error_message in result["analysis"]["recommendedActions"][2]

        # Verify metadata
        assert result["metadata"]["modelId"] == "fallback"
        assert result["metadata"]["error"] == error_message


class TestMetadataExtraction:
    """Tests for metadata extraction."""

    def test_extract_metadata_from_response(self):
        """Test metadata extraction from LLM response."""
        # Arrange
        llm_response = {
            "response": "Test response with some content",
            "metadata": {
                "modelId": "anthropic.claude-v2",
                "latency": 2.5,
                "stopReason": "stop_sequence",
            },
        }
        prompt_version = "v1.2"
        prompt_length = 1000

        # Act
        result = lambda_function.extract_metadata(llm_response, prompt_version, prompt_length)

        # Assert
        assert result["modelId"] == "anthropic.claude-v2"
        assert result["modelVersion"] == "2.1"
        assert result["promptVersion"] == "v1.2"
        assert result["latency"] == 2.5
        assert "tokenUsage" in result
        assert result["tokenUsage"]["input"] > 0
        assert result["tokenUsage"]["output"] > 0

    def test_extract_metadata_estimates_tokens(self):
        """Test that metadata extraction estimates token usage."""
        # Arrange
        llm_response = {
            "response": "A" * 400,  # 400 characters ≈ 100 tokens
            "metadata": {"modelId": "anthropic.claude-v2", "latency": 1.0},
        }
        prompt_version = "v1.0"
        prompt_length = 800  # 800 characters ≈ 200 tokens

        # Act
        result = lambda_function.extract_metadata(llm_response, prompt_version, prompt_length)

        # Assert
        assert result["tokenUsage"]["input"] == 200  # 800 / 4
        assert result["tokenUsage"]["output"] == 100  # 400 / 4

    def test_extract_metadata_handles_missing_fields(self):
        """Test metadata extraction with missing fields."""
        # Arrange
        llm_response = {"response": "Test", "metadata": {}}
        prompt_version = "v1.0"
        prompt_length = 100

        # Act
        result = lambda_function.extract_metadata(llm_response, prompt_version, prompt_length)

        # Assert
        assert result["modelId"] == "anthropic.claude-v2"  # Default
        assert result["latency"] == 0.0  # Default
        assert result["promptVersion"] == "v1.0"


class TestDefaultPromptTemplate:
    """Tests for default prompt template."""

    def test_default_template_has_required_sections(self):
        """Test that default template contains required sections."""
        # Act
        template = lambda_function.get_default_prompt_template()

        # Assert
        assert "Site Reliability Engineer" in template
        assert "{structured_context}" in template
        assert "OUTPUT FORMAT" in template
        assert "CONSTRAINTS" in template
        assert "rootCauseHypothesis" in template
        assert "confidence" in template
        assert "evidence" in template
        assert "contributingFactors" in template
        assert "recommendedActions" in template


class TestResponseParserObservability:
    """Tests for Fix 3: raw LLM response logged at DEBUG + LLMParseLevel metric."""

    def test_parse_level_1_metric_emitted_for_valid_json(self, sample_llm_response):
        """parse_llm_response should emit LLMParseLevel=1 when JSON parses cleanly."""
        from llm_analyzer.response_parser import parse_llm_response as _parse

        with patch("llm_analyzer.response_parser.put_metric") as mock_put:
            _parse(json.dumps(sample_llm_response))

        level_calls = [
            c for c in mock_put.call_args_list
            if (c.args and c.args[0] == "LLMParseLevel") or c.kwargs.get("metric_name") == "LLMParseLevel"
        ]
        assert len(level_calls) == 1
        # value should be 1.0 (level 1)
        call = level_calls[0]
        value_arg = call.args[1] if len(call.args) > 1 else call.kwargs.get("value")
        assert value_arg == 1.0

    def test_parse_level_2_metric_emitted_for_non_json(self):
        """parse_llm_response should emit LLMParseLevel=2 when response is plain text."""
        from llm_analyzer.response_parser import parse_llm_response as _parse

        with patch("llm_analyzer.response_parser.put_metric") as mock_put:
            _parse("This is a plain text answer without any JSON")

        level_calls = [
            c for c in mock_put.call_args_list
            if (c.args and c.args[0] == "LLMParseLevel") or c.kwargs.get("metric_name") == "LLMParseLevel"
        ]
        assert len(level_calls) == 1
        call = level_calls[0]
        value_arg = call.args[1] if len(call.args) > 1 else call.kwargs.get("value")
        assert value_arg == 2.0

    def test_parse_level_3_metric_emitted_for_bad_json(self):
        """parse_llm_response should emit LLMParseLevel=3 when validation raises an exception.

        Level 3 is triggered when the JSON contains all required fields but a field
        that must be a string is not (e.g. rootCauseHypothesis=123), causing the
        explicit ValueError inside the validation block to be caught and re-routed
        to the except handler, which emits level 3.
        """
        from llm_analyzer.response_parser import parse_llm_response as _parse

        # Provide all required keys but with rootCauseHypothesis as an integer.
        # The parser finds valid JSON, enters the field-validation block, and
        # raises ValueError("rootCauseHypothesis must be a string"), which is
        # caught by the except handler → level 3.
        bad_response = json.dumps(
            {
                "rootCauseHypothesis": 123,  # wrong type → ValueError inside try block
                "confidence": "high",
                "evidence": [],
                "contributingFactors": [],
                "recommendedActions": [],
            }
        )

        with patch("llm_analyzer.response_parser.put_metric") as mock_put:
            _parse(bad_response)

        level_calls = [
            c for c in mock_put.call_args_list
            if (c.args and c.args[0] == "LLMParseLevel") or c.kwargs.get("metric_name") == "LLMParseLevel"
        ]
        assert len(level_calls) == 1
        call = level_calls[0]
        value_arg = call.args[1] if len(call.args) > 1 else call.kwargs.get("value")
        assert value_arg == 3.0

    def test_raw_response_logged_at_debug_before_parsing(self, sample_llm_response):
        """parse_llm_response should log the raw response at DEBUG before any parsing."""
        import logging
        from llm_analyzer.response_parser import parse_llm_response as _parse

        debug_messages = []

        class _DebugCapture(logging.Handler):
            def emit(self, record):
                if record.levelno == logging.DEBUG:
                    debug_messages.append(record.getMessage())

        handler = _DebugCapture()
        parser_logger = logging.getLogger("llm_analyzer.response_parser")
        original_level = parser_logger.level
        parser_logger.setLevel(logging.DEBUG)
        parser_logger.addHandler(handler)

        try:
            with patch("llm_analyzer.response_parser.put_metric"):
                raw = json.dumps(sample_llm_response)
                _parse(raw)
        finally:
            parser_logger.removeHandler(handler)
            parser_logger.setLevel(original_level)

        assert any("rawResponse" in m or "Raw LLM" in m for m in debug_messages), (
            "Expected a DEBUG log containing raw response; got: " + str(debug_messages)
        )


class TestCircuitBreakerSubModule:
    """Tests for Fix 4 & 5: circuit_breaker sub-module + cold-start log."""

    def test_circuit_breaker_module_exposes_global_instance(self):
        """bedrock_circuit_breaker should be importable from circuit_breaker sub-module."""
        from llm_analyzer.circuit_breaker import bedrock_circuit_breaker, CircuitBreaker

        assert isinstance(bedrock_circuit_breaker, CircuitBreaker)

    def test_circuit_breaker_re_exported_from_lambda_function(self):
        """lambda_function should re-export CircuitBreaker and bedrock_circuit_breaker."""
        assert hasattr(lambda_function, "CircuitBreaker")
        assert hasattr(lambda_function, "CircuitState")
        assert hasattr(lambda_function, "bedrock_circuit_breaker")
        assert isinstance(
            lambda_function.bedrock_circuit_breaker, lambda_function.CircuitBreaker
        )

    def test_prompt_builder_re_exported_from_lambda_function(self):
        """lambda_function should re-export prompt_builder helpers."""
        assert hasattr(lambda_function, "retrieve_prompt_template")
        assert hasattr(lambda_function, "get_default_prompt_template")
        assert hasattr(lambda_function, "construct_prompt")

    def test_response_parser_re_exported_from_lambda_function(self):
        """lambda_function should re-export parse_llm_response."""
        assert hasattr(lambda_function, "parse_llm_response")
        # Ensure it is callable and returns a dict
        with patch("llm_analyzer.response_parser.put_metric"):
            result = lambda_function.parse_llm_response("")
        assert isinstance(result, dict)
