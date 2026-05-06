from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Type

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.ai.base import AIAdapter
from app.ai.types import AICompletionRequest, AIMessage

REACT_AGENT_PROMPT_PREFIX = """你是一个采用轻规划 ReAct 风格的短视频创作执行代理。

执行原则：
1. 先阅读本轮任务简报，只围绕本轮目标推进，不要被历史细节干扰。
2. 先判断当前真正缺什么信息，再选择最合适的工具推进。
3. 不要跳步，不要重复调用无必要的工具。
4. 当用户需求涉及视频剪辑导出、片段拼接、压缩导出、字幕烧录、尺寸比例调整、平台发布规格等技术执行时，应先使用 derive_clip_segments 建立原视频片段映射，再调用 run_video_edit_subagent，把具体导出交给专门的剪辑导出子代理处理。
5. 如果用户意图不明确，或完成任务还缺少关键信息，你可以直接 finalize，让系统向用户输出澄清问题或建议；这时不要强行调用工具。
6. 如果某个工具已经完成同类必要工作，避免无意义重复调用。
7. 如果工具观察结果明确提示参数错误、命令错误或执行失败，必须根据错误内容再次调用合适工具推进，不能直接 finalize。
8. task board 是可选的管理工具：当任务较复杂、需要拆分多步执行或跟踪导出状态时再使用；简单轮次不必为了形式先建 task board。

输出要求：
1. 只返回 JSON，格式为 {"thought":"...","action":"...","action_input":"..."}。
2. thought 要简洁说明为什么此刻需要该工具。
3. action 必须是可用工具名之一，或 finalize。
4. action_input 要写清本次调用目标；若工具无需参数，可返回空字符串。
5. 当 action=finalize 且本轮未调用工具时，表示你正在直接与用户沟通确认意图或补充信息。
"""

OPENAI_TOOL_CALLING_PROMPT_PREFIX = """你是一个自主视频创作 agent。

你的目标是独立完成用户本轮需求。
你可以调用工具读取事实、生成字幕、生成剪辑方案、建立片段映射、导出视频。
每次选择最能推进目标的工具。
不要虚构工具执行结果。
如果工具失败，应基于错误信息修正策略并继续尝试。
当确认用户目标已完成时，直接输出最终回复。
"""


def _runtime_block(title: str, content: str) -> str:
    return f"\n[{title}]\n{content}"


ToolFunc = Callable[[BaseModel], Awaitable[str]]
ProgressFunc = Callable[[str], Awaitable[None]]
TraceFunc = Callable[[str, str, str], Awaitable[None]]
PlannerStreamFunc = Callable[[str, str], Awaitable[None]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    input_model: Type[BaseModel]
    run: ToolFunc

    def to_openai_tool(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema["additionalProperties"] = False
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
                "strict": True,
            },
        }

    def validate_json(self, arguments: str | None) -> BaseModel:
        payload = (arguments or "").strip() or "{}"
        return self.input_model.model_validate_json(payload)


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

    def to_openai_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self.tools.values()]


@dataclass(slots=True)
class ReActStep:
    thought: str
    action: str
    action_input: str


@dataclass(slots=True)
class LightPlanningReActResult:
    scratchpad: List[Dict[str, str]]


@dataclass(slots=True)
class OpenAIToolCallingResult:
    scratchpad: List[Dict[str, str]]
    final_text: str = ""


class ToolResult(BaseModel):
    ok: bool
    summary: str
    artifact_type: str | None = None
    state_patch: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    next_recommendation: str | None = None
    error_code: str | None = None
    required_action: dict[str, Any] | None = None
    retry_same_tool_allowed: bool = True
    next_tool: str | None = None
    next_tool_input: dict[str, Any] | None = None
    expected_duration_seconds: float | None = None
    actual_duration_seconds: float | None = None
    duration_ok: bool | None = None
    probe_metadata: dict[str, Any] = Field(default_factory=dict)


class LightPlanningReActRuntime:
    """Explicit Python implementation of a lightweight-planning ReAct loop."""

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
        task_brief: str,
        context_prompt: str,
        completion_guard: Callable[[List[Dict[str, str]]], bool],
        fallback_step: Callable[[List[Dict[str, str]]], ReActStep],
        should_skip_step: Callable[[ReActStep, List[Dict[str, str]]], bool] | None,
        progress: ProgressFunc,
        trace: TraceFunc,
        planner_stream: PlannerStreamFunc | None = None,
    ) -> LightPlanningReActResult:
        scratchpad: List[Dict[str, str]] = []
        for _ in range(self._max_steps):
            await progress("Agent 正在规划下一步执行动作...")
            step = await self._next_step(
                user_prompt=user_prompt,
                task_brief=task_brief,
                context_prompt=context_prompt,
                scratchpad=scratchpad,
                planner_stream=planner_stream,
            )
            if not step.action:
                step = fallback_step(scratchpad)
            if step.action == "finalize":
                if completion_guard(scratchpad):
                    break
                step = fallback_step(scratchpad)
                if step.action == "finalize":
                    break

            if should_skip_step and should_skip_step(step, scratchpad):
                step = fallback_step(scratchpad)
                if step.action == "finalize":
                    break

            forced_action = self._forced_action_for_requested_tool(step.action, scratchpad)
            if forced_action is not None:
                step = ReActStep(
                    thought=f"工具 {step.action} 当前不允许直接重试，先执行修复动作。",
                    action=forced_action["tool"],
                    action_input=json.dumps(forced_action.get("input", {}), ensure_ascii=False),
                )

            if step.action not in self._tool_registry.tools:
                step = fallback_step(scratchpad)
                if step.action == "finalize":
                    break

            tool = self._tool_registry.get(step.action)
            await progress(self._progress_text_for_action(step.action))
            tool_input = tool.validate_json(step.action_input)
            observation = await tool.run(tool_input)
            scratchpad.append(
                {
                    "thought": step.thought,
                    "action": step.action,
                    "action_input": step.action_input,
                    "observation": observation,
                }
            )
            await trace(step.thought, step.action, observation)
            auto_result = await self._follow_required_action(
                action=step.action,
                observation=observation,
                scratchpad=scratchpad,
                progress=progress,
                trace=trace,
            )
            if auto_result == "break":
                break
            if completion_guard(scratchpad):
                break

        return LightPlanningReActResult(scratchpad=scratchpad)

    async def _next_step(
        self,
        *,
        user_prompt: str,
        task_brief: str,
        context_prompt: str,
        scratchpad: List[Dict[str, str]],
        planner_stream: PlannerStreamFunc | None = None,
    ) -> ReActStep:
        prompt = (
            REACT_AGENT_PROMPT_PREFIX
            + _runtime_block("可用工具", self._tool_registry.render_prompt())
            + _runtime_block("用户需求", user_prompt)
            + _runtime_block("本轮任务简报", task_brief)
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
            "create_task_board": "Agent 正在创建当前轮次任务板...",
            "read_task_board": "Agent 正在读取当前轮次任务板...",
            "update_task_status": "Agent 正在更新当前轮次任务状态...",
            "run_keyframe_vision_subagent": "Agent 正在调用关键帧视觉子代理...",
            "read_video_context": "Agent 正在读取视频上下文...",
            "read_manual": "Agent 正在读取产品说明...",
            "read_current_artifacts": "Agent 正在读取当前产物...",
            "derive_clip_segments": "Agent 正在建立原视频片段映射...",
            "run_video_edit_subagent": "Agent 正在委托剪辑导出子代理执行视频导出...",
            "read_video_edit_context": "Agent 正在读取视频导出上下文...",
            "render_clip_segment": "Agent 正在渲染单个视频片段...",
            "merge_rendered_segments": "Agent 正在合并已渲染片段并生成成片...",
            "write_subtitles": "Agent 正在生成字幕草稿...",
            "write_edit_plan": "Agent 正在生成剪辑方案...",
            "write_title": "Agent 正在生成英文标题...",
            "write_tags": "Agent 正在生成标签...",
        }
        return mapping.get(action, "Agent 正在执行工具...")

    async def _follow_required_action(
        self,
        *,
        action: str,
        observation: str,
        scratchpad: List[Dict[str, str]],
        progress: ProgressFunc,
        trace: TraceFunc,
    ) -> str | None:
        del action
        tool_result = self._parse_tool_result(observation)
        if not tool_result or tool_result.ok or not tool_result.required_action:
            return None
        forced_tool = str(tool_result.required_action.get("tool", "")).strip()
        forced_input = tool_result.required_action.get("input") or {}
        if not forced_tool:
            return None
        if forced_tool not in self._tool_registry.tools:
            return None
        await progress(self._progress_text_for_action(forced_tool))
        serialized_input = json.dumps(forced_input, ensure_ascii=False)
        tool = self._tool_registry.get(forced_tool)
        tool_input = tool.validate_json(serialized_input)
        forced_observation = await tool.run(tool_input)
        scratchpad.append(
            {
                "thought": f"根据工具失败结果，直接执行修复动作 {forced_tool}。",
                "action": forced_tool,
                "action_input": serialized_input,
                "observation": forced_observation,
            }
        )
        await trace(f"根据工具失败结果，直接执行修复动作 {forced_tool}。", forced_tool, forced_observation)
        return None

    def _parse_tool_result(self, observation: str) -> ToolResult | None:
        payload = self._parse_json_object(observation)
        if not isinstance(payload, dict) or "ok" not in payload:
            return None
        try:
            return ToolResult.model_validate(payload)
        except Exception:
            return None

    def _forced_action_for_requested_tool(
        self,
        action: str,
        scratchpad: List[Dict[str, str]],
    ) -> dict[str, Any] | None:
        for item in reversed(scratchpad):
            if str(item.get("action", "")).strip() != action:
                continue
            result = self._parse_tool_result(str(item.get("observation", "")))
            if result is None:
                return None
            if result.ok:
                return None
            if result.retry_same_tool_allowed:
                return None
            required_action = result.required_action or {}
            required_tool = str(required_action.get("tool", "")).strip()
            required_input = required_action.get("input") or {}
            if not required_tool:
                return None
            if self._has_successful_tool_call_after(
                required_tool,
                required_input,
                scratchpad,
                item,
            ):
                return None
            return {"tool": required_tool, "input": required_input}
        return None

    def _has_successful_tool_call_after(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        scratchpad: List[Dict[str, str]],
        anchor: Dict[str, str],
    ) -> bool:
        try:
            start_index = scratchpad.index(anchor) + 1
        except ValueError:
            start_index = 0
        expected_input = json.dumps(tool_input, ensure_ascii=False)
        for item in scratchpad[start_index:]:
            if str(item.get("action", "")).strip() != tool_name:
                continue
            actual_input = str(item.get("action_input", "")).strip()
            result = self._parse_tool_result(str(item.get("observation", "")))
            if result and result.ok and (not expected_input or actual_input == expected_input):
                return True
        return False


class OpenAIToolCallingRuntime:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        tool_registry: ToolRegistry,
        max_steps: int,
        timeout_seconds: int,
        system_prompt: str = OPENAI_TOOL_CALLING_PROMPT_PREFIX,
    ) -> None:
        if not api_key:
            raise ValueError("tool-calling runtime api key is not configured")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )
        self._model = model
        self._tool_registry = tool_registry
        self._max_steps = max_steps
        self._system_prompt = system_prompt

    async def run(
        self,
        *,
        user_prompt: str,
        task_brief: str,
        context_prompt: str,
        completion_guard: Callable[[List[Dict[str, str]]], bool] | None = None,
        progress: ProgressFunc,
        trace: TraceFunc,
    ) -> OpenAIToolCallingResult:
        scratchpad: List[Dict[str, str]] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt.strip()},
            {
                "role": "user",
                "content": (
                    _runtime_block("用户需求", user_prompt)
                    + _runtime_block("本轮任务简报", task_brief)
                    + _runtime_block("上下文", context_prompt)
                ).strip(),
            },
        ]
        final_text = ""

        for _ in range(self._max_steps):
            await progress("Agent 正在规划下一步执行动作...")
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=self._tool_registry.to_openai_tools(),
                tool_choice="auto",
            )
            message = response.choices[0].message
            assistant_content = self._message_text(message.content)
            messages.append(self._serialize_assistant_message(message, assistant_content))

            if not message.tool_calls:
                final_text = assistant_content.strip()
                break

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                resolved_tool_name = tool_name
                resolved_arguments = tool_call.function.arguments
                forced_action = self._forced_action_for_requested_tool(tool_name, scratchpad)
                if forced_action is not None:
                    resolved_tool_name = forced_action["tool"]
                    resolved_arguments = json.dumps(forced_action.get("input", {}), ensure_ascii=False)
                await progress(self._progress_text_for_action(resolved_tool_name))
                observation, normalized_input = await self._execute_tool_call(
                    resolved_tool_name,
                    resolved_arguments,
                )
                scratchpad.append(
                    {
                        "thought": assistant_content,
                        "action": resolved_tool_name,
                        "action_input": normalized_input,
                        "observation": observation,
                    }
                )
                await trace(assistant_content, resolved_tool_name, observation)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": observation,
                    }
                )
                await self._follow_required_action(
                    observation=observation,
                    scratchpad=scratchpad,
                    messages=messages,
                    progress=progress,
                    trace=trace,
                )

            if completion_guard and completion_guard(scratchpad):
                break

        return OpenAIToolCallingResult(scratchpad=scratchpad, final_text=final_text)

    async def _execute_tool_call(self, tool_name: str, arguments: str | None) -> tuple[str, str]:
        normalized_input = (arguments or "").strip() or "{}"
        try:
            tool = self._tool_registry.get(tool_name)
        except KeyError as exc:
            result = ToolResult(
                ok=False,
                summary=f"工具调用失败：{exc}",
                error=str(exc),
            )
            return result.model_dump_json(), normalized_input

        try:
            tool_input = tool.validate_json(arguments)
        except Exception as exc:
            result = ToolResult(
                ok=False,
                summary=f"工具参数校验失败：{exc}",
                error=str(exc),
                next_recommendation=f"重新调用 {tool_name} 并提供符合 schema 的参数。",
            )
            return result.model_dump_json(), normalized_input

        normalized_input = tool_input.model_dump_json(exclude_none=True)
        try:
            return await tool.run(tool_input), normalized_input
        except Exception as exc:
            result = ToolResult(
                ok=False,
                summary=f"工具执行失败：{exc}",
                error=str(exc),
                next_recommendation=f"根据错误信息修正后再次调用 {tool_name}。",
            )
            return result.model_dump_json(), normalized_input

    def _serialize_assistant_message(self, message: Any, assistant_content: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": assistant_content,
        }
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]
        return payload

    def _message_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif hasattr(item, "type") and getattr(item, "type") == "text":
                    parts.append(str(getattr(item, "text", "")))
            return "\n".join(part for part in parts if part)
        return ""

    def _progress_text_for_action(self, action: str) -> str:
        return LightPlanningReActRuntime._progress_text_for_action(self, action)

    async def _follow_required_action(
        self,
        *,
        observation: str,
        scratchpad: List[Dict[str, str]],
        messages: list[dict[str, Any]],
        progress: ProgressFunc,
        trace: TraceFunc,
    ) -> None:
        result = self._parse_tool_result(observation)
        if not result or result.ok or not result.required_action:
            return
        forced_tool = str(result.required_action.get("tool", "")).strip()
        forced_input = result.required_action.get("input") or {}
        if not forced_tool or forced_tool not in self._tool_registry.tools:
            return
        await progress(self._progress_text_for_action(forced_tool))
        serialized_input = json.dumps(forced_input, ensure_ascii=False)
        forced_observation, normalized_input = await self._execute_tool_call(forced_tool, serialized_input)
        scratchpad.append(
            {
                "thought": f"根据工具失败结果，直接执行修复动作 {forced_tool}。",
                "action": forced_tool,
                "action_input": normalized_input,
                "observation": forced_observation,
            }
        )
        await trace(f"根据工具失败结果，直接执行修复动作 {forced_tool}。", forced_tool, forced_observation)
        messages.append(
            {
                "role": "system",
                "content": (
                    f"系统已根据工具失败结果自动执行修复动作 {forced_tool}。"
                    f"\n修复动作结果：{forced_observation}"
                ),
            }
        )

    def _parse_tool_result(self, observation: str) -> ToolResult | None:
        text = observation.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or "ok" not in payload:
            return None
        try:
            return ToolResult.model_validate(payload)
        except Exception:
            return None

    def _forced_action_for_requested_tool(
        self,
        action: str,
        scratchpad: List[Dict[str, str]],
    ) -> dict[str, Any] | None:
        for item in reversed(scratchpad):
            if str(item.get("action", "")).strip() != action:
                continue
            result = self._parse_tool_result(str(item.get("observation", "")))
            if result is None:
                return None
            if result.ok or result.retry_same_tool_allowed:
                return None
            required_action = result.required_action or {}
            required_tool = str(required_action.get("tool", "")).strip()
            required_input = required_action.get("input") or {}
            if not required_tool:
                return None
            if self._has_successful_tool_call_after(required_tool, required_input, scratchpad, item):
                return None
            return {"tool": required_tool, "input": required_input}
        return None

    def _has_successful_tool_call_after(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        scratchpad: List[Dict[str, str]],
        anchor: Dict[str, str],
    ) -> bool:
        try:
            start_index = scratchpad.index(anchor) + 1
        except ValueError:
            start_index = 0
        expected_input = json.dumps(tool_input, ensure_ascii=False)
        for item in scratchpad[start_index:]:
            if str(item.get("action", "")).strip() != tool_name:
                continue
            actual_input = str(item.get("action_input", "")).strip()
            result = self._parse_tool_result(str(item.get("observation", "")))
            if result and result.ok and (not expected_input or actual_input == expected_input):
                return True
        return False
