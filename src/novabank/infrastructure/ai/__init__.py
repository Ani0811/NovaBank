"""Local AI Subsystem for NovaBank."""

from novabank.infrastructure.ai.exceptions import (
    AIConnectionError,
    AIError,
    AIPrivacyViolationError,
    AIResponseError,
    AISecurityBoundaryError,
    AITimeoutError,
)
from novabank.infrastructure.ai.lm_studio_client import (
    AIStatus,
    ChatCompletionResponse,
    LMStudioClient,
)

__all__ = [
    "AIConnectionError",
    "AIError",
    "AIPrivacyViolationError",
    "AIResponseError",
    "AISecurityBoundaryError",
    "AIStatus",
    "AITimeoutError",
    "ChatCompletionResponse",
    "LMStudioClient",
]

