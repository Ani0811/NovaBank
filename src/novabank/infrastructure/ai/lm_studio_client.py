"""Local LM Studio HTTP Client with trust boundary enforcement and graceful degradation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from novabank.infrastructure.ai.exceptions import (
    AIConnectionError,
    AIResponseError,
    AISecurityBoundaryError,
    AITimeoutError,
)
from novabank.infrastructure.config import AppConfig


class AIStatus(str, Enum):
    """Runtime health status of local LM Studio AI service."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ChatCompletionResponse:
    """Standardized response from local AI chat completion."""

    content: str
    model: str
    usage_tokens: Optional[dict[str, int]] = None
    is_fallback: bool = False
    latency_seconds: float = 0.0


class LMStudioClient:
    """Client for local LM Studio OpenAI-compatible REST server (http://localhost:1234/v1)."""

    ALLOWED_HOSTS = ("localhost", "127.0.0.1", "::1")

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        config: Optional[AppConfig] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        cfg = config or AppConfig()
        self.base_url = (base_url or cfg.ai_base_url).rstrip("/")
        self.model = model or cfg.ai_model
        self.timeout_seconds = timeout_seconds or cfg.ai_timeout_seconds
        self._transport = transport
        self.status: AIStatus = AIStatus.OFFLINE

        # Enforce local security trust boundary
        self._validate_trust_boundary(self.base_url)

    def _validate_trust_boundary(self, url: str) -> None:
        """Enforce strict local loopback boundary: reject all external hosts."""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host not in self.ALLOWED_HOSTS:
            raise AISecurityBoundaryError(
                f"AI trust boundary violation: Network requests to non-local host '{host}' are prohibited. "
                f"NovaBank AI operations are strictly restricted to local loopback (localhost / 127.0.0.1)."
            )

    def _create_http_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self._transport,
        )

    def check_health(self) -> bool:
        """Ping local LM Studio /models endpoint to verify service availability."""
        try:
            with self._create_http_client() as client:
                resp = client.get("/models")
                if resp.status_code == 200:
                    self.status = AIStatus.ONLINE
                    return True
                self.status = AIStatus.ERROR
                return False
        except (httpx.ConnectError, httpx.ConnectTimeout):
            self.status = AIStatus.OFFLINE
            return False
        except httpx.TimeoutException:
            self.status = AIStatus.OFFLINE
            return False
        except Exception:
            self.status = AIStatus.ERROR
            return False

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 500,
        response_format: Optional[dict[str, Any]] = None,
    ) -> ChatCompletionResponse:
        """Send chat completion prompt to local LM Studio endpoint.

        Args:
            messages: Conversation messages list [{"role": "user", "content": "..."}].
            temperature: Sampling temperature (default 0.2 for deterministic banking answers).
            max_tokens: Maximum tokens in response.
            response_format: Optional format constraint (e.g. {"type": "json_object"}).

        Returns:
            ChatCompletionResponse with extracted content and latency.

        Raises:
            AIConnectionError: If connection is refused or server is offline.
            AITimeoutError: If request times out.
            AIResponseError: If response status != 200 or payload schema is unexpected.
        """
        start_time = time.time()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        try:
            with self._create_http_client() as client:
                resp = client.post("/chat/completions", json=payload)
                latency = time.time() - start_time

                if resp.status_code != 200:
                    self.status = AIStatus.ERROR
                    raise AIResponseError(
                        f"LM Studio API returned HTTP {resp.status_code}: {resp.text}"
                    )

                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    raise AIResponseError("LM Studio returned empty 'choices' list.")

                message = choices[0].get("message", {})
                content = message.get("content", "")
                usage = data.get("usage")

                self.status = AIStatus.ONLINE
                return ChatCompletionResponse(
                    content=content,
                    model=data.get("model", self.model),
                    usage_tokens=usage,
                    is_fallback=False,
                    latency_seconds=latency,
                )

        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            self.status = AIStatus.OFFLINE
            raise AIConnectionError(
                f"Failed to connect to local LM Studio endpoint at {self.base_url}. Ensure LM Studio server is running."
            ) from exc

        except httpx.TimeoutException as exc:
            self.status = AIStatus.OFFLINE
            raise AITimeoutError(
                f"LM Studio request timed out after {self.timeout_seconds}s."
            ) from exc

        except (AIResponseError, AIConnectionError, AITimeoutError):
            raise

        except Exception as exc:
            self.status = AIStatus.ERROR
            raise AIResponseError(f"Unexpected error communicating with LM Studio: {exc}") from exc

    def chat_completion_with_fallback(
        self,
        messages: list[dict[str, str]],
        fallback_text: str = "Local AI assistant is currently offline. Basic banking operations remain fully available.",
        temperature: float = 0.2,
        max_tokens: int = 500,
        response_format: Optional[dict[str, Any]] = None,
    ) -> ChatCompletionResponse:
        """Safe wrapper executing chat completion and returning graceful fallback on connection/timeout errors."""
        try:
            return self.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
        except (AIConnectionError, AITimeoutError, AIResponseError):
            return ChatCompletionResponse(
                content=fallback_text,
                model="fallback",
                usage_tokens=None,
                is_fallback=True,
                latency_seconds=0.0,
            )

