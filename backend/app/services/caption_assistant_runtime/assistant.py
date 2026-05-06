from __future__ import annotations

import asyncio
import copy
import json
import os
from threading import Lock
from typing import Any, AsyncIterator, Dict, List
from uuid import uuid4

from app.agent.runtime import LightPlanningReActRuntime, OpenAIToolCallingRuntime, ReActStep, ToolRegistry
from app.core.config import settings
from app.models import AgentTurn, AnalysisMode, CaptionSession, EditedVideoArtifact, GlobalEditingState, TurnEventItem, TurnTaskBoard, utcnow
from app.services.caption_assistant_runtime.broker import CaptionEventBroker
from app.services.caption_assistant_runtime.clip_derivation import ClipDerivationService
from app.services.caption_assistant_runtime.completion import CompletionService
from app.services.caption_assistant_runtime.content_generation import ContentGenerationService
from app.services.caption_assistant_runtime.serialization import SerializationService
from app.services.caption_assistant_runtime.shared import parse_json_object
from app.services.caption_assistant_runtime.store import CaptionSessionStore
from app.services.caption_assistant_runtime.task_board import TaskBoardService
from app.services.caption_assistant_runtime.tools import (
    CaptionToolContext,
    CreateTaskBoardTool,
    DeriveClipSegmentsTool,
    MergeRenderedSegmentsTool,
    ReadCurrentArtifactsTool,
    ReadManualTool,
    ReadTaskBoardTool,
    ReadVideoContextTool,
    ReadVideoEditContextTool,
    RenderClipSegmentTool,
    RunKeyframeVisionSubagentTool,
    RunVideoEditSubagentTool,
    UpdateTaskStatusTool,
    WriteEditPlanTool,
    WriteSubtitlesTool,
    WriteTagsTool,
    WriteTitleTool,
)
from app.services.caption_assistant_runtime.video_context import VideoContextService
from app.services.caption_assistant_runtime.video_edit_agent import VideoEditExportSubAgent, VideoEditSubAgentContext
from app.services.caption_assistant_runtime.video_export import VideoExportService


class CaptionConversationAssistant:
    def __init__(self) -> None:
        self.store = CaptionSessionStore()
        self.events = CaptionEventBroker()
        self.completion_service = CompletionService()
        self.task_board_service = TaskBoardService()
        self.clip_derivation_service = ClipDerivationService(self.completion_service)
        self.video_context_service = VideoContextService(self.completion_service, self.task_board_service)
        self.content_generation_service = ContentGenerationService(
            self.completion_service,
            self.task_board_service,
            self.clip_derivation_service,
        )
        self.video_export_service = VideoExportService(
            self.task_board_service,
            self.clip_derivation_service,
        )
        self.serialization_service = SerializationService()
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._completion_events: Dict[str, asyncio.Event] = {}
        self._meta_lock = Lock()

    async def create_session(
        self,
        video_path: str,
        platform: str,
        product_manual: str | None,
        user_prompt: str,
        analysis_mode: AnalysisMode = "keyframe",
    ) -> Dict[str, Any]:
        turn = AgentTurn(turn_id=str(uuid4()), user_prompt=user_prompt)
        session = CaptionSession(
            session_id=str(uuid4()),
            video_path=video_path,
            platform=platform,
            product_manual=product_manual or "",
            analysis_mode=analysis_mode,
            turns=[turn],
            status="processing",
            active_turn_id=turn.turn_id,
        )
        session.global_editing_state.request_summary = user_prompt.strip()
        session.updated_at = utcnow()
        self.store.save(session)
        self.ensure_session_primitives(session.session_id)
        self.reset_completion_event(session.session_id)
        asyncio.create_task(self.run_turn(session.session_id, turn.turn_id, user_prompt))
        return self.serialize(session)

    async def continue_session(self, session_id: str, user_prompt: str) -> Dict[str, Any]:
        session = self.store.get(session_id)
        if session.status == "processing":
            raise ValueError("session is still processing")

        turn = AgentTurn(turn_id=str(uuid4()), user_prompt=user_prompt)
        session.turns.append(turn)
        session.status = "processing"
        session.active_turn_id = turn.turn_id
        session.error_message = ""
        session.updated_at = utcnow()
        self.store.save(session)
        self.ensure_session_primitives(session_id)
        self.reset_completion_event(session_id)
        asyncio.create_task(self.run_turn(session_id, turn.turn_id, user_prompt))
        return self.serialize(session)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self.serialize(self.store.get(session_id))

    async def wait_for_completion(self, session_id: str) -> Dict[str, Any]:
        event = self.ensure_completion_event(session_id)
        await event.wait()
        return self.get_session(session_id)

    async def stream_session_events(self, session_id: str) -> AsyncIterator[Dict[str, Any]]:
        session = self.store.get(session_id)
        queue = self.events.subscribe(session_id)
        try:
            yield {"event": "snapshot", "data": self.serialize(session)}
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield message
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": {"session_id": session_id, "ts": utcnow()}}
        finally:
            self.events.unsubscribe(session_id, queue)

    def get_exported_video_path(self, session_id: str) -> str:
        session = self.store.get(session_id)
        edited_video = session.global_editing_state.edited_video
        if not edited_video.storage_path:
            raise KeyError(f"session '{session_id}' has no exported video")
        if not os.path.exists(edited_video.storage_path):
            raise FileNotFoundError(edited_video.storage_path)
        return edited_video.storage_path

    def serialize(self, session: CaptionSession) -> Dict[str, Any]:
        return self.serialization_service.serialize(session)

    def ensure_session_primitives(self, session_id: str) -> None:
        with self._meta_lock:
            self._session_locks.setdefault(session_id, asyncio.Lock())
            self._completion_events.setdefault(session_id, asyncio.Event())

    def reset_completion_event(self, session_id: str) -> None:
        with self._meta_lock:
            self._completion_events[session_id] = asyncio.Event()

    def ensure_completion_event(self, session_id: str) -> asyncio.Event:
        with self._meta_lock:
            return self._completion_events.setdefault(session_id, asyncio.Event())

    def get_session_lock(self, session_id: str) -> asyncio.Lock:
        with self._meta_lock:
            return self._session_locks.setdefault(session_id, asyncio.Lock())

    async def run_turn(self, session_id: str, turn_id: str, user_prompt: str) -> None:
        async with self.get_session_lock(session_id):
            try:
                session = self.store.get(session_id)
                turn = self.get_turn(session, turn_id)
                working_state = copy.deepcopy(session.global_editing_state)
                working_state.request_summary = user_prompt.strip()
                working_state.updated_at = utcnow()
                targets = self.build_open_tool_targets()
                turn.plan_summary = self.build_runtime_task_brief()
                turn.task_board = TurnTaskBoard(summary="等待 agent 自主判断并按需拆解任务。")
                scratchpad, runtime_final_text = await self.execute_targets(
                    session=session,
                    turn=turn,
                    working_state=working_state,
                    user_prompt=user_prompt,
                    targets=targets,
                    task_brief=self.build_runtime_task_brief(),
                )
                await self.finalize_turn(
                    session=session,
                    turn=turn,
                    working_state=working_state,
                    user_prompt=user_prompt,
                    scratchpad=scratchpad,
                    runtime_final_text=runtime_final_text,
                    targets=targets,
                )
            except Exception as exc:
                await self.fail_turn(session_id, turn_id, exc)

    async def execute_targets(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        targets: Dict[str, Any],
        task_brief: str,
    ) -> tuple[List[Dict[str, str]], str]:
        registry = self.build_tool_registry(session, turn, working_state, user_prompt, targets)
        runtime = OpenAIToolCallingRuntime(
            model=settings.deepseek_chat_model,
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key or "",
            tool_registry=registry,
            max_steps=settings.agent_max_steps,
            timeout_seconds=settings.glm_request_timeout_seconds,
        )
        result = await runtime.run(
            user_prompt=user_prompt,
            task_brief=task_brief,
            context_prompt=self.build_runtime_context_prompt(session, working_state, targets),
            completion_guard=self.build_completion_guard(turn, targets, working_state),
            progress=self.noop_progress,
            trace=lambda thought, _action, observation: self.append_turn_thought(
                session,
                turn,
                thought,
                observation,
            ),
        )
        return result.scratchpad, result.final_text

    async def finalize_turn(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        runtime_final_text: str,
        targets: Dict[str, Any],
    ) -> None:
        del targets
        action_names = {str(item.get("action", "")).strip() for item in scratchpad}
        if (
            "run_video_edit_subagent" in action_names
            and not working_state.edited_video.download_url
            and not working_state.edited_video.error_message
        ):
            working_state.edited_video.error_message = "本轮未生成有效的导出结果。"
            self.task_board_service.update_workflow_artifact(
                working_state,
                "edited_video",
                status="error",
                detail=working_state.edited_video.error_message,
                requested=True,
                needs_refresh=False,
            )

        should_compose_reply = (
            not runtime_final_text.strip()
            or "run_video_edit_subagent" in action_names
            or "merge_rendered_segments" in action_names
        )
        final_text = runtime_final_text.strip()
        if should_compose_reply:
            final_text = (
                await self.content_generation_service.compose_assistant_reply(
                    session,
                    working_state,
                    user_prompt,
                    scratchpad,
                    action_names,
                )
            ).strip()
        if not final_text:
            final_text = self.serialization_service.build_assistant_reply_fallback(
                working_state,
                action_names,
                self.clip_derivation_service.summarize_clip_segments(working_state.executable_edit.segments),
            )

        await self.commit_completed_turn(
            session=session,
            turn=turn,
            working_state=working_state,
            final_text=final_text,
        )

    async def commit_completed_turn(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        final_text: str,
    ) -> None:
        working_state.updated_at = utcnow()
        turn.final_text = final_text
        turn.turn_summary = self.serialization_service.build_turn_summary(turn, working_state)
        turn.status = "completed"
        turn.finished_at = utcnow()
        turn.events.append(TurnEventItem(type="final_text", content=final_text))
        session.global_editing_state = working_state
        session.status = "completed"
        session.error_message = ""
        session.updated_at = utcnow()
        self.store.save(session)
        self.events.publish(session.session_id, "turn_completed", self.serialize(session))
        self.ensure_completion_event(session.session_id).set()

    async def fail_turn(self, session_id: str, turn_id: str, exc: Exception) -> None:
        session = self.store.get(session_id)
        turn = self.get_turn(session, turn_id)
        turn.status = "error"
        turn.error_message = str(exc)
        turn.turn_summary = self.serialization_service.build_error_turn_summary(turn, str(exc))
        turn.finished_at = utcnow()
        session.status = "error"
        session.error_message = str(exc)
        session.updated_at = utcnow()
        self.store.save(session)
        self.events.publish(session.session_id, "turn_error", self.serialize(session))
        self.ensure_completion_event(session_id).set()

    async def append_turn_event(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        event: TurnEventItem,
    ) -> None:
        turn.events.append(event)
        session.updated_at = utcnow()
        self.store.save(session)
        self.events.publish(
            session.session_id,
            "turn_event",
            {
                "session_id": session.session_id,
                "turn_id": turn.turn_id,
                "version": session.version,
                "updated_at": session.updated_at,
                "event": {
                    "type": event.type,
                    "content": event.content,
                    "tool_name": event.tool_name,
                    "arguments": event.arguments,
                    "created_at": event.created_at,
                },
            },
        )

    async def append_turn_thought(
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
        await self.append_turn_event(
            session,
            turn,
            TurnEventItem(type="thought", content=content),
        )

    def build_tool_registry(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        targets: Dict[str, Any],
    ) -> ToolRegistry:
        registry = ToolRegistry()
        context = CaptionToolContext(
            assistant=self,
            session=session,
            turn=turn,
            working_state=working_state,
            user_prompt=user_prompt,
            targets=targets,
        )
        for tool in [
            RunKeyframeVisionSubagentTool(context),
            ReadVideoContextTool(context),
            ReadManualTool(context),
            ReadCurrentArtifactsTool(context),
            DeriveClipSegmentsTool(context),
            CreateTaskBoardTool(context),
            ReadTaskBoardTool(context),
            UpdateTaskStatusTool(context),
            WriteSubtitlesTool(context),
            WriteEditPlanTool(context),
            WriteTitleTool(context),
            WriteTagsTool(context),
            RunVideoEditSubagentTool(context),
        ]:
            registry.register(tool.to_spec())
        return registry

    def build_video_edit_tool_registry(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
    ) -> ToolRegistry:
        registry = ToolRegistry()
        context = CaptionToolContext(
            assistant=self,
            session=session,
            turn=turn,
            working_state=working_state,
            user_prompt=user_prompt,
            targets={},
        )
        for tool in [
            ReadVideoEditContextTool(context),
            WriteSubtitlesTool(context),
            RenderClipSegmentTool(context),
            MergeRenderedSegmentsTool(context),
        ]:
            registry.register(tool.to_spec())
        return registry

    async def tool_run_video_edit_subagent(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        subagent = VideoEditExportSubAgent(
            VideoEditSubAgentContext(
                assistant=self,
                session=session,
                turn=turn,
                working_state=working_state,
                user_prompt=user_prompt,
            )
        )
        return await subagent.run(action_input)

    async def tool_derive_clip_segments(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        try:
            self.task_board_service.set_task_status(turn, "derive_clip_segments", "doing", notes="正在把成片方案映射为原视频片段。")
            guidance = action_input.strip() or user_prompt
            working_state.executable_edit = await self.clip_derivation_service.derive_executable_edit_decision(
                session=session,
                working_state=working_state,
                guidance=guidance,
                user_prompt=user_prompt,
            )
            working_state.edited_video = EditedVideoArtifact()
            self.task_board_service.update_workflow_artifact(
                working_state,
                "edited_video",
                status="idle",
                detail="片段已更新，等待重新导出",
                requested=True,
                needs_refresh=True,
            )
            self.task_board_service.complete_workflow_artifact(
                working_state,
                "clip_segments",
                f"已生成 {len(working_state.executable_edit.segments)} 个原视频片段映射。",
            )
            self.task_board_service.set_task_status(
                turn,
                "derive_clip_segments",
                "done",
                notes=self.clip_derivation_service.summarize_clip_segments(working_state.executable_edit.segments)[:3000],
                current_focus="run_video_edit_subagent",
            )
            return f"已生成 {len(working_state.executable_edit.segments)} 个原视频片段映射。"
        except Exception as exc:
            self.task_board_service.set_task_status(
                turn,
                "derive_clip_segments",
                "blocked",
                notes=str(exc),
                current_focus="derive_clip_segments",
                blocked_reason=str(exc),
            )
            return f"片段映射失败：{exc}"

    def build_open_tool_targets(self) -> Dict[str, Any]:
        return {
            "run_keyframe_analysis": True,
            "update_subtitles": True,
            "update_editing_plan": True,
            "update_title": True,
            "update_tags": True,
            "update_edited_video": True,
            "is_supported_request": True,
            "reason": "Agent 可自主调用全部核心工具。",
            "requests_full_editing": False,
            "force_keyframe_refresh": False,
        }

    def build_runtime_task_brief(self) -> str:
        return (
            "理解并完成用户这一轮的最新目标。"
            "\n只调用真正有帮助的工具，避免无意义重复。"
            "\n如果用户要求导出视频，先确认视觉摘要、字幕和剪辑方案是否足够，再建立片段映射并执行导出。"
            "\n如果信息不足，可以直接向用户说明缺口；如果任务已完成，直接给出最终回复。"
        )

    def build_recent_turn_memory(self, session: CaptionSession, current_turn_id: str, *, limit: int = 6) -> str:
        memories: List[str] = []
        for turn in reversed(session.turns):
            if turn.turn_id == current_turn_id:
                continue
            summary = turn.turn_summary.strip() or turn.final_text.strip()[:500]
            if not summary:
                continue
            memories.append(
                f"- 用户需求：{turn.user_prompt.strip()[:120]}\n  状态：{turn.status}\n  摘要：{summary[:400]}"
            )
            if len(memories) >= limit:
                break
        if not memories:
            return "无历史轮次摘要。"
        return "\n".join(reversed(memories))

    def build_runtime_context_prompt(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        targets: Dict[str, Any],
    ) -> str:
        del targets
        history = self.build_recent_turn_memory(session, session.active_turn_id, limit=6)
        instruction = """
[当前任务指引]
- 优先依据当前状态选择下一步，不要照搬固定 SOP。
- 服务端会自动注入 ffmpeg 的输入视频路径与输出文件路径，不需要再次向用户索要。
- 如果要导出视频，通常应先调用 derive_clip_segments，再调用 run_video_edit_subagent。
- 只能基于真实工具结果继续规划，不要假设工具已经成功。
""".strip()
        current_state = (
            "[当前剪辑状态 - 权威事实]\n"
            f"视频路径: {session.video_path}\n"
            f"导出目录: {os.path.join(settings.export_dir, session.session_id)}\n"
            f"平台: {session.platform}\n"
            f"说明书: {session.product_manual or '无'}\n"
            f"任务板: {self.task_board_service.serialize_task_board(self.get_turn(session, session.active_turn_id).task_board)}\n"
            f"视频摘要: {working_state.video_summary or '尚未分析'}\n"
            f"关键帧分析: {json.dumps(working_state.frame_analyses[:12], ensure_ascii=False) if working_state.frame_analyses else '尚未分析'}\n"
            f"字幕草稿: {working_state.subtitle_draft or '未生成'}\n"
            f"剪辑方案: {working_state.editing_plan or '未生成'}\n"
            f"片段映射: {self.clip_derivation_service.summarize_clip_segments(working_state.executable_edit.segments) or '未生成'}\n"
            f"英文标题: {working_state.english_title or '未生成'}\n"
            f"标签: {json.dumps(working_state.tags, ensure_ascii=False) if working_state.tags else '未生成'}\n"
            f"导出视频地址: {working_state.edited_video.download_url or '尚未导出'}\n"
            f"导出错误: {working_state.edited_video.error_message or '无'}"
        )
        return f"[历史对话记忆]\n{history}\n\n{instruction}\n\n{current_state}"

    def build_video_edit_task_brief(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
    ) -> str:
        del turn
        return (
            "你是专门负责 ffmpeg 剪辑导出的 ReAct 子代理。"
            "\n目标：基于已有片段映射，把原视频逐段裁切、缩放、必要时调速，先生成单段片段，再合并成最终成片。"
            "\n执行要求："
            "\n1. 先调用 read_video_edit_context，确认输入视频路径、输出目录、片段映射、字幕状态、上一条失败命令和错误。"
            "\n2. 片段必须逐个处理：优先调用 render_clip_segment，一次只处理一个 segment。"
            "\n3. 如果片段很多，要主动判断是否需要提高某些片段的 speed 来满足目标时长；不要盲目把所有片段都原速保留。"
            "\n4. 如果发现当前片段映射明显不够支撑目标时长，或 segment 语义混乱，应回到主 agent 重新做更密的关键帧分析和片段映射，而不是强行 finalize。"
            "\n5. 只有当所有片段都渲染完成后，才能调用 merge_rendered_segments 合并并在需要时烧录字幕。"
            "\n6. 如果 render_clip_segment 或 merge_rendered_segments 返回错误，必须基于错误内容修改输入参数后再次调用对应工具，不能重复提交相同参数，也不能直接 finalize。"
            "\n7. 如果 merge_rendered_segments 明确指出字幕时间轴格式错误，必须先调用 write_subtitles 重新生成严格 timeline_plain 格式字幕，成功后才能再次合并。"
            f"\n用户目标：{user_prompt.strip() or '执行视频导出'}"
            f"\n平台：{session.platform}"
            f"\n字幕是否可用：{bool(working_state.subtitle_draft.strip())}"
        )

    def build_video_edit_context_prompt(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
    ) -> str:
        return (
            f"输入视频路径：{session.video_path}"
            f"\n输出目录：{os.path.join(settings.export_dir, session.session_id)}"
            f"\n当前任务板：{self.task_board_service.serialize_task_board(turn.task_board)}"
            f"\n片段映射摘要：\n{self.clip_derivation_service.summarize_clip_segments(working_state.executable_edit.segments) or '无'}"
            f"\n片段渲染状态：\n{self.clip_derivation_service.summarize_rendered_segments(working_state.executable_edit) or '无'}"
            f"\n字幕草稿预览：{working_state.subtitle_draft[:1200] if working_state.subtitle_draft else '无'}"
            f"\n字幕开关：{working_state.executable_edit.burn_subtitles}"
            f"\n目标比例：{working_state.executable_edit.aspect_ratio}"
            f"\n上一次失败命令：{working_state.edited_video.command or '无'}"
            f"\n上一次错误：{working_state.edited_video.error_message or '无'}"
            f"\n片段合并错误：{working_state.executable_edit.merge_error_message or '无'}"
        )

    def build_video_edit_completion_guard(self, working_state: GlobalEditingState):
        def guard(_scratchpad: List[Dict[str, str]]) -> bool:
            return bool(working_state.edited_video.download_url)

        return guard

    def build_video_edit_fallback_step(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
    ):
        del session
        def fallback(scratchpad: List[Dict[str, str]]) -> ReActStep:
            action_names = [item.get("action") for item in scratchpad]
            if "read_video_edit_context" not in action_names:
                return ReActStep("需要先读取当前导出上下文，再决定 ffmpeg 参数。", "read_video_edit_context", "")
            last_item = scratchpad[-1] if scratchpad else {}
            last_action = str(last_item.get("action", "")).strip()
            last_input = str(last_item.get("action_input", "")).strip()
            last_observation = str(last_item.get("observation", "")).strip()
            repeated_render_failures = [
                item
                for item in scratchpad
                if str(item.get("action", "")).strip() == "render_clip_segment"
                and self.observation_has_failure(str(item.get("observation", "")))
            ]
            if (
                last_action == "render_clip_segment"
                and self.observation_has_failure(last_observation)
                and self.count_identical_action_attempts(scratchpad, "render_clip_segment", last_input) >= 2
            ):
                payload = parse_json_object(last_input)
                target_segment = str(payload.get("segment_id", "")).strip() if isinstance(payload, dict) else ""
                forced_payload = {
                    "segment_id": target_segment,
                    "drop_audio": True,
                    "vf_override": "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "notes": "相同参数已经重复失败；强制改用兼容滤镜与静音导出，避免死循环。",
                }
                return ReActStep(
                    "相同的 render_clip_segment 参数已经重复失败，必须修改 vf_override 或 drop_audio，先用最小兼容参数重试。",
                    "render_clip_segment",
                    json.dumps(forced_payload, ensure_ascii=False),
                )
            next_segment = self.clip_derivation_service.next_pending_segment(working_state.executable_edit)
            if next_segment is not None:
                return ReActStep(
                    f"还有未完成片段 {next_segment.id}，需要先逐段渲染。",
                    "render_clip_segment",
                    json.dumps({"segment_id": next_segment.id}, ensure_ascii=False),
                )
            if self.clip_derivation_service.all_segments_rendered(working_state.executable_edit) and not working_state.edited_video.download_url:
                return ReActStep(
                    "所有片段都已渲染完成，下一步应合并片段并在需要时烧录字幕。",
                    "merge_rendered_segments",
                    json.dumps({"burn_subtitles": working_state.executable_edit.burn_subtitles}, ensure_ascii=False),
                )
            if repeated_render_failures:
                return ReActStep(
                    "render_clip_segment 已连续报错，不能再重复原参数；必须修改 vf_override、af_override 或 drop_audio 后继续渲染。",
                    "read_video_edit_context",
                    "",
                )
            if working_state.edited_video.error_message or working_state.executable_edit.merge_error_message:
                return ReActStep("上一次导出失败，需要重新读取上下文并修正参数。", "read_video_edit_context", "")
            return ReActStep("已经具备导出结果。", "finalize", "")

        return fallback

    def build_video_edit_step_skipper(self):
        def should_skip(step: ReActStep, scratchpad: List[Dict[str, str]]) -> bool:
            if step.action not in {"render_clip_segment", "merge_rendered_segments"}:
                return False
            normalized_input = step.action_input.strip()
            matched_items = [
                item
                for item in scratchpad
                if item.get("action") == step.action
                and str(item.get("action_input", "")).strip() == normalized_input
            ]
            if not matched_items:
                return False
            if any(self.observation_has_failure(str(item.get("observation", ""))) for item in matched_items):
                return False
            return any(
                item.get("action") == step.action
                and str(item.get("action_input", "")).strip() == normalized_input
                for item in scratchpad
            )

        return should_skip

    def observation_has_failure(self, observation: str) -> bool:
        normalized = observation.strip().lower()
        return any(keyword in normalized for keyword in ["错误", "失败", "error", "failed", "invalid"])

    def count_identical_action_attempts(
        self,
        scratchpad: List[Dict[str, str]],
        action: str,
        action_input: str,
    ) -> int:
        normalized_input = action_input.strip()
        return sum(
            1
            for item in scratchpad
            if str(item.get("action", "")).strip() == action
            and str(item.get("action_input", "")).strip() == normalized_input
        )

    def build_completion_guard(self, turn: AgentTurn, targets: Dict[str, Any], working_state: GlobalEditingState):
        del targets
        def guard(scratchpad: List[Dict[str, str]]) -> bool:
            action_names = {str(item.get("action", "")).strip() for item in scratchpad}
            if "finalize" in action_names:
                return True
            if turn.task_board.tasks:
                required_done = all(task.status == "done" for task in turn.task_board.tasks)
                if required_done:
                    if any(task.id == "verify_export" for task in turn.task_board.tasks):
                        return bool(working_state.edited_video.download_url)
                    return True
            return False

        return guard

    def build_fallback_step(self, turn: AgentTurn, targets: Dict[str, Any]):
        del targets
        def fallback(scratchpad: List[Dict[str, str]]) -> ReActStep:
            action_names = {str(item.get("action", "")).strip() for item in scratchpad}
            if turn.task_board.blocked_reason and "run_video_edit_subagent" in action_names:
                return ReActStep("导出子代理执行失败，请检查上下文错误并修正重试。", "run_video_edit_subagent", "")
            if not scratchpad:
                return ReActStep("未检测到工具调用，请直接输出对用户的回答，或者调用所需工具。", "finalize", "")
            return ReActStep("操作已结束或陷入未知状态，请整理结果回复用户。", "finalize", "")

        return fallback

    def build_step_skipper(self):
        single_run_actions = {
            "create_task_board",
            "read_task_board",
            "run_keyframe_vision_subagent",
            "derive_clip_segments",
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

    async def noop_progress(self, _message: str) -> None:
        return

    def get_turn(self, session: CaptionSession, turn_id: str) -> AgentTurn:
        for turn in session.turns:
            if turn.turn_id == turn_id:
                return turn
        raise KeyError(f"turn '{turn_id}' not found")
