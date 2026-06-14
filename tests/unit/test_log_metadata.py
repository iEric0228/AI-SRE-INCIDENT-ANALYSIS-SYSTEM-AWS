"""Unit tests for shared.log_metadata."""

import json
from unittest.mock import MagicMock

from shared.log_metadata import add_function_metadata, enhance_log_message


class TestAddFunctionMetadata:
    """Tests for add_function_metadata covering context and env branches."""

    def test_uses_context_when_present(self):
        ctx = MagicMock()
        ctx.function_name = "my-func"
        ctx.function_version = "7"

        out = add_function_metadata({"existing": "value"}, ctx)

        assert out["functionName"] == "my-func"
        assert out["functionVersion"] == "7"
        assert out["existing"] == "value"

    def test_falls_back_to_environment(self, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "env-func")
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_VERSION", "3")

        out = add_function_metadata({})

        assert out["functionName"] == "env-func"
        assert out["functionVersion"] == "3"

    def test_defaults_when_no_context_and_no_env(self, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_VERSION", raising=False)

        out = add_function_metadata({})

        assert out["functionName"] == "unknown"
        assert out["functionVersion"] == "$LATEST"


class TestEnhanceLogMessage:
    """Tests for enhance_log_message covering JSON and non-JSON inputs."""

    def test_json_message_gets_metadata(self, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "f")
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_VERSION", "1")

        out = enhance_log_message(json.dumps({"level": "INFO", "msg": "hello"}))
        parsed = json.loads(out)

        assert parsed["level"] == "INFO"
        assert parsed["msg"] == "hello"
        assert parsed["functionName"] == "f"
        assert parsed["functionVersion"] == "1"

    def test_non_json_message_is_wrapped(self, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_VERSION", raising=False)

        out = enhance_log_message("plain text log")
        parsed = json.loads(out)

        assert parsed["message"] == "plain text log"
        assert parsed["functionName"] == "unknown"
        assert parsed["functionVersion"] == "$LATEST"

    def test_non_json_message_uses_context(self):
        ctx = MagicMock()
        ctx.function_name = "ctx-func"
        ctx.function_version = "9"

        out = enhance_log_message("plain text", ctx)
        parsed = json.loads(out)

        assert parsed["message"] == "plain text"
        assert parsed["functionName"] == "ctx-func"
        assert parsed["functionVersion"] == "9"
