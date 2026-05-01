from __future__ import annotations

from app.ai.adapters.openai_compatible import OpenAICompatibleAdapter
from app.ai.base import AIAdapter
from app.core.config import settings


class AIAdapterFactory:
    """Creates adapters for the models used by the caption agent."""

    def __init__(self) -> None:
        self._text_adapter: AIAdapter | None = None
        self._vision_adapter: AIAdapter | None = None

    def get_text_adapter(self) -> AIAdapter:
        if self._text_adapter is None:
            self._text_adapter = OpenAICompatibleAdapter(
                base_url=settings.deepseek_base_url,
                api_key=settings.deepseek_api_key,
                default_timeout_seconds=settings.glm_request_timeout_seconds,
            )
        return self._text_adapter

    def get_vision_adapter(self) -> AIAdapter:
        if self._vision_adapter is None:
            self._vision_adapter = OpenAICompatibleAdapter(
                base_url=settings.multimodal_base_url or settings.glm_base_url,
                api_key=settings.multimodal_api_key or settings.glm_api_key,
                default_timeout_seconds=settings.glm_request_timeout_seconds,
                enable_reasoning=bool(settings.multimodal_enable_thinking),
            )
        return self._vision_adapter
