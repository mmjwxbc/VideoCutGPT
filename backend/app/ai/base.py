from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai.types import AICompletionRequest, AICompletionResponse, AIStream


class AIAdapter(ABC):
    """Unified adapter interface for text and multimodal model calls."""

    @abstractmethod
    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        raise NotImplementedError

    @abstractmethod
    def stream(self, request: AICompletionRequest) -> AIStream:
        raise NotImplementedError
