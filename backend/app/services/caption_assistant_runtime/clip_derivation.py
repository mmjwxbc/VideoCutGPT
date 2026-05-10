from __future__ import annotations

import re
from typing import Any, Dict, List

from app.models import (
    CaptionSession,
    ClipSegment,
    ExecutableEditDecision,
    GlobalEditingState,
    RenderedClipSegment,
    utcnow,
)
from app.services.caption_assistant_runtime.completion import CompletionService
from app.services.caption_assistant_runtime.prompts import (
    CAPTION_ASSISTANT_SYSTEM_PROMPT,
    DERIVE_CLIP_SEGMENTS_PROMPT,
)
from app.services.caption_assistant_runtime.shared import parse_json_object, prompt_block


class ClipDerivationService:
    def __init__(self, completion_service: CompletionService) -> None:
        self._completion_service = completion_service

    async def derive_executable_edit_decision(
        self,
        *,
        session: CaptionSession,
        working_state: GlobalEditingState,
        guidance: str,
        user_prompt: str,
    ) -> ExecutableEditDecision:
        del user_prompt
        prompt = (
            DERIVE_CLIP_SEGMENTS_PROMPT
            + prompt_block("用户需求", guidance)
            + prompt_block("平台", session.platform)
            + prompt_block("视频摘要", working_state.video_summary or "无")
            + prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + prompt_block("当前字幕草稿", working_state.subtitle_draft or "无")
            + prompt_block("当前剪辑方案", working_state.editing_plan or "无")
            + prompt_block("历史片段映射", self.summarize_clip_segments(working_state.executable_edit.segments) or "无")
        )
        raw = await self._completion_service.text_complete(
            prompt,
            system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT,
            require_json=True,
        )
        decision = self.coerce_executable_edit_decision(parse_json_object(raw))
        self.normalize_executable_edit_decision(decision)
        return decision

    def coerce_executable_edit_decision(self, parsed: Dict[str, Any]) -> ExecutableEditDecision:
        if not isinstance(parsed, dict):
            raise RuntimeError("片段映射结果不是合法 JSON 对象。")
        raw_segments = parsed.get("segments")
        if not isinstance(raw_segments, list) or not raw_segments:
            raise RuntimeError("片段映射结果缺少 segments。")

        segments: List[ClipSegment] = []
        for index, item in enumerate(raw_segments, start=1):
            if not isinstance(item, dict):
                continue
            source_start = str(item.get("source_start", "")).strip()
            source_end = str(item.get("source_end", "")).strip()
            timeline_start = str(item.get("timeline_start", "")).strip()
            timeline_end = str(item.get("timeline_end", "")).strip()
            if not source_start or not source_end or not timeline_start or not timeline_end:
                continue
            speed = float(item.get("speed", 1.0) or 1.0)
            if speed <= 0:
                speed = 1.0
            segments.append(
                ClipSegment(
                    id=str(item.get("id", f"seg_{index}")).strip() or f"seg_{index}",
                    source_start=source_start,
                    source_end=source_end,
                    timeline_start=timeline_start,
                    timeline_end=timeline_end,
                    output_duration_seconds=float(item.get("output_duration_seconds", 0) or 0),
                    source_duration_seconds=0.0,
                    purpose=str(item.get("purpose", "")).strip(),
                    visual_instruction=str(item.get("visual_instruction", "")).strip(),
                    speed=speed,
                    transition_to_next=str(item.get("transition_to_next", "hard_cut")).strip() or "hard_cut",
                )
            )

        if not segments:
            raise RuntimeError("片段映射结果中没有可用 segment。")

        return ExecutableEditDecision(
            summary=str(parsed.get("summary", "")).strip(),
            total_duration_seconds=float(parsed.get("total_duration_seconds", 0) or 0),
            aspect_ratio=str(parsed.get("aspect_ratio", "9:16")).strip() or "9:16",
            burn_subtitles=bool(parsed.get("burn_subtitles", True)),
            segments=segments,
            rendered_segments=[RenderedClipSegment(segment_id=segment.id) for segment in segments],
            updated_at=utcnow(),
        )

    def normalize_executable_edit_decision(self, decision: ExecutableEditDecision) -> None:
        decision.segments.sort(key=lambda item: self.timestamp_to_seconds(item.timeline_start))
        for segment in decision.segments:
            source_duration = self.timestamp_to_seconds(segment.source_end) - self.timestamp_to_seconds(segment.source_start)
            timeline_duration = self.timestamp_to_seconds(segment.timeline_end) - self.timestamp_to_seconds(segment.timeline_start)
            if source_duration <= 0:
                raise RuntimeError(f"片段 {segment.id} 的 source 时间范围无效。")
            if timeline_duration <= 0 and segment.output_duration_seconds <= 0:
                raise RuntimeError(f"片段 {segment.id} 的 timeline 时间范围无效。")
            segment.source_duration_seconds = round(source_duration, 4)
            segment.output_duration_seconds = round(
                max(0.2, timeline_duration if timeline_duration > 0 else segment.output_duration_seconds),
                4,
            )
            segment.speed = round(
                max(0.25, segment.source_duration_seconds / segment.output_duration_seconds),
                4,
            )
        if decision.total_duration_seconds <= 0 and decision.segments:
            decision.total_duration_seconds = round(
                max(self.timestamp_to_seconds(segment.timeline_end) for segment in decision.segments),
                4,
            )
        elif decision.segments:
            decision.total_duration_seconds = round(
                max(
                    float(decision.total_duration_seconds or 0),
                    max(self.timestamp_to_seconds(segment.timeline_end) for segment in decision.segments),
                ),
                4,
            )
        self.ensure_rendered_segment_entries(decision)
        decision.merged_segments_path = ""
        decision.merge_command = ""
        decision.merge_error_message = ""
        decision.updated_at = utcnow()

    def summarize_clip_segments(self, segments: List[ClipSegment]) -> str:
        if not segments:
            return ""
        lines = []
        for segment in segments[:12]:
            lines.append(
                f"{segment.id}: 原视频 {segment.source_start}-{segment.source_end} -> "
                f"成片 {segment.timeline_start}-{segment.timeline_end} | "
                f"转场 {segment.transition_to_next or 'hard_cut'} | "
                f"{segment.purpose or segment.visual_instruction or '无说明'}"
            )
        return "\n".join(lines)

    def timestamp_to_seconds(self, value: str) -> float:
        normalized = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", str(value)).strip()
        normalized = re.sub(r"\s+", "", normalized)
        try:
            seconds = float(normalized)
            if seconds < 0:
                raise RuntimeError(f"时间戳必须为正数：{value}")
            return seconds
        except ValueError:
            pass

        parts = normalized.split(":")
        if len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        elif len(parts) == 3:
            hours, minutes, seconds = parts
        else:
            raise RuntimeError(f"无法解析时间戳：{value}")
        total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if total_seconds < 0:
            raise RuntimeError(f"时间戳必须为正数：{value}")
        return float(total_seconds)

    def get_rendered_segment(
        self,
        decision: ExecutableEditDecision,
        segment_id: str,
    ) -> RenderedClipSegment | None:
        for item in decision.rendered_segments:
            if item.segment_id == segment_id:
                return item
        return None

    def ensure_rendered_segment_entries(self, decision: ExecutableEditDecision) -> None:
        known_ids = {item.segment_id for item in decision.rendered_segments}
        for segment in decision.segments:
            if segment.id not in known_ids:
                decision.rendered_segments.append(RenderedClipSegment(segment_id=segment.id))
        decision.rendered_segments = [
            item for item in decision.rendered_segments if any(segment.id == item.segment_id for segment in decision.segments)
        ]

    def next_pending_segment(self, decision: ExecutableEditDecision) -> ClipSegment | None:
        self.ensure_rendered_segment_entries(decision)
        for segment in decision.segments:
            rendered = self.get_rendered_segment(decision, segment.id)
            if rendered and rendered.status in {"todo", "blocked"}:
                return segment
        return None

    def all_segments_rendered(self, decision: ExecutableEditDecision) -> bool:
        self.ensure_rendered_segment_entries(decision)
        if not decision.segments:
            return False
        return all(
            (rendered := self.get_rendered_segment(decision, segment.id)) is not None
            and rendered.status == "done"
            and rendered.storage_path
            and rendered.duration_ok
            for segment in decision.segments
        )

    def summarize_rendered_segments(self, decision: ExecutableEditDecision) -> str:
        self.ensure_rendered_segment_entries(decision)
        lines: List[str] = []
        for segment in decision.segments[:20]:
            rendered = self.get_rendered_segment(decision, segment.id)
            if rendered is None:
                continue
            lines.append(
                f"{segment.id}: status={rendered.status}, file={rendered.file_name or '无'}, error={rendered.error_message[:120] or '无'}"
            )
        return "\n".join(lines)
