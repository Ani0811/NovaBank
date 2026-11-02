"""Tests for local LM Studio client, security trust boundary, and offline fallback."""

from __future__ import annotations

import httpx
import pytest

from novabank.infrastructure.ai.exceptions import (
    AIConnectionError,
    AIResponseError,
    AISecurityBoundaryError,
    AITimeoutError,
)
from novabank.infrastructure.ai.lm_studio_client import (
    AIStatus,
    ChatCompletionResponse,
    LMStudioClient,
)


def test_trust_boundary_enforcement() -> None:
    """Verify strictly local loopback is allowed; all external hosts are blocked."""
    # Valid local hosts
    LMStudioClient(base_url="http://localhost:1234/v1")
    LMStudioClient(base_url="http://127.0.0.1:1234/v1")
    LMStudioClient(base_url="http://localhost:8080/v1")

    # External hosts must raise AISecurityBoundaryError
    with pytest.raises(AISecurityBoundaryError, match="trust boundary violation"):
        LMStudioClient(base_url="https://api.openai.com/v1")

    with pytest.raises(AISecurityBoundaryError, match="trust boundary violation"):
        LMStudioClient(base_url="http://remote-server.com:1234/v1")

    with pytest.raises(AISecurityBoundaryError, match="trust boundary violation"):
        LMStudioClient(base_url="http://192.168.1.50:1234/v1")


def test_check_health_success() -> None:
    """Verify health check returns True and status is ONLINE when endpoint returns 200."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "llama-3.2-3b-instruct"}]})

    client = LMStudioClient(
        base_url="http://localhost:1234/v1",
        transport=httpx.MockTransport(handler),
    )
    assert client.check_health() is True
    assert client.status == AIStatus.ONLINE


def test_check_health_connection_refused() -> None:
    """Verify health check returns False and status is OFFLINE when server is not running."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = LMStudioClient(
        base_url="http://localhost:1234/v1",
        transport=httpx.MockTransport(handler),
    )
    assert client.check_health() is False
    assert client.status == AIStatus.OFFLINE


def test_chat_completion_success() -> None:
    """Verify successful chat completion returns content and latency metadata."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "llama-3.2-3b-instruct",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Your statement shows steady monthly savings growth.",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 12, "total_tokens": 62},
            },
        )

    client = LMStudioClient(
        base_url="http://localhost:1234/v1",
        transport=httpx.MockTransport(handler),
    )

    resp: ChatCompletionResponse = client.chat_completion(
        messages=[{"role": "user", "content": "Analyze my account."}],
    )

    assert resp.content == "Your statement shows steady monthly savings growth."
    assert resp.model == "llama-3.2-3b-instruct"
    assert resp.is_fallback is False
    assert resp.usage_tokens["total_tokens"] == 62
    assert resp.latency_seconds >= 0.0
    assert client.status == AIStatus.ONLINE


def test_chat_completion_connection_refused_raises() -> None:
    """Verify connection failure raises AIConnectionError and marks status OFFLINE."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = LMStudioClient(
        base_url="http://localhost:1234/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AIConnectionError, match="Failed to connect to local LM Studio"):
        client.chat_completion(messages=[{"role": "user", "content": "Test"}])

    assert client.status == AIStatus.OFFLINE


def test_chat_completion_timeout_raises() -> None:
    """Verify request timeout raises AITimeoutError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out")

    client = LMStudioClient(
        base_url="http://localhost:1234/v1",
        timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AITimeoutError, match="timed out"):
        client.chat_completion(messages=[{"role": "user", "content": "Test"}])

    assert client.status == AIStatus.OFFLINE


def test_chat_completion_http_error_raises_response_error() -> None:
    """Verify HTTP 500 raises AIResponseError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error: Out of VRAM")

    client = LMStudioClient(
        base_url="http://localhost:1234/v1",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AIResponseError, match="HTTP 500"):
        client.chat_completion(messages=[{"role": "user", "content": "Test"}])

    assert client.status == AIStatus.ERROR


def test_chat_completion_with_fallback_graceful_recovery() -> None:
    """Verify chat_completion_with_fallback returns graceful response on connection failure without raising."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Server down")

    client = LMStudioClient(
        base_url="http://localhost:1234/v1",
        transport=httpx.MockTransport(handler),
    )

    resp = client.chat_completion_with_fallback(
        messages=[{"role": "user", "content": "Hello"}],
        fallback_text="AI service currently offline.",
    )

    assert resp.content == "AI service currently offline."
    assert resp.is_fallback is True
    assert resp.model == "fallback"
    assert client.status == AIStatus.OFFLINE
