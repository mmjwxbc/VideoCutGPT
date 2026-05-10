from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import asdict
from typing import Any, Dict, List

from app.agent.runtime import ToolResult
from app.core.config import settings
from app.models import AgentTurn, CaptionSession, EditedVideoArtifact, GlobalEditingState, RenderedClipSegment, utcnow
from app.services.caption_assistant_runtime.clip_derivation import ClipDerivationService
from app.services.caption_assistant_runtime.shared import parse_json_object
from app.services.caption_assistant_runtime.task_board import TaskBoardService
from app.services.caption_assistant_runtime.tts_service import KokoroTtsService

logger = logging.getLogger(__name__)


class VideoExportService:
    XFADE_TRANSITIONS = {
        "fade",
        "fadeblack",
        "fadewhite",
        "fadegrays",
        "wipeleft",
        "wiperight",
        "wipeup",
        "wipedown",
        "wipetl",
        "wipetr",
        "wipebl",
        "wipebr",
        "slideleft",
        "slideright",
        "slideup",
        "slidedown",
        "revealright",
        "revealleft",
        "revealup",
        "revealdown",
        "horzopen",
        "horzclose",
        "vertopen",
        "vertclose",
        "circleopen",
        "circleclose",
        "circlecrop",
        "rectcrop",
        "hblur",
        "radial",
        "diagtl",
        "diagtr",
        "diagbl",
        "diagbr",
        "dissolve",
        "pixelize",
        "hlslice",
        "hrslice",
        "vuslice",
        "vdslice",
        "zoomin",
        "squeezeh",
        "squeezev",
        "hlwind",
        "hrwind",
        "vuwind",
        "vdwind",
        "coverleft",
        "coverright",
        "coverup",
        "coverdown",
    }

    def __init__(
        self,
        task_board_service: TaskBoardService,
        clip_derivation_service: ClipDerivationService,
        tts_service: KokoroTtsService,
    ) -> None:
        self._task_board_service = task_board_service
        self._clip_derivation_service = clip_derivation_service
        self._tts_service = tts_service

    async def tool_read_video_edit_context(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
    ) -> str:
        del turn
        export_dir = os.path.join(settings.export_dir, session.session_id)
        payload = {
            "video_path": session.video_path,
            "output_dir": export_dir,
            "platform": session.platform,
            "aspect_ratio": working_state.executable_edit.aspect_ratio,
            "burn_subtitles": working_state.executable_edit.burn_subtitles,
            "subtitle_available": bool(working_state.subtitle_draft.strip()),
            "subtitle_preview": working_state.subtitle_draft[:1200],
            "tts_enabled": self._tts_service.is_enabled(),
            "segments": [asdict(segment) for segment in working_state.executable_edit.segments],
            "rendered_segments": [asdict(item) for item in working_state.executable_edit.rendered_segments],
            "next_pending_segment": asdict(next_segment) if (next_segment := self._clip_derivation_service.next_pending_segment(working_state.executable_edit)) else None,
            "last_attempted_command": working_state.edited_video.command,
            "last_error": working_state.edited_video.error_message,
            "merge_error": working_state.executable_edit.merge_error_message,
        }
        return json.dumps(payload, ensure_ascii=False)

    async def tool_render_clip_segment(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        del user_prompt
        decision = working_state.executable_edit
        if not decision.segments:
            raise RuntimeError("当前没有可渲染的片段映射。")
        self._clip_derivation_service.ensure_rendered_segment_entries(decision)

        payload = parse_json_object(action_input)
        segment_id = str(payload.get("segment_id", "")).strip() if isinstance(payload, dict) else ""
        drop_audio = bool(payload.get("drop_audio")) if isinstance(payload, dict) else False
        vf_override = str(payload.get("vf_override", "")).strip() if isinstance(payload, dict) else ""
        af_override = str(payload.get("af_override", "")).strip() if isinstance(payload, dict) else ""
        notes = str(payload.get("notes", "")).strip() if isinstance(payload, dict) else ""

        target_segment = None
        if segment_id:
            for segment in decision.segments:
                if segment.id == segment_id:
                    target_segment = segment
                    break
        if target_segment is None:
            target_segment = self._clip_derivation_service.next_pending_segment(decision)
        if target_segment is None:
            return "所有片段都已经渲染完成。"

        rendered = self._clip_derivation_service.get_rendered_segment(decision, target_segment.id)
        if rendered is None:
            rendered = RenderedClipSegment(segment_id=target_segment.id)
            decision.rendered_segments.append(rendered)

        self._task_board_service.set_task_status(
            turn,
            "run_video_edit_subagent",
            "doing",
            notes=f"正在渲染片段 {target_segment.id}。{notes}".strip(),
            current_focus="run_video_edit_subagent",
        )
        rendered.status = "doing"
        rendered.updated_at = utcnow()

        session_export_dir = os.path.join(settings.export_dir, session.session_id)
        segment_export_dir = os.path.join(session_export_dir, "segments")
        os.makedirs(segment_export_dir, exist_ok=True)
        output_name = f"{turn.turn_id}_{target_segment.id}.mp4"
        output_path = os.path.join(segment_export_dir, output_name)
        command_args = self.build_segment_render_command_args(
            session=session,
            segment=target_segment,
            output_path=output_path,
            aspect_ratio=decision.aspect_ratio,
            drop_audio=drop_audio,
            vf_override=vf_override or None,
            af_override=af_override or None,
        )
        rendered.command = shlex.join(command_args)
        try:
            await self.run_ffmpeg_command(command_args)
            if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError("片段渲染完成，但未生成有效片段文件。")
            probe = self.probe_media(output_path)
            expected_duration = round(float(target_segment.output_duration_seconds or 0), 4)
            actual_duration = round(float(probe.get("duration_seconds") or 0), 4)
            duration_delta = round(abs(actual_duration - expected_duration), 4)
            duration_ok = actual_duration <= expected_duration + 0.3
            rendered.expected_duration_seconds = expected_duration
            rendered.actual_duration_seconds = actual_duration
            rendered.duration_delta_seconds = duration_delta
            rendered.duration_ok = duration_ok
            rendered.probe_metadata = probe
            if not duration_ok:
                raise RuntimeError(
                    f"片段 {target_segment.id} 时长校验失败：expected={expected_duration:.2f}s, "
                    f"actual={actual_duration:.2f}s。当前仅拦截超出目标时长的情况，短于目标时长不会拦截。"
                )
            rendered.status = "done"
            rendered.file_name = output_name
            rendered.storage_path = output_path
            rendered.error_message = ""
            rendered.summary = (
                f"片段 {target_segment.id} 渲染完成，时长 {actual_duration:.2f}s / 目标 {expected_duration:.2f}s。"
            )
            rendered.size_bytes = os.path.getsize(output_path)
            rendered.updated_at = utcnow()
            working_state.edited_video.error_message = ""
            decision.updated_at = rendered.updated_at
            return ToolResult(
                ok=True,
                summary=(
                    f"片段 {target_segment.id} 已渲染完成。"
                    f"\n原视频：{target_segment.source_start}-{target_segment.source_end}"
                    f"\n成片：{target_segment.timeline_start}-{target_segment.timeline_end}"
                    f"\n文件：{output_name}"
                ),
                artifact_type="rendered_segment",
                expected_duration_seconds=expected_duration,
                actual_duration_seconds=actual_duration,
                duration_ok=True,
                probe_metadata=probe,
            )
        except Exception as exc:
            rendered.status = "blocked"
            rendered.error_message = str(exc)
            rendered.duration_ok = False
            rendered.updated_at = utcnow()
            decision.updated_at = rendered.updated_at
            working_state.edited_video.error_message = str(exc)
            return ToolResult(
                ok=False,
                summary=(
                    f"片段 {target_segment.id} 渲染失败，请基于错误修正后重试："
                    f"\n错误：{exc}"
                    f"\n片段：{json.dumps(asdict(target_segment), ensure_ascii=False)}"
                ),
                artifact_type="rendered_segment",
                expected_duration_seconds=round(float(target_segment.output_duration_seconds or 0), 4),
                actual_duration_seconds=round(float(rendered.actual_duration_seconds or 0), 4) or None,
                duration_ok=False,
                probe_metadata=rendered.probe_metadata,
                error=str(exc),
            )

    async def tool_merge_rendered_segments(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        del user_prompt
        decision = working_state.executable_edit
        self._clip_derivation_service.ensure_rendered_segment_entries(decision)

        logger.info(
            "merge_rendered_segments subtitle draft preview: %s",
            (working_state.subtitle_draft or "")[:100],
        )

        if self.decision_requires_transitions(decision):
            return await self.tool_merge_rendered_segments_with_transitions(
                session,
                turn,
                working_state,
                user_prompt,
                action_input,
            )

        payload = parse_json_object(action_input)
        burn_subtitles = decision.burn_subtitles if not isinstance(payload, dict) else bool(payload.get("burn_subtitles", decision.burn_subtitles))
        drop_audio = bool(payload.get("drop_audio")) if isinstance(payload, dict) else False
        tts_language = str(payload.get("tts_language", "")).strip() if isinstance(payload, dict) else ""
        tts_voice = str(payload.get("tts_voice", "")).strip() if isinstance(payload, dict) else ""

        session_export_dir = os.path.join(settings.export_dir, session.session_id)
        os.makedirs(session_export_dir, exist_ok=True)
        concat_list_path = os.path.join(session_export_dir, f"{turn.turn_id}_segments.txt")
        merged_path = os.path.join(session_export_dir, f"{turn.turn_id}_merged.mp4")
        final_path = os.path.join(session_export_dir, f"{turn.turn_id}.mp4")

        with open(concat_list_path, "w", encoding="utf-8") as file:
            for segment in decision.segments:
                rendered = self._clip_derivation_service.get_rendered_segment(decision, segment.id)
                if rendered is None or not rendered.storage_path:
                    raise RuntimeError(f"片段 {segment.id} 尚未渲染完成。")
                abs_path = os.path.abspath(rendered.storage_path)
                if not os.path.exists(abs_path):
                    raise RuntimeError(f"片段 {segment.id} 的渲染文件不存在：{abs_path}")
                file.write(f"file {shlex.quote(abs_path)}\n")

        merge_args = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-video_track_timescale",
            "90000",
        ]
        if drop_audio:
            merge_args.extend(["-an"])
        else:
            merge_args.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"])
        merge_args.append(merged_path)

        try:
            incomplete_segments = self.collect_incomplete_segments(decision)
            if incomplete_segments:
                raise RuntimeError(
                    "仍有片段未完成渲染，不能执行最终合并："
                    + ", ".join(incomplete_segments)
                )
            await self.run_ffmpeg_command(merge_args)
            decision.merge_command = shlex.join(merge_args)
            decision.merged_segments_path = merged_path
            decision.merge_error_message = ""
            merged_probe = self.probe_media(merged_path)
            merged_duration = round(float(merged_probe.get("duration_seconds") or 0), 4)

            subtitle_path = ""
            if burn_subtitles and working_state.subtitle_draft.strip():
                subtitle_path = self.write_subtitle_sidecar(turn.turn_id, working_state.subtitle_draft)
                if not subtitle_path:
                    return ToolResult(
                        ok=False,
                        summary=(
                            "字幕解析失败：字幕草稿中未找到符合 `00:00-00:03 字幕内容` 格式的时间轴！"
                            "请重新调用 write_subtitles，仅传入 guidance 让底层模型重新生成规范格式。"
                        ),
                        artifact_type="edited_video",
                        error=(
                            "字幕解析失败：字幕草稿中未找到符合 `00:00-00:03 字幕内容` 格式的时间轴！"
                        ),
                        error_code="SUBTITLE_TIMELINE_PARSE_FAILED",
                        retry_same_tool_allowed=False,
                        required_action={
                            "tool": "write_subtitles",
                            "input": {
                                "action": "rewrite",
                                "guidance": (
                                    "重新生成规范字幕。每行必须严格为 `00:00-00:03 字幕内容` 格式。"
                                    "不要 markdown、不要表格、不要编号、不要解释文字、不要单点时间戳。"
                                ),
                                "format": "timeline_plain",
                                "strict": True,
                                "total_duration_seconds": decision.total_duration_seconds,
                            },
                        },
                        next_tool="write_subtitles",
                        next_tool_input={
                            "action": "rewrite",
                            "guidance": (
                                "重新生成规范字幕。每行必须严格为 `00:00-00:03 字幕内容` 格式。"
                                "不要 markdown、不要表格、不要编号、不要解释文字、不要单点时间戳。"
                            ),
                            "format": "timeline_plain",
                            "strict": True,
                            "total_duration_seconds": decision.total_duration_seconds,
                        },
                        duration_ok=False,
                    )
            tts_audio_path = ""
            tts_metadata: Dict[str, Any] = {}
            if (
                not drop_audio
                and self._tts_service.is_enabled()
                and working_state.subtitle_draft.strip()
            ):
                tts_audio_path = os.path.join(session_export_dir, f"{turn.turn_id}_tts.wav")
                tts_metadata = self._tts_service.synthesize_timeline_audio(
                    subtitle_draft=working_state.subtitle_draft,
                    output_path=tts_audio_path,
                    target_duration_seconds=merged_duration,
                    language_hint=tts_language or None,
                    voice_hint=tts_voice or None,
                )

            if subtitle_path or tts_audio_path:
                final_args = ["ffmpeg", "-y", "-i", merged_path]
                if tts_audio_path:
                    final_args.extend(["-i", tts_audio_path])
                if subtitle_path:
                    escaped_subtitle = self.escape_subtitle_filter_path(subtitle_path)
                    final_args.extend(["-vf", f"subtitles={escaped_subtitle}"])
                final_args.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "23"])
                if tts_audio_path:
                    final_args.extend(
                        [
                            "-map",
                            "0:v:0",
                            "-map",
                            "1:a:0",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "128k",
                            "-ar",
                            "48000",
                            "-ac",
                            "1",
                        ]
                    )
                elif drop_audio:
                    final_args.extend(["-an"])
                else:
                    final_args.extend(["-c:a", "aac", "-b:a", "128k"])
                final_args.append(final_path)
                await self.run_ffmpeg_command(final_args)
                final_command = shlex.join(final_args)
            else:
                final_command = shlex.join(merge_args)
                if merged_path != final_path:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    os.replace(merged_path, final_path)

            final_probe = self.probe_media(final_path)
            expected_total_duration = round(
                sum(float(segment.output_duration_seconds or 0) for segment in decision.segments),
                4,
            )
            actual_total_duration = round(float(final_probe.get("duration_seconds") or 0), 4)
            duration_delta = round(abs(actual_total_duration - expected_total_duration), 4)
            target_duration = round(float(decision.total_duration_seconds or expected_total_duration), 4)
            duration_ok = (
                actual_total_duration <= expected_total_duration + 1.0
                and actual_total_duration <= target_duration + 1.0
            )
            if not duration_ok:
                raise RuntimeError(
                    "最终成片时长校验失败："
                    f" expected_total={expected_total_duration:.2f}s,"
                    f" actual_total={actual_total_duration:.2f}s,"
                    f" target={target_duration:.2f}s,"
                    " 当前仅拦截超出目标时长的情况，短于目标时长不会再触发死循环重试。"
                )

            working_state.edited_video = EditedVideoArtifact(
                file_name=os.path.basename(final_path),
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video?v={turn.turn_id}",
                storage_path=final_path,
                command=final_command,
                summary=(
                    (decision.summary or turn.user_prompt.strip())
                    + f"\n实际导出时长：{actual_total_duration:.2f}s"
                    + f"\n目标时长：{target_duration:.2f}s"
                    + (
                        f"\nTTS：{tts_metadata.get('voice', '')} / {tts_metadata.get('cue_count', 0)} 条字幕"
                        if tts_metadata
                        else ""
                    )
                ),
                error_message="",
                size_bytes=os.path.getsize(final_path),
                expected_duration_seconds=expected_total_duration,
                actual_duration_seconds=actual_total_duration,
                duration_ok=True,
                probe_metadata={
                    **final_probe,
                    "tts": tts_metadata,
                },
            )
            self._task_board_service.complete_workflow_artifact(working_state, "edited_video", "剪辑视频已导出，可在右侧下载。")
            self._task_board_service.set_task_status(turn, "verify_export", "done", notes="已生成可下载成片。")
            return ToolResult(
                ok=True,
                summary=(
                    "片段已合并并生成最终成片。"
                    f"\n文件名：{working_state.edited_video.file_name}"
                    f"\n下载地址：{working_state.edited_video.download_url}"
                ),
                artifact_type="edited_video",
                expected_duration_seconds=expected_total_duration,
                actual_duration_seconds=actual_total_duration,
                duration_ok=True,
                probe_metadata={
                    **final_probe,
                    "tts": tts_metadata,
                },
            )
        except Exception as exc:
            decision.merge_error_message = str(exc)
            working_state.edited_video.error_message = str(exc)
            self._task_board_service.update_workflow_artifact(
                working_state,
                "edited_video",
                status="error",
                detail=str(exc),
                requested=True,
                needs_refresh=False,
            )
            return ToolResult(
                ok=False,
                summary=f"片段合并失败：{exc}",
                artifact_type="edited_video",
                duration_ok=False,
                error=str(exc),
            )

    async def tool_merge_rendered_segments_with_transitions(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        del user_prompt
        decision = working_state.executable_edit
        self._clip_derivation_service.ensure_rendered_segment_entries(decision)
        payload = parse_json_object(action_input)
        if not isinstance(payload, dict):
            payload = {}

        burn_subtitles = bool(payload.get("burn_subtitles", decision.burn_subtitles))
        drop_audio = bool(payload.get("drop_audio"))
        fps = int(payload.get("fps", 30) or 30)
        summary = str(payload.get("summary", "")).strip()
        tts_language = str(payload.get("tts_language", "")).strip()
        tts_voice = str(payload.get("tts_voice", "")).strip()
        default_transition = str(payload.get("default_transition", "fade")).strip() or "fade"
        default_duration = float(payload.get("default_duration_seconds", 1.0) or 1.0)
        use_segment_transition_metadata = bool(payload.get("use_segment_transition_metadata", True))

        ordered_clips = self.collect_rendered_transition_clips(decision)
        if len(ordered_clips) < 2:
            raise RuntimeError("至少需要 2 个已渲染片段，才能添加转场合并。")

        transition_specs = self.normalize_transition_specs(
            segments=decision.segments,
            raw_transitions=payload.get("transitions"),
            default_transition=default_transition,
            default_duration=default_duration,
            use_segment_transition_metadata=use_segment_transition_metadata,
        )

        width, height = self.resolution_for_aspect_ratio(decision.aspect_ratio)
        session_export_dir = os.path.join(settings.export_dir, session.session_id)
        os.makedirs(session_export_dir, exist_ok=True)
        transitioned_path = os.path.join(session_export_dir, f"{turn.turn_id}_transitioned.mp4")
        final_path = os.path.join(session_export_dir, f"{turn.turn_id}.mp4")

        input_args: List[str] = []
        filter_parts: List[str] = []
        durations: List[float] = []
        any_audio = False

        for index, clip in enumerate(ordered_clips):
            input_args.extend(["-i", clip["path"]])
            durations.append(float(clip["duration_seconds"]))
            filter_parts.append(
                f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p,settb=AVTB[v{index}]"
            )
            if not drop_audio:
                if clip["has_audio"]:
                    any_audio = True
                    filter_parts.append(
                        f"[{index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]"
                    )
                else:
                    filter_parts.append(
                        f"anullsrc=r=48000:cl=stereo,atrim=duration={durations[-1]},asetpts=PTS-STARTPTS[a{index}]"
                    )

        current_video = "v0"
        current_audio = "a0"
        accumulated_duration = durations[0]
        transition_names: List[str] = []

        for index, spec in enumerate(transition_specs):
            transition_name = str(spec["transition"])
            transition_duration = float(spec["duration_seconds"])
            if transition_duration >= accumulated_duration or transition_duration >= durations[index + 1]:
                raise RuntimeError(
                    f"第 {index + 1} 个转场时长 {transition_duration:.2f}s 过长，必须短于当前累计时长 {accumulated_duration:.2f}s"
                    f" 且短于下一个片段时长 {durations[index + 1]:.2f}s。"
                )
            offset = round(accumulated_duration - transition_duration, 4)
            next_video = f"vx{index + 1}"
            next_audio = f"ax{index + 1}"
            expr_part = (
                f":expr='{self.escape_filter_value(str(spec['custom_expr']))}'"
                if transition_name == "custom"
                else ""
            )
            filter_parts.append(
                f"[{current_video}][v{index + 1}]xfade=transition={transition_name}:duration={transition_duration}:offset={offset}{expr_part}[{next_video}]"
            )
            if not drop_audio and any_audio and bool(spec.get("audio_crossfade", True)):
                filter_parts.append(
                    f"[{current_audio}][a{index + 1}]acrossfade=d={transition_duration}:c1={spec['audio_curve1']}:c2={spec['audio_curve2']}[{next_audio}]"
                )
                current_audio = next_audio
            elif not drop_audio and any_audio:
                filter_parts.append(f"[{current_audio}][a{index + 1}]concat=n=2:v=0:a=1[{next_audio}]")
                current_audio = next_audio
            current_video = next_video
            accumulated_duration = accumulated_duration + durations[index + 1] - transition_duration
            transition_names.append(transition_name)

        transition_args = [
            "ffmpeg",
            "-y",
            *input_args,
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            f"[{current_video}]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-video_track_timescale",
            "90000",
        ]
        if not drop_audio and any_audio:
            transition_args.extend(
                [
                    "-map",
                    f"[{current_audio}]",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                ]
            )
        else:
            transition_args.extend(["-an"])
        transition_args.append(transitioned_path)

        try:
            incomplete_segments = self.collect_incomplete_segments(decision)
            if incomplete_segments:
                raise RuntimeError("仍有片段未完成渲染，不能执行转场合并：" + ", ".join(incomplete_segments))

            await self.run_ffmpeg_command(transition_args)
            decision.merge_command = shlex.join(transition_args)
            decision.merged_segments_path = transitioned_path
            decision.merge_error_message = ""

            final_command = decision.merge_command
            final_probe, final_path, final_command = await self.finalize_video_output(
                source_video_path=transitioned_path,
                session=session,
                turn=turn,
                working_state=working_state,
                burn_subtitles=burn_subtitles,
                drop_audio=drop_audio,
                final_path=final_path,
                tts_language=tts_language,
                tts_voice=tts_voice,
                default_command=decision.merge_command,
            )

            expected_total_duration = round(
                sum(float(segment.output_duration_seconds or 0) for segment in decision.segments) - sum(float(spec["duration_seconds"]) for spec in transition_specs),
                4,
            )
            actual_total_duration = round(float(final_probe.get("duration_seconds") or 0), 4)
            duration_ok = actual_total_duration <= expected_total_duration + 1.0
            if not duration_ok:
                raise RuntimeError(
                    "最终成片时长校验失败："
                    f" expected_total={expected_total_duration:.2f}s,"
                    f" actual_total={actual_total_duration:.2f}s。"
                )

            working_state.edited_video = EditedVideoArtifact(
                file_name=os.path.basename(final_path),
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video?v={turn.turn_id}",
                storage_path=final_path,
                command=final_command,
                summary=(
                    (summary or decision.summary or turn.user_prompt.strip())
                    + f"\n转场：{', '.join(transition_names)}"
                    + f"\n实际导出时长：{actual_total_duration:.2f}s"
                ),
                error_message="",
                size_bytes=os.path.getsize(final_path),
                expected_duration_seconds=expected_total_duration,
                actual_duration_seconds=actual_total_duration,
                duration_ok=True,
                probe_metadata=final_probe,
            )
            self._task_board_service.complete_workflow_artifact(working_state, "edited_video", "带转场的视频已导出，可在右侧下载。")
            self._task_board_service.set_task_status(turn, "verify_export", "done", notes="已生成带转场的可下载成片。")
            return ToolResult(
                ok=True,
                summary=(
                    "片段已按转场顺序合并并生成最终成片。"
                    f"\n转场：{', '.join(transition_names)}"
                    f"\n文件名：{working_state.edited_video.file_name}"
                    f"\n下载地址：{working_state.edited_video.download_url}"
                ),
                artifact_type="edited_video",
                expected_duration_seconds=expected_total_duration,
                actual_duration_seconds=actual_total_duration,
                duration_ok=True,
                probe_metadata=final_probe,
            )
        except Exception as exc:
            decision.merge_error_message = str(exc)
            working_state.edited_video.error_message = str(exc)
            self._task_board_service.update_workflow_artifact(
                working_state,
                "edited_video",
                status="error",
                detail=str(exc),
                requested=True,
                needs_refresh=False,
            )
            return ToolResult(
                ok=False,
                summary=f"带转场的片段合并失败：{exc}",
                artifact_type="edited_video",
                duration_ok=False,
                error=str(exc),
            )

    async def tool_apply_fade_effect(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        del user_prompt
        payload = parse_json_object(action_input)
        if not isinstance(payload, dict):
            payload = {}

        target = str(payload.get("target", "edited_video")).strip() or "edited_video"
        fade_in_seconds = float(payload.get("fade_in_seconds", 0.0) or 0.0)
        fade_out_seconds = float(payload.get("fade_out_seconds", 0.0) or 0.0)
        fade_out_start_seconds = payload.get("fade_out_start_seconds")
        color = str(payload.get("color", "black")).strip() or "black"
        fade_audio = bool(payload.get("fade_audio", True))
        output_extension = str(payload.get("output_extension", "mp4")).strip().lstrip(".") or "mp4"
        summary = str(payload.get("summary", "")).strip()

        source_path = self.resolve_fade_source_path(
            session=session,
            working_state=working_state,
            target=target,
            segment_id=str(payload.get("segment_id", "")).strip() or None,
        )
        probe = self.probe_media(source_path)
        total_duration = float(probe.get("duration_seconds") or 0.0)
        if total_duration <= 0:
            raise RuntimeError("无法读取目标视频时长，不能应用淡入淡出。")

        video_filters: List[str] = []
        audio_filters: List[str] = []
        if fade_in_seconds > 0:
            video_filters.append(f"fade=t=in:st=0:d={fade_in_seconds}:color={color}")
            if fade_audio and self.media_has_audio_stream(probe):
                audio_filters.append(f"afade=t=in:st=0:d={fade_in_seconds}")
        if fade_out_seconds > 0:
            fade_out_start = (
                float(fade_out_start_seconds)
                if fade_out_start_seconds is not None
                else max(total_duration - fade_out_seconds, 0.0)
            )
            video_filters.append(f"fade=t=out:st={round(fade_out_start, 4)}:d={fade_out_seconds}:color={color}")
            if fade_audio and self.media_has_audio_stream(probe):
                audio_filters.append(f"afade=t=out:st={round(fade_out_start, 4)}:d={fade_out_seconds}")
        if not video_filters:
            raise RuntimeError("至少需要提供 fade_in_seconds 或 fade_out_seconds 之一。")

        session_export_dir = os.path.join(settings.export_dir, session.session_id)
        os.makedirs(session_export_dir, exist_ok=True)
        output_path = os.path.join(session_export_dir, f"{turn.turn_id}_fade.{output_extension}")
        command_args = [
            "ffmpeg",
            "-y",
            "-i",
            source_path,
            "-vf",
            ",".join(video_filters),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
        ]
        if audio_filters:
            command_args.extend(["-af", ",".join(audio_filters), "-c:a", "aac", "-b:a", "128k"])
        elif self.media_has_audio_stream(probe):
            command_args.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            command_args.extend(["-an"])
        command_args.append(output_path)

        await self.run_ffmpeg_command(command_args)
        final_probe = self.probe_media(output_path)
        actual_duration = round(float(final_probe.get("duration_seconds") or 0), 4)
        working_state.edited_video = EditedVideoArtifact(
            file_name=os.path.basename(output_path),
            download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video?v={turn.turn_id}",
            storage_path=output_path,
            command=shlex.join(command_args),
            summary=(summary or f"已对 {target} 应用淡入淡出") + f"\n实际导出时长：{actual_duration:.2f}s",
            error_message="",
            size_bytes=os.path.getsize(output_path),
            expected_duration_seconds=round(total_duration, 4),
            actual_duration_seconds=actual_duration,
            duration_ok=True,
            probe_metadata=final_probe,
        )
        self._task_board_service.complete_workflow_artifact(working_state, "edited_video", "淡入淡出效果已导出，可在右侧下载。")
        self._task_board_service.set_task_status(turn, "verify_export", "done", notes="已生成带淡入淡出的可下载成片。")
        return ToolResult(
            ok=True,
            summary=(
                "淡入淡出效果已应用完成。"
                f"\n文件名：{working_state.edited_video.file_name}"
                f"\n下载地址：{working_state.edited_video.download_url}"
            ),
            artifact_type="edited_video",
            expected_duration_seconds=round(total_duration, 4),
            actual_duration_seconds=actual_duration,
            duration_ok=True,
            probe_metadata=final_probe,
        )

    async def tool_run_bash_ffmpeg(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        attempted_command = ""
        try:
            self._task_board_service.set_task_status(turn, "run_video_edit_subagent", "doing", notes="正在执行 ffmpeg 导出。")
            if shutil.which("ffmpeg") is None:
                raise RuntimeError("当前运行环境未安装 ffmpeg，无法执行视频导出。")

            payload = self.parse_ffmpeg_command_input(action_input)
            command_template = payload["command_template"]
            needs_subtitle_file = payload["needs_subtitle_file"]
            output_extension = payload["output_extension"]
            summary = payload["summary"] or user_prompt.strip()

            subtitle_path = ""
            if needs_subtitle_file:
                subtitle_path = self.write_subtitle_sidecar(turn.turn_id, working_state.subtitle_draft)
                if not subtitle_path:
                    raise RuntimeError("当前没有可解析成 SRT 的字幕草稿，无法执行需要字幕文件的 ffmpeg 导出。")

            session_export_dir = os.path.join(settings.export_dir, session.session_id)
            os.makedirs(session_export_dir, exist_ok=True)
            output_name = f"{turn.turn_id}.{output_extension}"
            output_path = os.path.join(session_export_dir, output_name)
            command_args = self.materialize_ffmpeg_command_args(
                command_template=command_template,
                input_video=session.video_path,
                output_video=output_path,
                subtitle_file=subtitle_path or None,
            )
            attempted_command = shlex.join(command_args)
            await self.run_ffmpeg_command(command_args)
            if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError("ffmpeg 命令执行完成，但未生成有效导出文件。")
            probe = self.probe_media(output_path)
            actual_duration = round(float(probe.get("duration_seconds") or 0), 4)

            working_state.edited_video = EditedVideoArtifact(
                file_name=output_name,
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video?v={turn.turn_id}",
                storage_path=output_path,
                command=attempted_command,
                summary=summary + f"\n实际导出时长：{actual_duration:.2f}s",
                error_message="",
                size_bytes=os.path.getsize(output_path),
                actual_duration_seconds=actual_duration,
                duration_ok=True,
                probe_metadata=probe,
            )
            self._task_board_service.complete_workflow_artifact(working_state, "edited_video", "剪辑视频已导出，可在右侧下载。")
            self._task_board_service.set_task_status(turn, "run_video_edit_subagent", "done", notes="ffmpeg 导出已完成。", current_focus="verify_export")
            self._task_board_service.set_task_status(turn, "verify_export", "done", notes="已生成可下载成片。")
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
            self._task_board_service.update_workflow_artifact(
                working_state,
                "edited_video",
                status="error",
                detail=str(exc),
                requested=True,
                needs_refresh=False,
            )
            self._task_board_service.set_task_status(
                turn,
                "run_video_edit_subagent",
                "blocked",
                notes=str(exc),
                current_focus="run_video_edit_subagent",
                blocked_reason=str(exc),
            )
            self._task_board_service.set_task_status(
                turn,
                "verify_export",
                "todo",
                notes="等待修正 ffmpeg 命令并重新导出。",
            )
            return (
                "ffmpeg 导出失败，请根据以下信息修正参数后重试："
                f"\n错误：{exc}"
                f"\n当前输入视频路径：{session.video_path}"
                f"\n当前输出目录：{session_export_dir}"
                f"\n当前字幕文件占位符：{{{{subtitle_file}}}}"
                "\n注意：不要显式传入 -i 输入路径，不要传 input/output 占位符，服务端会自动注入。"
                "\n不要向用户确认视频路径，直接基于当前路径和错误信息修正命令。"
                '\n推荐改用 JSON 重新调用：{"command_template":"-vf ... -c:v libx264 -c:a aac","output_extension":"mp4","summary":"...","needs_subtitle_file":false}'
            )

    def build_segment_render_command_args(
        self,
        *,
        session: CaptionSession,
        segment: Any,
        output_path: str,
        aspect_ratio: str,
        drop_audio: bool,
        vf_override: str | None = None,
        af_override: str | None = None,
    ) -> List[str]:
        width, height = self.resolution_for_aspect_ratio(aspect_ratio)
        start = self._clip_derivation_service.timestamp_to_seconds(segment.source_start)
        end = self._clip_derivation_service.timestamp_to_seconds(segment.source_end)
        if end <= start:
            raise RuntimeError(f"片段 {segment.id} 的 source_end 必须大于 source_start。")
        source_duration = round(float(segment.source_duration_seconds or (end - start)), 4)
        expected_duration = round(float(segment.output_duration_seconds or 0), 4)
        if source_duration <= 0 or expected_duration <= 0:
            raise RuntimeError(f"片段 {segment.id} 的目标时长无效。")
        speed = round(max(0.25, source_duration / expected_duration), 4)
        setpts = f"(PTS-STARTPTS)/{speed}"
        vf = (
            vf_override.strip()
            if vf_override and vf_override.strip()
            else (
                f"setpts={setpts},trim=duration={expected_duration},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            )
        )
        args = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-to",
            str(end),
            "-i",
            session.video_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-video_track_timescale",
            "90000",
        ]
        has_audio = self.video_has_audio_stream(session.video_path)
        if drop_audio or not has_audio:
            args.extend(["-an"])
        else:
            args.extend(["-map", "0:v:0", "-map", "0:a:0"])
            if af_override and af_override.strip():
                audio_filter = af_override.strip()
            else:
                audio_filter = ",".join(
                    [*self.build_atempo_filters(speed), f"atrim=duration={expected_duration}", "asetpts=PTS-STARTPTS"]
                )
            if audio_filter:
                args.extend(["-af", audio_filter])
            args.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"])
        args.extend(["-t", str(expected_duration)])
        args.append(output_path)
        return args

    def collect_rendered_transition_clips(self, decision: Any) -> List[Dict[str, Any]]:
        ordered_clips: List[Dict[str, Any]] = []
        for segment in decision.segments:
            rendered = self._clip_derivation_service.get_rendered_segment(decision, segment.id)
            if rendered is None or rendered.status != "done" or not rendered.storage_path:
                raise RuntimeError(f"片段 {segment.id} 尚未渲染完成，无法用于转场合并。")
            if not os.path.exists(rendered.storage_path):
                raise RuntimeError(f"片段 {segment.id} 的渲染文件不存在：{rendered.storage_path}")
            probe = rendered.probe_metadata or self.probe_media(rendered.storage_path)
            duration_seconds = float(rendered.actual_duration_seconds or probe.get("duration_seconds") or 0.0)
            if duration_seconds <= 0:
                raise RuntimeError(f"片段 {segment.id} 的实际时长无效，无法用于转场合并。")
            ordered_clips.append(
                {
                    "segment_id": segment.id,
                    "path": rendered.storage_path,
                    "duration_seconds": duration_seconds,
                    "has_audio": self.media_has_audio_stream(probe),
                }
            )
        return ordered_clips

    def decision_requires_transitions(self, decision: Any) -> bool:
        segments = list(getattr(decision, "segments", []) or [])
        if len(segments) < 2:
            return False
        for segment in segments[:-1]:
            transition_name = str(getattr(segment, "transition_to_next", "") or "").strip().lower()
            if transition_name and transition_name not in {"hard_cut", "cut", "none"}:
                return True
        return False

    def normalize_transition_specs(
        self,
        *,
        segments: List[Any],
        raw_transitions: Any,
        default_transition: str,
        default_duration: float,
        use_segment_transition_metadata: bool,
    ) -> List[Dict[str, Any]]:
        clip_count = len(segments)
        if clip_count < 2:
            return []
        normalized_default = self.normalize_transition_name(default_transition)
        if normalized_default == "custom":
            raise RuntimeError("default_transition 不能为 custom；请在 transitions 列表里为每个切点单独提供 custom_expr。")

        source_items = raw_transitions if isinstance(raw_transitions, list) else []
        result: List[Dict[str, Any]] = []
        for index in range(clip_count - 1):
            raw_item = source_items[index] if index < len(source_items) and isinstance(source_items[index], dict) else {}
            transition_name = str(raw_item.get("transition", "")).strip()
            custom_expr = str(raw_item.get("custom_expr", "")).strip() or None
            if not transition_name and use_segment_transition_metadata:
                transition_name = str(getattr(segments[index], "transition_to_next", "") or "").strip()
            if transition_name.lower() in {"hard_cut", "cut", "none"}:
                transition_name = ""
            normalized_name = self.normalize_transition_name(transition_name or normalized_default)
            duration_seconds = float(raw_item.get("duration_seconds", default_duration) or default_duration)
            if normalized_name == "custom" and not custom_expr:
                raise RuntimeError(f"第 {index + 1} 个转场声明为 custom，但未提供 custom_expr。")
            result.append(
                {
                    "transition": normalized_name,
                    "duration_seconds": duration_seconds,
                    "custom_expr": custom_expr,
                    "audio_crossfade": bool(raw_item.get("audio_crossfade", True)),
                    "audio_curve1": str(raw_item.get("audio_curve1", "tri")).strip() or "tri",
                    "audio_curve2": str(raw_item.get("audio_curve2", "tri")).strip() or "tri",
                }
            )
        return result

    def normalize_transition_name(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "":
            return "fade"
        if normalized == "custom":
            return normalized
        if normalized not in self.XFADE_TRANSITIONS:
            raise RuntimeError(f"不支持的转场类型：{value}")
        return normalized

    def build_filter_complex_for_segments(
        self,
        *,
        segments: List[Any],
        aspect_ratio: str,
        subtitle_file: str | None,
    ) -> tuple[str, str]:
        width, height = self.resolution_for_aspect_ratio(aspect_ratio)
        parts: List[str] = []
        concat_inputs: List[str] = []
        for index, segment in enumerate(segments):
            start = self._clip_derivation_service.timestamp_to_seconds(segment.source_start)
            end = self._clip_derivation_service.timestamp_to_seconds(segment.source_end)
            if end <= start:
                raise RuntimeError(f"片段 {segment.id} 的 source_end 必须大于 source_start。")
            speed = max(0.5, min(2.0, float(segment.speed or 1.0)))
            video_pts = "PTS-STARTPTS" if abs(speed - 1.0) < 1e-6 else f"(PTS-STARTPTS)/{speed}"
            audio_filters = [f"atrim=start={start}:end={end}", "asetpts=PTS-STARTPTS"]
            if abs(speed - 1.0) >= 1e-6:
                audio_filters.extend(self.build_atempo_filters(speed))
            parts.append(
                f"[0:v]trim=start={start}:end={end},setpts={video_pts},"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[v{index}]"
            )
            parts.append(f"[0:a]{','.join(audio_filters)}[a{index}]")
            concat_inputs.append(f"[v{index}][a{index}]")

        parts.append(f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a=1[vcat][aout]")
        if subtitle_file:
            escaped_subtitle = self.escape_subtitle_filter_path(subtitle_file)
            parts.append(f"[vcat]subtitles='{escaped_subtitle}'[vout]")
        else:
            parts.append("[vcat]null[vout]")

        return ";".join(parts), "-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart"

    def build_atempo_filters(self, speed: float) -> List[str]:
        remaining = speed
        filters: List[str] = []
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:.4f}".rstrip("0").rstrip("."))
        return filters

    def resolution_for_aspect_ratio(self, aspect_ratio: str) -> tuple[int, int]:
        mapping = {
            "9:16": (1080, 1920),
            "1:1": (1080, 1080),
            "16:9": (1920, 1080),
        }
        return mapping.get(aspect_ratio.strip(), (1080, 1920))

    def collect_incomplete_segments(self, decision: Any) -> List[str]:
        self._clip_derivation_service.ensure_rendered_segment_entries(decision)
        incomplete: List[str] = []
        for segment in decision.segments:
            rendered = self._clip_derivation_service.get_rendered_segment(decision, segment.id)
            if rendered is None:
                incomplete.append(f"{segment.id}:missing")
                continue
            if rendered.status != "done":
                incomplete.append(f"{segment.id}:{rendered.status}")
                continue
            if not rendered.storage_path or not os.path.exists(rendered.storage_path):
                incomplete.append(f"{segment.id}:missing_file")
                continue
            if not rendered.duration_ok:
                incomplete.append(f"{segment.id}:duration_invalid")
        return incomplete

    def probe_media(self, media_path: str) -> Dict[str, Any]:
        if shutil.which("ffprobe") is None:
            raise RuntimeError("当前运行环境未安装 ffprobe，无法校验导出时长。")
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                media_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"ffprobe 校验失败：{stderr[-1000:]}")
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"ffprobe 输出解析失败：{exc}") from exc
        format_payload = payload.get("format", {}) if isinstance(payload, dict) else {}
        duration_raw = format_payload.get("duration", 0)
        try:
            duration_seconds = float(duration_raw or 0)
        except (TypeError, ValueError):
            duration_seconds = 0.0
        return {
            "duration_seconds": round(duration_seconds, 4),
            "format": format_payload,
            "streams": payload.get("streams", []) if isinstance(payload, dict) else [],
            "path": media_path,
        }

    def media_has_audio_stream(self, probe_or_path: Dict[str, Any] | str) -> bool:
        probe = probe_or_path if isinstance(probe_or_path, dict) else self.probe_media(probe_or_path)
        for stream in probe.get("streams", []):
            if isinstance(stream, dict) and stream.get("codec_type") == "audio":
                return True
        return False

    def escape_subtitle_filter_path(self, path: str) -> str:
        return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    def escape_filter_value(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    def parse_ffmpeg_command_input(self, action_input: str) -> Dict[str, Any]:
        parsed = parse_json_object(action_input)
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
            raise RuntimeError("ffmpeg 命令不能为空。请先读取 ffmpeg skill，再给出明确的 ffmpeg 参数或命令。")
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
        if "\n" in normalized_template or "\r" in normalized_template or "\x00" in normalized_template:
            raise RuntimeError("ffmpeg 命令模板包含非法控制字符。")
        if any(token in normalized_template for token in ["&&", "||", "`", "$("]):
            raise RuntimeError("ffmpeg 命令模板包含不被允许的 shell 执行语法。")
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

    def write_subtitle_sidecar(self, turn_id: str, subtitle_draft: str) -> str:
        srt_content = self.subtitle_draft_to_srt(subtitle_draft)
        if not srt_content:
            return ""
        file_path = os.path.join(settings.export_dir, f"{turn_id}.srt")
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(srt_content)
        return file_path

    def subtitle_draft_to_srt(self, subtitle_draft: str) -> str:
        if not subtitle_draft.strip():
            return ""

        entries: List[str] = []
        pattern = re.compile(
            r"^[\s\*\-\.]*(?P<start>\d{1,2}:\d{2}(?::\d{2})?)[\s\*]*[-—–~to]+[\s\*]*(?P<end>\d{1,2}:\d{2}(?::\d{2})?)[\s\*:]+(?P<text>.+)$"
        )
        for line in subtitle_draft.splitlines():
            normalized_line = line.strip().strip("\"'“”‘’")
            match = pattern.match(normalized_line)
            if not match:
                continue
            start = self.to_srt_timestamp(match.group("start"))
            end = self.to_srt_timestamp(match.group("end"))
            text = match.group("text").strip().strip("\"'“”‘’")
            if not text:
                continue
            entries.append(f"{len(entries) + 1}\n{start} --> {end}\n{text}\n")
        return "\n".join(entries).strip()

    def to_srt_timestamp(self, value: str) -> str:
        parts = value.split(":")
        if len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        else:
            hours, minutes, seconds = parts
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},000"

    def materialize_ffmpeg_command_args(
        self,
        *,
        command_template: str,
        input_video: str,
        output_video: str,
        subtitle_file: str | None,
    ) -> List[str]:
        args = command_template[len("ffmpeg") :].strip() if command_template.startswith("ffmpeg") else command_template.strip()
        if "{{subtitle_file}}" in args:
            if not subtitle_file:
                raise RuntimeError("ffmpeg 命令要求字幕文件，但当前没有可用的 subtitle_file。")
            args = args.replace("{{subtitle_file}}", subtitle_file)
        command_args = ["ffmpeg", "-y", "-i", input_video]
        if args:
            try:
                command_args.extend(shlex.split(args))
            except ValueError as exc:
                raise RuntimeError(f"ffmpeg 命令模板无法解析，请检查引号或参数格式：{exc}") from exc
        command_args.append(output_video)
        return command_args

    def resolve_fade_source_path(
        self,
        *,
        session: CaptionSession,
        working_state: GlobalEditingState,
        target: str,
        segment_id: str | None,
    ) -> str:
        if target == "edited_video":
            if not working_state.edited_video.storage_path:
                raise RuntimeError("当前没有可用的 edited_video。")
            return working_state.edited_video.storage_path
        if target == "merged_video":
            if not working_state.executable_edit.merged_segments_path:
                raise RuntimeError("当前没有可用的 merged_video。")
            return working_state.executable_edit.merged_segments_path
        if target == "session_video":
            return session.video_path
        if target == "rendered_segment":
            if not segment_id:
                raise RuntimeError("target=rendered_segment 时必须提供 segment_id。")
            rendered = self._clip_derivation_service.get_rendered_segment(working_state.executable_edit, segment_id)
            if rendered is None or not rendered.storage_path:
                raise RuntimeError(f"找不到 segment_id={segment_id} 对应的已渲染片段。")
            return rendered.storage_path
        raise RuntimeError(f"不支持的 fade target：{target}")

    async def finalize_video_output(
        self,
        *,
        source_video_path: str,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        burn_subtitles: bool,
        drop_audio: bool,
        final_path: str,
        tts_language: str,
        tts_voice: str,
        default_command: str,
    ) -> tuple[Dict[str, Any], str, str]:
        merged_probe = self.probe_media(source_video_path)
        merged_duration = round(float(merged_probe.get("duration_seconds") or 0), 4)

        subtitle_path = ""
        if burn_subtitles and working_state.subtitle_draft.strip():
            subtitle_path = self.write_subtitle_sidecar(turn.turn_id, working_state.subtitle_draft)
            if not subtitle_path:
                raise RuntimeError("字幕解析失败：字幕草稿中未找到符合 `00:00-00:03 字幕内容` 格式的时间轴。")

        session_export_dir = os.path.join(settings.export_dir, session.session_id)
        tts_audio_path = ""
        if (
            not drop_audio
            and self._tts_service.is_enabled()
            and working_state.subtitle_draft.strip()
        ):
            tts_audio_path = os.path.join(session_export_dir, f"{turn.turn_id}_tts.wav")
            self._tts_service.synthesize_timeline_audio(
                subtitle_draft=working_state.subtitle_draft,
                output_path=tts_audio_path,
                target_duration_seconds=merged_duration,
                language_hint=tts_language or None,
                voice_hint=tts_voice or None,
            )

        if subtitle_path or tts_audio_path:
            final_args = ["ffmpeg", "-y", "-i", source_video_path]
            if tts_audio_path:
                final_args.extend(["-i", tts_audio_path])
            if subtitle_path:
                escaped_subtitle = self.escape_subtitle_filter_path(subtitle_path)
                final_args.extend(["-vf", f"subtitles={escaped_subtitle}"])
            final_args.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "23"])
            if tts_audio_path:
                final_args.extend(
                    [
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        "-ar",
                        "48000",
                        "-ac",
                        "1",
                    ]
                )
            elif drop_audio:
                final_args.extend(["-an"])
            else:
                final_args.extend(["-c:a", "aac", "-b:a", "128k"])
            final_args.append(final_path)
            await self.run_ffmpeg_command(final_args)
            return self.probe_media(final_path), final_path, shlex.join(final_args)

        if source_video_path != final_path:
            if os.path.exists(final_path):
                os.remove(final_path)
            os.replace(source_video_path, final_path)
        return self.probe_media(final_path), final_path, default_command

    async def run_ffmpeg_command(self, command_args: List[str]) -> None:
        process = await asyncio.create_subprocess_exec(
            *command_args,
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

    def video_has_audio_stream(self, video_path: str) -> bool:
        if shutil.which("ffprobe") is None:
            return False
        try:
            import subprocess

            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0 and "audio" in (result.stdout or "")
        except Exception:
            return False
