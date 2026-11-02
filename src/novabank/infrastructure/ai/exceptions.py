"""Exception hierarchy for NovaBank AI subsystem and trust boundaries."""

from __future__ import annotations


class AIError(Exception):
    """Base exception for all AI subsystem errors."""


class AISecurityBoundaryError(AIError):
    """Raised when an operation attempts to breach the local trust boundary (e.g. non-localhost network call)."""


class AIConnectionError(AIError):
    """Raised when connecting to the local LM Studio endpoint fails or is refused."""


class AITimeoutError(AIError):
    """Raised when an AI generation request exceeds the configured timeout."""


class AIResponseError(AIError):
    """Raised when the AI model returns invalid or unparseable output."""


class AIPrivacyViolationError(AIError):
    """Raised when unmasked Personally Identifiable Information (PII) is detected in an AI prompt payload."""

