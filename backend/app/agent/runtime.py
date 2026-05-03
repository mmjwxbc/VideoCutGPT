from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.ai.base import AIAdapter
from app.ai.types import AICompletionRequest, AIMessage

REACT_AGENT_PROMPT_PREFIX = """你是一个采用 ReAct 风格的短视频创作执行代理。

执行原则：
1. 先判断当前真正缺什么信息，再选择最合适的工具推进。
2. 不要跳步，不要重复调用无必要的工具。
3. 当用户需求涉及 ffmpeg 命令、视频裁剪拼接、压缩导出、字幕烧录、尺寸比例调整、平台发布规格等技术执行时，应优先读取相关 skill 工具，再决定后续写作动作。
4. 如果信息还不够，不要提前 finalize。
5. 如果某个工具已经完成同类必要工作，避免无意义重复调用。
6. 如果工具观察结果明确提示参数错误、命令错误或执行失败，必须根据错误内容修正后再次调用合适工具，不能直接 finalize。

输出要求：
1. 只返回 JSON，格式为 {"thought":"...","action":"...","action_input":"..."}。
2. thought 要简洁说明为什么此刻需要该工具。
3. action 必须是可用工具名之一，或 finalize。
4. action_input 要写清本次调用目标；若工具无需参数，可返回空字符串。
"""


def _runtime_block(title: str, content: str) -> str:
    return f"\n[{title}]\n{content}"


ToolFunc = Callable[[str], Awaitable[str]]
ProgressFunc = Callable[[str], Awaitable[None]]
TraceFunc = Callable[[str, str, str], Awaitable[None]]
PlannerStreamFunc = Callable[[str, str], Awaitable[None]]


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
        planner_stream: PlannerStreamFunc | None = None,
    ) -> PlanAndExecuteResult:
        scratchpad: List[Dict[str, str]] = []
        for _ in range(self._max_steps):
            await progress("Agent 正在规划下一步执行动作...")
            step = await self._next_step(
                user_prompt=user_prompt,
                execution_plan=execution_plan,
                context_prompt=context_prompt,
                scratchpad=scratchpad,
                planner_stream=planner_stream,
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
        planner_stream: PlannerStreamFunc | None = None,
    ) -> ReActStep:
        prompt = (
            REACT_AGENT_PROMPT_PREFIX
            + _runtime_block("可用工具", self._tool_registry.render_prompt())
            + _runtime_block("用户需求", user_prompt)
            + _runtime_block("执行计划", json.dumps(execution_plan, ensure_ascii=False))
            + _runtime_block("上下文", context_prompt)
            + _runtime_block("已有观察", json.dumps(scratchpad, ensure_ascii=False))
        )
        content = ""
        pending_delta = ""
        last_emit_chars = 0
        async for delta in self._adapter.stream(
            AICompletionRequest(
                model=self._model,
                timeout_seconds=self._timeout_seconds,
                require_json=True,
                messages=[AIMessage(role="user", content=prompt)],
            )
        ):
            if not delta:
                continue
            content += delta
            pending_delta += delta
            if planner_stream and len(content) - last_emit_chars >= 40:
                await planner_stream(content, pending_delta)
                pending_delta = ""
                last_emit_chars = len(content)
        if planner_stream and pending_delta:
            await planner_stream(content, pending_delta)
        parsed = self._parse_json_object(content)
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
            "read_skill_ffmpeg_usage": "Agent 正在读取 ffmpeg 技能文档...",
            "read_current_artifacts": "Agent 正在读取当前产物...",
            "write_subtitles": "Agent 正在生成字幕草稿...",
            "write_edit_plan": "Agent 正在生成剪辑方案...",
            "write_title": "Agent 正在生成英文标题...",
            "write_tags": "Agent 正在生成标签...",
            "run_bash_ffmpeg": "Agent 正在执行 ffmpeg bash 导出视频...",
        }
        return mapping.get(action, "Agent 正在执行工具...")
