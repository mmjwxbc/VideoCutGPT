from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Literal, Type

from pydantic import BaseModel, Field

from app.agent.runtime import ToolResult, ToolSpec
from app.models import AgentTurn, CaptionSession, GlobalEditingState, TurnEventItem

if TYPE_CHECKING:
    from app.services.caption_assistant_runtime.assistant import CaptionConversationAssistant

logger = logging.getLogger(__name__)


class EmptyToolInput(BaseModel):
    pass


class GuidanceToolInput(BaseModel):
    guidance: str = ""


class DeriveClipSegmentsInput(BaseModel):
    guidance: str = ""
    target_duration_seconds: float | None = None
    aspect_ratio: str | None = None


class CreateTaskBoardInput(BaseModel):
    summary: str = ""
    selected_ids: list[str] = Field(default_factory=list)
    export_intent: bool = False


class UpdateTaskStatusInput(BaseModel):
    task_id: str
    status: str
    notes: str | None = None
    current_focus: str | None = None
    blocked_reason: str | None = None


class WriteSubtitlesInput(BaseModel):
    action: Literal["rewrite", "append", "modify_partial"] = "rewrite"
    guidance: str = ""
    content: str | None = None
    language: str | None = None
    tone: str | None = None
    format: str | None = None
    strict: bool = False
    total_duration_seconds: float | None = None


class WriteEditPlanInput(BaseModel):
    action: Literal["rewrite", "append", "modify_partial"] = "rewrite"
    guidance: str = ""
    content: str | None = None
    platform: str | None = None
    target_duration_seconds: float | None = None


class RunVideoEditSubagentInput(BaseModel):
    guidance: str = ""
    target_output: str | None = None


class RunFfmpegExportInput(BaseModel):
    command_template: str
    output_extension: str | None = None
    summary: str | None = None
    needs_subtitle_file: bool = False


class RenderClipSegmentInput(BaseModel):
    segment_id: str | None = None
    speed: float | None = None
    drop_audio: bool = False
    notes: str | None = None
    vf_override: str | None = None
    af_override: str | None = None
    retry_guidance: str | None = None


class MergeRenderedSegmentsInput(BaseModel):
    guidance: str | None = None
    burn_subtitles: bool | None = None
    drop_audio: bool = False
    notes: str | None = None


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
    input_model: Type[BaseModel] = EmptyToolInput

    def __init__(self, context: CaptionToolContext) -> None:
        self.context = context

    async def run(self, action_input: BaseModel) -> str:
        normalized_input = action_input.model_dump_json(exclude_none=True)
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
        normalized_result = self._normalize_result(result)
        logger.info(
            "caption_tool_result tool=%s session_id=%s turn_id=%s result=%r",
            self.name,
            self.context.session.session_id,
            self.context.turn.turn_id,
            normalized_result[:4000],
        )
        return normalized_result

    @abstractmethod
    async def execute(self, action_input: BaseModel) -> str | ToolResult:
        """Execute the concrete tool action."""

    def to_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_model=self.input_model,
            run=self.run,
        )

    def _normalize_result(self, result: str | ToolResult) -> str:
        if isinstance(result, ToolResult):
            return result.model_dump_json(exclude_none=True)
        text = result.strip()
        lowered = text.lower()
        ok = not any(keyword in lowered for keyword in ["错误", "失败", "error", "failed", "invalid"])
        return ToolResult(
            ok=ok,
            summary=text or "工具执行完成。",
            error=text if text and not ok else None,
        ).model_dump_json(exclude_none=True)


class RunKeyframeVisionSubagentTool(CaptionAssistantTool):
    name = "run_keyframe_vision_subagent"
    description = "调用关键帧视觉子代理：提取关键帧、逐帧调用多模态大模型分析图片，并汇总视频摘要。"
    input_model = EmptyToolInput

    async def execute(self, action_input: EmptyToolInput) -> str:
        del action_input
        return await self.context.assistant.video_context_service.run_keyframe_vision_subagent(
            self.context.turn,
            self.context.session,
            self.context.working_state,
        )


class ReadVideoContextTool(CaptionAssistantTool):
    name = "read_video_context"
    description = "读取视频关键帧分析和视频摘要。"
    input_model = EmptyToolInput

    async def execute(self, action_input: EmptyToolInput) -> str:
        del action_input
        return await self.context.assistant.video_context_service.tool_read_video_context(self.context.working_state)


class ReadManualTool(CaptionAssistantTool):
    name = "read_manual"
    description = "读取产品说明书。"
    input_model = EmptyToolInput

    async def execute(self, action_input: EmptyToolInput) -> str:
        del action_input
        return await self.context.assistant.video_context_service.tool_read_manual(self.context.session)


class ReadCurrentArtifactsTool(CaptionAssistantTool):
    name = "read_current_artifacts"
    description = "读取当前字幕、剪辑方案、标题和标签。"
    input_model = EmptyToolInput

    async def execute(self, action_input: EmptyToolInput) -> str:
        del action_input
        return await self.context.assistant.content_generation_service.tool_read_current_artifacts(self.context.working_state)


class DeriveClipSegmentsTool(CaptionAssistantTool):
    name = "derive_clip_segments"
    description = "把成片剪辑方案映射为原视频片段列表，生成可执行的 source_start/source_end 时间线。"
    input_model = DeriveClipSegmentsInput

    async def execute(self, action_input: DeriveClipSegmentsInput) -> str:
        return await self.context.assistant.tool_derive_clip_segments(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input.guidance.strip() or self.context.user_prompt,
        )


class CreateTaskBoardTool(CaptionAssistantTool):
    name = "create_task_board"
    description = "为当前轮次创建或刷新任务板，拆分本轮子任务并标记当前焦点。"
    input_model = CreateTaskBoardInput

    async def execute(self, action_input: CreateTaskBoardInput) -> str:
        return await self.context.assistant.task_board_service.tool_create_task_board(
            self.context.turn,
            action_input.model_dump_json(exclude_none=True),
        )


class ReadTaskBoardTool(CaptionAssistantTool):
    name = "read_task_board"
    description = "读取当前轮次任务板，查看任务状态、阻塞原因和当前焦点。"
    input_model = EmptyToolInput

    async def execute(self, action_input: EmptyToolInput) -> str:
        del action_input
        return await self.context.assistant.task_board_service.tool_read_task_board(self.context.turn)


class UpdateTaskStatusTool(CaptionAssistantTool):
    name = "update_task_status"
    description = "更新当前轮次任务状态。"
    input_model = UpdateTaskStatusInput

    async def execute(self, action_input: UpdateTaskStatusInput) -> str:
        return await self.context.assistant.task_board_service.tool_update_task_status(
            self.context.turn,
            action_input.model_dump_json(exclude_none=True),
        )


class WriteSubtitlesTool(CaptionAssistantTool):
    name = "write_subtitles"
    description = "生成或更新字幕草稿。支持 strict timeline_plain 模式；优先只提供 guidance，让底层专用生成器产出标准字幕格式。"
    input_model = WriteSubtitlesInput

    async def execute(self, action_input: WriteSubtitlesInput) -> str:
        return await self.context.assistant.content_generation_service.tool_write_subtitles(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input.model_dump_json(exclude_none=True),
        )


class WriteEditPlanTool(CaptionAssistantTool):
    name = "write_edit_plan"
    description = "生成或更新剪辑方案。优先只提供 guidance，让底层专用生成器产出完整结构。"
    input_model = WriteEditPlanInput

    async def execute(self, action_input: WriteEditPlanInput) -> str:
        return await self.context.assistant.content_generation_service.tool_write_edit_plan(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input.model_dump_json(exclude_none=True),
        )


class WriteTitleTool(CaptionAssistantTool):
    name = "write_title"
    description = "生成或更新英文标题。"
    input_model = GuidanceToolInput

    async def execute(self, action_input: GuidanceToolInput) -> str:
        return await self.context.assistant.content_generation_service.tool_write_title(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input.guidance.strip() or self.context.user_prompt,
        )


class WriteTagsTool(CaptionAssistantTool):
    name = "write_tags"
    description = "生成或更新标签。"
    input_model = GuidanceToolInput

    async def execute(self, action_input: GuidanceToolInput) -> str:
        return await self.context.assistant.content_generation_service.tool_write_tags(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input.guidance.strip() or self.context.user_prompt,
        )


class RunVideoEditSubagentTool(CaptionAssistantTool):
    name = "run_video_edit_subagent"
    description = "调用专门的视频剪辑导出子代理：负责片段映射、构建 ffmpeg concat 命令、执行导出并在失败时重试。"
    input_model = RunVideoEditSubagentInput

    async def execute(self, action_input: RunVideoEditSubagentInput) -> str:
        return await self.context.assistant.tool_run_video_edit_subagent(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input.guidance.strip() or self.context.user_prompt,
        )


class ReadVideoEditContextTool(CaptionAssistantTool):
    name = "read_video_edit_context"
    description = "读取当前视频导出上下文：包括输入视频路径、输出目录、片段映射、字幕状态、上一条失败命令和 stderr。"
    input_model = EmptyToolInput

    async def execute(self, action_input: EmptyToolInput) -> str:
        del action_input
        return await self.context.assistant.video_export_service.tool_read_video_edit_context(
            self.context.session,
            self.context.turn,
            self.context.working_state,
        )


class RunFfmpegExportTool(CaptionAssistantTool):
    name = "run_ffmpeg_export"
    description = "执行一次 ffmpeg 导出。不要传 ffmpeg、-i 或输出路径，服务端会自动注入。"
    input_model = RunFfmpegExportInput

    async def execute(self, action_input: RunFfmpegExportInput) -> str:
        return await self.context.assistant.video_export_service.tool_run_bash_ffmpeg(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input.model_dump_json(exclude_none=True),
        )


class RenderClipSegmentTool(CaptionAssistantTool):
    name = "render_clip_segment"
    description = "逐个渲染单个视频片段；失败时可通过 vf_override、af_override 或 drop_audio 自愈。"
    input_model = RenderClipSegmentInput

    async def execute(self, action_input: RenderClipSegmentInput) -> str:
        return await self.context.assistant.video_export_service.tool_render_clip_segment(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input.model_dump_json(exclude_none=True),
        )


class MergeRenderedSegmentsTool(CaptionAssistantTool):
    name = "merge_rendered_segments"
    description = "合并已经渲染完成的所有片段，并在需要时烧录字幕生成最终成片。"
    input_model = MergeRenderedSegmentsInput

    async def execute(self, action_input: MergeRenderedSegmentsInput) -> str:
        return await self.context.assistant.video_export_service.tool_merge_rendered_segments(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input.model_dump_json(exclude_none=True),
        )
