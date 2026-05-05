from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
from dataclasses import asdict
from typing import Any, Dict, List

from app.core.config import settings
from app.models import AgentTurn, CaptionSession, EditedVideoArtifact, GlobalEditingState, RenderedClipSegment, utcnow
from app.services.caption_assistant_runtime.clip_derivation import ClipDerivationService
from app.services.caption_assistant_runtime.shared import parse_json_object
from app.services.caption_assistant_runtime.task_board import TaskBoardService

logger = logging.getLogger(__name__)


class VideoExportService:
    def __init__(
        self,
        task_board_service: TaskBoardService,
        clip_derivation_service: ClipDerivationService,
    ) -> None:
        self._task_board_service = task_board_service
        self._clip_derivation_service = clip_derivation_service

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
        speed_override = payload.get("speed") if isinstance(payload, dict) else None
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
            speed_override=float(speed_override) if speed_override is not None else None,
            vf_override=vf_override or None,
            af_override=af_override or None,
        )
        rendered.command = shlex.join(command_args)
        try:
            await self.run_ffmpeg_command(command_args)
            if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError("片段渲染完成，但未生成有效片段文件。")
            rendered.status = "done"
            rendered.file_name = output_name
            rendered.storage_path = output_path
            rendered.error_message = ""
            rendered.summary = target_segment.purpose or target_segment.visual_instruction
            rendered.size_bytes = os.path.getsize(output_path)
            rendered.updated_at = utcnow()
            decision.updated_at = rendered.updated_at
            return (
                f"片段 {target_segment.id} 已渲染完成。"
                f"\n原视频：{target_segment.source_start}-{target_segment.source_end}"
                f"\n成片：{target_segment.timeline_start}-{target_segment.timeline_end}"
                f"\n文件：{output_name}"
            )
        except Exception as exc:
            rendered.status = "blocked"
            rendered.error_message = str(exc)
            rendered.updated_at = utcnow()
            decision.updated_at = rendered.updated_at
            working_state.edited_video.error_message = str(exc)
            return (
                f"片段 {target_segment.id} 渲染失败，请基于错误修正后重试："
                f"\n错误：{exc}"
                f"\n片段：{json.dumps(asdict(target_segment), ensure_ascii=False)}"
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
        if not self._clip_derivation_service.all_segments_rendered(decision):
            raise RuntimeError("仍有片段未完成渲染，不能执行最终合并。")

        logger.info(
            "merge_rendered_segments subtitle draft preview: %s",
            (working_state.subtitle_draft or "")[:100],
        )

        payload = parse_json_object(action_input)
        burn_subtitles = decision.burn_subtitles if not isinstance(payload, dict) else bool(payload.get("burn_subtitles", decision.burn_subtitles))
        drop_audio = bool(payload.get("drop_audio")) if isinstance(payload, dict) else False

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
            await self.run_ffmpeg_command(merge_args)
            decision.merge_command = shlex.join(merge_args)
            decision.merged_segments_path = merged_path
            decision.merge_error_message = ""

            subtitle_path = ""
            if burn_subtitles and working_state.subtitle_draft.strip():
                subtitle_path = self.write_subtitle_sidecar(turn.turn_id, working_state.subtitle_draft)
                if not subtitle_path:
                    raise RuntimeError(
                        "字幕解析失败：字幕草稿中未找到符合 `00:00-00:03 字幕内容` 格式的时间轴！"
                        "请重新调用 write_subtitles，仅传入 guidance 让底层模型重新生成规范格式。"
                    )
            if subtitle_path:
                escaped_subtitle = self.escape_subtitle_filter_path(subtitle_path)
                subtitle_args = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    merged_path,
                    "-vf",
                    f"subtitles={escaped_subtitle}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "23",
                ]
                if drop_audio:
                    subtitle_args.extend(["-an"])
                else:
                    subtitle_args.extend(["-c:a", "aac", "-b:a", "128k"])
                subtitle_args.append(final_path)
                await self.run_ffmpeg_command(subtitle_args)
                final_command = shlex.join(subtitle_args)
            else:
                final_command = shlex.join(merge_args)
                if merged_path != final_path:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    os.replace(merged_path, final_path)

            working_state.edited_video = EditedVideoArtifact(
                file_name=os.path.basename(final_path),
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video?v={turn.turn_id}",
                storage_path=final_path,
                command=final_command,
                summary=decision.summary or turn.user_prompt.strip(),
                error_message="",
                size_bytes=os.path.getsize(final_path),
            )
            self._task_board_service.complete_workflow_artifact(working_state, "edited_video", "剪辑视频已导出，可在右侧下载。")
            self._task_board_service.set_task_status(turn, "verify_export", "done", notes="已生成可下载成片。")
            return (
                "片段已合并并生成最终成片。"
                f"\n文件名：{working_state.edited_video.file_name}"
                f"\n下载地址：{working_state.edited_video.download_url}"
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
            return f"片段合并失败：{exc}"

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

            working_state.edited_video = EditedVideoArtifact(
                file_name=output_name,
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video?v={turn.turn_id}",
                storage_path=output_path,
                command=attempted_command,
                summary=summary,
                error_message="",
                size_bytes=os.path.getsize(output_path),
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
        speed_override: float | None = None,
        vf_override: str | None = None,
        af_override: str | None = None,
    ) -> List[str]:
        width, height = self.resolution_for_aspect_ratio(aspect_ratio)
        start = self._clip_derivation_service.timestamp_to_seconds(segment.source_start)
        end = self._clip_derivation_service.timestamp_to_seconds(segment.source_end)
        if end <= start:
            raise RuntimeError(f"片段 {segment.id} 的 source_end 必须大于 source_start。")
        speed = max(0.5, min(2.0, float(speed_override if speed_override is not None else (segment.speed or 1.0))))
        setpts = "PTS-STARTPTS" if abs(speed - 1.0) < 1e-6 else f"(PTS-STARTPTS)/{speed}"
        vf = (
            vf_override.strip()
            if vf_override and vf_override.strip()
            else (
                f"setpts={setpts},"
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
            elif abs(speed - 1.0) >= 1e-6:
                audio_filter = ",".join(self.build_atempo_filters(speed))
            else:
                audio_filter = ""
            if audio_filter:
                args.extend(["-af", audio_filter])
            args.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-shortest"])
        args.append(output_path)
        return args

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

    def escape_subtitle_filter_path(self, path: str) -> str:
        return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

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
