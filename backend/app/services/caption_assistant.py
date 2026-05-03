from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import shlex
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from app.agent.runtime import PlanAndExecuteRuntime, ReActStep, ToolRegistry, ToolSpec
from app.ai.factory import AIAdapterFactory
from app.ai.types import AICompletionRequest, AIImageInput, AIMessage
from app.core.config import settings
from app.core.utils import extract_keyframes, select_keyframes_for_analysis

CAPTION_ASSISTANT_SYSTEM_PROMPT = """你是一个短视频创意与剪辑执行助手。
你的职责是围绕单个视频会话，生成可执行、可复用、可继续迭代的结果。

全局原则：
1. 优先输出可直接交付的结果，不输出空泛分析。
2. 严格区分“已有信息”和“推断建议”，不要编造视频中不存在的强事实。
3. 若用户要求局部修改，只改相关部分，尽量继承已有有效内容。
4. 输出必须贴合短视频场景，强调 hook、卖点推进、证据、CTA、节奏与转化。
5. 如果上下文已经足够，不要重复请求同类信息。
"""

VIDEO_SUMMARY_SYSTEM_PROMPT = "请输出结构化、简洁、可供后续字幕与剪辑生成直接消费的中文摘要。"

SUBTITLE_GENERATION_PROMPT = """任务：生成或修改短视频字幕草稿。

角色：
你是资深短视频字幕导演与广告文案编辑。

目标：
基于视频理解、产品信息和本轮要求，产出一版可以直接进入人工审校的字幕草稿。

工作原则：
1. 先理解视频结构，再按镜头节奏写字幕，不要堆叠卖点。
2. 字幕要服务转化，优先突出痛点、解决方案、证据、利益点、行动引导。
3. 若用户要求修改，必须在当前草稿上定向迭代，不要无故推翻已有有效内容。
4. 若视频上下文不足，可结合说明书补足，但不要编造未出现的强事实。

输出要求：
1. 输出中文。
2. 优先按时间轴分段，格式示例：00:00-00:03 字幕内容。
3. 每段字幕尽量短促、易读、适合口播或画面停留时长。
4. 语言风格贴合短视频平台，避免书面腔和冗长表达。
5. 只输出最终字幕草稿正文，不要解释，不要 JSON。
"""

EDIT_PLAN_GENERATION_PROMPT = """任务：生成或修改短视频剪辑方案。

角色：
你是短视频剪辑导演、广告创意总监和后期执行统筹。

目标：
基于视频摘要、关键帧、产品说明与当前字幕，输出一版可以直接交给剪辑师执行的剪辑方案。

工作原则：
1. 方案必须可执行，而不是抽象口号。
2. 体现短视频转化逻辑：开场 hook、痛点/场景、卖点展开、证明、CTA。
3. 若用户要求局部调整，只修改相关段落，并继承当前方案中仍然合理的部分。
4. 如果用户明确提到 ffmpeg、裁切、拼接、压缩、字幕烧录、尺寸适配、平台导出等技术执行，请先结合技能信息，再给出可操作建议。

输出要求：
1. 按镜头或时间段列出，便于直接执行。
2. 每段至少说明：镜头目标、画面内容、字幕策略、节奏或转场建议。
3. 如有必要，补充 B-roll、特写、音效、音乐、速度变化建议。
4. 若存在明确后期技术动作，可写出简洁执行提示。
5. 只输出最终剪辑方案正文，不要解释，不要 JSON。
"""

TITLE_GENERATION_PROMPT = """任务：生成或修改英文标题。

角色：
你是短视频投放创意策划。

输出要求：
1. 只输出 1 条最优英文标题。
2. 标题要抓核心卖点、场景或结果，避免空泛。
3. 长度尽量精炼，便于广告团队快速识别创意方向。
4. 不要引号，不要解释，不要多个候选。
"""

TAGS_GENERATION_PROMPT = """任务：生成或修改标签。

角色：
你是短视频投放创意策划。

输出要求：
1. 只输出 JSON，格式为 {"tags":["tag1","tag2"]}。
2. 生成 5 到 8 个英文标签。
3. 标签覆盖产品、场景、卖点、创意角度或视频形态。
4. 不要带 #，不要输出解释。
"""

ASSISTANT_REPLY_PROMPT = """任务：整理本轮最终回复。

角色：
你是面向业务用户的视频创意执行助手。

目标：
把本轮已经完成的可交付结果直接回复给用户，而不是只汇报过程。

输出规则：
1. 以用户拿到就能继续工作的结果为中心。
2. 优先展示本轮真正更新过的内容。
3. 如果只改了字幕，就直接给出字幕草稿。
4. 如果只改了剪辑方案，就直接给出剪辑方案。
5. 如果同时更新了多个产物，按“字幕草稿 / 剪辑方案 / 英文标题 / 标签 / 视频摘要洞察”分段输出。
6. 如果只做了关键帧分析，没有产出字幕或剪辑方案，就给出视频摘要和关键帧洞察。
7. 默认输出中文；英文标题与英文标签保持英文原文。
8. 不要重复工具日志，不要说“我已经帮你”，不要虚构未完成内容。
9. 如果本轮成功导出了视频，明确告知视频已可导出下载，并简要说明导出结果。
10. 如果本轮导出视频失败，要明确说明失败原因，并提示用户当前还没有可下载成片。
"""

PLAN_PROPOSAL_PROMPT = """任务：把用户需求映射到本系统支持的执行项。

标准执行项固定为：
- keyframe_analysis
- subtitle_draft
- editing_plan
- english_title
- tags
- edited_video

规划原则：
1. 只选择本轮真正需要更新的执行项，避免默认把所有产物都重做。
2. 若用户要求重新分析素材、重新理解视频、重新看关键帧，必须包含 keyframe_analysis。
3. 若用户表达为“剪辑视频”“重剪”“重新剪一版”“做完整剪辑”“出成片方案”，默认包含 subtitle_draft、editing_plan、english_title、tags；若当前没有视频上下文，额外包含 keyframe_analysis。
4. 若用户只改字幕文案、语气、长度、节奏、错字、语言表达，只保留 subtitle_draft。
5. 若用户只改镜头、转场、节奏、时长、结构、开场 hook、CTA，只保留 editing_plan；若同时要求重看素材，再加入 keyframe_analysis。
6. 若用户明确要求标题或标签，只补充对应字段，不要顺带重做其他产物。
7. 若用户提到 ffmpeg、压制、裁剪、拼接、硬字幕、导出尺寸、码率等技术执行，优先归入 editing_plan；是否需要 keyframe_analysis 取决于是否要重新理解素材。
8. 若用户明确要求导出视频、输出成片、渲染视频、执行剪辑、生成可下载成片，必须包含 edited_video。
9. 如果请求不属于当前视频创意会话能力，is_supported_request=false，并在 reason 中明确说明边界。

输出要求：
1. 只返回 JSON。
2. summary 要简洁概括用户本轮目标。
3. steps 要写成可执行步骤，而不是空泛描述。
4. JSON 格式必须是 {"summary":"...","steps":["..."],"selected_ids":["editing_plan"],"is_supported_request":true,"reason":"...","requests_full_editing":false,"force_keyframe_refresh":false}
"""


def _prompt_block(title: str, content: str) -> str:
    return f"\n[{title}]\n{content}"


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="microseconds") + "Z"


@dataclass
class WorkflowArtifactState:
    label: str
    status: str = "idle"
    detail: str = ""
    requested: bool = False
    needs_refresh: bool = False
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class EditingWorkflowState:
    keyframe_analysis: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="关键帧分析")
    )
    video_summary: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="视频摘要")
    )
    subtitle_draft: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="字幕草稿")
    )
    editing_plan: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="剪辑方案")
    )
    english_title: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="英文标题")
    )
    tags: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="标签")
    )
    edited_video: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="导出视频")
    )


@dataclass
class EditedVideoArtifact:
    file_name: str = ""
    download_url: str = ""
    storage_path: str = ""
    command: str = ""
    summary: str = ""
    error_message: str = ""
    size_bytes: int = 0
    created_at: str = field(default_factory=_utcnow)


@dataclass
class GlobalEditingState:
    request_summary: str = ""
    keyframes: List[Dict[str, Any]] = field(default_factory=list)
    frame_analyses: List[str] = field(default_factory=list)
    video_summary: str = ""
    subtitle_draft: str = ""
    editing_plan: str = ""
    english_title: str = ""
    tags: List[str] = field(default_factory=list)
    edited_video: EditedVideoArtifact = field(default_factory=EditedVideoArtifact)
    workflow: EditingWorkflowState = field(default_factory=EditingWorkflowState)
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class TurnEventItem:
    type: str
    content: str = ""
    tool_name: str = ""
    arguments: str = ""
    created_at: str = field(default_factory=_utcnow)


@dataclass
class AgentTurn:
    turn_id: str
    user_prompt: str
    status: str = "running"
    events: List[TurnEventItem] = field(default_factory=list)
    final_text: str = ""
    error_message: str = ""
    started_at: str = field(default_factory=_utcnow)
    finished_at: str = ""


@dataclass
class CaptionSession:
    session_id: str
    video_path: str
    platform: str
    product_manual: str
    turns: List[AgentTurn] = field(default_factory=list)
    global_editing_state: GlobalEditingState = field(default_factory=GlobalEditingState)
    status: str = "idle"
    active_turn_id: str = ""
    error_message: str = ""
    version: int = 0
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


class CaptionSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, CaptionSession] = {}
        self._lock = Lock()

    def save(self, session: CaptionSession) -> None:
        with self._lock:
            session.version += 1
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
        self._ffmpeg_skill_path = Path(__file__).resolve().parents[3] / "skills" / "ffmpeg-usage" / "SKILL.md"
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
        turn = AgentTurn(turn_id=str(uuid4()), user_prompt=user_prompt)
        session = CaptionSession(
            session_id=str(uuid4()),
            video_path=video_path,
            platform=platform,
            product_manual=product_manual or "",
            turns=[turn],
            status="processing",
            active_turn_id=turn.turn_id,
        )
        session.global_editing_state.request_summary = user_prompt.strip()
        session.updated_at = _utcnow()
        self.store.save(session)
        self._ensure_session_primitives(session.session_id)
        self._reset_completion_event(session.session_id)
        asyncio.create_task(
            self._run_turn(session.session_id, turn.turn_id, user_prompt)
        )
        return self._serialize(session)

    async def continue_session(self, session_id: str, user_prompt: str) -> Dict[str, Any]:
        session = self.store.get(session_id)
        if session.status == "processing":
            raise ValueError("session is still processing")

        turn = AgentTurn(turn_id=str(uuid4()), user_prompt=user_prompt)
        session.turns.append(turn)
        session.status = "processing"
        session.active_turn_id = turn.turn_id
        session.error_message = ""
        session.updated_at = _utcnow()
        self.store.save(session)
        self._ensure_session_primitives(session_id)
        self._reset_completion_event(session_id)
        asyncio.create_task(self._run_turn(session_id, turn.turn_id, user_prompt))
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
            yield {"event": "snapshot", "data": self._serialize(session)}
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield message
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": {"session_id": session_id, "ts": _utcnow()}}
        finally:
            self.events.unsubscribe(session_id, queue)

    def _ensure_session_primitives(self, session_id: str) -> None:
        with self._meta_lock:
            self._session_locks.setdefault(session_id, asyncio.Lock())
            self._completion_events.setdefault(session_id, asyncio.Event())

    def _reset_completion_event(self, session_id: str) -> None:
        with self._meta_lock:
            self._completion_events[session_id] = asyncio.Event()

    def _ensure_completion_event(self, session_id: str) -> asyncio.Event:
        with self._meta_lock:
            return self._completion_events.setdefault(session_id, asyncio.Event())

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        with self._meta_lock:
            return self._session_locks.setdefault(session_id, asyncio.Lock())

    async def _run_turn(self, session_id: str, turn_id: str, user_prompt: str) -> None:
        async with self._get_session_lock(session_id):
            try:
                session = self.store.get(session_id)
                turn = self._get_turn(session, turn_id)
                working_state = copy.deepcopy(session.global_editing_state)
                working_state.request_summary = user_prompt.strip()
                working_state.updated_at = _utcnow()

                plan_payload = await self._build_plan_proposal(session, working_state, user_prompt)
                if not plan_payload.get("is_supported_request", True):
                    await self._commit_completed_turn(
                        session=session,
                        turn=turn,
                        working_state=working_state,
                        final_text=self._compose_scope_guard_reply(user_prompt, plan_payload),
                    )
                    return

                targets = self._plan_targets_from_selection(
                    plan_payload.get("selected_ids") or [],
                    plan_payload,
                )
                self._mark_selected_items_in_progress(working_state, targets)
                scratchpad = await self._execute_targets(
                    session=session,
                    turn=turn,
                    working_state=working_state,
                    user_prompt=user_prompt,
                    targets=targets,
                    execution_plan=list(plan_payload.get("steps") or []),
                )
                await self._finalize_turn(
                    session=session,
                    turn=turn,
                    working_state=working_state,
                    user_prompt=user_prompt,
                    scratchpad=scratchpad,
                    targets=targets,
                )
            except Exception as exc:
                await self._fail_turn(session_id, turn_id, exc)

    async def _execute_targets(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        targets: Dict[str, Any],
        execution_plan: List[str],
    ) -> List[Dict[str, str]]:
        if not any(
            [
                targets["run_keyframe_analysis"],
                targets["update_subtitles"],
                targets["update_editing_plan"],
                targets["update_title"],
                targets["update_tags"],
                targets["update_edited_video"],
            ]
        ):
            return []

        registry = self._build_tool_registry(session, turn, working_state, user_prompt)
        runtime = PlanAndExecuteRuntime(
            adapter=self._adapter_factory.get_text_adapter(),
            model=settings.deepseek_chat_model,
            tool_registry=registry,
            max_steps=settings.agent_max_steps,
            timeout_seconds=settings.glm_request_timeout_seconds,
        )
        result = await runtime.run(
            user_prompt=user_prompt,
            execution_plan=execution_plan,
            context_prompt=self._build_runtime_context_prompt(session, working_state, targets),
            completion_guard=self._build_completion_guard(targets, working_state),
            fallback_step=self._build_fallback_step(targets),
            should_skip_step=self._build_step_skipper(),
            progress=self._noop_progress,
            trace=lambda thought, _action, observation: self._append_turn_thought(
                session,
                turn,
                thought,
                observation,
            ),
        )
        return result.scratchpad

    async def _finalize_turn(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        targets: Dict[str, Any],
    ) -> None:
        if targets["update_subtitles"] and not working_state.subtitle_draft:
            working_state.subtitle_draft = await self._generate_subtitle_draft(
                session, working_state, "补全初始字幕草稿。"
            )
            self._complete_workflow_artifact(working_state, "subtitle_draft", "字幕草稿已更新。")
        if targets["update_editing_plan"] and not working_state.editing_plan:
            working_state.editing_plan = await self._generate_editing_plan(
                session, working_state, "补全初始剪辑方案。"
            )
            self._complete_workflow_artifact(working_state, "editing_plan", "剪辑执行方案已更新。")
        if targets["update_title"] and not working_state.english_title:
            working_state.english_title = await self._generate_english_title(
                session, working_state, "补全英文标题。"
            )
            self._complete_workflow_artifact(working_state, "english_title", "英文标题已更新。")
        if targets["update_tags"] and not working_state.tags:
            working_state.tags = await self._generate_tags(
                session, working_state, "补全标签。"
            )
            self._complete_workflow_artifact(working_state, "tags", "标签已更新。")
        if targets["update_edited_video"] and not working_state.edited_video.download_url:
            await self._tool_run_bash_ffmpeg(
                session,
                turn,
                working_state,
                user_prompt,
                user_prompt,
            )

        final_text = (
            await self._compose_assistant_reply(
                session,
                working_state,
                user_prompt,
                scratchpad,
                targets,
            )
        ).strip()
        if not final_text:
            final_text = self._build_assistant_reply_fallback(working_state, targets)

        await self._commit_completed_turn(
            session=session,
            turn=turn,
            working_state=working_state,
            final_text=final_text,
        )

    async def _commit_completed_turn(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        final_text: str,
    ) -> None:
        working_state.updated_at = _utcnow()
        turn.final_text = final_text
        turn.status = "completed"
        turn.finished_at = _utcnow()
        turn.events.append(TurnEventItem(type="final_text", content=final_text))
        session.global_editing_state = working_state
        session.status = "completed"
        session.error_message = ""
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(session.session_id, "turn_completed", self._serialize(session))
        self._ensure_completion_event(session.session_id).set()

    async def _fail_turn(self, session_id: str, turn_id: str, exc: Exception) -> None:
        session = self.store.get(session_id)
        turn = self._get_turn(session, turn_id)
        turn.status = "error"
        turn.error_message = str(exc)
        turn.finished_at = _utcnow()
        session.status = "error"
        session.error_message = str(exc)
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(session.session_id, "turn_error", self._serialize(session))
        self._ensure_completion_event(session_id).set()

    async def _append_turn_event(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        event: TurnEventItem,
    ) -> None:
        turn.events.append(event)
        session.updated_at = _utcnow()
        self.store.save(session)
        self.events.publish(
            session.session_id,
            "turn_event",
            {
                "session_id": session.session_id,
                "turn_id": turn.turn_id,
                "version": session.version,
                "updated_at": session.updated_at,
                "event": asdict(event),
            },
        )

    async def _append_turn_thought(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        thought: str,
        observation: str,
    ) -> None:
        content = thought.strip()
        if not content:
            return
        if turn.events and turn.events[-1].type == "thought" and turn.events[-1].content == content:
            return
        if observation.strip():
            content = f"{content}\n\n结果摘要：{observation.strip()[:2800]}"
        await self._append_turn_event(
            session,
            turn,
            TurnEventItem(type="thought", content=content),
        )

    def _build_tool_registry(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
    ) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="run_keyframe_vision_subagent",
                description="调用关键帧视觉子代理：提取关键帧、逐帧调用多模态大模型分析图片，并汇总视频摘要。",
                run=lambda _input: self._run_keyframe_vision_subagent(session, working_state),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="read_video_context",
                description="读取视频关键帧分析和视频摘要。",
                run=lambda _input: self._tool_read_video_context(working_state),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="read_manual",
                description="读取产品说明书。",
                run=lambda _input: self._tool_read_manual(session),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="read_skill_ffmpeg_usage",
                description=(
                    "读取 skills/ffmpeg-usage/SKILL.md。"
                    "当用户要求输出 ffmpeg 命令、字幕烧录、裁剪拼接、比例调整、平台导出规范、"
                    "压缩优化或任何可执行音视频处理步骤时，应优先调用此工具。"
                ),
                run=lambda _input: self._tool_read_skill_ffmpeg_usage(),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="read_current_artifacts",
                description="读取当前字幕、剪辑方案、标题和标签。",
                run=lambda _input: self._tool_read_current_artifacts(working_state),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="write_subtitles",
                description="生成或更新字幕草稿。",
                run=lambda action_input: self._tool_write_subtitles(
                    session, working_state, user_prompt, action_input
                ),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="write_edit_plan",
                description="生成或更新剪辑方案。",
                run=lambda action_input: self._tool_write_edit_plan(
                    session, working_state, user_prompt, action_input
                ),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="write_title",
                description="生成或更新英文标题。",
                run=lambda action_input: self._tool_write_title(
                    session, working_state, user_prompt, action_input
                ),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="write_tags",
                description="生成或更新标签。",
                run=lambda action_input: self._tool_write_tags(
                    session, working_state, user_prompt, action_input
                ),
            )
        )
        registry.register(
            self._build_tool_spec(
                session,
                turn,
                name="run_bash_ffmpeg",
                description=(
                    "执行单条 ffmpeg bash 命令并导出视频。"
                    "必须先读取 ffmpeg skill，再传入单条 ffmpeg 命令模板。"
                    "输入视频路径与输出文件路径由服务端自动注入；若要烧录字幕，使用 {{subtitle_file}}。"
                    "如果参数不合法或执行失败，工具会返回错误观察结果，代理必须根据错误信息修正后重试。"
                ),
                run=lambda action_input: self._tool_run_bash_ffmpeg(
                    session, turn, working_state, user_prompt, action_input
                ),
            )
        )
        return registry

    def _build_tool_spec(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        *,
        name: str,
        description: str,
        run: Any,
    ) -> ToolSpec:
        async def wrapped(action_input: str) -> str:
            await self._append_turn_event(
                session,
                turn,
                TurnEventItem(
                    type="tool_call",
                    tool_name=name,
                    arguments=action_input.strip() or "{}",
                ),
            )
            return await run(action_input)

        return ToolSpec(name=name, description=description, run=wrapped)

    async def _run_keyframe_vision_subagent(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
    ) -> str:
        if (
            working_state.video_summary
            and working_state.frame_analyses
            and not working_state.workflow.keyframe_analysis.needs_refresh
        ):
            return "视频上下文已存在，跳过重复分析。"

        working_state.keyframes = []
        working_state.frame_analyses = []
        working_state.video_summary = ""
        await self._prepare_video_context(session, working_state)
        return (
            "关键帧视觉分析已完成。"
            f"\n关键帧数量：{len(working_state.keyframes)}"
            f"\n分析结果数量：{len(working_state.frame_analyses)}"
            f"\n视频摘要：{working_state.video_summary or '无'}"
        )

    async def _prepare_video_context(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
    ) -> None:
        self._update_workflow_artifact(
            working_state,
            "keyframe_analysis",
            status="in_progress",
            detail="正在提取关键帧并进行分析。",
            requested=True,
            needs_refresh=False,
        )
        self._update_workflow_artifact(
            working_state,
            "video_summary",
            status="in_progress",
            detail="将基于最新关键帧刷新视频摘要。",
            requested=True,
            needs_refresh=False,
        )
        working_state.keyframes = await asyncio.to_thread(
            extract_keyframes,
            session.video_path,
            settings.keyframe_interval_seconds,
            None,
            settings.keyframe_scene_threshold,
        )
        working_state.frame_analyses = await self._analyze_video_frames(working_state)
        working_state.video_summary = await self._summarize_video(session, working_state)
        self._complete_workflow_artifact(
            working_state,
            "keyframe_analysis",
            f"已完成 {len(working_state.frame_analyses)} 条关键帧理解。",
        )
        self._complete_workflow_artifact(
            working_state,
            "video_summary",
            "视频摘要已生成。",
        )

    async def _analyze_video_frames(self, working_state: GlobalEditingState) -> List[str]:
        analysis_frames = select_keyframes_for_analysis(
            working_state.keyframes,
            max_frames=settings.max_keyframes,
        )
        analyses: List[str] = []
        for index, keyframe in enumerate(analysis_frames, start=1):
            analysis = await self._analyze_single_frame(
                index,
                str(keyframe.get("image_base64", "")),
            )
            timestamp = keyframe.get("timestamp_seconds")
            source = keyframe.get("source", "unknown")
            analyses.append(f"关键帧{index}（{timestamp}s, 来源: {source}）: {analysis}")
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

    async def _summarize_video(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
    ) -> str:
        prompt = (
            "任务：总结视频的核心内容、产品卖点、适合人群、镜头节奏，以及适合做字幕和剪辑决策的信息。"
            + _prompt_block("平台", session.platform)
            + _prompt_block("说明书", session.product_manual or "无说明书")
            + _prompt_block("关键帧分析", "\n".join(working_state.frame_analyses))
        )
        return await self._text_complete(
            prompt,
            system_prompt=VIDEO_SUMMARY_SYSTEM_PROMPT,
        )

    async def _tool_read_video_context(self, working_state: GlobalEditingState) -> str:
        return (
            f"视频摘要：{working_state.video_summary or '暂无'}\n关键帧分析：\n"
            + "\n".join(working_state.frame_analyses or ["暂无"])
        )

    async def _tool_read_manual(self, session: CaptionSession) -> str:
        return session.product_manual or "用户未提供说明书。"

    async def _tool_read_skill_ffmpeg_usage(self) -> str:
        if not self._ffmpeg_skill_path.exists():
            return "未找到 ffmpeg skill 文档：skills/ffmpeg-usage/SKILL.md"
        return self._ffmpeg_skill_path.read_text(encoding="utf-8")

    async def _tool_read_current_artifacts(self, working_state: GlobalEditingState) -> str:
        return (
            f"当前字幕草稿：\n{working_state.subtitle_draft or '暂无'}\n\n"
            f"当前剪辑方案：\n{working_state.editing_plan or '暂无'}\n\n"
            f"当前英文标题：\n{working_state.english_title or '暂无'}\n\n"
            f"当前标签：\n{', '.join(working_state.tags) if working_state.tags else '暂无'}\n\n"
            f"当前导出视频：\n{working_state.edited_video.download_url or '暂无'}"
        )

    async def _tool_write_subtitles(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        working_state.subtitle_draft = await self._generate_subtitle_draft(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "subtitle_draft", "字幕草稿已更新。")
        return "字幕草稿已更新。"

    async def _tool_write_edit_plan(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        working_state.editing_plan = await self._generate_editing_plan(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "editing_plan", "剪辑执行方案已更新。")
        return "剪辑执行方案已更新。"

    async def _tool_write_title(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        working_state.english_title = await self._generate_english_title(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "english_title", "英文标题已更新。")
        return "英文标题已更新。"

    async def _tool_write_tags(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        working_state.tags = await self._generate_tags(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "tags", "标签已更新。")
        return "标签已更新。"

    async def _tool_run_bash_ffmpeg(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        attempted_command = ""
        try:
            if shutil.which("ffmpeg") is None:
                raise RuntimeError("当前运行环境未安装 ffmpeg，无法执行视频导出。")

            payload = self._parse_ffmpeg_command_input(action_input)
            command_template = payload["command_template"]
            needs_subtitle_file = payload["needs_subtitle_file"]
            output_extension = payload["output_extension"]
            summary = payload["summary"] or user_prompt.strip()

            subtitle_path = ""
            if needs_subtitle_file:
                subtitle_path = self._write_subtitle_sidecar(turn.turn_id, working_state.subtitle_draft)
                if not subtitle_path:
                    raise RuntimeError("当前没有可解析成 SRT 的字幕草稿，无法执行需要字幕文件的 ffmpeg 导出。")

            session_export_dir = os.path.join(settings.export_dir, session.session_id)
            os.makedirs(session_export_dir, exist_ok=True)
            output_name = f"{turn.turn_id}.{output_extension}"
            output_path = os.path.join(session_export_dir, output_name)
            command = self._materialize_ffmpeg_command(
                command_template=command_template,
                input_video=session.video_path,
                output_video=output_path,
                subtitle_file=subtitle_path or None,
            )
            attempted_command = command
            await self._run_bash_command(command)
            if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError("ffmpeg 命令执行完成，但未生成有效导出文件。")

            working_state.edited_video = EditedVideoArtifact(
                file_name=output_name,
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video",
                storage_path=output_path,
                command=command,
                summary=summary,
                error_message="",
                size_bytes=os.path.getsize(output_path),
            )
            self._complete_workflow_artifact(working_state, "edited_video", "剪辑视频已导出，可在右侧下载。")
            return (
                "剪辑视频导出完成。"
                f"\n文件名：{output_name}"
                f"\n大小：{working_state.edited_video.size_bytes} bytes"
                f"\n下载地址：{working_state.edited_video.download_url}"
            )
        except Exception as exc:
            session_export_dir = os.path.join(settings.export_dir, session.session_id)
            working_state.edited_video = EditedVideoArtifact(
                file_name="",
                download_url="",
                storage_path="",
                command=attempted_command,
                summary="",
                error_message=str(exc),
                size_bytes=0,
            )
            self._update_workflow_artifact(
                working_state,
                "edited_video",
                status="error",
                detail=str(exc),
                requested=True,
                needs_refresh=False,
            )
            return (
                "ffmpeg 导出失败，请根据以下信息修正参数后重试："
                f"\n错误：{exc}"
                f"\n当前输入视频路径：{session.video_path}"
                f"\n当前输出目录：{session_export_dir}"
                f"\n当前字幕文件占位符：{{{{subtitle_file}}}}"
                "\n注意：不要显式传入 -i 输入路径，不要传 input/output 占位符，服务端会自动注入。"
            )

    async def _generate_subtitle_draft(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
    ) -> str:
        prompt = (
            SUBTITLE_GENERATION_PROMPT
            + _prompt_block("用户需求", guidance)
            + _prompt_block("平台", session.platform)
            + _prompt_block("说明书", session.product_manual or "无")
            + _prompt_block("视频摘要", working_state.video_summary or "无")
            + _prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + _prompt_block("当前字幕草稿", working_state.subtitle_draft or "无")
        )
        return await self._text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)

    async def _generate_editing_plan(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
    ) -> str:
        prompt = (
            EDIT_PLAN_GENERATION_PROMPT
            + _prompt_block("用户需求", guidance)
            + _prompt_block("平台", session.platform)
            + _prompt_block("说明书", session.product_manual or "无")
            + _prompt_block("视频摘要", working_state.video_summary or "无")
            + _prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + _prompt_block("当前剪辑方案", working_state.editing_plan or "无")
            + _prompt_block("当前字幕草稿", working_state.subtitle_draft or "无")
        )
        return await self._text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)

    async def _generate_english_title(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
    ) -> str:
        prompt = (
            TITLE_GENERATION_PROMPT
            + _prompt_block("用户需求", guidance)
            + _prompt_block("平台", session.platform)
            + _prompt_block("说明书", session.product_manual or "无")
            + _prompt_block("视频摘要", working_state.video_summary or "无")
            + _prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + _prompt_block("当前英文标题", working_state.english_title or "无")
        )
        return (await self._text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)).strip()

    async def _generate_tags(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
    ) -> List[str]:
        prompt = (
            TAGS_GENERATION_PROMPT
            + _prompt_block("用户需求", guidance)
            + _prompt_block("平台", session.platform)
            + _prompt_block("说明书", session.product_manual or "无")
            + _prompt_block("视频摘要", working_state.video_summary or "无")
            + _prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + _prompt_block("当前标签", ", ".join(working_state.tags) if working_state.tags else "无")
        )
        parsed = self._parse_json_object(
            await self._text_complete(
                prompt,
                system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT,
                require_json=True,
            )
        )
        tags = parsed.get("tags") if isinstance(parsed, dict) else None
        if isinstance(tags, list) and tags:
            return [str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()][:8]
        return []

    async def _compose_assistant_reply(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        targets: Dict[str, Any],
    ) -> str:
        prompt = (
            ASSISTANT_REPLY_PROMPT
            + _prompt_block("用户需求", user_prompt)
            + _prompt_block("本轮更新范围", json.dumps(targets, ensure_ascii=False))
            + _prompt_block("工具执行记录", json.dumps(scratchpad, ensure_ascii=False))
            + _prompt_block("视频摘要", working_state.video_summary or "无")
            + _prompt_block("关键帧分析", json.dumps(working_state.frame_analyses[:12], ensure_ascii=False))
            + _prompt_block("最新字幕草稿全文", working_state.subtitle_draft[:6000] if working_state.subtitle_draft else "无")
            + _prompt_block("最新剪辑方案全文", working_state.editing_plan[:6000] if working_state.editing_plan else "无")
            + _prompt_block("最新英文标题", working_state.english_title or "无")
            + _prompt_block("最新标签", json.dumps(working_state.tags, ensure_ascii=False))
            + _prompt_block("导出视频", json.dumps({
                "download_url": working_state.edited_video.download_url,
                "summary": working_state.edited_video.summary,
                "error_message": working_state.edited_video.error_message,
                "size_bytes": working_state.edited_video.size_bytes,
            }, ensure_ascii=False))
        )
        return await self._text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)

    async def _build_plan_proposal(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
    ) -> Dict[str, Any]:
        prompt = (
            PLAN_PROPOSAL_PROMPT
            + _prompt_block("平台", session.platform)
            + _prompt_block("说明书", session.product_manual or "无")
            + _prompt_block("用户需求", user_prompt)
            + _prompt_block("已有视频摘要", working_state.video_summary or "无")
            + _prompt_block("已有字幕草稿", working_state.subtitle_draft[:1200] if working_state.subtitle_draft else "无")
            + _prompt_block("已有剪辑方案", working_state.editing_plan[:1200] if working_state.editing_plan else "无")
            + _prompt_block("已有英文标题", working_state.english_title or "无")
            + _prompt_block("已有标签", json.dumps(working_state.tags, ensure_ascii=False))
        )
        parsed = self._parse_json_object(
            await self._text_complete(
                prompt,
                system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT,
                require_json=True,
            )
        )
        return self._coerce_plan_proposal(working_state, user_prompt, parsed)

    def _parse_ffmpeg_command_input(self, action_input: str) -> Dict[str, Any]:
        parsed = self._parse_json_object(action_input)
        if isinstance(parsed, dict) and parsed.get("command_template"):
            command_template = str(parsed.get("command_template", "")).strip()
            output_extension = str(parsed.get("output_extension", "mp4")).strip().lstrip(".") or "mp4"
            summary = str(parsed.get("summary", "")).strip()
            needs_subtitle_file = bool(parsed.get("needs_subtitle_file"))
        else:
            command_template = action_input.strip()
            output_extension = "mp4"
            summary = ""
            needs_subtitle_file = "{{subtitle_file}}" in command_template

        if not command_template:
            raise RuntimeError(
                "ffmpeg 命令不能为空。请先读取 ffmpeg skill，再给出明确的 ffmpeg 参数或命令。"
            )
        if command_template.startswith("ffmpeg "):
            normalized_template = command_template
        else:
            normalized_template = f"ffmpeg {command_template}"
        if "{{input_video}}" in normalized_template or "{{output_video}}" in normalized_template:
            raise RuntimeError("不需要传入 input/output 占位符，服务端会自动注入输入视频和输出路径。")
        if re.search(r"(^|\s)-i(\s|$)", normalized_template):
            raise RuntimeError("不需要在 ffmpeg 命令里显式传入 -i 输入路径，服务端会自动注入。")
        if normalized_template.strip() == "ffmpeg":
            raise RuntimeError("ffmpeg 命令模板缺少处理参数。")
        if any(token in normalized_template for token in ["&&", "||", ";", "`", "$(", "|", ">", "<"]):
            raise RuntimeError("ffmpeg 命令模板包含不被允许的 shell 控制符。")
        if needs_subtitle_file and "{{subtitle_file}}" not in normalized_template:
            raise RuntimeError("needs_subtitle_file=true 时，命令模板必须包含 {{subtitle_file}} 占位符。")
        if output_extension.lower() not in {"mp4", "mov", "webm", "mkv"}:
            raise RuntimeError("暂不支持该导出格式，请使用 mp4、mov、webm 或 mkv。")

        return {
            "command_template": normalized_template,
            "output_extension": output_extension.lower(),
            "summary": summary,
            "needs_subtitle_file": needs_subtitle_file,
        }

    def _write_subtitle_sidecar(self, turn_id: str, subtitle_draft: str) -> str:
        srt_content = self._subtitle_draft_to_srt(subtitle_draft)
        if not srt_content:
            return ""
        file_path = os.path.join(settings.export_dir, f"{turn_id}.srt")
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(srt_content)
        return file_path

    def _subtitle_draft_to_srt(self, subtitle_draft: str) -> str:
        if not subtitle_draft.strip():
            return ""

        entries: List[str] = []
        pattern = re.compile(
            r"^(?P<start>\d{1,2}:\d{2}(?::\d{2})?)\s*[-—–~]\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?)\s+(?P<text>.+)$"
        )
        for line in subtitle_draft.splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            start = self._to_srt_timestamp(match.group("start"))
            end = self._to_srt_timestamp(match.group("end"))
            text = match.group("text").strip()
            if not text:
                continue
            entries.append(f"{len(entries) + 1}\n{start} --> {end}\n{text}\n")
        return "\n".join(entries).strip()

    def _to_srt_timestamp(self, value: str) -> str:
        parts = value.split(":")
        if len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        else:
            hours, minutes, seconds = parts
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},000"

    def _materialize_ffmpeg_command(
        self,
        *,
        command_template: str,
        input_video: str,
        output_video: str,
        subtitle_file: str | None,
    ) -> str:
        args = command_template[len("ffmpeg") :].strip() if command_template.startswith("ffmpeg") else command_template.strip()
        if "{{subtitle_file}}" in args:
            if not subtitle_file:
                raise RuntimeError("ffmpeg 命令要求字幕文件，但当前没有可用的 subtitle_file。")
            args = args.replace("{{subtitle_file}}", shlex.quote(subtitle_file))
        if args:
            return f"ffmpeg -y -i {shlex.quote(input_video)} {args} {shlex.quote(output_video)}"
        return f"ffmpeg -y -i {shlex.quote(input_video)} {shlex.quote(output_video)}"

    async def _run_bash_command(self, command: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.ffmpeg_execution_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("ffmpeg 执行超时，已中止导出。") from exc

        if process.returncode != 0:
            raise RuntimeError(
                "ffmpeg 执行失败："
                + (stderr.decode("utf-8", errors="ignore") or stdout.decode("utf-8", errors="ignore"))[-3000:]
            )

    def get_exported_video_path(self, session_id: str) -> str:
        session = self.store.get(session_id)
        edited_video = session.global_editing_state.edited_video
        if not edited_video.storage_path:
            raise KeyError(f"session '{session_id}' has no exported video")
        if not os.path.exists(edited_video.storage_path):
            raise FileNotFoundError(edited_video.storage_path)
        return edited_video.storage_path

    def _coerce_plan_proposal(
        self,
        working_state: GlobalEditingState,
        user_prompt: str,
        parsed: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized_prompt = user_prompt.lower()
        selected_ids = parsed.get("selected_ids") if isinstance(parsed, dict) else None
        selected = {
            str(item).strip()
            for item in (selected_ids if isinstance(selected_ids, list) else [])
            if str(item).strip()
        }
        allowed_ids = {
            "keyframe_analysis",
            "subtitle_draft",
            "editing_plan",
            "english_title",
            "tags",
            "edited_video",
        }
        selected &= allowed_ids

        requests_full_editing = bool(parsed.get("requests_full_editing")) if isinstance(parsed, dict) else False
        force_keyframe_refresh = bool(parsed.get("force_keyframe_refresh")) if isinstance(parsed, dict) else False
        is_supported_request = bool(parsed.get("is_supported_request", True)) if isinstance(parsed, dict) else True
        reason = str(parsed.get("reason", "")).strip() if isinstance(parsed, dict) else ""
        summary = str(parsed.get("summary", "")).strip() if isinstance(parsed, dict) else ""
        steps = parsed.get("steps") if isinstance(parsed, dict) else None

        if any(
            keyword in normalized_prompt
            for keyword in ["重新分析关键帧", "重分析关键帧", "重新看关键帧", "重新分析素材", "重新理解视频"]
        ):
            force_keyframe_refresh = True
            selected.add("keyframe_analysis")

        if any(
            keyword in normalized_prompt
            for keyword in ["剪辑视频", "重剪", "重新剪", "完整剪辑", "剪一版", "出成片"]
        ):
            requests_full_editing = True
            selected.update({"subtitle_draft", "editing_plan", "english_title", "tags"})
            if not working_state.video_summary:
                selected.add("keyframe_analysis")

        if any(
            keyword in normalized_prompt
            for keyword in ["导出视频", "导出成片", "输出成片", "渲染视频", "生成成片", "执行剪辑", "烧录字幕", "压制视频"]
        ):
            selected.add("edited_video")
            if not working_state.editing_plan:
                selected.add("editing_plan")
            if not working_state.video_summary:
                selected.add("keyframe_analysis")
            if "字幕" in normalized_prompt and not working_state.subtitle_draft:
                selected.add("subtitle_draft")

        if not selected and is_supported_request:
            selected.update({"subtitle_draft", "editing_plan"})

        if force_keyframe_refresh:
            selected.add("keyframe_analysis")

        if working_state.video_summary == "" and (
            "subtitle_draft" in selected or "editing_plan" in selected
        ):
            selected.add("keyframe_analysis")

        fallback_steps = ["理解用户本轮目标", "读取当前视频上下文"]
        if "keyframe_analysis" in selected:
            fallback_steps.append("重新分析关键帧并更新视频理解")
        if "subtitle_draft" in selected:
            fallback_steps.append("生成或更新字幕草稿")
        if "editing_plan" in selected:
            fallback_steps.append("生成或更新剪辑方案")
        if "english_title" in selected:
            fallback_steps.append("生成或更新英文标题")
        if "tags" in selected:
            fallback_steps.append("生成或更新标签")
        if "edited_video" in selected:
            fallback_steps.append("执行 ffmpeg 导出并生成可下载成片")
        fallback_steps.append("整理最终回复")

        return {
            "summary": summary or user_prompt.strip(),
            "steps": [str(step).strip() for step in steps[:6]] if isinstance(steps, list) and steps else fallback_steps,
            "selected_ids": [
                option_id
                for option_id in ["keyframe_analysis", "subtitle_draft", "editing_plan", "english_title", "tags", "edited_video"]
                if option_id in selected
            ],
            "is_supported_request": is_supported_request,
            "reason": reason or "根据用户需求自动拆解执行计划。",
            "requests_full_editing": requests_full_editing,
            "force_keyframe_refresh": force_keyframe_refresh,
        }

    def _plan_targets_from_selection(
        self,
        selected_plan_ids: List[str],
        inferred_targets: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        selected = set(selected_plan_ids)
        return {
            "run_keyframe_analysis": "keyframe_analysis" in selected,
            "update_subtitles": "subtitle_draft" in selected,
            "update_editing_plan": "editing_plan" in selected,
            "update_title": "english_title" in selected,
            "update_tags": "tags" in selected,
            "update_edited_video": "edited_video" in selected,
            "is_supported_request": True,
            "reason": str((inferred_targets or {}).get("reason") or "根据自动规划执行。"),
            "requests_full_editing": bool((inferred_targets or {}).get("requests_full_editing")),
            "force_keyframe_refresh": bool((inferred_targets or {}).get("force_keyframe_refresh")),
        }

    def _build_runtime_context_prompt(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        targets: Dict[str, Any],
    ) -> str:
        return (
            f"平台：{session.platform}"
            f"\n是否执行关键帧视觉子代理：{targets['run_keyframe_analysis']}"
            f"\n是否更新字幕：{targets['update_subtitles']}"
            f"\n是否更新剪辑方案：{targets['update_editing_plan']}"
            f"\n是否更新英文标题：{targets['update_title']}"
            f"\n是否更新标签：{targets['update_tags']}"
            f"\n是否导出视频：{targets['update_edited_video']}"
            "\n可用技能文档：skills/ffmpeg-usage/SKILL.md，可通过 read_skill_ffmpeg_usage 读取。"
            "\n当用户需求涉及 ffmpeg 命令、裁剪、拼接、压缩、比例调整、字幕烧录、导出规范时，应优先读取该技能。"
            "\n服务端会自动注入 ffmpeg 的输入视频路径与输出文件路径。"
            f"\n当前输入视频路径：{session.video_path}"
            f"\n当前输出目录：{os.path.join(settings.export_dir, session.session_id)}"
            "\n如果 run_bash_ffmpeg 返回错误观察结果，必须根据错误内容修正参数后再次调用该工具。"
            f"\n视频摘要：{working_state.video_summary or '无'}"
            f"\n关键帧分析条数：{len(working_state.frame_analyses)}"
            f"\n当前字幕草稿：{working_state.subtitle_draft[:1200] if working_state.subtitle_draft else '无'}"
            f"\n当前剪辑方案：{working_state.editing_plan[:1200] if working_state.editing_plan else '无'}"
            f"\n当前英文标题：{working_state.english_title or '无'}"
            f"\n当前标签：{json.dumps(working_state.tags, ensure_ascii=False)}"
            f"\n当前导出视频：{working_state.edited_video.download_url or '无'}"
        )

    def _build_completion_guard(self, targets: Dict[str, Any], working_state: GlobalEditingState):
        def guard(scratchpad: List[Dict[str, str]]) -> bool:
            action_names = {item.get("action") for item in scratchpad}
            keyframe_ready = (not targets["run_keyframe_analysis"]) or ("run_keyframe_vision_subagent" in action_names)
            subtitles_ready = (not targets["update_subtitles"]) or ("write_subtitles" in action_names)
            editing_ready = (not targets["update_editing_plan"]) or ("write_edit_plan" in action_names)
            title_ready = (not targets["update_title"]) or ("write_title" in action_names)
            tags_ready = (not targets["update_tags"]) or ("write_tags" in action_names)
            video_ready = (not targets["update_edited_video"]) or bool(working_state.edited_video.download_url)
            return keyframe_ready and subtitles_ready and editing_ready and title_ready and tags_ready and video_ready

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
            if targets["update_edited_video"] and "run_bash_ffmpeg" not in action_names:
                return ReActStep("还需要基于当前方案执行 ffmpeg 导出成片。", "run_bash_ffmpeg", "")
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

    def _mark_selected_items_in_progress(
        self,
        working_state: GlobalEditingState,
        targets: Dict[str, Any],
    ) -> None:
        if targets.get("run_keyframe_analysis"):
            self._update_workflow_artifact(
                working_state,
                "keyframe_analysis",
                status="in_progress",
                detail="正在提取并分析关键帧。",
                requested=True,
                needs_refresh=False,
            )
            self._update_workflow_artifact(
                working_state,
                "video_summary",
                status="in_progress",
                detail="将基于最新关键帧重建视频摘要。",
                requested=True,
                needs_refresh=False,
            )
        for key, flag, detail in [
            ("subtitle_draft", targets.get("update_subtitles"), "正在生成或更新字幕草稿。"),
            ("editing_plan", targets.get("update_editing_plan"), "正在生成或更新剪辑方案。"),
            ("english_title", targets.get("update_title"), "正在生成或更新英文标题。"),
            ("tags", targets.get("update_tags"), "正在生成或更新标签。"),
            ("edited_video", targets.get("update_edited_video"), "正在执行 ffmpeg 导出视频。"),
        ]:
            if flag:
                self._update_workflow_artifact(
                    working_state,
                    key,
                    status="in_progress",
                    detail=detail,
                    requested=True,
                    needs_refresh=False,
                )

    def _complete_workflow_artifact(
        self,
        working_state: GlobalEditingState,
        artifact: str,
        detail: str,
    ) -> None:
        self._update_workflow_artifact(
            working_state,
            artifact,
            status="completed",
            detail=detail,
            requested=True,
            needs_refresh=False,
        )

    def _update_workflow_artifact(
        self,
        working_state: GlobalEditingState,
        artifact: str,
        *,
        status: str | None = None,
        detail: str | None = None,
        requested: bool | None = None,
        needs_refresh: bool | None = None,
    ) -> None:
        item = getattr(working_state.workflow, artifact)
        if status is not None:
            item.status = status
        if detail is not None:
            item.detail = detail
        if requested is not None:
            item.requested = requested
        if needs_refresh is not None:
            item.needs_refresh = needs_refresh
        item.updated_at = _utcnow()
        working_state.updated_at = item.updated_at

    async def _noop_progress(self, _message: str) -> None:
        return

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

    async def _vision_complete(
        self,
        prompt: str,
        frame_base64: str,
        *,
        trace_label: str | None = None,
    ) -> str:
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

    def _compose_scope_guard_reply(self, user_prompt: str, targets: Dict[str, Any]) -> str:
        return (
            "这条需求没有落在当前视频创意会话的可执行范围内。"
            "\n\n当前会话支持的交付有："
            "\n1. 字幕草稿修改"
            "\n2. 剪辑方案修改"
            "\n3. 英文标题"
            "\n4. 标签"
            "\n5. 基于 ffmpeg 的视频导出"
            f"\n\n本轮识别结果：{targets['reason']}"
            f"\n\n你的原始输入：{user_prompt}"
        )

    def _build_assistant_reply_fallback(
        self,
        working_state: GlobalEditingState,
        targets: Dict[str, Any],
    ) -> str:
        sections: List[str] = []
        if targets.get("run_keyframe_analysis") and working_state.video_summary:
            sections.append(f"视频摘要：\n{working_state.video_summary.strip()}")
        if targets.get("update_subtitles") and working_state.subtitle_draft:
            sections.append(f"字幕草稿：\n{working_state.subtitle_draft.strip()}")
        if targets.get("update_editing_plan") and working_state.editing_plan:
            sections.append(f"剪辑方案：\n{working_state.editing_plan.strip()}")
        if targets.get("update_title") and working_state.english_title:
            sections.append(f"英文标题：\n{working_state.english_title.strip()}")
        if targets.get("update_tags") and working_state.tags:
            sections.append(
                "标签：\n" + "\n".join(f"- {tag}" for tag in working_state.tags if str(tag).strip())
            )
        if targets.get("update_edited_video") and working_state.edited_video.download_url:
            sections.append(
                "导出视频：\n"
                f"文件名：{working_state.edited_video.file_name}\n"
                f"下载地址：{working_state.edited_video.download_url}\n"
                f"导出说明：{working_state.edited_video.summary or '已生成可下载成片。'}"
            )
        elif targets.get("update_edited_video") and working_state.edited_video.error_message:
            sections.append(
                "导出视频：\n"
                "当前导出失败，尚未生成可下载成片。\n"
                f"失败原因：{working_state.edited_video.error_message}"
            )

        if sections:
            return "\n\n".join(sections)
        if working_state.video_summary:
            return f"视频摘要：\n{working_state.video_summary.strip()}"
        return "本轮产物已生成完成。"

    def _get_turn(self, session: CaptionSession, turn_id: str) -> AgentTurn:
        for turn in session.turns:
            if turn.turn_id == turn_id:
                return turn
        raise KeyError(f"turn '{turn_id}' not found")

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
        editing_state = asdict(session.global_editing_state)
        if isinstance(editing_state.get("edited_video"), dict):
            editing_state["edited_video"].pop("storage_path", None)
        return {
            "session_id": session.session_id,
            "platform": session.platform,
            "turns": [asdict(turn) for turn in session.turns],
            "global_editing_state": editing_state,
            "status": session.status,
            "active_turn_id": session.active_turn_id,
            "error_message": session.error_message,
            "version": session.version,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
