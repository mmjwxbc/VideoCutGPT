from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

import httpx

from app.core.config import settings


class LLMProvider(ABC):
    """Synchronous provider abstraction used by legacy modules."""

    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def analyze_image(self, image_base64: str, prompt: str) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None,
        base_url: str,
        enable_reasoning: bool = False,
    ) -> None:
        if not api_key:
            raise ValueError("provider api key is not configured")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._enable_reasoning = enable_reasoning
        self._client = httpx.Client(timeout=settings.glm_request_timeout_seconds)

    def generate_text(self, prompt: str) -> str:
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        return self._post_chat(payload)

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.2,
        }
        if self._enable_reasoning:
            payload["thinking"] = {"type": "enabled"}
        return self._post_chat(payload)

    def _post_chat(self, payload: Dict[str, Any]) -> str:
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        return self._extract_content(response.json())

    def _extract_content(self, payload: Dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("provider response does not contain choices")

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")).strip())
                elif isinstance(item, str):
                    parts.append(item.strip())
            merged = "\n".join(part for part in parts if part)
            if merged:
                return merged
        return str(content).strip()


class LLMProviderFactory:
    """Factory for the repository's legacy synchronous provider API."""

    @staticmethod
    def get_provider(provider_name: str = "openai") -> LLMProvider:
        normalized = provider_name.lower()
        if normalized == "openai":
            return OpenAICompatibleProvider(
                model=settings.default_llm_model,
                api_key=settings.openai_api_key,
                base_url="https://api.openai.com/v1",
            )
        if normalized == "deepseek":
            return OpenAICompatibleProvider(
                model=settings.deepseek_chat_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        if normalized == "glm":
            return OpenAICompatibleProvider(
                model=settings.glm_vision_model,
                api_key=settings.glm_api_key,
                base_url=settings.glm_base_url,
                enable_reasoning=settings.glm_enable_thinking,
            )
        if normalized in {"multimodal", "vision", "qwen"}:
            return OpenAICompatibleProvider(
                model=settings.multimodal_model or settings.glm_vision_model,
                api_key=settings.multimodal_api_key or settings.glm_api_key,
                base_url=settings.multimodal_base_url or settings.glm_base_url,
                enable_reasoning=bool(settings.multimodal_enable_thinking),
            )
        raise ValueError(f"不支持的LLM提供商: {provider_name}")
