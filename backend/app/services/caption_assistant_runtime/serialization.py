from __future__ import annotations

from typing import List, Set

from app.models import AgentTurn, CaptionSession, GlobalEditingState, serialize_session


class SerializationService:
    def serialize(self, session: CaptionSession) -> dict:
        return serialize_session(session)

    def build_turn_summary(self, turn: AgentTurn, working_state: GlobalEditingState) -> str:
        action_names = {
            event.tool_name
            for event in turn.events
            if event.type == "tool_call" and event.tool_name
        }
        updated_items: List[str] = []
        if "run_keyframe_vision_subagent" in action_names:
            updated_items.append("关键帧分析")
        if "write_subtitles" in action_names:
            updated_items.append("字幕草稿")
        if "write_edit_plan" in action_names:
            updated_items.append("剪辑方案")
        if "derive_clip_segments" in action_names:
            updated_items.append("片段映射")
        if "write_title" in action_names:
            updated_items.append("英文标题")
        if "write_tags" in action_names:
            updated_items.append("标签")
        if working_state.edited_video.download_url and (
            "run_video_edit_subagent" in action_names
            or "render_clip_segment" in action_names
            or "merge_rendered_segments" in action_names
        ):
            updated_items.append("导出视频")
        elif working_state.edited_video.error_message and (
            "run_video_edit_subagent" in action_names
            or "render_clip_segment" in action_names
            or "merge_rendered_segments" in action_names
        ):
            updated_items.append("导出视频失败")

        return (
            f"用户需求：{turn.user_prompt.strip()[:180]}"
            f"\n计划摘要：{turn.plan_summary.strip()[:400] or '无'}"
            f"\n结果：{('、'.join(updated_items) if updated_items else '无显式更新')}"
            f"\n最终状态：{turn.status}"
        )

    def build_error_turn_summary(self, turn: AgentTurn, error_message: str) -> str:
        return (
            f"用户需求：{turn.user_prompt.strip()[:180]}"
            f"\n计划摘要：{turn.plan_summary.strip()[:400] or '无'}"
            f"\n结果：执行失败"
            f"\n错误：{error_message[:500]}"
        )

    def build_assistant_reply_fallback(
        self,
        working_state: GlobalEditingState,
        action_names: Set[str],
        clip_segment_summary: str,
    ) -> str:
        sections: List[str] = []
        if "run_keyframe_vision_subagent" in action_names and working_state.video_summary:
            sections.append(f"视频摘要：\n{working_state.video_summary.strip()}")
        if "write_subtitles" in action_names and working_state.subtitle_draft:
            sections.append(f"字幕草稿：\n{working_state.subtitle_draft.strip()}")
        if "write_edit_plan" in action_names and working_state.editing_plan:
            sections.append(f"剪辑方案：\n{working_state.editing_plan.strip()}")
        if "derive_clip_segments" in action_names and working_state.executable_edit.segments:
            sections.append("片段映射：\n" + clip_segment_summary)
        if "write_title" in action_names and working_state.english_title:
            sections.append(f"英文标题：\n{working_state.english_title.strip()}")
        if "write_tags" in action_names and working_state.tags:
            sections.append("标签：\n" + "\n".join(f"- {tag}" for tag in working_state.tags if str(tag).strip()))
        if "run_video_edit_subagent" in action_names and working_state.edited_video.download_url:
            sections.append(
                "导出视频：\n"
                f"文件名：{working_state.edited_video.file_name}\n"
                f"下载地址：{working_state.edited_video.download_url}\n"
                f"导出说明：{working_state.edited_video.summary or '已生成可下载成片。'}"
            )
        elif "run_video_edit_subagent" in action_names and working_state.edited_video.error_message:
            sections.append(
                "导出视频：\n"
                "当前导出失败，尚未生成可下载成片。\n"
                f"失败原因：{working_state.edited_video.error_message}"
            )

        if sections:
            return "\n\n".join(sections)
        if not action_names:
            return (
                "当前已经收到你的素材或指令，但还需要更明确的目标。\n\n"
                "你可以直接告诉我想让我做哪一类工作：分析视频、生成字幕、写剪辑方案、出标题标签，或导出成片。"
            )
        if working_state.video_summary:
            return f"视频摘要：\n{working_state.video_summary.strip()}"
        return "本轮产物已生成完成。"
