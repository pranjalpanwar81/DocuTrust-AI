from unittest.mock import patch

import httpx

from app.models import Evidence
from app.synthesis import synthesize


def _evidence():
    return [
        Evidence(
            chunk_id="doc-1:p1:c0",
            document_id="doc-1",
            document_name="leave-policy.pdf",
            page=2,
            text="Leave requests must be approved by the reporting manager within five working days.",
            score=0.08,
        )
    ]


def test_synthesize_without_api_key():
    with patch("app.synthesis.settings") as settings:
        settings.openai_api_key = None
        result = synthesize("Who approves leave?", _evidence())
    assert result.text is None
    assert result.source == "fallback"
    assert result.error == "api_key_missing"


def test_synthesize_success():
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(200, request=request, json={"choices": [{"message": {"content": "The reporting manager approves leave [S1]."}}]})
    with patch("app.synthesis.settings") as settings, patch("httpx.Client") as client_cls:
        settings.openai_api_key = "test-key"
        settings.openai_base_url = "https://api.example.com/v1"
        settings.openai_model = "test-model"
        client_cls.return_value.__enter__.return_value.post.return_value = response
        result = synthesize("Who approves leave?", _evidence())
    assert result.text == "The reporting manager approves leave [S1]."
    assert result.source == "llm"
    assert result.error is None


def test_synthesize_timeout_falls_back():
    with patch("app.synthesis.settings") as settings, patch("httpx.Client") as client_cls:
        settings.openai_api_key = "test-key"
        settings.openai_base_url = "https://api.example.com/v1"
        settings.openai_model = "test-model"
        client_cls.return_value.__enter__.return_value.post.side_effect = httpx.TimeoutException("timed out")
        result = synthesize("Who approves leave?", _evidence())
    assert result.text is None
    assert result.source == "fallback"
    assert result.error == "timeout"


def test_synthesize_http_error_falls_back():
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(401, request=request, text='{"error":"invalid_api_key"}')
    with patch("app.synthesis.settings") as settings, patch("httpx.Client") as client_cls:
        settings.openai_api_key = "bad-key"
        settings.openai_base_url = "https://api.example.com/v1"
        settings.openai_model = "test-model"
        client_cls.return_value.__enter__.return_value.post.return_value = response
        result = synthesize("Who approves leave?", _evidence())
    assert result.text is None
    assert result.source == "fallback"
    assert result.error == "http_401"


def test_synthesize_llm_abstains():
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(200, request=request, json={"choices": [{"message": {"content": "INSUFFICIENT_EVIDENCE"}}]})
    with patch("app.synthesis.settings") as settings, patch("httpx.Client") as client_cls:
        settings.openai_api_key = "test-key"
        settings.openai_base_url = "https://api.example.com/v1"
        settings.openai_model = "test-model"
        client_cls.return_value.__enter__.return_value.post.return_value = response
        result = synthesize("What is the encryption standard?", _evidence())
    assert result.text is None
    assert result.source == "fallback"
    assert result.error == "llm_abstained"
