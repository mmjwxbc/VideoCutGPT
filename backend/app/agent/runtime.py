from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.ai.base import AIAdapter
from app.ai.types import AICompletionRequest, AIMessage


ToolFunc = Callable[[str], Awaitable[str]]
ProgressFunc = Callable[[str], Awaitable[None]]
TraceFunc = Callable[[str, str, str], Awaitable[None]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    run: ToolFunc


@dataclass(slots=True)
class ToolRegistry:
    tools: Dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, tool: ToolSpec) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        if name not in self.tools:
            raise KeyError(f"tool '{name}' not found")
        return self.tools[name]

    def render_prompt(self) -> str:
        lines = []
        for tool in self.tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)


@dataclass(slots=True)
class ReActStep:
    thought: str
    action: str
    action_input: str


@dataclass(slots=True)
class PlanAndExecuteResult:
    scratchpad: List[Dict[str, str]]


class PlanAndExecuteRuntime:
    """Explicit Python implementation of a ReAct plan-and-execute loop."""

    def __init__(
        self,
        *,
        adapter: AIAdapter,
        model: str,
        tool_registry: ToolRegistry,
        max_steps: int,
        timeout_seconds: int,
    ) -> None:
        self._adapter = adapter
        self._model = model
        self._tool_registry = tool_registry
        self._max_steps = max_steps
        self._timeout_seconds = timeout_seconds

    async def run(
        self,
        *,
        user_prompt: str,
        execution_plan: List[str],
        context_prompt: str,
        completion_guard: Callable[[List[Dict[str, str]]], bool],
        fallback_step: Callable[[List[Dict[str, str]]], ReActStep],
        should_skip_step: Callable[[ReActStep, List[Dict[str, str]]], bool] | None,
        progress: ProgressFunc,
        trace: TraceFunc,
    ) -> PlanAndExecuteResult:
        scratchpad: List[Dict[str, str]] = []
        for _ in range(self._max_steps):
            await progress("Agent 正在规划下一步执行动作...")
            step = await self._next_step(
                user_prompt=user_prompt,
                execution_plan=execution_plan,
                context_prompt=context_prompt,
                scratchpad=scratchpad,
            )
            if not step.action:
                step = fallback_step(scratchpad)
            if step.action == "finalize":
                break

            if should_skip_step and should_skip_step(step, scratchpad):
                step = fallback_step(scratchpad)
                if step.action == "finalize":
                    break

            if step.action not in self._tool_registry.tools:
                step = fallback_step(scratchpad)
                if step.action == "finalize":
                    break

            tool = self._tool_registry.get(step.action)
            await progress(self._progress_text_for_action(step.action))
            observation = await tool.run(step.action_input)
            scratchpad.append(
                {
                    "thought": step.thought,
                    "action": step.action,
                    "observation": observation,
                }
            )
            await trace(step.thought, step.action, observation)
            if completion_guard(scratchpad):
                break

        return PlanAndExecuteResult(scratchpad=scratchpad)

    async def _next_step(
        self,
        *,
        user_prompt: str,
        execution_plan: List[str],
        context_prompt: str,
        scratchpad: List[Dict[str, str]],
    ) -> ReActStep:
        prompt = (
            "你是一个采用 ReAct 风格的短视频创作执行代理。"
            "\n你必须从以下工具中选择下一步动作，或返回 finalize。"
            f"\n可用工具：\n{self._tool_registry.render_prompt()}"
            "\n\n只返回 JSON，格式为 "
            '{"thought":"...","action":"...","action_input":"..."}'
            f"\n\n用户需求：{user_prompt}"
            f"\n执行计划：{json.dumps(execution_plan, ensure_ascii=False)}"
            f"\n上下文：{context_prompt}"
            f"\n已有观察：{json.dumps(scratchpad, ensure_ascii=False)}"
        )
        response = await self._adapter.complete(
            AICompletionRequest(
                model=self._model,
                timeout_seconds=self._timeout_seconds,
                require_json=True,
                messages=[AIMessage(role="user", content=prompt)],
            )
        )
        parsed = self._parse_json_object(response.content)
        if not isinstance(parsed, dict):
            return ReActStep(thought="", action="", action_input="")
        return ReActStep(
            thought=str(parsed.get("thought", "")).strip(),
            action=str(parsed.get("action", "")).strip(),
            action_input=str(parsed.get("action_input", "")).strip(),
        )

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}

    def _progress_text_for_action(self, action: str) -> str:
        mapping = {
            "run_keyframe_vision_subagent": "Agent 正在调用关键帧视觉子代理...",
            "read_video_context": "Agent 正在读取视频上下文...",
            "read_manual": "Agent 正在读取产品说明...",
            "read_current_artifacts": "Agent 正在读取当前产物...",
            "write_subtitles": "Agent 正在生成字幕草稿...",
            "write_edit_plan": "Agent 正在生成剪辑方案...",
            "write_title": "Agent 正在生成英文标题...",
            "write_tags": "Agent 正在生成标签...",
        }
        return mapping.get(action, "Agent 正在执行工具...")
