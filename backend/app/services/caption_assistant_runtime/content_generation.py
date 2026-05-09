from __future__ import annotations

import json
import re
from typing import Dict, List

from app.agent.runtime import ToolResult
from app.models import AgentTurn, CaptionSession, GlobalEditingState
from app.services.caption_assistant_runtime.clip_derivation import ClipDerivationService
from app.services.caption_assistant_runtime.completion import CompletionService
from app.services.caption_assistant_runtime.prompts import (
    ASSISTANT_REPLY_PROMPT,
    CAPTION_ASSISTANT_SYSTEM_PROMPT,
    EDIT_PLAN_GENERATION_PROMPT,
    SUBTITLE_GENERATION_PROMPT,
    TAGS_GENERATION_PROMPT,
    TITLE_GENERATION_PROMPT,
)
from app.services.caption_assistant_runtime.shared import parse_json_object, prompt_block
from app.services.caption_assistant_runtime.task_board import TaskBoardService


class ContentGenerationService:
    def __init__(
        self,
        completion_service: CompletionService,
        task_board_service: TaskBoardService,
        clip_derivation_service: ClipDerivationService,
    ) -> None:
        self._completion_service = completion_service
        self._task_board_service = task_board_service
        self._clip_derivation_service = clip_derivation_service

    async def tool_read_current_artifacts(self, working_state: GlobalEditingState) -> str:
        return (
            f"当前字幕草稿：\n{working_state.subtitle_draft or '暂无'}\n\n"
            f"当前剪辑方案：\n{working_state.editing_plan or '暂无'}\n\n"
            f"当前片段映射：\n{self._clip_derivation_service.summarize_clip_segments(working_state.executable_edit.segments) or '暂无'}\n\n"
            f"当前英文标题：\n{working_state.english_title or '暂无'}\n\n"
            f"当前标签：\n{', '.join(working_state.tags) if working_state.tags else '暂无'}\n\n"
            f"当前导出视频：\n{working_state.edited_video.download_url or '暂无'}"
        )

    async def tool_write_subtitles(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str | ToolResult:
        self._task_board_service.set_task_status(turn, "subtitle_draft", "doing", notes="正在生成字幕草稿。")
        payload = parse_json_object(action_input)
        strict_timeline_plain = (
            isinstance(payload, dict)
            and str(payload.get("format", "")).strip() == "timeline_plain"
            and bool(payload.get("strict"))
        )
        total_duration_seconds = (
            float(payload.get("total_duration_seconds", 0) or 0)
            if isinstance(payload, dict)
            else 0.0
        )

        def finalize_success(subtitle_text: str) -> ToolResult:
            self._task_board_service.invalidate_edited_video_due_to_upstream_change(
                working_state,
                detail="前置文案已更新，等待重新导出成片",
            )
            self._task_board_service.complete_workflow_artifact(working_state, "subtitle_draft", "字幕草稿已更新。")
            self._task_board_service.set_task_status(turn, "subtitle_draft", "done", notes="字幕草稿已更新。")
            return ToolResult(
                ok=True,
                summary="字幕草稿已更新。",
                artifact_type="subtitle_draft",
                state_patch={"subtitle_draft_preview": subtitle_text[:200]},
                retry_same_tool_allowed=True,
            )

        def finalize_failure(error_code: str, error_message: str) -> ToolResult:
            self._task_board_service.set_task_status(
                turn,
                "subtitle_draft",
                "blocked",
                notes=error_message,
                current_focus="subtitle_draft",
                blocked_reason=error_message,
            )
            return ToolResult(
                ok=False,
                summary=error_message,
                artifact_type="subtitle_draft",
                error=error_message,
                error_code=error_code,
                retry_same_tool_allowed=True,
            )

        if isinstance(payload, dict) and "action" in payload:
            action = str(payload.get("action", "rewrite")).strip() or "rewrite"
            content = str(payload.get("content", "")).strip()
            guidance = str(payload.get("guidance", "")).strip()
            if action == "append":
                base = working_state.subtitle_draft.rstrip()
                candidate = f"{base}\n{content}".strip() if base else content
                validation_error = self.validate_timeline_plain_subtitles(candidate, total_duration_seconds)
                if strict_timeline_plain and validation_error:
                    return finalize_failure("SUBTITLE_GENERATION_INVALID_FORMAT", validation_error)
                working_state.subtitle_draft = candidate
            elif action == "modify_partial":
                candidate = await self.generate_subtitle_draft(
                    session,
                    working_state,
                    guidance or content or user_prompt,
                    format_name="timeline_plain" if strict_timeline_plain else None,
                    strict=strict_timeline_plain,
                    total_duration_seconds=total_duration_seconds or None,
                )
                if strict_timeline_plain:
                    candidate = await self.retry_invalid_timeline_subtitles_once(
                        session,
                        working_state,
                        base_guidance=guidance or content or user_prompt,
                        candidate=candidate,
                        total_duration_seconds=total_duration_seconds or None,
                    )
                    validation_error = self.validate_timeline_plain_subtitles(candidate, total_duration_seconds)
                    if validation_error:
                        return finalize_failure("SUBTITLE_GENERATION_INVALID_FORMAT", validation_error)
                working_state.subtitle_draft = candidate
            else:
                if guidance:
                    candidate = await self.generate_subtitle_draft(
                        session,
                        working_state,
                        guidance,
                        format_name="timeline_plain" if strict_timeline_plain else None,
                        strict=strict_timeline_plain,
                        total_duration_seconds=total_duration_seconds or None,
                    )
                else:
                    candidate = content or await self.generate_subtitle_draft(
                        session,
                        working_state,
                        user_prompt,
                        format_name="timeline_plain" if strict_timeline_plain else None,
                        strict=strict_timeline_plain,
                        total_duration_seconds=total_duration_seconds or None,
                    )
                if strict_timeline_plain:
                    candidate = await self.retry_invalid_timeline_subtitles_once(
                        session,
                        working_state,
                        base_guidance=guidance or content or user_prompt,
                        candidate=candidate,
                        total_duration_seconds=total_duration_seconds or None,
                    )
                    validation_error = self.validate_timeline_plain_subtitles(candidate, total_duration_seconds)
                    if validation_error:
                        return finalize_failure("SUBTITLE_GENERATION_INVALID_FORMAT", validation_error)
                working_state.subtitle_draft = candidate
        else:
            candidate = await self.generate_subtitle_draft(
                session,
                working_state,
                action_input or user_prompt,
                format_name="timeline_plain" if strict_timeline_plain else None,
                strict=strict_timeline_plain,
                total_duration_seconds=total_duration_seconds or None,
            )
            if strict_timeline_plain:
                candidate = await self.retry_invalid_timeline_subtitles_once(
                    session,
                    working_state,
                    base_guidance=action_input or user_prompt,
                    candidate=candidate,
                    total_duration_seconds=total_duration_seconds or None,
                )
                validation_error = self.validate_timeline_plain_subtitles(candidate, total_duration_seconds)
                if validation_error:
                    return finalize_failure("SUBTITLE_GENERATION_INVALID_FORMAT", validation_error)
            working_state.subtitle_draft = candidate
        return finalize_success(working_state.subtitle_draft)

    async def tool_write_edit_plan(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        self._task_board_service.set_task_status(turn, "editing_plan", "doing", notes="正在生成剪辑方案。")
        payload = parse_json_object(action_input)
        if isinstance(payload, dict) and "action" in payload:
            action = str(payload.get("action", "rewrite")).strip() or "rewrite"
            content = str(payload.get("content", "")).strip()
            guidance = str(payload.get("guidance", "")).strip()
            if action == "append":
                base = working_state.editing_plan.rstrip()
                working_state.editing_plan = f"{base}\n{content}".strip() if base else content
            elif action == "modify_partial":
                working_state.editing_plan = await self.generate_editing_plan(
                    session,
                    working_state,
                    guidance or content or user_prompt,
                )
            else:
                if guidance:
                    working_state.editing_plan = await self.generate_editing_plan(
                        session,
                        working_state,
                        guidance,
                    )
                else:
                    working_state.editing_plan = content or await self.generate_editing_plan(
                        session,
                        working_state,
                        user_prompt,
                    )
        else:
            working_state.editing_plan = await self.generate_editing_plan(
                session,
                working_state,
                action_input or user_prompt,
            )
        self._task_board_service.invalidate_edited_video_due_to_upstream_change(
            working_state,
            detail="前置文案已更新，等待重新导出成片",
        )
        self._task_board_service.complete_workflow_artifact(working_state, "editing_plan", "剪辑执行方案已更新。")
        self._task_board_service.set_task_status(turn, "editing_plan", "done", notes="剪辑方案已更新。")
        return "剪辑执行方案已更新。"

    async def tool_write_title(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        self._task_board_service.set_task_status(turn, "english_title", "doing", notes="正在生成英文标题。")
        working_state.english_title = await self.generate_english_title(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._task_board_service.complete_workflow_artifact(working_state, "english_title", "英文标题已更新。")
        self._task_board_service.set_task_status(turn, "english_title", "done", notes="英文标题已更新。")
        return "英文标题已更新。"

    async def tool_write_tags(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        self._task_board_service.set_task_status(turn, "tags", "doing", notes="正在生成标签。")
        working_state.tags = await self.generate_tags(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._task_board_service.complete_workflow_artifact(working_state, "tags", "标签已更新。")
        self._task_board_service.set_task_status(turn, "tags", "done", notes="标签已更新。")
        return "标签已更新。"

    async def generate_subtitle_draft(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
        *,
        format_name: str | None = None,
        strict: bool = False,
        total_duration_seconds: float | None = None,
    ) -> str:
        prompt = (
            SUBTITLE_GENERATION_PROMPT
            + prompt_block("用户需求", guidance)
            + prompt_block("平台", session.platform)
            + prompt_block("说明书", session.product_manual or "无")
            + prompt_block("视频摘要", working_state.video_summary or "无")
            + prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + prompt_block("当前字幕草稿", working_state.subtitle_draft or "无")
        )
        if format_name:
            prompt += prompt_block("输出格式", format_name)
        if strict:
            prompt += prompt_block(
                "严格格式要求",
                (
                    "只输出纯文本字幕，不要 markdown、不要表格、不要编号、不要项目符号、不要解释文字。"
                    "\n每行必须严格为 `00:00-00:03 字幕内容` 格式。"
                    "\n不允许单点时间戳。"
                    "\n每行字幕必须能在对应时间里自然念完，宁可更短，不要硬塞长句。"
                ),
            )
        if total_duration_seconds:
            prompt += prompt_block(
                "总时长要求（秒）",
                f"{total_duration_seconds}。字幕时间轴不能超过该时长，但最后一条可以早于该时长结束。",
            )
        return await self._completion_service.text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)

    async def retry_invalid_timeline_subtitles_once(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        *,
        base_guidance: str,
        candidate: str,
        total_duration_seconds: float | None,
    ) -> str:
        if not self.validate_timeline_plain_subtitles(candidate, total_duration_seconds):
            return candidate
        retry_guidance = (
            f"{base_guidance}\n\n"
            "重新生成规范字幕。每行必须严格为 `00:00-00:03 字幕内容` 格式。"
            "不要 markdown、不要表格、不要编号、不要解释文字、不要单点时间戳。"
        )
        return await self.generate_subtitle_draft(
            session,
            working_state,
            retry_guidance,
            format_name="timeline_plain",
            strict=True,
            total_duration_seconds=total_duration_seconds,
        )

    def validate_timeline_plain_subtitles(
        self,
        subtitle_draft: str,
        total_duration_seconds: float | None = None,
    ) -> str | None:
        text = subtitle_draft.strip()
        if not text:
            return "字幕生成失败：输出为空。"
        pattern = re.compile(
            r"^(?P<start>\d{2}:\d{2})-(?P<end>\d{2}:\d{2}) (?P<text>.+)$"
        )
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "字幕生成失败：没有可解析的字幕行。"
        previous_end = 0
        for line in lines:
            match = pattern.match(line)
            if not match:
                return (
                    "字幕解析失败：字幕草稿中未找到符合 `00:00-00:03 字幕内容` 格式的时间轴！"
                    "请重新调用 write_subtitles，仅传入 guidance 让底层模型重新生成规范格式。"
                )
            start = self._mmss_to_seconds(match.group("start"))
            end = self._mmss_to_seconds(match.group("end"))
            if end <= start:
                return "字幕生成失败：存在结束时间早于或等于开始时间的字幕行。"
            if start < previous_end:
                return "字幕生成失败：字幕时间轴存在重叠或倒序。"
            previous_end = end
        if total_duration_seconds and previous_end - float(total_duration_seconds) > 1.0:
            return "字幕生成失败：字幕总时长超出目标视频时长。"
        return None

    def _mmss_to_seconds(self, value: str) -> int:
        minutes, seconds = value.split(":")
        return int(minutes) * 60 + int(seconds)

    async def generate_editing_plan(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
    ) -> str:
        prompt = (
            EDIT_PLAN_GENERATION_PROMPT
            + prompt_block("用户需求", guidance)
            + prompt_block("平台", session.platform)
            + prompt_block("说明书", session.product_manual or "无")
            + prompt_block("视频摘要", working_state.video_summary or "无")
            + prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + prompt_block("当前剪辑方案", working_state.editing_plan or "无")
            + prompt_block("当前字幕草稿", working_state.subtitle_draft or "无")
        )
        return await self._completion_service.text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)

    async def generate_english_title(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
    ) -> str:
        prompt = (
            TITLE_GENERATION_PROMPT
            + prompt_block("用户需求", guidance)
            + prompt_block("平台", session.platform)
            + prompt_block("说明书", session.product_manual or "无")
            + prompt_block("视频摘要", working_state.video_summary or "无")
            + prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + prompt_block("当前英文标题", working_state.english_title or "无")
        )
        return (await self._completion_service.text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)).strip()

    async def generate_tags(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
    ) -> List[str]:
        prompt = (
            TAGS_GENERATION_PROMPT
            + prompt_block("用户需求", guidance)
            + prompt_block("平台", session.platform)
            + prompt_block("说明书", session.product_manual or "无")
            + prompt_block("视频摘要", working_state.video_summary or "无")
            + prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + prompt_block("当前标签", ", ".join(working_state.tags) if working_state.tags else "无")
        )
        parsed = parse_json_object(
            await self._completion_service.text_complete(
                prompt,
                system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT,
                require_json=True,
            )
        )
        tags = parsed.get("tags") if isinstance(parsed, dict) else None
        if isinstance(tags, list) and tags:
            return [str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()][:8]
        return []

    async def compose_assistant_reply(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        scratchpad: List[Dict[str, str]],
        action_names: set[str],
    ) -> str:
        interaction_mode = "clarification" if not scratchpad else "delivery"
        prompt = (
            ASSISTANT_REPLY_PROMPT
            + prompt_block("用户需求", user_prompt)
            + prompt_block("本轮回复模式", interaction_mode)
            + prompt_block("本轮实际调用工具", json.dumps(sorted(action_names), ensure_ascii=False))
            + prompt_block("工具执行记录", json.dumps(scratchpad, ensure_ascii=False))
            + prompt_block("平台", session.platform)
            + prompt_block("说明书", session.product_manual or "无")
            + prompt_block("视频摘要", working_state.video_summary or "无")
            + prompt_block("关键帧分析", json.dumps(working_state.frame_analyses[:12], ensure_ascii=False))
            + prompt_block("最新字幕草稿全文", working_state.subtitle_draft[:6000] if working_state.subtitle_draft else "无")
            + prompt_block("最新剪辑方案全文", working_state.editing_plan[:6000] if working_state.editing_plan else "无")
            + prompt_block("最新片段映射", self._clip_derivation_service.summarize_clip_segments(working_state.executable_edit.segments) or "无")
            + prompt_block("最新英文标题", working_state.english_title or "无")
            + prompt_block("最新标签", json.dumps(working_state.tags, ensure_ascii=False))
            + prompt_block("导出视频", json.dumps({
                "download_url": working_state.edited_video.download_url,
                "summary": working_state.edited_video.summary,
                "error_message": working_state.edited_video.error_message,
                "size_bytes": working_state.edited_video.size_bytes,
                "expected_duration_seconds": working_state.edited_video.expected_duration_seconds,
                "actual_duration_seconds": working_state.edited_video.actual_duration_seconds,
                "duration_ok": working_state.edited_video.duration_ok,
            }, ensure_ascii=False))
        )
        return await self._completion_service.text_complete(prompt, system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT)
