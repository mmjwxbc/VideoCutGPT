from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

import httpx
from openai import AsyncOpenAI

from app.ai.base import AIAdapter
from app.ai.errors import AIAdapterConfigError, AIAdapterResponseError
from app.ai.types import AICompletionRequest, AICompletionResponse, AIImageInput, AIStream, AIUsage


logger = logging.getLogger(__name__)


class OpenAICompatibleAdapter(AIAdapter):
    """Async adapter for providers implementing the OpenAI chat completions protocol."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        default_timeout_seconds: int,
        enable_reasoning: bool = False,
    ) -> None:
        if not api_key:
            raise AIAdapterConfigError("provider api key is not configured")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_timeout_seconds = default_timeout_seconds
        self._enable_reasoning = enable_reasoning
        self._client: httpx.AsyncClient | None = None
        self._sdk_client: AsyncOpenAI | None = None
        self._sdk_timeout_seconds: int | None = None

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        payload = self._build_payload(request)
        trace_label = str(request.metadata.get("trace_label") or request.model)
        image_count = sum(len(message.images) for message in request.messages)
        started_at = time.perf_counter()
        logger.info(
            "AI request started: label=%s model=%s images=%s require_json=%s timeout=%ss",
            trace_label,
            request.model,
            image_count,
            request.require_json,
            request.timeout_seconds or self._default_timeout_seconds,
        )
        try:
            response = await self._get_sdk_client(timeout_seconds=request.timeout_seconds).chat.completions.create(
                **payload
            )
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.exception(
                "AI request failed: label=%s model=%s duration_ms=%s",
                trace_label,
                request.model,
                duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "AI request finished: label=%s model=%s duration_ms=%s",
            trace_label,
            request.model,
            duration_ms,
        )
        payload = response.model_dump()
        content = self._extract_content(payload)
        usage_payload = payload.get("usage", {})
        usage = AIUsage(
            prompt_tokens=usage_payload.get("prompt_tokens"),
            completion_tokens=usage_payload.get("completion_tokens"),
            total_tokens=usage_payload.get("total_tokens"),
        )
        return AICompletionResponse(content=content, usage=usage, raw_response=payload)

    async def stream(self, request: AICompletionRequest) -> AIStream:
        payload = self._build_payload(request)
        trace_label = str(request.metadata.get("trace_label") or request.model)
        image_count = sum(len(message.images) for message in request.messages)
        started_at = time.perf_counter()
        logger.info(
            "AI stream started: label=%s model=%s images=%s require_json=%s timeout=%ss",
            trace_label,
            request.model,
            image_count,
            request.require_json,
            request.timeout_seconds or self._default_timeout_seconds,
        )

        try:
            stream = await self._get_sdk_client(timeout_seconds=request.timeout_seconds).chat.completions.create(
                **payload,
                stream=True,
            )
            async for chunk in stream:
                chunk_payload = chunk.model_dump()
                delta = self._extract_delta_content(chunk_payload)
                if delta:
                    yield delta
                if self._is_stream_finished(chunk_payload):
                    break
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.exception(
                "AI stream failed: label=%s model=%s duration_ms=%s",
                trace_label,
                request.model,
                duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "AI stream finished: label=%s model=%s duration_ms=%s",
            trace_label,
            request.model,
            duration_ms,
        )

    def _get_client(self, *, timeout_seconds: int) -> httpx.AsyncClient:
        if self._client is None or self._client.timeout.connect != timeout_seconds:
            self._client = httpx.AsyncClient(timeout=timeout_seconds or self._default_timeout_seconds)
        return self._client

    def _get_sdk_client(self, *, timeout_seconds: int) -> AsyncOpenAI:
        effective_timeout = timeout_seconds or self._default_timeout_seconds
        if self._sdk_client is None or self._sdk_timeout_seconds != effective_timeout:
            self._sdk_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=effective_timeout,
            )
            self._sdk_timeout_seconds = effective_timeout
        return self._sdk_client

    def _build_payload(self, request: AICompletionRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": request.model,
            "temperature": request.temperature,
            "messages": [self._serialize_message(message) for message in request.messages],
        }
        if self._enable_reasoning or request.metadata.get("enable_reasoning"):
            payload["thinking"] = {"type": "enabled"}
        return payload

    def _serialize_message(self, message: Any) -> Dict[str, Any]:
        if not getattr(message, "images", None):
            return {"role": message.role, "content": message.content}

        content: List[Dict[str, Any]] = [{"type": "text", "text": message.content}]
        for image in message.images:
            assert isinstance(image, AIImageInput)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.media_type};base64,{image.data_base64}",
                    },
                }
            )
        return {"role": message.role, "content": content}

    def _extract_content(self, payload: Dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIAdapterResponseError("provider response does not contain choices")

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
        raise AIAdapterResponseError("provider response content is empty")

    def _extract_delta_content(self, payload: Dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""

        delta = choices[0].get("delta", {})
        content = delta.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(part for part in parts if part)
        return ""

    def _is_stream_finished(self, payload: Dict[str, Any]) -> bool:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return False
        finish_reason = choices[0].get("finish_reason")
        return isinstance(finish_reason, str) and bool(finish_reason.strip())
