from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from app.agent.runtime import PlanAndExecuteRuntime, ReActStep, ToolRegistry, ToolSpec
from app.ai.factory import AIAdapterFactory
from app.ai.types import AICompletionRequest, AIImageInput, AIMessage
from app.core.config import settings
from app.core.utils import extract_keyframes, select_keyframes_for_analysis


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class ConversationMessage:
    role: str
    content: str
    created_at: str = field(default_factory=_utcnow)


@dataclass
class ExecutionPlanOption:
    id: str
    title: str
    description: str
    required: bool = False
    selected: bool = False


@dataclass
class AgentTraceItem:
    thought: str
    action: str
    observation: str
    created_at: str = field(default_factory=_utcnow)


@dataclass
class ExecutionEventItem:
    kind: str
    title: str
    detail: str
    tool: str = ""
    artifact: str = ""
    created_at: str = field(default_factory=_utcnow)


@dataclass
class CaptionSession:
    session_id: str
    video_path: str
    platform: str
    product_manual: str
    messages: List[ConversationMessage] = field(default_factory=list)
    keyframes: List[Dict[str, Any]] = field(default_factory=list)
    frame_analyses: List[str] = field(default_factory=list)
    video_summary: str = ""
    execution_plan: List[str] = field(default_factory=list)
    plan_options: List[ExecutionPlanOption] = field(default_factory=list)
    selected_plan_ids: List[str] = field(default_factory=list)
    agent_trace: List[AgentTraceItem] = field(default_factory=list)
    execution_events: List[ExecutionEventItem] = field(default_factory=list)
    subtitle_draft: str = ""
    editing_plan: str = ""
    english_title: str = ""
    tags: List[str] = field(default_factory=list)
    status: str = "idle"
    progress_message: str = ""
    error_message: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


class CaptionSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, CaptionSession] = {}
        self._lock = Lock()

    def save(self, session: CaptionSession) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> CaptionSession:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"session '{session_id}' not found")
            return self._sessions[session_id]


class CaptionEventBroker:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue[Dict[str, Any]]]] = {}
        self._lock = Lock()

    def subscribe(self, session_id: str) -> asyncio.Queue[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        with self._lock:
            queues = self._subscribers.get(session_id, [])
            self._subscribers[session_id] = [item for item in queues if item is not queue]
            if not self._subscribers[session_id]:
                self._subscribers.pop(session_id, None)

    def publish(self, session_id: str, event: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            queues = list(self._subscribers.get(session_id, []))
        message = {"event": event, "data": payload}
        for queue in queues:
            queue.put_nowait(message)


class CaptionConversationAssistant:
    def __init__(self) -> None:
        self.store = CaptionSessionStore()
        self.events = CaptionEventBroker()
        self._adapter_factory = AIAdapterFactory()
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._completion_events: Dict[str, asyncio.Event] = {}
        self._meta_lock = Lock()

    async def create_session(
        self,
        video_path: str,
        platform: str,
        product_manual: Optional[str],
        user_prompt: str,
    ) -> Dict[str, Any]:
        session = CaptionSession(
            session_id=str(uuid4()),
            video_path=video_path,
            platform=platform,
            product_manual=product_manual or "",
            status="queued",
            progress_message="任务已创建，准备生成 Agent 执行计划。",
        )
        session.messages.append(ConversationMessage(role="user", content=user_prompt))
        self.store.save(session)
        self._ensure_session_primitives(session.session_id)
        self._publish_snapshot(session, "session_created")
        asyncio.create_task(self._prepare_initial_plan(session.session_id, user_prompt))
        return self._serialize(session)

    async def continue_session(self, session_id: str, user_prompt: str) -> Dict[str, Any]:
        session = self.store.get(session_id)
        if session.status in {"processing", "planning"}:
            raise ValueError("session is still processing")
        if session.status == "awaiting_plan_selection":
            raise ValueError("session is waiting for plan selection")

        session.messages.append(ConversationMessage(role="user", content=user_prompt))
        session.status = "queued"
        session.progress_message = "已收到修改要求，等待开始。"
        session.error_message = ""
        session.updated_at = _utcnow()
        self.store.save(session)
        self._ensure_session_primitives(session_id)
        self._publish_snapshot(session, "message_queued")
        asyncio.create_task(self._process_followup_session(session_id, user_prompt))
        return self._serialize(session)

    async def confirm_execution_plan(
        self,
        session_id: str,
        selected_plan_ids: List[str],
    ) -> Dict[str, Any]:
        session = self.store.get(session_id)
        if session.status != "awaiting_plan_selection":
            raise ValueError("session is not awaiting plan selection")

        available_ids = {option.id for option in session.plan_options}
        required_ids = {option.id for option in session.plan_options if option.required}
        chosen_ids = [plan_id for plan_id in selected_plan_ids if plan_id in available_ids]
        if not required_ids.issubset(set(chosen_ids)):
            raise ValueError("required plan options must be selected")

        session.selected_plan_ids = chosen_ids
        session.plan_options = [
            ExecutionPlanOption(
                id=option.id,
                title=option.title,
                description=option.description,
                required=option.required,
                selected=option.id in chosen_ids,
            )
            for option in session.plan_options
        ]
        session.status = "queued"
        session.progress_message = "已确认执行项，等待 Agent 开始执行。"
        session.error_message = ""
        session.updated_at = _utcnow()
        self.store.save(session)
        self._ensure_session_primitives(session_id)
        self._publish_snapshot(session, "plan_confirmed")
        user_prompt = next(
            (message.content for message in reversed(session.messages) if message.role == "user"),
            "",
        )
        asyncio.create_task(self._process_selected_plan(session_id, user_prompt))
        return self._serialize(session)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._serialize(self.store.get(session_id))

    async def wait_for_completion(self, session_id: str) -> Dict[str, Any]:
        event = self._ensure_completion_event(session_id)
        await event.wait()
        return self.get_session(session_id)

    async def stream_session_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        session = self.store.get(session_id)
        queue = self.events.subscribe(session_id)
        try:
            initial_snapshot = self._serialize(session)
            yield {"event": "snapshot", "data": initial_snapshot}
            if initial_snapshot["status"] in {"completed", "error"}:
                return
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield message
                    data = message.get("data", {})
                    if isinstance(data, dict) and data.get("status") in {"completed", "error"}:
                        return
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": {"session_id": session_id, "ts": _utcnow()}}
        finally:
            self.events.unsubscribe(session_id, queue)

    def _ensure_session_primitives(self, session_id: str) -> None:
        with self._meta_lock:
            self._session_locks.setdefault(session_id, asyncio.Lock())
            self._completion_events[session_id] = asyncio.Event()

    def _ensure_completion_event(self, session_id: str) -> asyncio.Event:
        with self._meta_lock:
            return self._completion_events.setdefault(session_id, asyncio.Event())

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        with self._meta_lock:
            return self._session_locks.setdefault(session_id, asyncio.Lock())

    async def _prepare_initial_plan(self, session_id: str, user_prompt: str) -> None:
        async with self._get_session_lock(session_id):
            try:
                session = self.store.get(session_id)
                await self._set_progress(session, "planning", "Agent 正在生成可执行计划...")
                session.plan_options = await self._build_initial_plan_options(session, user_prompt)
                session.selected_plan_ids = [
                    option.id for option in session.plan_options if option.required or option.selected
                ]
                session.execution_plan = [
                    f"{option.title}：{option.description}" for option in session.plan_options
                ]
                session.status = "awaiting_plan_selection"
                session.progress_message = "请勾选要执行的项，关键帧分析为必选项。"
                session.updated_at = _utcnow()
                self.store.save(session)
                self._publish_snapshot(session, "plan_ready")
                self._ensure_completion_event(session_id).set()
            except Exception as exc:
                await self._fail_session(session_id, exc)

    async def _process_selected_plan(self, session_id: str, user_prompt: str) -> None:
        async with self._get_session_lock(session_id):
            try:
                session = self.store.get(session_id)
                if "keyframe_analysis" not in set(session.selected_plan_ids):
                    raise ValueError("keyframe_analysis must be selected")
                await self._run_selected_initial_turn(session, user_prompt)
                self._ensure_completion_event(session_id).set()
            except Exception as exc:
                await self._fail_session(session_id, exc)

    async def _process_followup_session(self, session_id: str, user_prompt: str) -> None:
        async with self._get_session_lock(session_id):
            try:
                session = self.store.get(session_id)
                await self._set_progress(session, "processing", "正在根据你的新要求改稿...")
                await self._run_turn(session, user_prompt)
                self._ensure_completion_event(session_id).set()
            except Exception as exc:
                await self._fail_session(session_id, exc)

    async def _prepare_video_context(self, session: CaptionSession) -> None:
        await self._set_progress(session, "processing", "正在提取关键帧...")
        session.keyframes = await asyncio.to_thread(
            extract_keyframes,
            session.video_path,
            settings.keyframe_interval_seconds,
            None,
            settings.keyframe_scene_threshold,
        )
        session.updated_at = _utcnow()
        self.store.save(session)
        await self._publish_artifact_updated(
            session,
            "keyframes",
            session.keyframes,
            f"已提取 {len(session.keyframes)} 张关键帧。",
        )
        self._publish_snapshot(session)

        await self._set_progress(session, "processing", "正在分析关键帧内容...")
        session.frame_analyses = await self._analyze_video_frames(session)
        session.updated_at = _utcnow()
        self.store.save(session)
        await self._publish_artifact_updated(
            session,
            "frame_analyses",
            session.frame_analyses,
            f"已完成 {len(session.frame_analyses)} 条关键帧理解。",
        )
        self._publish_snapshot(session)

        await self._set_progress(session, "processing", "正在总结视频内容...")
        session.video_summary = await self._summarize_video(session)
        session.updated_at = _utcnow()
        self.store.save(session)
        await self._publish_artifact_updated(
            session,
            "video_summary",
            session.video_summary,
            "视频摘要已生成。",
        )
        self._publish_snapshot(session)

    async def _run_keyframe_vision_subagent(self, session: CaptionSession) -> str:
        if session.video_summary and session.frame_analyses:
            return "关键帧视觉子代理发现视频上下文已存在，跳过重复执行。"

        await self._prepare_video_context(session)
        return (
            "关键帧视觉子代理已完成。"
            f"\n关键帧数量：{len(session.keyframes)}"
            f"\n分析结果数量：{len(session.frame_analyses)}"
            f"\n视频摘要：{session.video_summary or '无'}"
        )

    async def _run_selected_initial_turn(self, session: CaptionSession, user_prompt: str) -> None:
        targets = self._plan_targets_from_selection(session.selected_plan_ids)
        session.agent_trace = []
        session.execution_events = []
        session.execution_plan = [
            f"{option.title}：{option.description}"
            for option in session.plan_options
            if option.id in set(session.selected_plan_ids)
        ]
        self.store.save(session)
        self._publish_snapshot(session)
        scratchpad = await self._execute_targets(session, user_prompt, targets)
        await self._finalize_turn(
            session,
            user_prompt,
            scratchpad,
            targets,
            completion_message="所选执行项已完成。",
        )

    async def _run_turn(self, session: CaptionSession, user_prompt: str) -> None:
        targets = await self._determine_update_targets(session, user_prompt)
        session.execution_events = []
        if not targets["is_supported_request"]:
            session.execution_plan = [
                "识别当前请求不属于当前会话支持的视频创意产出范围",
                "明确当前会话可处理的能力边界",
                "引导用户提供字幕、剪辑、标题或标签需求",
            ]
            session.messages.append(
                ConversationMessage(
                    role="assistant",
                    content=self._compose_scope_guard_reply(user_prompt, targets),
                )
            )
            session.updated_at = _utcnow()
            self.store.save(session)
            session.status = "completed"
            session.progress_message = "本轮修改完成。"
            session.updated_at = _utcnow()
            self.store.save(session)
            self._publish_snapshot(session, "completed")
            return

        session.agent_trace = []
        session.execution_plan = await self._build_plan(session, user_prompt, targets)
        self.store.save(session)
        self._publish_snapshot(session)
        scratchpad = await self._execute_targets(session, user_prompt, targets)
        await self._finalize_turn(
            session,
            user_prompt,
            scratchpad,
            targets,
            completion_message="本轮修改完成。",
        )

    async def _execute_targets(
        self,
        session: CaptionSession,
        user_prompt: str,
        targets: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        if not any(
            [
                targets["run_keyframe_analysis"],
                targets["update_subtitles"],
                targets["update_editing_plan"],
                targets["update_title"],
                targets["update_tags"],
            ]
        ):
            return []

        registry = self._build_tool_registry(session, user_prompt)
        runtime = PlanAndExecuteRuntime(
            adapter=self._adapter_factory.get_text_adapter(),
            model=settings.deepseek_chat_model,
            tool_registry=registry,
            max_steps=settings.agent_max_steps,
            timeout_seconds=settings.glm_request_timeout_seconds,
        )
        completion_guard = self._build_completion_guard(session, targets)
        fallback_step = self._build_fallback_step(targets)
        should_skip_step = self._build_step_skipper()
        context_prompt = self._build_runtime_context_prompt(session, targets)
        result = await runtime.run(
            user_prompt=user_prompt,
            execution_plan=session.execution_plan,
            context_prompt=context_prompt,
            completion_guard=completion_guard,
            fallback_step=fallback_step,
            should_skip_step=should_skip_step,
            progress=lambda message: self._set_progress(session, "processing", message),
            trace=lambda thought, action, observation: self._append_trace(session, thought, action, observation),
        )
        return result.scratchpad

    def _build_tool_registry(self, session: CaptionSession, user_prompt: str) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            self._build_tool_spec(
                session,
                name="run_keyframe_vision_subagent",
                description="调用关键帧视觉子代理：提取关键帧、逐帧调用多模态大模型分析图片，并汇总视频摘要。",
                title="关键帧视觉子代理",
                run=lambda _input: self._run_keyframe_vision_subagent(session),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                name="read_video_context",
                description="读取视频关键帧分析和视频摘要。",
                title="读取视频上下文",
                run=lambda _input: self._tool_read_video_context(session),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                name="read_manual",
                description="读取产品说明书。",
                title="读取产品说明书",
                run=lambda _input: self._tool_read_manual(session),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                name="read_current_artifacts",
                description="读取当前字幕、剪辑方案、标题和标签。",
                title="读取当前产物",
                run=lambda _input: self._tool_read_current_artifacts(session),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                name="write_subtitles",
                description="生成或更新字幕草稿。",
                title="生成字幕草稿",
                run=lambda action_input: self._tool_write_subtitles(session, user_prompt, action_input),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                name="write_edit_plan",
                description="生成或更新剪辑方案。",
                title="生成剪辑方案",
                run=lambda action_input: self._tool_write_edit_plan(session, user_prompt, action_input),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                name="write_title",
                description="生成或更新英文标题。",
                title="生成英文标题",
                run=lambda action_input: self._tool_write_title(session, user_prompt, action_input),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                name="write_tags",
                description="生成或更新标签。",
                title="生成标签",
                run=lambda action_input: self._tool_write_tags(session, user_prompt, action_input),
            )
        )
        return registry

    def _build_tool_spec(
        self,
        session: CaptionSession,
        *,
        name: str,
        description: str,
        title: str,
        run: Any,
    ) -> ToolSpec:
        async def wrapped(action_input: str) -> str:
            detail = action_input.strip() or "使用默认上下文执行。"
            await self._append_execution_event(
                session,
                "tool_started",
                title,
                detail,
                tool=name,
            )
            observation = await run(action_input)
            await self._append_execution_event(
                session,
                "tool_completed",
                title,
                observation,
                tool=name,
            )
            return observation

        return ToolSpec(name=name, description=description, run=wrapped)

    def _build_runtime_context_prompt(self, session: CaptionSession, targets: Dict[str, Any]) -> str:
        return (
            f"平台：{session.platform}"
            f"\n是否执行关键帧视觉子代理：{targets['run_keyframe_analysis']}"
            f"\n是否更新字幕：{targets['update_subtitles']}"
            f"\n是否更新剪辑方案：{targets['update_editing_plan']}"
            f"\n是否更新英文标题：{targets['update_title']}"
            f"\n是否更新标签：{targets['update_tags']}"
            f"\n视频摘要：{session.video_summary or '无'}"
            f"\n关键帧分析条数：{len(session.frame_analyses)}"
            f"\n当前字幕草稿：{session.subtitle_draft[:1200] if session.subtitle_draft else '无'}"
            f"\n当前剪辑方案：{session.editing_plan[:1200] if session.editing_plan else '无'}"
            f"\n当前英文标题：{session.english_title or '无'}"
            f"\n当前标签：{json.dumps(session.tags, ensure_ascii=False)}"
        )

    def _build_completion_guard(self, session: CaptionSession, targets: Dict[str, Any]):
        def guard(scratchpad: List[Dict[str, str]]) -> bool:
            action_names = {item.get("action") for item in scratchpad}
            keyframe_ready = (not targets["run_keyframe_analysis"]) or ("run_keyframe_vision_subagent" in action_names)
            subtitles_ready = (not targets["update_subtitles"]) or ("write_subtitles" in action_names)
            editing_ready = (not targets["update_editing_plan"]) or ("write_edit_plan" in action_names)
            title_ready = (not targets["update_title"]) or ("write_title" in action_names)
            tags_ready = (not targets["update_tags"]) or ("write_tags" in action_names)
            return keyframe_ready and subtitles_ready and editing_ready and title_ready and tags_ready

        return guard

    def _build_fallback_step(self, targets: Dict[str, Any]):
        def fallback(scratchpad: List[Dict[str, str]]) -> ReActStep:
            action_names = {item.get("action") for item in scratchpad}
            if targets["run_keyframe_analysis"] and "run_keyframe_vision_subagent" not in action_names:
                return ReActStep("需要先完成关键帧视觉分析，建立视频上下文。", "run_keyframe_vision_subagent", "")
            if targets["update_subtitles"] and "write_subtitles" not in action_names:
                return ReActStep("需要先产出字幕。", "write_subtitles", "")
            if targets["update_editing_plan"] and "write_edit_plan" not in action_names:
                return ReActStep("还需要产出剪辑方案。", "write_edit_plan", "")
            if targets["update_title"] and "write_title" not in action_names:
                return ReActStep("还需要产出英文标题。", "write_title", "")
            if targets["update_tags"] and "write_tags" not in action_names:
                return ReActStep("还需要产出标签。", "write_tags", "")
            return ReActStep("本轮结果已经齐备。", "finalize", "")

        return fallback

    def _build_step_skipper(self):
        single_run_actions = {
            "run_keyframe_vision_subagent",
            "write_subtitles",
            "write_edit_plan",
            "write_title",
            "write_tags",
        }

        def should_skip(step: ReActStep, scratchpad: List[Dict[str, str]]) -> bool:
            if step.action not in single_run_actions:
                return False
            return any(item.get("action") == step.action for item in scratchpad)

        return should_skip

    async def _finalize_turn(
        self,
        session: CaptionSession,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        targets: Dict[str, Any],
        completion_message: str,
    ) -> None:
        await self._set_progress(session, "processing", "Agent 正在整理最终回复...")
        if targets["update_subtitles"] and not session.subtitle_draft:
            session.subtitle_draft = await self._generate_subtitle_draft(session, "补全初始字幕草稿。")
        if targets["update_editing_plan"] and not session.editing_plan:
            session.editing_plan = await self._generate_editing_plan(session, "补全初始剪辑方案。")
        if targets["update_title"] and not session.english_title:
            session.english_title = await self._generate_english_title(session, "补全英文标题。")
        if targets["update_tags"] and not session.tags:
            session.tags = await self._generate_tags(session, "补全标签。")
        session.messages.append(
            ConversationMessage(
                role="assistant",
                content=self._build_assistant_reply_fallback(session, targets),
            )
        )
        session.status = "completed"
        session.progress_message = completion_message
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session, "completed")

    async def _append_trace(self, session: CaptionSession, thought: str, action: str, observation: str) -> None:
        session.agent_trace.append(
            AgentTraceItem(
                thought=thought,
                action=action,
                observation=observation,
            )
        )
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session)

    async def _append_execution_event(
        self,
        session: CaptionSession,
        kind: str,
        title: str,
        detail: str,
        *,
        tool: str = "",
        artifact: str = "",
    ) -> None:
        item = ExecutionEventItem(
            kind=kind,
            title=title,
            detail=detail,
            tool=tool,
            artifact=artifact,
        )
        session.execution_events.append(item)
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(session.session_id, "execution_event", {"session_id": session.session_id, **asdict(item)})

    async def _publish_artifact_updated(
        self,
        session: CaptionSession,
        artifact: str,
        value: Any,
        summary: str,
    ) -> None:
        await self._append_execution_event(
            session,
            "artifact_updated",
            f"{artifact} 已更新",
            summary,
            artifact=artifact,
        )
        self.events.publish(
            session.session_id,
            "artifact_updated",
            {
                "session_id": session.session_id,
                "artifact": artifact,
                "value": value,
                "updated_at": session.updated_at,
                "summary": summary,
            },
        )

    async def _publish_artifact_chunk(
        self,
        session: CaptionSession,
        artifact: str,
        content: str,
        delta: str,
    ) -> None:
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(
            session.session_id,
            "artifact_chunk",
            {
                "session_id": session.session_id,
                "artifact": artifact,
                "content": content,
                "delta": delta,
                "updated_at": session.updated_at,
            },
        )

    async def _publish_message_chunk(
        self,
        session: CaptionSession,
        message_index: int,
        content: str,
        delta: str,
    ) -> None:
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(
            session.session_id,
            "message_chunk",
            {
                "session_id": session.session_id,
                "message_index": message_index,
                "content": content,
                "delta": delta,
                "updated_at": session.updated_at,
            },
        )

    async def _stream_artifact_text(
        self,
        session: CaptionSession,
        artifact: str,
        content: str,
        delta: str,
    ) -> None:
        if artifact == "subtitle_draft":
            session.subtitle_draft = content
        elif artifact == "editing_plan":
            session.editing_plan = content
        elif artifact == "english_title":
            session.english_title = content
        elif artifact == "video_summary":
            session.video_summary = content
        await self._publish_artifact_chunk(session, artifact, content, delta)

    async def _fail_session(self, session_id: str, exc: Exception) -> None:
        session = self.store.get(session_id)
        session.status = "error"
        session.error_message = str(exc)
        session.progress_message = "处理失败。"
        session.updated_at = _utcnow()
        self.store.save(session)
        self._publish_snapshot(session, "error")
        self._ensure_completion_event(session_id).set()

    async def _set_progress(self, session: CaptionSession, status: str, message: str) -> None:
        session.status = status
        session.progress_message = message
        session.error_message = ""
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(
            session.session_id,
            "progress",
            {
                "session_id": session.session_id,
                "status": status,
                "message": message,
                "updated_at": session.updated_at,
            },
        )

    def _publish_snapshot(self, session: CaptionSession, event: str = "snapshot") -> None:
        self.events.publish(session.session_id, event, self._serialize(session))

    async def _text_complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        require_json: bool = False,
        temperature: float = 0.2,
    ) -> str:
        messages: List[AIMessage] = []
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))
        messages.append(AIMessage(role="user", content=prompt))
        response = await self._adapter_factory.get_text_adapter().complete(
            AICompletionRequest(
                model=settings.deepseek_chat_model,
                messages=messages,
                temperature=temperature,
                timeout_seconds=settings.glm_request_timeout_seconds,
                require_json=require_json,
            )
        )
        return response.content

    async def _text_stream_complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        trace_label: str,
        on_delta: Any | None = None,
    ) -> str:
        messages: List[AIMessage] = []
        if system_prompt:
            messages.append(AIMessage(role="system", content=system_prompt))
        messages.append(AIMessage(role="user", content=prompt))
        content = ""
        pending_delta = ""
        last_emit_at = time.monotonic()
        min_emit_interval_seconds = 0.15
        min_emit_chars = 120
        async for delta in self._adapter_factory.get_text_adapter().stream(
            AICompletionRequest(
                model=settings.deepseek_chat_model,
                messages=messages,
                temperature=temperature,
                timeout_seconds=settings.glm_request_timeout_seconds,
                metadata={"trace_label": trace_label},
            )
        ):
            if not delta:
                continue
            content += delta
            pending_delta += delta
            if on_delta is not None:
                now = time.monotonic()
                if (
                    now - last_emit_at >= min_emit_interval_seconds
                    or len(pending_delta) >= min_emit_chars
                ):
                    await on_delta(content, pending_delta)
                    pending_delta = ""
                    last_emit_at = now
        if on_delta is not None and pending_delta:
            await on_delta(content, pending_delta)
        return content.strip()

    async def _vision_complete(self, prompt: str, frame_base64: str, *, trace_label: str | None = None) -> str:
        response = await self._adapter_factory.get_vision_adapter().complete(
            AICompletionRequest(
                model=settings.multimodal_model or settings.glm_vision_model,
                messages=[
                    AIMessage(
                        role="user",
                        content=prompt,
                        images=[AIImageInput(media_type="image/jpeg", data_base64=frame_base64)],
                    )
                ],
                timeout_seconds=settings.glm_request_timeout_seconds,
                metadata={"trace_label": trace_label or "vision_request"},
            )
        )
        return response.content

    async def _build_initial_plan_options(
        self,
        session: CaptionSession,
        user_prompt: str,
    ) -> List[ExecutionPlanOption]:
        prompt = (
            "你是短视频创作规划器。标准执行项固定为："
            "keyframe_analysis、subtitle_draft、editing_plan、english_title、tags。"
            "\n请只为这些标准项补充描述，并给出 selected 建议。"
            "\nkeyframe_analysis 必须 required=true 且 selected=true。"
            "\n只返回 JSON，格式为 "
            '{"options":[{"id":"subtitle_draft","title":"字幕生成","description":"...","selected":true}]}'
            f"\n\n平台：{session.platform}"
            f"\n说明书：{session.product_manual or '无'}"
            f"\n用户需求：{user_prompt}"
        )
        raw = await self._text_complete(prompt, require_json=True)
        parsed = self._parse_json_object(raw)
        return self._coerce_plan_options(parsed.get("options") if isinstance(parsed, dict) else None)

    def _coerce_plan_options(self, raw_options: Any) -> List[ExecutionPlanOption]:
        allowed = {
            "keyframe_analysis": ("关键帧分析", "提取关键帧并做多模态分析，沉淀视频结构与卖点上下文。", True),
            "subtitle_draft": ("字幕生成", "基于关键帧理解和平台语气生成字幕初稿。", False),
            "editing_plan": ("剪辑脚本生成", "输出镜头级剪辑脚本，包含 hook、节奏推进和 CTA。", False),
            "english_title": ("英文标题生成", "为投放素材或成片生成英文标题。", False),
            "tags": ("标签生成", "生成适合平台分发和投放的英文标签。", False),
        }
        options_by_id: Dict[str, ExecutionPlanOption] = {}
        if isinstance(raw_options, list):
            for item in raw_options:
                if not isinstance(item, dict):
                    continue
                option_id = str(item.get("id", "")).strip()
                if option_id not in allowed:
                    continue
                default_title, default_description, default_required = allowed[option_id]
                options_by_id[option_id] = ExecutionPlanOption(
                    id=option_id,
                    title=str(item.get("title") or default_title).strip() or default_title,
                    description=str(item.get("description") or default_description).strip() or default_description,
                    required=default_required or bool(item.get("required")),
                    selected=default_required or bool(item.get("selected")),
                )

        normalized: List[ExecutionPlanOption] = []
        for option_id in ["keyframe_analysis", "subtitle_draft", "editing_plan", "english_title", "tags"]:
            if option_id in options_by_id:
                option = options_by_id[option_id]
                if option_id == "keyframe_analysis":
                    option.required = True
                    option.selected = True
                normalized.append(option)
                continue
            title, description, required = allowed[option_id]
            normalized.append(
                ExecutionPlanOption(
                    id=option_id,
                    title=title,
                    description=description,
                    required=required,
                    selected=required,
                )
            )
        return normalized

    def _plan_targets_from_selection(self, selected_plan_ids: List[str]) -> Dict[str, Any]:
        selected = set(selected_plan_ids)
        return {
            "run_keyframe_analysis": "keyframe_analysis" in selected,
            "update_subtitles": "subtitle_draft" in selected,
            "update_editing_plan": "editing_plan" in selected,
            "update_title": "english_title" in selected,
            "update_tags": "tags" in selected,
            "is_supported_request": True,
            "reason": "根据用户勾选的 Agent 执行项执行。",
        }

    async def _analyze_video_frames(self, session: CaptionSession) -> List[str]:
        analysis_frames = select_keyframes_for_analysis(session.keyframes, max_frames=settings.max_keyframes)
        analyses: List[str] = []
        total = len(analysis_frames)
        for index, keyframe in enumerate(analysis_frames, start=1):
            await self._set_progress(session, "processing", f"正在准备分析关键帧 {index}/{max(total, 1)}...")
            await self._set_progress(
                session,
                "processing",
                f"正在发送关键帧 {index}/{max(total, 1)} 到 {settings.multimodal_model or settings.glm_vision_model}...",
            )
            analysis = await self._analyze_single_frame(index, str(keyframe.get("image_base64", "")))
            timestamp = keyframe.get("timestamp_seconds")
            source = keyframe.get("source", "unknown")
            analyses.append(f"关键帧{index}（{timestamp}s, 来源: {source}）: {analysis}")
            session.frame_analyses = analyses.copy()
            session.updated_at = _utcnow()
            self.store.save(session)
            await self._append_execution_event(
                session,
                "artifact_updated",
                f"关键帧 {index} 理解完成",
                analyses[-1],
                artifact="frame_analyses",
            )
            self.events.publish(
                session.session_id,
                "artifact_updated",
                {
                    "session_id": session.session_id,
                    "artifact": "frame_analyses",
                    "value": session.frame_analyses,
                    "updated_at": session.updated_at,
                    "summary": f"关键帧 {index}/{max(total, 1)} 分析完成。",
                },
            )
            self._publish_snapshot(session)
        return analyses

    async def _analyze_single_frame(self, frame_index: int, frame_base64: str) -> str:
        prompt = (
            f"你正在分析短视频的第{frame_index}个关键帧。"
            "请把图像内容转成后续可供文案与剪辑模型消费的中文文本。"
            "\n请严格覆盖这些维度："
            "\n1. 画面主体、场景、拍摄景别与构图"
            "\n2. 产品出现方式、人物动作、使用步骤或演示细节"
            "\n3. 能识别到的字幕、贴纸、包装、品牌、价格、参数、口播线索"
            "\n4. 这一帧对短视频结构的作用：开场钩子 / 痛点引入 / 卖点展示 / 证明背书 / CTA / 转场"
            "\n5. 对字幕生成和剪辑节奏有帮助的补充判断"
            "\n输出要求：只输出简洁中文文本，不要 JSON，不要坐标，不要解释推理过程。"
        )
        return await self._vision_complete(prompt, frame_base64, trace_label=f"keyframe_{frame_index}")

    async def _summarize_video(self, session: CaptionSession) -> str:
        prompt = (
            "你是视频理解助手。请根据关键帧分析和说明书，总结视频的核心内容、产品卖点、"
            "适合的人群、镜头节奏，以及适合做字幕和剪辑决策的信息。"
            f"\n\n平台：{session.platform}"
            f"\n\n说明书：\n{session.product_manual or '无说明书'}"
            f"\n\n关键帧分析：\n" + "\n".join(session.frame_analyses)
        )
        return await self._text_stream_complete(
            prompt,
            system_prompt="请输出结构化但简洁的中文摘要。",
            trace_label="video_summary",
            on_delta=lambda content, delta: self._stream_artifact_text(session, "video_summary", content, delta),
        )

    async def _determine_update_targets(self, session: CaptionSession, user_prompt: str) -> Dict[str, Any]:
        prompt = (
            "你是短视频制作任务分流器。请判断用户本轮需求需要更新哪些产物。"
            "\n产物只有四个：subtitle_draft、editing_plan、english_title、tags。"
            "\n只返回 JSON，格式为 "
            '{"update_subtitles":true,"update_editing_plan":false,"update_title":false,"update_tags":false,"is_supported_request":true,"reason":"..."}'
            f"\n\n用户需求：{user_prompt}"
            f"\n当前字幕草稿：{session.subtitle_draft[:800] if session.subtitle_draft else '无'}"
            f"\n当前剪辑方案：{session.editing_plan[:800] if session.editing_plan else '无'}"
            f"\n当前英文标题：{session.english_title or '无'}"
            f"\n当前标签：{json.dumps(session.tags, ensure_ascii=False)}"
        )
        raw = await self._text_complete(prompt, require_json=True)
        parsed = self._parse_json_object(raw)
        if isinstance(parsed, dict) and parsed.get("is_supported_request") is not None:
            return {
                "run_keyframe_analysis": False,
                "update_subtitles": bool(parsed.get("update_subtitles")),
                "update_editing_plan": bool(parsed.get("update_editing_plan")),
                "update_title": bool(parsed.get("update_title")),
                "update_tags": bool(parsed.get("update_tags")),
                "is_supported_request": bool(parsed.get("is_supported_request")),
                "reason": str(parsed.get("reason", "")).strip() or "根据用户需求自动判断。",
            }

        normalized_prompt = user_prompt.lower()
        subtitle_keywords = ["字幕", "文案", "口播", "翻译", "台词", "语气", "中文"]
        editing_keywords = ["剪辑", "镜头", "转场", "节奏", "分镜", "时长", "结构", "hook", "钩子", "cta"]
        title_keywords = ["英文标题", "headline", "title", "英文题目"]
        tag_keywords = ["tag", "tags", "标签", "hashtags", "hashtag", "话题"]
        unsupported_keywords = [
            "agent",
            "前端",
            "frontend",
            "ui",
            "页面",
            "界面",
            "bug",
            "历史记录",
            "header",
            "sidebar",
            "工作区",
        ]
        update_subtitles = any(keyword in normalized_prompt for keyword in subtitle_keywords)
        update_editing_plan = any(keyword in normalized_prompt for keyword in editing_keywords)
        update_title = any(keyword in normalized_prompt for keyword in title_keywords)
        update_tags = any(keyword in normalized_prompt for keyword in tag_keywords)
        is_unsupported_request = (
            any(keyword in normalized_prompt for keyword in unsupported_keywords)
            and not update_subtitles
            and not update_editing_plan
            and not update_title
            and not update_tags
        )
        if is_unsupported_request:
            return {
                "run_keyframe_analysis": False,
                "update_subtitles": False,
                "update_editing_plan": False,
                "update_title": False,
                "update_tags": False,
                "is_supported_request": False,
                "reason": "当前输入更像系统、产品或界面需求，不属于字幕或剪辑修改指令。",
            }
        if not update_subtitles and not update_editing_plan and not update_title and not update_tags:
            update_subtitles = True
            update_editing_plan = True
        return {
            "run_keyframe_analysis": False,
            "update_subtitles": update_subtitles,
            "update_editing_plan": update_editing_plan,
            "update_title": update_title,
            "update_tags": update_tags,
            "is_supported_request": True,
            "reason": "基于关键词回退判断本轮需要更新的产物。",
        }

    async def _build_plan(self, session: CaptionSession, user_prompt: str, targets: Dict[str, Any]) -> List[str]:
        prompt = (
            "你是视频制作任务规划器。请根据用户需求、当前视频理解和已有产出，给出本轮最合理的 3 到 5 个执行步骤。"
            '\n只返回 JSON，格式为 {"goal":"...","steps":["...","..."]}。'
            f"\n\n用户需求：{user_prompt}"
            f"\n本轮更新范围：{json.dumps(targets, ensure_ascii=False)}"
            f"\n视频摘要：{session.video_summary}"
            f"\n当前字幕草稿：{session.subtitle_draft or '无'}"
            f"\n当前剪辑方案：{session.editing_plan or '无'}"
        )
        raw = await self._text_complete(prompt, require_json=True)
        parsed = self._parse_json_object(raw)
        steps = parsed.get("steps") if isinstance(parsed, dict) else None
        if isinstance(steps, list) and steps:
            return [str(step).strip() for step in steps[:5] if str(step).strip()]
        fallback_steps = ["理解用户本轮修改目标", "读取视频与说明书上下文"]
        if targets["update_subtitles"]:
            fallback_steps.append("更新字幕草稿")
        if targets["update_editing_plan"]:
            fallback_steps.append("更新剪辑执行方案")
        if targets["update_title"]:
            fallback_steps.append("生成或更新英文标题")
        if targets["update_tags"]:
            fallback_steps.append("生成或更新标签")
        fallback_steps.append("整理最终结果并直接回复用户")
        return fallback_steps

    async def _tool_read_video_context(self, session: CaptionSession, *_args: Any) -> str:
        return f"视频摘要：{session.video_summary}\n关键帧分析：\n" + "\n".join(session.frame_analyses)

    async def _tool_read_manual(self, session: CaptionSession, *_args: Any) -> str:
        return session.product_manual or "用户未提供说明书。"

    async def _tool_read_current_artifacts(self, session: CaptionSession, *_args: Any) -> str:
        return (
            f"当前字幕草稿：\n{session.subtitle_draft or '暂无'}\n\n"
            f"当前剪辑方案：\n{session.editing_plan or '暂无'}\n\n"
            f"当前英文标题：\n{session.english_title or '暂无'}\n\n"
            f"当前标签：\n{', '.join(session.tags) if session.tags else '暂无'}"
        )

    async def _tool_write_subtitles(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        session.subtitle_draft = await self._generate_subtitle_draft(session, action_input or user_prompt)
        session.updated_at = _utcnow()
        self.store.save(session)
        await self._publish_artifact_updated(session, "subtitle_draft", session.subtitle_draft, "字幕草稿已更新。")
        self._publish_snapshot(session)
        return "字幕草稿已更新。"

    async def _tool_write_edit_plan(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        session.editing_plan = await self._generate_editing_plan(session, action_input or user_prompt)
        session.updated_at = _utcnow()
        self.store.save(session)
        await self._publish_artifact_updated(session, "editing_plan", session.editing_plan, "剪辑执行方案已更新。")
        self._publish_snapshot(session)
        return "剪辑执行方案已更新。"

    async def _tool_write_title(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        session.english_title = await self._generate_english_title(session, action_input or user_prompt)
        session.updated_at = _utcnow()
        self.store.save(session)
        await self._publish_artifact_updated(session, "english_title", session.english_title, "英文标题已更新。")
        self._publish_snapshot(session)
        return "英文标题已更新。"

    async def _tool_write_tags(self, session: CaptionSession, user_prompt: str, action_input: str) -> str:
        session.tags = await self._generate_tags(session, action_input or user_prompt)
        session.updated_at = _utcnow()
        self.store.save(session)
        await self._publish_artifact_updated(session, "tags", session.tags, "标签已更新。")
        self._publish_snapshot(session)
        return "标签已更新。"

    async def _generate_subtitle_draft(self, session: CaptionSession, guidance: str) -> str:
        prompt = (
            "你是资深短视频字幕导演。请根据以下信息生成或修改字幕草稿。"
            "\n要求："
            "\n1. 输出中文"
            "\n2. 尽量按时间轴分段，格式示例：00:00-00:03 字幕内容"
            "\n3. 体现产品卖点、镜头节奏和平台语气"
            "\n4. 如果用户要求修改，请在当前草稿基础上改写而不是完全忽略历史版本"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前字幕草稿：\n{session.subtitle_draft or '无'}"
        )
        return await self._text_stream_complete(
            prompt,
            trace_label="subtitle_draft",
            on_delta=lambda content, delta: self._stream_artifact_text(session, "subtitle_draft", content, delta),
        )

    async def _generate_editing_plan(self, session: CaptionSession, guidance: str) -> str:
        prompt = (
            "你是短视频剪辑导演。请根据视频摘要、关键帧和用户需求输出一个可执行的剪辑方案。"
            "\n要求："
            "\n1. 按镜头或时间段列出"
            "\n2. 明确镜头目标、转场、字幕配合、B-roll 或特写建议"
            "\n3. 包含开场 hook、卖点推进、收尾 CTA"
            "\n4. 如果用户要求修改，请在当前方案上迭代"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前剪辑方案：\n{session.editing_plan or '无'}"
            + f"\n\n当前字幕草稿：\n{session.subtitle_draft or '无'}"
        )
        return await self._text_stream_complete(
            prompt,
            trace_label="editing_plan",
            on_delta=lambda content, delta: self._stream_artifact_text(session, "editing_plan", content, delta),
        )

    async def _generate_english_title(self, session: CaptionSession, guidance: str) -> str:
        prompt = (
            "你是短视频投放创意策划。请生成或修改一个英文标题。"
            "\n要求："
            "\n1. 输出 1 条最优英文标题"
            "\n2. 适合短视频投放或素材命名"
            "\n3. 不要加引号，不要解释"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前英文标题：\n{session.english_title or '无'}"
        )
        return (
            await self._text_stream_complete(
                prompt,
                trace_label="english_title",
                on_delta=lambda content, delta: self._stream_artifact_text(session, "english_title", content, delta),
            )
        ).strip()

    async def _generate_tags(self, session: CaptionSession, guidance: str) -> List[str]:
        prompt = (
            "你是短视频投放创意策划。请生成或修改一组标签。"
            '\n要求：\n1. 输出 JSON，格式为 {"tags":["tag1","tag2"]}'
            "\n2. 生成 5 到 8 个英文标签"
            "\n3. 不要带 #"
            f"\n\n用户需求：{guidance}"
            f"\n平台：{session.platform}"
            f"\n说明书：\n{session.product_manual or '无'}"
            f"\n视频摘要：\n{session.video_summary}"
            f"\n关键帧分析：\n" + "\n".join(session.frame_analyses)
            + f"\n\n当前标签：\n{', '.join(session.tags) if session.tags else '无'}"
        )
        parsed = self._parse_json_object(await self._text_complete(prompt, require_json=True))
        tags = parsed.get("tags") if isinstance(parsed, dict) else None
        if isinstance(tags, list) and tags:
            return [str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()][:8]
        return []

    async def _compose_assistant_reply(
        self,
        session: CaptionSession,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        targets: Dict[str, Any],
    ) -> str:
        prompt = (
            "你是一个视频创意对话助手。请直接把本轮可交付结果回复给用户，而不是只做项目总结。"
            "\n要求："
            "\n1. 根据用户需求，判断应该展示关键帧分析摘要、字幕草稿、剪辑方案，或其中任意组合。"
            "\n2. 如果本轮只改了字幕，就重点给出更新后的字幕。"
            "\n3. 如果本轮只改了剪辑方案，就重点给出更新后的剪辑方案。"
            "\n4. 如果本轮生成了英文标题，就直接给出英文标题。"
            "\n5. 如果本轮生成了标签，就直接给出标签列表。"
            "\n6. 如果本轮只执行了关键帧分析，没有生成字幕或剪辑方案，就给出视频摘要和关键帧洞察。"
            "\n7. 如果多个产物都改了，按产物分段给出。"
            f"\n\n用户需求：{user_prompt}"
            f"\n本轮更新范围：{json.dumps(targets, ensure_ascii=False)}"
            f"\n执行计划：{json.dumps(session.execution_plan, ensure_ascii=False)}"
            f"\n工具执行记录：{json.dumps(scratchpad, ensure_ascii=False)}"
            f"\n视频摘要：{session.video_summary or '无'}"
            f"\n关键帧分析：{json.dumps(session.frame_analyses[:12], ensure_ascii=False)}"
            f"\n最新字幕草稿全文：{session.subtitle_draft[:6000] if session.subtitle_draft else '无'}"
            f"\n最新剪辑方案全文：{session.editing_plan[:6000] if session.editing_plan else '无'}"
            f"\n最新英文标题：{session.english_title or '无'}"
            f"\n最新标签：{json.dumps(session.tags, ensure_ascii=False)}"
        )
        message_index = max(len(session.messages) - 1, 0)
        return await self._text_stream_complete(
            prompt,
            trace_label="assistant_reply",
            on_delta=lambda content, delta: self._stream_assistant_reply(session, message_index, content, delta),
        )

    async def _stream_assistant_reply(
        self,
        session: CaptionSession,
        message_index: int,
        content: str,
        delta: str,
    ) -> None:
        if 0 <= message_index < len(session.messages):
            session.messages[message_index].content = content
        await self._publish_message_chunk(session, message_index, content, delta)

    def _compose_scope_guard_reply(self, user_prompt: str, targets: Dict[str, Any]) -> str:
        return (
            "这条需求没有落在当前视频创意会话的可执行范围内。"
            "\n\n当前会话支持的交付有："
            "\n1. 字幕草稿修改"
            "\n2. 剪辑方案修改"
            "\n3. 英文标题"
            "\n4. 标签"
            f"\n\n本轮识别结果：{targets['reason']}"
            f"\n\n你的原始输入：{user_prompt}"
            "\n\n如果你要继续这个视频任务，请直接告诉我："
            "\n- 想怎么改字幕"
            "\n- 想怎么改镜头/节奏/时长/转场"
            "\n- 想要什么风格的英文标题"
            "\n- 想要什么方向的标签"
        )

    def _build_assistant_reply_fallback(
        self,
        session: CaptionSession,
        targets: Dict[str, Any],
    ) -> str:
        sections: List[str] = []
        if targets.get("run_keyframe_analysis") and session.video_summary:
            sections.append(f"视频摘要：\n{session.video_summary.strip()}")
        if targets.get("update_subtitles") and session.subtitle_draft:
            sections.append(f"字幕草稿：\n{session.subtitle_draft.strip()}")
        if targets.get("update_editing_plan") and session.editing_plan:
            sections.append(f"剪辑方案：\n{session.editing_plan.strip()}")
        if targets.get("update_title") and session.english_title:
            sections.append(f"英文标题：\n{session.english_title.strip()}")
        if targets.get("update_tags") and session.tags:
            sections.append("标签：\n" + "\n".join(f"- {tag}" for tag in session.tags if str(tag).strip()))

        if sections:
            return "\n\n".join(sections)

        if session.video_summary:
            return f"视频摘要：\n{session.video_summary.strip()}"
        if session.subtitle_draft:
            return f"字幕草稿：\n{session.subtitle_draft.strip()}"
        if session.editing_plan:
            return f"剪辑方案：\n{session.editing_plan.strip()}"
        if session.english_title:
            return f"英文标题：\n{session.english_title.strip()}"
        if session.tags:
            return "标签：\n" + "\n".join(f"- {tag}" for tag in session.tags if str(tag).strip())
        return "本轮产物已生成完成。"

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

    def _serialize(self, session: CaptionSession) -> Dict[str, Any]:
        return {
            "session_id": session.session_id,
            "platform": session.platform,
            "keyframes": session.keyframes,
            "video_summary": session.video_summary,
            "frame_analyses": session.frame_analyses,
            "execution_plan": session.execution_plan,
            "plan_options": [asdict(option) for option in session.plan_options],
            "selected_plan_ids": session.selected_plan_ids,
            "agent_trace": [asdict(item) for item in session.agent_trace],
            "execution_events": [asdict(item) for item in session.execution_events],
            "subtitle_draft": session.subtitle_draft,
            "editing_plan": session.editing_plan,
            "english_title": session.english_title,
            "tags": session.tags,
            "messages": [asdict(message) for message in session.messages],
            "status": session.status,
            "progress_message": session.progress_message,
            "error_message": session.error_message,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
