from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict

from app.agent.runtime import ToolSpec
from app.models import AgentTurn, CaptionSession, GlobalEditingState, TurnEventItem

if TYPE_CHECKING:
    from app.services.caption_assistant_runtime.assistant import CaptionConversationAssistant

logger = logging.getLogger(__name__)


@dataclass
class CaptionToolContext:
    assistant: "CaptionConversationAssistant"
    session: CaptionSession
    turn: AgentTurn
    working_state: GlobalEditingState
    user_prompt: str
    targets: Dict[str, Any]


class CaptionAssistantTool(ABC):
    name: str = ""
    description: str = ""

    def __init__(self, context: CaptionToolContext) -> None:
        self.context = context

    async def run(self, action_input: str) -> str:
        normalized_input = action_input.strip() or "{}"
        logger.info(
            "caption_tool_call tool=%s session_id=%s turn_id=%s user_prompt=%r arguments=%r",
            self.name,
            self.context.session.session_id,
            self.context.turn.turn_id,
            self.context.user_prompt[:200],
            normalized_input[:4000],
        )
        await self.context.assistant.append_turn_event(
            self.context.session,
            self.context.turn,
            TurnEventItem(
                type="tool_call",
                tool_name=self.name,
                arguments=normalized_input,
            ),
        )
        result = await self.execute(action_input)
        logger.info(
            "caption_tool_result tool=%s session_id=%s turn_id=%s result=%r",
            self.name,
            self.context.session.session_id,
            self.context.turn.turn_id,
            result[:4000],
        )
        return result

    @abstractmethod
    async def execute(self, action_input: str) -> str:
        """Execute the concrete tool action."""

    def to_spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, run=self.run)


class RunKeyframeVisionSubagentTool(CaptionAssistantTool):
    name = "run_keyframe_vision_subagent"
    description = "调用关键帧视觉子代理：提取关键帧、逐帧调用多模态大模型分析图片，并汇总视频摘要。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant.video_context_service.run_keyframe_vision_subagent(
            self.context.turn,
            self.context.session,
            self.context.working_state,
        )


class ReadVideoContextTool(CaptionAssistantTool):
    name = "read_video_context"
    description = "读取视频关键帧分析和视频摘要。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant.video_context_service.tool_read_video_context(self.context.working_state)


class ReadManualTool(CaptionAssistantTool):
    name = "read_manual"
    description = "读取产品说明书。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant.video_context_service.tool_read_manual(self.context.session)


class ReadCurrentArtifactsTool(CaptionAssistantTool):
    name = "read_current_artifacts"
    description = "读取当前字幕、剪辑方案、标题和标签。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant.content_generation_service.tool_read_current_artifacts(self.context.working_state)


class DeriveClipSegmentsTool(CaptionAssistantTool):
    name = "derive_clip_segments"
    description = "把成片剪辑方案映射为原视频片段列表，生成可执行的 source_start/source_end 时间线。"

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.tool_derive_clip_segments(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class CreateTaskBoardTool(CaptionAssistantTool):
    name = "create_task_board"
    description = (
        "为当前轮次创建或刷新任务板，拆分本轮子任务并标记当前焦点。"
        "推荐传入 JSON：{\"summary\":\"...\",\"selected_ids\":[\"keyframe_analysis\",\"subtitle_draft\",\"editing_plan\"],\"export_intent\":false}。"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.task_board_service.tool_create_task_board(self.context.turn, action_input)


class ReadTaskBoardTool(CaptionAssistantTool):
    name = "read_task_board"
    description = "读取当前轮次任务板，查看任务状态、阻塞原因和当前焦点。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant.task_board_service.tool_read_task_board(self.context.turn)


class UpdateTaskStatusTool(CaptionAssistantTool):
    name = "update_task_status"
    description = (
        "更新当前轮次任务状态。"
        "建议传入 JSON：{\"task_id\":\"run_video_edit_subagent\",\"status\":\"done\",\"notes\":\"...\",\"current_focus\":\"verify_export\",\"blocked_reason\":\"\"}。"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.task_board_service.tool_update_task_status(self.context.turn, action_input)


class WriteSubtitlesTool(CaptionAssistantTool):
    name = "write_subtitles"
    description = (
        "生成或更新字幕草稿。"
        "必须传入 JSON: {\"action\": \"rewrite\" | \"append\" | \"modify_partial\", \"guidance\": \"你的要求，如'翻译为英文'\", \"content\": \"\"}"
        "\n【严重警告】若是重写(rewrite)或大改，强烈建议只传 guidance！让底层的专属模型去生成带时间轴的标准格式！绝对不要自己把全文写在 content 里，否则会导致时间轴丢失！"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.content_generation_service.tool_write_subtitles(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class WriteEditPlanTool(CaptionAssistantTool):
    name = "write_edit_plan"
    description = (
        "生成或更新剪辑方案。"
        "必须传入 JSON: {\"action\": \"rewrite\" | \"append\" | \"modify_partial\", \"guidance\": \"你的要求，如'改成更强的 TikTok hook'\", \"content\": \"\"}"
        "\n【严重警告】若是重写(rewrite)或大改，强烈建议只传 guidance！让底层的专属模型去生成结构完整的标准方案！绝对不要自己把全文写在 content 里，否则会导致结构退化！"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.content_generation_service.tool_write_edit_plan(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class WriteTitleTool(CaptionAssistantTool):
    name = "write_title"
    description = "生成或更新英文标题。"

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.content_generation_service.tool_write_title(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class WriteTagsTool(CaptionAssistantTool):
    name = "write_tags"
    description = "生成或更新标签。"

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.content_generation_service.tool_write_tags(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class RunVideoEditSubagentTool(CaptionAssistantTool):
    name = "run_video_edit_subagent"
    description = "调用专门的视频剪辑导出子代理：负责片段映射、构建 ffmpeg concat 命令、执行导出并在失败时重试。"

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.tool_run_video_edit_subagent(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class ReadVideoEditContextTool(CaptionAssistantTool):
    name = "read_video_edit_context"
    description = "读取当前视频导出上下文：包括输入视频路径、输出目录、片段映射、字幕状态、上一条失败命令和 stderr。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant.video_export_service.tool_read_video_edit_context(
            self.context.session,
            self.context.turn,
            self.context.working_state,
        )


class RunFfmpegExportTool(CaptionAssistantTool):
    name = "run_ffmpeg_export"
    description = (
        "执行一次 ffmpeg 导出。"
        "action_input 必须是 JSON：{\"command_template\":\"-filter_complex \\\"...\\\" -map \\\"[vout]\\\" -map \\\"[aout]\\\" -c:v libx264 ...\",\"output_extension\":\"mp4\",\"summary\":\"...\",\"needs_subtitle_file\":true}。"
        "不要传 ffmpeg、不要传 -i、不要传输出路径；服务端会自动注入。"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.video_export_service.tool_run_bash_ffmpeg(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class RenderClipSegmentTool(CaptionAssistantTool):
    name = "render_clip_segment"
    description = (
        "逐个渲染单个视频片段。"
        "action_input 推荐为 JSON：{\"segment_id\":\"seg_1\",\"speed\":1.25,\"drop_audio\":false,\"notes\":\"根据上一条错误修正\"}。"
        "如果发生 FFmpeg 报错（如奇数分辨率、色彩空间问题），可以通过传入 vf_override 覆盖视频滤镜，或 af_override 覆盖音频滤镜来尝试自愈。"
        "如果不传 segment_id，服务端会自动选择下一个待处理片段。"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.video_export_service.tool_render_clip_segment(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class MergeRenderedSegmentsTool(CaptionAssistantTool):
    name = "merge_rendered_segments"
    description = (
        "合并已经渲染完成的所有片段，并在需要时烧录字幕生成最终成片。"
        "action_input 推荐为 JSON：{\"burn_subtitles\":true,\"drop_audio\":false,\"notes\":\"...\"}。"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant.video_export_service.tool_merge_rendered_segments(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )
