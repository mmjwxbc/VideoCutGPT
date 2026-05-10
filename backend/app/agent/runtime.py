from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Literal, Type

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.ai.base import AIAdapter
from app.ai.types import AICompletionRequest, AIMessage

REACT_AGENT_PROMPT_PREFIX = """你是一个采用轻规划 ReAct 风格的短视频创作执行代理，也是本轮任务的现场总控。

核心原则：
1. 只围绕“本轮最新目标”推进，历史内容仅作为参考，不能盖过当前指令。
2. 先判断缺口，再选工具。不要为了走流程而调用工具。
3. 任何结论都必须基于上下文或真实工具结果，禁止脑补“已经导出”“已经分析完成”之类状态。
4. 简单任务直接完成；复杂任务再拆解。task board 不是必选项，只在需要跟踪多步执行或恢复现场时使用。
5. 避免重复劳动：已有可复用的字幕、剪辑方案、片段映射、导出结果时，优先复用，除非用户明确要求重做或现有结果已失效。
6. 用户要求“继续导出 / 重试导出 / 接着做”且当前已有片段映射时，不要重新调用 derive_clip_segments，以免破坏已有渲染进度；应优先继续 run_video_edit_subagent。
7. 当用户需求涉及视频剪辑导出、片段拼接、压缩导出、字幕烧录、比例调整、平台规格等技术执行时，通常先 derive_clip_segments，再 run_video_edit_subagent。
8. 如果工具失败，要根据失败类型决策：
   - 参数或格式问题：修正输入后再试。
   - 字幕时间轴问题：优先调用 write_subtitles 生成严格 timeline_plain。
   - 环境/依赖/权限类错误：不要盲目重复同一调用，应停止重复尝试，转为说明阻塞原因或选择别的可行步骤。
9. 如果信息不足以安全推进，可以直接 finalize，让系统向用户澄清；不要为了“有动作”而乱调用工具。

剪辑决策准则：
1. 平台短视频优先强节奏、高信息密度、明确 hook。
2. 没有用户明确要求时，不要默认保留原视频全部内容；应主动压缩冗余、保留最有转化价值的片段。
3. 字幕、标题、标签、剪辑方案必须彼此一致，围绕同一卖点和受众语气。
4. 生成导出时，若需要中文 TTS，可在 merge_rendered_segments 的 action_input 里显式传入 tts_language=\"汉语\"，必要时再传 tts_voice。

输出要求：
1. 只返回 JSON，格式为 {"thought":"...","action":"...","action_input":"..."}。
2. thought 简洁说明此刻真正的推进理由，不要写空话。
3. action 必须是可用工具名之一，或 finalize。
4. action_input 要具体、可执行；工具无需参数时可返回空字符串。
5. 当 action=finalize 且本轮未调用工具时，表示你正在直接与用户沟通确认意图或给出建议。
"""

OPENAI_TOOL_CALLING_PROMPT_PREFIX = """你是一个自主视频创作 agent，也是本轮视频项目的执行导演。

你的目标不是“调用尽可能多的工具”，而是以最少的必要步骤完成用户本轮需求。

工作纪律：
1. 每一步都先判断当前最关键缺口，再调用最合适的单个工具推进。
2. 仅依据真实上下文和工具结果行动；不要虚构素材内容、执行结果、导出状态或文件状态。
3. 尽量复用已有成果。已有有效字幕、剪辑方案、片段映射、导出结果时，不要无故重做。
4. 用户要求导出、重试导出、继续导出时，优先保护现有进度；如果已经有 segments，不要轻易重建片段映射。
5. 工具失败后要分类处理：
   - 可修正输入的问题，修正后再试。
   - 非输入问题的环境/依赖错误，不要无限重试同一调用。
   - 需要别的工具修复前置条件时，先修复再继续。
6. 当确认用户目标已完成时，直接输出最终回复；当确认当前无法继续推进时，明确说明真实阻塞点。
7. 若需要中文 TTS，请在 merge_rendered_segments 中传 tts_language=\"汉语\"；如需指定音色，再传 tts_voice。
"""


def _runtime_block(title: str, content: str) -> str:
    return f"\n[{title}]\n{content}"


ToolFunc = Callable[[BaseModel], Awaitable[str]]
ProgressFunc = Callable[[str], Awaitable[None]]
PlannerStreamFunc = Callable[[str, str], Awaitable[None]]
CompletionGuard = Callable[[List[Dict[str, str]]], bool]
AgentMode = Literal["openai_tools", "react_json"]


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_model: Type[BaseModel]

    @abstractmethod
    async def run(self, action_input: BaseModel) -> str:
        """Execute one tool call."""

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
    tools: Dict[str, BaseTool | ToolSpec] = field(default_factory=dict)
    _cached_definitions: list[dict[str, Any]] | None = None

    def register(self, tool: BaseTool | ToolSpec) -> None:
        self.tools[tool.name] = tool
        self._cached_definitions = None

    def get(self, name: str) -> BaseTool | ToolSpec:
        if name not in self.tools:
            raise KeyError(f"tool '{name}' not found")
        return self.tools[name]

    def has(self, name: str) -> bool:
        return name in self.tools

    def render_prompt(self) -> str:
        return "\n".join(f"- {tool.name}: {tool.description}" for tool in self.tools.values())

    def to_openai_tools(self) -> list[dict[str, Any]]:
        if self._cached_definitions is None:
            self._cached_definitions = [tool.to_openai_tool() for tool in self.tools.values()]
        return self._cached_definitions

    def prepare_call(
        self,
        name: str,
        arguments: str | None,
    ) -> tuple[BaseTool | ToolSpec | None, str, BaseModel | None, str | None]:
        normalized_input = (arguments or "").strip() or "{}"
        try:
            tool = self.get(name)
        except KeyError as exc:
            result = ToolResult(
                ok=False,
                summary=f"工具调用失败：{exc}",
                error=str(exc),
            )
            return None, normalized_input, None, result.model_dump_json(exclude_none=True)

        try:
            tool_input = tool.validate_json(arguments)
        except Exception as exc:
            result = ToolResult(
                ok=False,
                summary=f"工具参数校验失败：{exc}",
                error=str(exc),
                next_recommendation=f"重新调用 {name} 并提供符合 schema 的参数。",
            )
            return tool, normalized_input, None, result.model_dump_json(exclude_none=True)

        return tool, tool_input.model_dump_json(exclude_none=True), tool_input, None

    async def execute(self, name: str, arguments: str | None) -> tuple[str, str]:
        tool, normalized_input, tool_input, error = self.prepare_call(name, arguments)
        if error is not None:
            return error, normalized_input
        assert tool is not None
        assert tool_input is not None
        try:
            return await tool.run(tool_input), normalized_input
        except Exception as exc:
            result = ToolResult(
                ok=False,
                summary=f"工具执行失败：{exc}",
                error=str(exc),
                next_recommendation=f"根据错误信息修正后再次调用 {name}。",
            )
            return result.model_dump_json(exclude_none=True), normalized_input


@dataclass(slots=True)
class ReActStep:
    thought: str
    action: str
    action_input: str


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


@dataclass(slots=True)
class ToolCallRequest:
    name: str
    arguments: str


@dataclass(slots=True)
class AgentHookContext:
    iteration: int
    messages: list[dict[str, Any]]
    scratchpad: list[dict[str, str]]
    response_content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
    tool_events: list[dict[str, str]] = field(default_factory=list)
    final_content: str | None = None
    stop_reason: str | None = None
    error: str | None = None


class AgentHook:
    def wants_streaming(self) -> bool:
        return False

    async def before_iteration(self, context: AgentHookContext) -> None:
        pass

    async def on_progress(self, context: AgentHookContext, message: str) -> None:
        pass

    async def on_stream(self, context: AgentHookContext, delta: str) -> None:
        pass

    async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
        pass

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        pass

    async def after_iteration(self, context: AgentHookContext) -> None:
        pass

    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
        return content


@dataclass(slots=True)
class AgentRunSpec:
    mode: AgentMode
    model: str
    tool_registry: ToolRegistry
    max_iterations: int
    user_prompt: str
    task_brief: str
    context_prompt: str
    system_prompt: str = ""
    timeout_seconds: int = 120
    completion_guard: CompletionGuard | None = None
    fallback_step: Callable[[List[Dict[str, str]]], ReActStep] | None = None
    should_skip_step: Callable[[ReActStep, List[Dict[str, str]]], bool] | None = None
    planner_stream: PlannerStreamFunc | None = None
    progress_callback: ProgressFunc | None = None
    hook: AgentHook | None = None


@dataclass(slots=True)
class AgentRunResult:
    scratchpad: List[Dict[str, str]]
    final_content: str = ""
    stop_reason: str = "completed"
    tools_used: List[str] = field(default_factory=list)
    messages: List[dict[str, Any]] = field(default_factory=list)
    tool_events: list[dict[str, str]] = field(default_factory=list)


class AgentRunner:
    def __init__(
        self,
        *,
        client: AsyncOpenAI | None = None,
        adapter: AIAdapter | None = None,
    ) -> None:
        self._client = client
        self._adapter = adapter

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        if spec.mode == "openai_tools":
            return await self._run_openai_tools(spec)
        if spec.mode == "react_json":
            return await self._run_react_json(spec)
        raise ValueError(f"unsupported agent run mode: {spec.mode}")

    async def _run_openai_tools(self, spec: AgentRunSpec) -> AgentRunResult:
        if self._client is None:
            raise ValueError("openai client is not configured")
        hook = spec.hook or AgentHook()
        scratchpad: List[Dict[str, str]] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": (spec.system_prompt or OPENAI_TOOL_CALLING_PROMPT_PREFIX).strip()},
            {
                "role": "user",
                "content": (
                    _runtime_block("用户需求", spec.user_prompt)
                    + _runtime_block("本轮任务简报", spec.task_brief)
                    + _runtime_block("上下文", spec.context_prompt)
                ).strip(),
            },
        ]
        final_text = ""
        stop_reason = "max_iterations"
        tools_used: List[str] = []
        tool_events: list[dict[str, str]] = []
        context = AgentHookContext(iteration=0, messages=messages, scratchpad=scratchpad)

        for iteration in range(spec.max_iterations):
            context.iteration = iteration
            context.response_content = ""
            context.tool_calls = []
            context.tool_results = []
            context.tool_events = []
            await hook.before_iteration(context)
            await self._emit_progress(spec, hook, context, "Agent 正在规划下一步执行动作...")

            response = await self._client.chat.completions.create(
                model=spec.model,
                messages=messages,
                tools=spec.tool_registry.to_openai_tools(),
                tool_choice="auto",
            )
            message = response.choices[0].message
            assistant_content = self._message_text(message.content)
            context.response_content = assistant_content
            messages.append(self._serialize_assistant_message(message, assistant_content))

            if message.tool_calls:
                context.tool_calls = [
                    ToolCallRequest(
                        name=tool_call.function.name,
                        arguments=tool_call.function.arguments,
                    )
                    for tool_call in message.tool_calls
                ]
                await hook.before_execute_tools(context)
            else:
                final_text = assistant_content.strip()
                stop_reason = "final_response"
                break

            for tool_call in message.tool_calls:
                requested_tool = tool_call.function.name
                resolved_tool_name = requested_tool
                resolved_arguments = tool_call.function.arguments
                forced_action = self._forced_action_for_requested_tool(
                    requested_tool=requested_tool,
                    scratchpad=scratchpad,
                )
                if forced_action is not None:
                    resolved_tool_name = forced_action["tool"]
                    resolved_arguments = json.dumps(forced_action.get("input", {}), ensure_ascii=False)

                await self._emit_progress(spec, hook, context, self._progress_text_for_action(resolved_tool_name))
                observation, normalized_input = await spec.tool_registry.execute(
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
                if resolved_tool_name not in tools_used:
                    tools_used.append(resolved_tool_name)
                tool_event = self._build_tool_event(resolved_tool_name, observation)
                tool_events.append(tool_event)
                context.tool_results.append(observation)
                context.tool_events.append(tool_event)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": observation,
                    }
                )
                await self._follow_required_action(
                    spec=spec,
                    hook=hook,
                    context=context,
                    thought=assistant_content,
                    observation=observation,
                    scratchpad=scratchpad,
                    messages=messages,
                    tools_used=tools_used,
                    tool_events=tool_events,
                )

            if spec.completion_guard and spec.completion_guard(scratchpad):
                stop_reason = "completion_guard"
                break

            await hook.after_iteration(context)

        if stop_reason != "final_response":
            await hook.after_iteration(context)
        final_text = hook.finalize_content(context, final_text) or ""
        return AgentRunResult(
            scratchpad=scratchpad,
            final_content=final_text,
            stop_reason=stop_reason,
            tools_used=tools_used,
            messages=messages,
            tool_events=tool_events,
        )

    async def _run_react_json(self, spec: AgentRunSpec) -> AgentRunResult:
        if self._adapter is None:
            raise ValueError("ai adapter is not configured")
        if spec.fallback_step is None:
            raise ValueError("react_json mode requires fallback_step")
        hook = spec.hook or AgentHook()
        scratchpad: List[Dict[str, str]] = []
        messages: list[dict[str, Any]] = []
        final_text = ""
        stop_reason = "max_iterations"
        tools_used: List[str] = []
        tool_events: list[dict[str, str]] = []
        context = AgentHookContext(iteration=0, messages=messages, scratchpad=scratchpad)

        for iteration in range(spec.max_iterations):
            context.iteration = iteration
            context.response_content = ""
            context.tool_calls = []
            context.tool_results = []
            context.tool_events = []
            await hook.before_iteration(context)
            await self._emit_progress(spec, hook, context, "Agent 正在规划下一步执行动作...")

            step = await self._next_react_step(spec, hook, context, scratchpad)
            if not step.action:
                step = spec.fallback_step(scratchpad)
            if step.action == "finalize":
                if spec.completion_guard and spec.completion_guard(scratchpad):
                    stop_reason = "completion_guard"
                else:
                    fallback_step = spec.fallback_step(scratchpad)
                    if fallback_step.action == "finalize":
                        stop_reason = "finalize"
                    else:
                        step = fallback_step
                if stop_reason != "max_iterations":
                    break

            if spec.should_skip_step and spec.should_skip_step(step, scratchpad):
                fallback_step = spec.fallback_step(scratchpad)
                if fallback_step.action == "finalize":
                    stop_reason = "finalize"
                    break
                step = fallback_step

            forced_action = self._forced_action_for_requested_tool(
                requested_tool=step.action,
                scratchpad=scratchpad,
            )
            if forced_action is not None:
                step = ReActStep(
                    thought=f"工具 {step.action} 当前不允许直接重试，先执行修复动作。",
                    action=forced_action["tool"],
                    action_input=json.dumps(forced_action.get("input", {}), ensure_ascii=False),
                )

            if not spec.tool_registry.has(step.action):
                fallback_step = spec.fallback_step(scratchpad)
                if fallback_step.action == "finalize":
                    stop_reason = "finalize"
                    break
                step = fallback_step

            context.response_content = step.thought
            context.tool_calls = [ToolCallRequest(name=step.action, arguments=step.action_input)]
            await hook.before_execute_tools(context)
            await self._emit_progress(spec, hook, context, self._progress_text_for_action(step.action))
            observation, normalized_input = await spec.tool_registry.execute(step.action, step.action_input)
            scratchpad.append(
                {
                    "thought": step.thought,
                    "action": step.action,
                    "action_input": normalized_input,
                    "observation": observation,
                }
            )
            if step.action not in tools_used:
                tools_used.append(step.action)
            tool_event = self._build_tool_event(step.action, observation)
            tool_events.append(tool_event)
            context.tool_results.append(observation)
            context.tool_events.append(tool_event)
            await self._follow_required_action(
                spec=spec,
                hook=hook,
                context=context,
                thought=step.thought,
                observation=observation,
                scratchpad=scratchpad,
                messages=messages,
                tools_used=tools_used,
                tool_events=tool_events,
            )

            if spec.completion_guard and spec.completion_guard(scratchpad):
                stop_reason = "completion_guard"
                await hook.after_iteration(context)
                break

            await hook.after_iteration(context)

        final_text = hook.finalize_content(context, final_text) or ""
        return AgentRunResult(
            scratchpad=scratchpad,
            final_content=final_text,
            stop_reason=stop_reason,
            tools_used=tools_used,
            messages=messages,
            tool_events=tool_events,
        )

    async def _next_react_step(
        self,
        spec: AgentRunSpec,
        hook: AgentHook,
        context: AgentHookContext,
        scratchpad: List[Dict[str, str]],
    ) -> ReActStep:
        assert self._adapter is not None
        prompt = (
            REACT_AGENT_PROMPT_PREFIX
            + _runtime_block("可用工具", spec.tool_registry.render_prompt())
            + _runtime_block("用户需求", spec.user_prompt)
            + _runtime_block("本轮任务简报", spec.task_brief)
            + _runtime_block("上下文", spec.context_prompt)
            + _runtime_block("已有观察", json.dumps(scratchpad, ensure_ascii=False))
        )
        content = ""
        pending_delta = ""
        last_emit_chars = 0
        async for delta in self._adapter.stream(
            AICompletionRequest(
                model=spec.model,
                timeout_seconds=spec.timeout_seconds,
                require_json=True,
                messages=[AIMessage(role="user", content=prompt)],
            )
        ):
            if not delta:
                continue
            content += delta
            pending_delta += delta
            if hook.wants_streaming():
                await hook.on_stream(context, delta)
            if spec.planner_stream and len(content) - last_emit_chars >= 40:
                await spec.planner_stream(content, pending_delta)
                pending_delta = ""
                last_emit_chars = len(content)
        if hook.wants_streaming():
            await hook.on_stream_end(context, resuming=False)
        if spec.planner_stream and pending_delta:
            await spec.planner_stream(content, pending_delta)
        parsed = self._parse_json_object(content)
        if not isinstance(parsed, dict):
            return ReActStep(thought="", action="", action_input="")
        return ReActStep(
            thought=str(parsed.get("thought", "")).strip(),
            action=str(parsed.get("action", "")).strip(),
            action_input=str(parsed.get("action_input", "")).strip(),
        )

    async def _follow_required_action(
        self,
        *,
        spec: AgentRunSpec,
        hook: AgentHook,
        context: AgentHookContext,
        thought: str,
        observation: str,
        scratchpad: List[Dict[str, str]],
        messages: list[dict[str, Any]],
        tools_used: List[str],
        tool_events: list[dict[str, str]],
    ) -> None:
        result = self._parse_tool_result(observation)
        if not result or result.ok or not result.required_action:
            return
        forced_tool = str(result.required_action.get("tool", "")).strip()
        forced_input = result.required_action.get("input") or {}
        if not forced_tool or not spec.tool_registry.has(forced_tool):
            return

        await self._emit_progress(spec, hook, context, self._progress_text_for_action(forced_tool))
        serialized_input = json.dumps(forced_input, ensure_ascii=False)
        forced_observation, normalized_input = await spec.tool_registry.execute(forced_tool, serialized_input)
        scratchpad.append(
            {
                "thought": f"根据工具失败结果，直接执行修复动作 {forced_tool}。",
                "action": forced_tool,
                "action_input": normalized_input,
                "observation": forced_observation,
            }
        )
        if forced_tool not in tools_used:
            tools_used.append(forced_tool)
        forced_event = self._build_tool_event(forced_tool, forced_observation)
        tool_events.append(forced_event)
        context.tool_results.append(forced_observation)
        context.tool_events.append(forced_event)
        if messages is not None:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"系统已根据工具失败结果自动执行修复动作 {forced_tool}。"
                        f"\n修复动作结果：{forced_observation}"
                    ),
                }
            )

    async def _emit_progress(
        self,
        spec: AgentRunSpec,
        hook: AgentHook,
        context: AgentHookContext,
        message: str,
    ) -> None:
        if spec.progress_callback is not None:
            await spec.progress_callback(message)
        await hook.on_progress(context, message)

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

    def _parse_tool_result(self, observation: str) -> ToolResult | None:
        payload = self._parse_json_object(observation)
        if not isinstance(payload, dict) or "ok" not in payload:
            return None
        try:
            return ToolResult.model_validate(payload)
        except Exception:
            return None

    def _build_tool_event(self, action: str, observation: str) -> dict[str, str]:
        result = self._parse_tool_result(observation)
        if result is None:
            return {"name": action, "status": "ok", "detail": observation[:400]}
        return {
            "name": action,
            "status": "ok" if result.ok else "error",
            "detail": (result.summary or observation)[:400],
        }

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

    def _forced_action_for_requested_tool(
        self,
        *,
        requested_tool: str,
        scratchpad: List[Dict[str, str]],
    ) -> dict[str, Any] | None:
        for item in reversed(scratchpad):
            if str(item.get("action", "")).strip() != requested_tool:
                continue
            result = self._parse_tool_result(str(item.get("observation", "")))
            if result is None or result.ok or result.retry_same_tool_allowed:
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
