from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Literal, Optional


MessageRole = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class AIImageInput:
    media_type: str
    data_base64: str


@dataclass(slots=True)
class AIMessage:
    role: MessageRole
    content: str
    images: List[AIImageInput] = field(default_factory=list)


@dataclass(slots=True)
class AICompletionRequest:
    messages: List[AIMessage]
    model: str
    temperature: float = 0.2
    timeout_seconds: int = 120
    require_json: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AIUsage:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


@dataclass(slots=True)
class AICompletionResponse:
    content: str
    usage: AIUsage = field(default_factory=AIUsage)
    raw_response: Dict[str, Any] = field(default_factory=dict)


AIStream = AsyncIterator[str]
