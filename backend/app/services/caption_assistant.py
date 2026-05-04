from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import shlex
import shutil
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from app.agent.runtime import LightPlanningReActRuntime, ReActStep, ToolRegistry, ToolSpec
from app.ai.factory import AIAdapterFactory
from app.ai.types import AICompletionRequest, AIImageInput, AIMessage
from app.core.config import settings
from app.core.utils import extract_keyframes, select_keyframes_for_analysis

logger = logging.getLogger(__name__)

CAPTION_ASSISTANT_SYSTEM_PROMPT = """你是一个具备深度视觉理解和自动化视频剪辑能力的创意执行专家。
你拥有对视频素材、产品说明、字幕文案、剪辑方案的全局控制权。

你的工作模式：
1. 感知与评估：分析用户的最新指令，结合历史对话和当前剪辑状态，判断用户意图。
2. 严格按需执行与时长控制（极其重要）：
   - 坚守指令边界：用户要求做哪一步，就只做哪一步！
   - 短视频节奏原则：TikTok/短视频的黄金长度是 15s - 30s。除非用户明确要求保留长视频，否则你在出方案时必须大刀阔斧地精简！只保留高光时刻，并大胆使用加速（如2.0x-5.0x）。
   - 进度保护：如果用户要求“继续导出”或“重试”，且【当前剪辑状态】中已经存在片段映射（segments），绝不允许重新调用 derive_clip_segments！否则会清空已有的渲染进度。直接调用 run_video_edit_subagent 恢复导出即可。
3. 引导与沟通：如果用户意图完全空白，直接以亲和的语气反问，列举你可以提供的具体能力。
4. 拒绝幻觉：不要汇报你没做过的事，不要虚构视频中不存在的细节。

你可以调用或协调的核心能力：
- 关键帧视觉深度分析
- 字幕文案创作与定向修改
- 剪辑结构设计，从 Hook 到 CTA
- 自动片段选取与 FFmpeg 物理合成导出
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
11. 如果本轮没有任何工具被调用，意味着你正在与用户进行意图确认。请根据上下文直接给出建议或询问，语气像专业的导演助手。
"""

DERIVE_CLIP_SEGMENTS_PROMPT = """任务：把创意剪辑方案翻译成可执行的原视频取材片段。

角色：
你是资深短视频后期导演，非常擅长将冗长的原素材精简成 15-30 秒的爆款短视频。

工作原则：
1. 短视频法则：如果用户没有指定目标时长，默认将总时长严控在 15秒 到 30秒 之间！
2. 大胆压缩：对于缓慢的动作（如刷洗、等待），必须大跨度使用 speed 参数（2.0x, 3.0x 甚至 5.0x）进行加速，绝不要原速保留无聊过程。
3. 大刀阔斧地砍：不要试图把原视频的每一秒都塞进成片。只挑最抓眼球的画面（Hook）、最核心的产品展示和最爽的结果。
4. editing_plan 里的时间是成片时间线，不是原视频时间线。你必须输出原视频中的 source_start/source_end。
5. 如果片段数量偏多、总时长可能超标，立刻删减冗余片段或进一步提速。

输出要求：
1. 只输出 JSON。
2. 格式必须是：
{"summary":"...","total_duration_seconds":15,"aspect_ratio":"9:16","burn_subtitles":true,"segments":[{"id":"seg_1","source_start":"00:00:12","source_end":"00:00:18","timeline_start":"00:00:00","timeline_end":"00:00:03","output_duration_seconds":3,"purpose":"开场 hook","visual_instruction":"特写污渍区域","speed":2.0,"transition_to_next":"hard_cut","subtitle_text":"..."}]}
3. source_start/source_end 必须是原视频相对时间。
4. speed 默认 1.0，遇到冗长过程请务必填入 >1.0 的加速倍数。
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
    clip_segments: WorkflowArtifactState = field(
        default_factory=lambda: WorkflowArtifactState(label="片段映射")
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
class ClipSegment:
    id: str
    source_start: str
    source_end: str
    timeline_start: str
    timeline_end: str
    output_duration_seconds: float
    purpose: str = ""
    visual_instruction: str = ""
    speed: float = 1.0
    transition_to_next: str = "hard_cut"
    subtitle_text: str = ""


@dataclass
class RenderedClipSegment:
    segment_id: str
    status: str = "todo"
    file_name: str = ""
    storage_path: str = ""
    command: str = ""
    error_message: str = ""
    summary: str = ""
    size_bytes: int = 0
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class ExecutableEditDecision:
    summary: str = ""
    total_duration_seconds: float = 0.0
    aspect_ratio: str = "9:16"
    burn_subtitles: bool = True
    segments: List[ClipSegment] = field(default_factory=list)
    rendered_segments: List[RenderedClipSegment] = field(default_factory=list)
    merged_segments_path: str = ""
    merge_command: str = ""
    merge_error_message: str = ""
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class GlobalEditingState:
    request_summary: str = ""
    keyframes: List[Dict[str, Any]] = field(default_factory=list)
    frame_analyses: List[str] = field(default_factory=list)
    video_summary: str = ""
    subtitle_draft: str = ""
    editing_plan: str = ""
    executable_edit: ExecutableEditDecision = field(default_factory=ExecutableEditDecision)
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
class TaskBoardItem:
    id: str
    title: str
    status: str = "todo"
    notes: str = ""
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class TurnTaskBoard:
    summary: str = ""
    current_focus: str = ""
    blocked_reason: str = ""
    tasks: List[TaskBoardItem] = field(default_factory=list)
    updated_at: str = field(default_factory=_utcnow)


@dataclass
class AgentTurn:
    turn_id: str
    user_prompt: str
    status: str = "running"
    events: List[TurnEventItem] = field(default_factory=list)
    final_text: str = ""
    error_message: str = ""
    plan_summary: str = ""
    turn_summary: str = ""
    task_board: TurnTaskBoard = field(default_factory=TurnTaskBoard)
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


@dataclass
class CaptionToolContext:
    assistant: "CaptionConversationAssistant"
    session: CaptionSession
    turn: AgentTurn
    working_state: GlobalEditingState
    user_prompt: str
    targets: Dict[str, Any]


@dataclass
class VideoEditSubAgentContext:
    assistant: "CaptionConversationAssistant"
    session: CaptionSession
    turn: AgentTurn
    working_state: GlobalEditingState
    user_prompt: str


class VideoEditExportSubAgent:
    def __init__(self, context: VideoEditSubAgentContext) -> None:
        self.context = context

    async def run(self, instruction: str) -> str:
        assistant = self.context.assistant
        turn = self.context.turn
        session = self.context.session
        working_state = self.context.working_state
        user_prompt = instruction.strip() or self.context.user_prompt

        assistant._set_task_status(
            turn,
            "run_video_edit_subagent",
            "doing",
            notes="导出子代理正在读取上下文并尝试执行 ffmpeg。",
            current_focus="run_video_edit_subagent",
        )

        if not working_state.executable_edit.segments:
            await assistant._tool_derive_clip_segments(
                turn,
                session,
                working_state,
                user_prompt,
                user_prompt,
            )

        registry = assistant._build_video_edit_tool_registry(
            session=session,
            turn=turn,
            working_state=working_state,
            user_prompt=user_prompt,
        )
        runtime = LightPlanningReActRuntime(
            adapter=assistant._adapter_factory.get_text_adapter(),
            model=settings.deepseek_chat_model,
            tool_registry=registry,
            max_steps=20,
            timeout_seconds=settings.glm_request_timeout_seconds,
        )
        result = await runtime.run(
            user_prompt=user_prompt,
            task_brief=assistant._build_video_edit_task_brief(session, turn, working_state, user_prompt),
            context_prompt=assistant._build_video_edit_context_prompt(session, turn, working_state),
            completion_guard=assistant._build_video_edit_completion_guard(working_state),
            fallback_step=assistant._build_video_edit_fallback_step(session, turn, working_state),
            should_skip_step=assistant._build_video_edit_step_skipper(),
            progress=assistant._noop_progress,
            trace=lambda thought, _action, observation: assistant._append_turn_thought(
                session,
                turn,
                thought,
                observation,
            ),
        )
        if working_state.edited_video.download_url:
            assistant._set_task_status(
                turn,
                "run_video_edit_subagent",
                "done",
                notes="导出子代理已完成视频拼接与导出。",
                current_focus="verify_export",
            )
            return result.scratchpad[-1]["observation"] if result.scratchpad else "导出子代理已完成视频导出。"

        last_error = working_state.edited_video.error_message or turn.task_board.blocked_reason or "导出子代理执行失败。"
        assistant._set_task_status(
            turn,
            "run_video_edit_subagent",
            "blocked",
            notes=last_error,
            current_focus="run_video_edit_subagent",
            blocked_reason=last_error,
        )
        return last_error


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
        await self.context.assistant._append_turn_event(
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
        return await self.context.assistant._run_keyframe_vision_subagent(
            self.context.turn,
            self.context.session,
            self.context.working_state,
        )


class ReadVideoContextTool(CaptionAssistantTool):
    name = "read_video_context"
    description = "读取视频关键帧分析和视频摘要。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant._tool_read_video_context(self.context.working_state)


class ReadManualTool(CaptionAssistantTool):
    name = "read_manual"
    description = "读取产品说明书。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant._tool_read_manual(self.context.session)


class ReadCurrentArtifactsTool(CaptionAssistantTool):
    name = "read_current_artifacts"
    description = "读取当前字幕、剪辑方案、标题和标签。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant._tool_read_current_artifacts(self.context.working_state)


class DeriveClipSegmentsTool(CaptionAssistantTool):
    name = "derive_clip_segments"
    description = "把成片剪辑方案映射为原视频片段列表，生成可执行的 source_start/source_end 时间线。"

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant._tool_derive_clip_segments(
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
        return await self.context.assistant._tool_create_task_board(
            self.context.turn,
            self.context.targets,
            action_input,
        )


class ReadTaskBoardTool(CaptionAssistantTool):
    name = "read_task_board"
    description = "读取当前轮次任务板，查看任务状态、阻塞原因和当前焦点。"

    async def execute(self, action_input: str) -> str:
        del action_input
        return await self.context.assistant._tool_read_task_board(self.context.turn)


class UpdateTaskStatusTool(CaptionAssistantTool):
    name = "update_task_status"
    description = (
        "更新当前轮次任务状态。"
        "建议传入 JSON：{\"task_id\":\"run_video_edit_subagent\",\"status\":\"done\",\"notes\":\"...\",\"current_focus\":\"verify_export\",\"blocked_reason\":\"\"}。"
    )

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant._tool_update_task_status(
            self.context.turn,
            action_input,
        )


class WriteSubtitlesTool(CaptionAssistantTool):
    name = "write_subtitles"
    description = "生成或更新字幕草稿。"

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant._tool_write_subtitles(
            self.context.turn,
            self.context.session,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


class WriteEditPlanTool(CaptionAssistantTool):
    name = "write_edit_plan"
    description = "生成或更新剪辑方案。"

    async def execute(self, action_input: str) -> str:
        return await self.context.assistant._tool_write_edit_plan(
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
        return await self.context.assistant._tool_write_title(
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
        return await self.context.assistant._tool_write_tags(
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
        return await self.context.assistant._tool_run_video_edit_subagent(
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
        return await self.context.assistant._tool_read_video_edit_context(
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
        return await self.context.assistant._tool_run_bash_ffmpeg(
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
        return await self.context.assistant._tool_render_clip_segment(
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
        return await self.context.assistant._tool_merge_rendered_segments(
            self.context.session,
            self.context.turn,
            self.context.working_state,
            self.context.user_prompt,
            action_input,
        )


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
                targets = self._build_open_tool_targets()
                turn.plan_summary = self._build_runtime_task_brief()
                turn.task_board = TurnTaskBoard(summary="等待 agent 自主判断并按需拆解任务。")
                scratchpad = await self._execute_targets(
                    session=session,
                    turn=turn,
                    working_state=working_state,
                    user_prompt=user_prompt,
                    targets=targets,
                    task_brief=self._build_runtime_task_brief(),
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
        task_brief: str,
    ) -> List[Dict[str, str]]:
        registry = self._build_tool_registry(session, turn, working_state, user_prompt, targets)
        runtime = LightPlanningReActRuntime(
            adapter=self._adapter_factory.get_text_adapter(),
            model=settings.deepseek_chat_model,
            tool_registry=registry,
            max_steps=settings.agent_max_steps,
            timeout_seconds=settings.glm_request_timeout_seconds,
        )
        result = await runtime.run(
            user_prompt=user_prompt,
            task_brief=task_brief,
            context_prompt=self._build_runtime_context_prompt(session, working_state, targets),
            completion_guard=self._build_completion_guard(turn, targets, working_state),
            fallback_step=self._build_fallback_step(turn, targets),
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
        action_names = {str(item.get("action", "")).strip() for item in scratchpad}
        if (
            "run_video_edit_subagent" in action_names
            and not working_state.edited_video.download_url
            and not working_state.edited_video.error_message
        ):
            working_state.edited_video.error_message = "本轮未生成有效的导出结果。"
            self._update_workflow_artifact(
                working_state,
                "edited_video",
                status="error",
                detail=working_state.edited_video.error_message,
                requested=True,
                needs_refresh=False,
            )

        final_text = (
            await self._compose_assistant_reply(
                session,
                working_state,
                user_prompt,
                scratchpad,
                action_names,
            )
        ).strip()
        if not final_text:
            final_text = self._build_assistant_reply_fallback(working_state, action_names)

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
        turn.turn_summary = self._build_turn_summary(turn, working_state)
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
        turn.turn_summary = self._build_error_turn_summary(turn, str(exc))
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

    def _build_video_edit_tool_registry(
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
            RenderClipSegmentTool(context),
            MergeRenderedSegmentsTool(context),
        ]:
            registry.register(tool.to_spec())
        return registry

    async def _run_keyframe_vision_subagent(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
    ) -> str:
        self._set_task_status(turn, "keyframe_analysis", "doing", notes="正在执行关键帧分析。")
        if (
            working_state.video_summary
            and working_state.frame_analyses
            and not working_state.workflow.keyframe_analysis.needs_refresh
        ):
            self._set_task_status(turn, "keyframe_analysis", "done", notes="视频上下文已存在，跳过重复分析。")
            return "视频上下文已存在，跳过重复分析。"

        working_state.keyframes = []
        working_state.frame_analyses = []
        working_state.video_summary = ""
        await self._prepare_video_context(session, working_state)
        self._set_task_status(turn, "keyframe_analysis", "done", notes="关键帧分析与视频摘要已完成。")
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
        *,
        interval_seconds: int | None = None,
        max_frames: int | None = None,
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
            interval_seconds or settings.keyframe_interval_seconds,
            None,
            settings.keyframe_scene_threshold,
        )
        working_state.frame_analyses = await self._analyze_video_frames(working_state, max_frames=max_frames)
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

    async def _analyze_video_frames(self, working_state: GlobalEditingState, *, max_frames: int | None = None) -> List[str]:
        analysis_frames = select_keyframes_for_analysis(
            working_state.keyframes,
            max_frames=max_frames or settings.max_keyframes,
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

    async def _tool_read_current_artifacts(self, working_state: GlobalEditingState) -> str:
        return (
            f"当前字幕草稿：\n{working_state.subtitle_draft or '暂无'}\n\n"
            f"当前剪辑方案：\n{working_state.editing_plan or '暂无'}\n\n"
            f"当前片段映射：\n{self._summarize_clip_segments(working_state.executable_edit.segments) or '暂无'}\n\n"
            f"当前英文标题：\n{working_state.english_title or '暂无'}\n\n"
            f"当前标签：\n{', '.join(working_state.tags) if working_state.tags else '暂无'}\n\n"
            f"当前导出视频：\n{working_state.edited_video.download_url or '暂无'}"
        )

    async def _tool_run_video_edit_subagent(
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

    async def _tool_read_video_edit_context(
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
            "next_pending_segment": asdict(next_segment) if (next_segment := self._next_pending_segment(working_state.executable_edit)) else None,
            "last_attempted_command": working_state.edited_video.command,
            "last_error": working_state.edited_video.error_message,
            "merge_error": working_state.executable_edit.merge_error_message,
        }
        return json.dumps(payload, ensure_ascii=False)

    async def _tool_render_clip_segment(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        decision = working_state.executable_edit
        if not decision.segments:
            raise RuntimeError("当前没有可渲染的片段映射。")
        self._ensure_rendered_segment_entries(decision)

        payload = self._parse_json_object(action_input)
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
            target_segment = self._next_pending_segment(decision)
        if target_segment is None:
            return "所有片段都已经渲染完成。"

        rendered = self._get_rendered_segment(decision, target_segment.id)
        if rendered is None:
            rendered = RenderedClipSegment(segment_id=target_segment.id)
            decision.rendered_segments.append(rendered)

        self._set_task_status(
            turn,
            "run_video_edit_subagent",
            "doing",
            notes=f"正在渲染片段 {target_segment.id}。{notes}".strip(),
            current_focus="run_video_edit_subagent",
        )
        rendered.status = "doing"
        rendered.updated_at = _utcnow()

        session_export_dir = os.path.join(settings.export_dir, session.session_id)
        segment_export_dir = os.path.join(session_export_dir, "segments")
        os.makedirs(segment_export_dir, exist_ok=True)
        output_name = f"{turn.turn_id}_{target_segment.id}.mp4"
        output_path = os.path.join(segment_export_dir, output_name)
        command_args = self._build_segment_render_command_args(
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
            await self._run_ffmpeg_command(command_args)
            if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError("片段渲染完成，但未生成有效片段文件。")
            rendered.status = "done"
            rendered.file_name = output_name
            rendered.storage_path = output_path
            rendered.error_message = ""
            rendered.summary = target_segment.purpose or target_segment.visual_instruction or target_segment.subtitle_text
            rendered.size_bytes = os.path.getsize(output_path)
            rendered.updated_at = _utcnow()
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
            rendered.updated_at = _utcnow()
            decision.updated_at = rendered.updated_at
            working_state.edited_video.error_message = str(exc)
            return (
                f"片段 {target_segment.id} 渲染失败，请基于错误修正后重试："
                f"\n错误：{exc}"
                f"\n片段：{json.dumps(asdict(target_segment), ensure_ascii=False)}"
            )

    async def _tool_merge_rendered_segments(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        del user_prompt
        decision = working_state.executable_edit
        self._ensure_rendered_segment_entries(decision)
        if not self._all_segments_rendered(decision):
            raise RuntimeError("仍有片段未完成渲染，不能执行最终合并。")

        payload = self._parse_json_object(action_input)
        burn_subtitles = decision.burn_subtitles if not isinstance(payload, dict) else bool(payload.get("burn_subtitles", decision.burn_subtitles))
        drop_audio = bool(payload.get("drop_audio")) if isinstance(payload, dict) else False

        session_export_dir = os.path.join(settings.export_dir, session.session_id)
        os.makedirs(session_export_dir, exist_ok=True)
        concat_list_path = os.path.join(session_export_dir, f"{turn.turn_id}_segments.txt")
        merged_path = os.path.join(session_export_dir, f"{turn.turn_id}_merged.mp4")
        final_path = os.path.join(session_export_dir, f"{turn.turn_id}.mp4")

        with open(concat_list_path, "w", encoding="utf-8") as file:
            for segment in decision.segments:
                rendered = self._get_rendered_segment(decision, segment.id)
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
            await self._run_ffmpeg_command(merge_args)
            decision.merge_command = shlex.join(merge_args)
            decision.merged_segments_path = merged_path
            decision.merge_error_message = ""

            subtitle_path = ""
            if burn_subtitles and working_state.subtitle_draft.strip():
                subtitle_path = self._write_subtitle_sidecar(turn.turn_id, working_state.subtitle_draft)
            if subtitle_path:
                escaped_subtitle = self._escape_subtitle_filter_path(subtitle_path)
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
                await self._run_ffmpeg_command(subtitle_args)
                final_command = shlex.join(subtitle_args)
            else:
                final_command = shlex.join(merge_args)
                if merged_path != final_path:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    os.replace(merged_path, final_path)

            working_state.edited_video = EditedVideoArtifact(
                file_name=os.path.basename(final_path),
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video",
                storage_path=final_path,
                command=final_command,
                summary=decision.summary or turn.user_prompt.strip(),
                error_message="",
                size_bytes=os.path.getsize(final_path),
            )
            self._complete_workflow_artifact(working_state, "edited_video", "剪辑视频已导出，可在右侧下载。")
            self._set_task_status(turn, "verify_export", "done", notes="已生成可下载成片。")
            return (
                "片段已合并并生成最终成片。"
                f"\n文件名：{working_state.edited_video.file_name}"
                f"\n下载地址：{working_state.edited_video.download_url}"
            )
        except Exception as exc:
            decision.merge_error_message = str(exc)
            working_state.edited_video.error_message = str(exc)
            self._update_workflow_artifact(
                working_state,
                "edited_video",
                status="error",
                detail=str(exc),
                requested=True,
                needs_refresh=False,
            )
            return f"片段合并失败：{exc}"

    async def _tool_derive_clip_segments(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        try:
            self._set_task_status(turn, "derive_clip_segments", "doing", notes="正在把成片方案映射为原视频片段。")
            guidance = action_input.strip() or user_prompt
            working_state.executable_edit = await self._derive_executable_edit_decision(
                session=session,
                working_state=working_state,
                guidance=guidance,
                user_prompt=user_prompt,
            )
            working_state.edited_video = EditedVideoArtifact()
            self._update_workflow_artifact(
                working_state,
                "edited_video",
                status="idle",
                detail="片段已更新，等待重新导出",
                requested=True,
                needs_refresh=True,
            )
            self._complete_workflow_artifact(
                working_state,
                "clip_segments",
                f"已生成 {len(working_state.executable_edit.segments)} 个原视频片段映射。",
            )
            self._set_task_status(
                turn,
                "derive_clip_segments",
                "done",
                notes=self._summarize_clip_segments(working_state.executable_edit.segments)[:3000],
                current_focus="run_video_edit_subagent",
            )
            return json.dumps(asdict(working_state.executable_edit), ensure_ascii=False)
        except Exception as exc:
            self._set_task_status(
                turn,
                "derive_clip_segments",
                "blocked",
                notes=str(exc),
                current_focus="derive_clip_segments",
                blocked_reason=str(exc),
            )
            return f"片段映射失败：{exc}"

    async def _tool_create_task_board(
        self,
        turn: AgentTurn,
        targets: Dict[str, Any],
        action_input: str,
    ) -> str:
        del targets
        payload = self._parse_json_object(action_input)
        summary = turn.user_prompt
        selected_ids: List[str] = []
        export_intent = False
        if isinstance(payload, dict) and payload:
            summary = str(payload.get("summary", "")).strip() or summary
            raw_selected = payload.get("selected_ids")
            if isinstance(raw_selected, list):
                selected_ids = [
                    str(item).strip()
                    for item in raw_selected
                    if str(item).strip() in {
                        "keyframe_analysis",
                        "subtitle_draft",
                        "editing_plan",
                        "english_title",
                        "tags",
                    }
                ]
            export_intent = bool(payload.get("export_intent"))
        elif action_input.strip():
            summary = action_input.strip()
        turn.task_board = self._create_turn_task_board(summary, selected_ids, export_intent=export_intent)
        return self._serialize_task_board(turn.task_board)

    async def _tool_read_task_board(self, turn: AgentTurn) -> str:
        if not turn.task_board.tasks:
            return "当前轮次任务板为空。请先调用 create_task_board。"
        return self._serialize_task_board(turn.task_board)

    async def _tool_update_task_status(self, turn: AgentTurn, action_input: str) -> str:
        payload = self._parse_json_object(action_input)
        task_id = str(payload.get("task_id", "")).strip() if isinstance(payload, dict) else ""
        status = str(payload.get("status", "")).strip() if isinstance(payload, dict) else ""
        notes = str(payload.get("notes", "")).strip() if isinstance(payload, dict) else ""
        current_focus = str(payload.get("current_focus", "")).strip() if isinstance(payload, dict) else ""
        blocked_reason = str(payload.get("blocked_reason", "")).strip() if isinstance(payload, dict) else ""
        if not task_id or not status:
            raise RuntimeError("update_task_status 需要传入 task_id 和 status。")
        self._set_task_status(
            turn,
            task_id,
            status,
            notes=notes,
            current_focus=current_focus or None,
            blocked_reason=blocked_reason,
        )
        return self._serialize_task_board(turn.task_board)

    async def _tool_write_subtitles(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        self._set_task_status(turn, "subtitle_draft", "doing", notes="正在生成字幕草稿。")
        working_state.subtitle_draft = await self._generate_subtitle_draft(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "subtitle_draft", "字幕草稿已更新。")
        self._set_task_status(turn, "subtitle_draft", "done", notes="字幕草稿已更新。")
        return "字幕草稿已更新。"

    async def _tool_write_edit_plan(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        self._set_task_status(turn, "editing_plan", "doing", notes="正在生成剪辑方案。")
        working_state.editing_plan = await self._generate_editing_plan(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "editing_plan", "剪辑执行方案已更新。")
        self._set_task_status(turn, "editing_plan", "done", notes="剪辑方案已更新。")
        return "剪辑执行方案已更新。"

    async def _tool_write_title(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        self._set_task_status(turn, "english_title", "doing", notes="正在生成英文标题。")
        working_state.english_title = await self._generate_english_title(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "english_title", "英文标题已更新。")
        self._set_task_status(turn, "english_title", "done", notes="英文标题已更新。")
        return "英文标题已更新。"

    async def _tool_write_tags(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
        user_prompt: str,
        action_input: str,
    ) -> str:
        self._set_task_status(turn, "tags", "doing", notes="正在生成标签。")
        working_state.tags = await self._generate_tags(
            session,
            working_state,
            action_input or user_prompt,
        )
        self._complete_workflow_artifact(working_state, "tags", "标签已更新。")
        self._set_task_status(turn, "tags", "done", notes="标签已更新。")
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
            self._set_task_status(turn, "run_video_edit_subagent", "doing", notes="正在执行 ffmpeg 导出。")
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
            command_args = self._materialize_ffmpeg_command_args(
                command_template=command_template,
                input_video=session.video_path,
                output_video=output_path,
                subtitle_file=subtitle_path or None,
            )
            attempted_command = shlex.join(command_args)
            await self._run_ffmpeg_command(command_args)
            if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
                raise RuntimeError("ffmpeg 命令执行完成，但未生成有效导出文件。")

            working_state.edited_video = EditedVideoArtifact(
                file_name=output_name,
                download_url=f"/api/caption/assistant/session/{session.session_id}/exported-video",
                storage_path=output_path,
                command=attempted_command,
                summary=summary,
                error_message="",
                size_bytes=os.path.getsize(output_path),
            )
            self._complete_workflow_artifact(working_state, "edited_video", "剪辑视频已导出，可在右侧下载。")
            self._set_task_status(turn, "run_video_edit_subagent", "done", notes="ffmpeg 导出已完成。", current_focus="verify_export")
            self._set_task_status(turn, "verify_export", "done", notes="已生成可下载成片。")
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
            self._set_task_status(
                turn,
                "run_video_edit_subagent",
                "blocked",
                notes=str(exc),
                current_focus="run_video_edit_subagent",
                blocked_reason=str(exc),
            )
            self._set_task_status(
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
        action_names: set[str],
    ) -> str:
        interaction_mode = "clarification" if not scratchpad else "delivery"
        prompt = (
            ASSISTANT_REPLY_PROMPT
            + _prompt_block("用户需求", user_prompt)
            + _prompt_block("本轮回复模式", interaction_mode)
            + _prompt_block("本轮实际调用工具", json.dumps(sorted(action_names), ensure_ascii=False))
            + _prompt_block("工具执行记录", json.dumps(scratchpad, ensure_ascii=False))
            + _prompt_block("平台", session.platform)
            + _prompt_block("说明书", session.product_manual or "无")
            + _prompt_block("视频摘要", working_state.video_summary or "无")
            + _prompt_block("关键帧分析", json.dumps(working_state.frame_analyses[:12], ensure_ascii=False))
            + _prompt_block("最新字幕草稿全文", working_state.subtitle_draft[:6000] if working_state.subtitle_draft else "无")
            + _prompt_block("最新剪辑方案全文", working_state.editing_plan[:6000] if working_state.editing_plan else "无")
            + _prompt_block("最新片段映射", self._summarize_clip_segments(working_state.executable_edit.segments) or "无")
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

    async def _derive_executable_edit_decision(
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
            + _prompt_block("用户需求", guidance)
            + _prompt_block("平台", session.platform)
            + _prompt_block("视频摘要", working_state.video_summary or "无")
            + _prompt_block("关键帧分析", "\n".join(working_state.frame_analyses) or "无")
            + _prompt_block("当前字幕草稿", working_state.subtitle_draft or "无")
            + _prompt_block("当前剪辑方案", working_state.editing_plan or "无")
            + _prompt_block("历史片段映射", self._summarize_clip_segments(working_state.executable_edit.segments) or "无")
        )
        raw = await self._text_complete(
            prompt,
            system_prompt=CAPTION_ASSISTANT_SYSTEM_PROMPT,
            require_json=True,
        )
        decision = self._coerce_executable_edit_decision(self._parse_json_object(raw))
        self._normalize_executable_edit_decision(decision)
        return decision

    def _coerce_executable_edit_decision(self, parsed: Dict[str, Any]) -> ExecutableEditDecision:
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
                    purpose=str(item.get("purpose", "")).strip(),
                    visual_instruction=str(item.get("visual_instruction", "")).strip(),
                    speed=speed,
                    transition_to_next=str(item.get("transition_to_next", "hard_cut")).strip() or "hard_cut",
                    subtitle_text=str(item.get("subtitle_text", "")).strip(),
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
            updated_at=_utcnow(),
        )

    def _normalize_executable_edit_decision(self, decision: ExecutableEditDecision) -> None:
        decision.segments.sort(key=lambda item: self._timestamp_to_seconds(item.timeline_start))
        for segment in decision.segments:
            source_duration = self._timestamp_to_seconds(segment.source_end) - self._timestamp_to_seconds(segment.source_start)
            speed = max(0.5, min(2.0, float(segment.speed or 1.0)))
            segment.speed = speed
            if segment.output_duration_seconds <= 0:
                segment.output_duration_seconds = max(0.2, source_duration / speed)
        if decision.total_duration_seconds <= 0 and decision.segments:
            decision.total_duration_seconds = max(
                self._timestamp_to_seconds(segment.timeline_end) for segment in decision.segments
            )
        self._ensure_rendered_segment_entries(decision)
        decision.merged_segments_path = ""
        decision.merge_command = ""
        decision.merge_error_message = ""
        decision.updated_at = _utcnow()

    def _build_ffmpeg_command_payload(
        self,
        *,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
        summary: str,
    ) -> Dict[str, Any]:
        decision = working_state.executable_edit
        if not decision.segments:
            raise RuntimeError("当前没有可执行片段映射。")

        subtitle_required = bool(decision.burn_subtitles and working_state.subtitle_draft.strip())
        filter_complex, output_options = self._build_filter_complex_for_segments(
            segments=decision.segments,
            aspect_ratio=decision.aspect_ratio,
            subtitle_file="{{subtitle_file}}" if subtitle_required else None,
        )
        command_template = (
            f'-filter_complex "{filter_complex}" '
            f'-map "[vout]" -map "[aout]" '
            f'{output_options}'
        ).strip()
        return {
            "command_template": command_template,
            "output_extension": "mp4",
            "summary": summary.strip() or decision.summary or turn.user_prompt.strip(),
            "needs_subtitle_file": subtitle_required,
        }

    def _build_segment_render_command_args(
        self,
        *,
        session: CaptionSession,
        segment: ClipSegment,
        output_path: str,
        aspect_ratio: str,
        drop_audio: bool,
        speed_override: float | None = None,
        vf_override: str | None = None,
        af_override: str | None = None,
    ) -> List[str]:
        width, height = self._resolution_for_aspect_ratio(aspect_ratio)
        start = self._timestamp_to_seconds(segment.source_start)
        end = self._timestamp_to_seconds(segment.source_end)
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
        has_audio = self._video_has_audio_stream(session.video_path)
        if drop_audio or not has_audio:
            args.extend(["-an"])
        else:
            args.extend(["-map", "0:v:0", "-map", "0:a:0"])
            if af_override and af_override.strip():
                audio_filter = af_override.strip()
            elif abs(speed - 1.0) >= 1e-6:
                audio_filter = ",".join(self._build_atempo_filters(speed))
            else:
                audio_filter = ""
            if audio_filter:
                args.extend(["-af", audio_filter])
            args.extend(["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-shortest"])
        args.append(output_path)
        return args

    def _build_filter_complex_for_segments(
        self,
        *,
        segments: List[ClipSegment],
        aspect_ratio: str,
        subtitle_file: str | None,
    ) -> tuple[str, str]:
        width, height = self._resolution_for_aspect_ratio(aspect_ratio)
        parts: List[str] = []
        concat_inputs: List[str] = []
        for index, segment in enumerate(segments):
            start = self._timestamp_to_seconds(segment.source_start)
            end = self._timestamp_to_seconds(segment.source_end)
            if end <= start:
                raise RuntimeError(f"片段 {segment.id} 的 source_end 必须大于 source_start。")
            speed = max(0.5, min(2.0, float(segment.speed or 1.0)))
            video_pts = "PTS-STARTPTS" if abs(speed - 1.0) < 1e-6 else f"(PTS-STARTPTS)/{speed}"
            audio_filters = [f"atrim=start={start}:end={end}", "asetpts=PTS-STARTPTS"]
            if abs(speed - 1.0) >= 1e-6:
                audio_filters.extend(self._build_atempo_filters(speed))
            parts.append(
                f"[0:v]trim=start={start}:end={end},setpts={video_pts},"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[v{index}]"
            )
            parts.append(f"[0:a]{','.join(audio_filters)}[a{index}]")
            concat_inputs.append(f"[v{index}][a{index}]")

        parts.append(f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a=1[vcat][aout]")
        if subtitle_file:
            escaped_subtitle = self._escape_subtitle_filter_path(subtitle_file)
            parts.append(f"[vcat]subtitles='{escaped_subtitle}'[vout]")
        else:
            parts.append("[vcat]null[vout]")

        return ";".join(parts), "-c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart"

    def _build_atempo_filters(self, speed: float) -> List[str]:
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

    def _resolution_for_aspect_ratio(self, aspect_ratio: str) -> tuple[int, int]:
        mapping = {
            "9:16": (1080, 1920),
            "1:1": (1080, 1080),
            "16:9": (1920, 1080),
        }
        return mapping.get(aspect_ratio.strip(), (1080, 1920))

    def _timestamp_to_seconds(self, value: str) -> float:
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

    def _escape_subtitle_filter_path(self, path: str) -> str:
        return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    def _summarize_clip_segments(self, segments: List[ClipSegment]) -> str:
        if not segments:
            return ""
        lines = []
        for segment in segments[:12]:
            lines.append(
                f"{segment.id}: 原视频 {segment.source_start}-{segment.source_end} -> "
                f"成片 {segment.timeline_start}-{segment.timeline_end} | {segment.purpose or segment.visual_instruction or '无说明'}"
            )
        return "\n".join(lines)

    def _get_rendered_segment(self, decision: ExecutableEditDecision, segment_id: str) -> RenderedClipSegment | None:
        for item in decision.rendered_segments:
            if item.segment_id == segment_id:
                return item
        return None

    def _ensure_rendered_segment_entries(self, decision: ExecutableEditDecision) -> None:
        known_ids = {item.segment_id for item in decision.rendered_segments}
        for segment in decision.segments:
            if segment.id not in known_ids:
                decision.rendered_segments.append(RenderedClipSegment(segment_id=segment.id))
        decision.rendered_segments = [
            item for item in decision.rendered_segments if any(segment.id == item.segment_id for segment in decision.segments)
        ]

    def _next_pending_segment(self, decision: ExecutableEditDecision) -> ClipSegment | None:
        self._ensure_rendered_segment_entries(decision)
        for segment in decision.segments:
            rendered = self._get_rendered_segment(decision, segment.id)
            if rendered and rendered.status in {"todo", "blocked"}:
                return segment
        return None

    def _all_segments_rendered(self, decision: ExecutableEditDecision) -> bool:
        self._ensure_rendered_segment_entries(decision)
        if not decision.segments:
            return False
        return all(
            (rendered := self._get_rendered_segment(decision, segment.id)) is not None
            and rendered.status == "done"
            and rendered.storage_path
            for segment in decision.segments
        )

    def _summarize_rendered_segments(self, decision: ExecutableEditDecision) -> str:
        self._ensure_rendered_segment_entries(decision)
        lines: List[str] = []
        for segment in decision.segments[:20]:
            rendered = self._get_rendered_segment(decision, segment.id)
            if rendered is None:
                continue
            lines.append(
                f"{segment.id}: status={rendered.status}, file={rendered.file_name or '无'}, error={rendered.error_message[:120] or '无'}"
            )
        return "\n".join(lines)

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

    def _materialize_ffmpeg_command_args(
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

    async def _run_ffmpeg_command(self, command_args: List[str]) -> None:
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

    def _video_has_audio_stream(self, video_path: str) -> bool:
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

    def get_exported_video_path(self, session_id: str) -> str:
        session = self.store.get(session_id)
        edited_video = session.global_editing_state.edited_video
        if not edited_video.storage_path:
            raise KeyError(f"session '{session_id}' has no exported video")
        if not os.path.exists(edited_video.storage_path):
            raise FileNotFoundError(edited_video.storage_path)
        return edited_video.storage_path

    def _build_open_tool_targets(self) -> Dict[str, Any]:
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

    def _selected_ids_from_targets(self, targets: Dict[str, Any]) -> List[str]:
        mapping = [
            ("keyframe_analysis", targets.get("run_keyframe_analysis")),
            ("subtitle_draft", targets.get("update_subtitles")),
            ("editing_plan", targets.get("update_editing_plan")),
            ("english_title", targets.get("update_title")),
            ("tags", targets.get("update_tags")),
            ("edited_video", targets.get("update_edited_video")),
        ]
        return [task_id for task_id, enabled in mapping if enabled]

    def _create_turn_task_board(
        self,
        summary: str,
        selected_ids: List[str],
        *,
        export_intent: bool = False,
    ) -> TurnTaskBoard:
        tasks: List[TaskBoardItem] = []
        selected_id_set = set(selected_ids)
        for task_id, title in [
            ("keyframe_analysis", "分析关键帧并建立视频上下文"),
            ("subtitle_draft", "生成或更新字幕草稿"),
            ("editing_plan", "生成或更新剪辑方案"),
            ("english_title", "生成英文标题"),
            ("tags", "生成标签"),
        ]:
            if task_id in selected_id_set:
                tasks.append(TaskBoardItem(id=task_id, title=title))
        if export_intent:
            tasks.extend(
                [
                    TaskBoardItem(id="derive_clip_segments", title="建立原视频片段映射"),
                    TaskBoardItem(id="run_video_edit_subagent", title="调用剪辑导出子代理"),
                    TaskBoardItem(id="verify_export", title="确认成片可下载"),
                ]
            )
        current_focus = tasks[0].id if tasks else ""
        return TurnTaskBoard(
            summary=summary.strip() or "执行本轮视频创作任务",
            current_focus=current_focus,
            blocked_reason="",
            tasks=tasks,
            updated_at=_utcnow(),
        )

    def _serialize_task_board(self, task_board: TurnTaskBoard) -> str:
        return json.dumps(asdict(task_board), ensure_ascii=False)

    def _find_task_item(self, turn: AgentTurn, task_id: str) -> TaskBoardItem | None:
        for item in turn.task_board.tasks:
            if item.id == task_id:
                return item
        return None

    def _set_task_status(
        self,
        turn: AgentTurn,
        task_id: str,
        status: str,
        *,
        notes: str = "",
        current_focus: str | None = None,
        blocked_reason: str = "",
    ) -> None:
        item = self._find_task_item(turn, task_id)
        if item is None:
            return
        item.status = status
        if notes:
            item.notes = notes
        item.updated_at = _utcnow()
        if current_focus is not None:
            turn.task_board.current_focus = current_focus
        elif status == "done":
            for candidate in turn.task_board.tasks:
                if candidate.status in {"todo", "doing", "blocked"}:
                    turn.task_board.current_focus = candidate.id
                    break
            else:
                turn.task_board.current_focus = ""
        else:
            turn.task_board.current_focus = task_id
        turn.task_board.blocked_reason = blocked_reason
        turn.task_board.updated_at = _utcnow()

    def _build_runtime_task_brief(self) -> str:
        return (
            "理解并精准执行用户的最新指令。"
            "\n【严重警告】只调用完成指令所需的工具。但是，如果用户一次性下达了多个连贯任务（例如：写文案 -> 出方案 -> 导出视频），你必须在当前轮次内连续调用多个工具一口气做完最终产物！绝不允许在中间步骤停下来询问用户“草稿是否满意”、“是否继续”。"
            "\n【多任务强制规则】面对包含 2 个及以上步骤的需求，你必须第一步先调用 create_task_board 把所有步骤规划好！系统会监督你全部完成。"
            "\n如果用户要求导出视频，必须先补齐视觉摘要、字幕和剪辑方案，再调用 derive_clip_segments 和 run_video_edit_subagent。"
            "\n只有当所有要求的任务都已彻底完成，或者严重缺乏前置信息时，才触发 finalize。"
        )

    def _build_recent_turn_memory(
        self,
        session: CaptionSession,
        current_turn_id: str,
        *,
        limit: int = 6,
    ) -> str:
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

    def _build_runtime_context_prompt(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        targets: Dict[str, Any],
    ) -> str:
        del targets
        history = self._build_recent_turn_memory(session, session.active_turn_id, limit=6)
        instruction = """
[当前任务指引]
- 如果这是会话的第一轮且用户没提明确要求，请先通过对话了解目标。
- 【严禁中途打断】如果用户指令包含多个步骤（如生成字幕并出方案并剪辑），请连续调用工具达成所有最终目的，绝对不要在某一个中间产物生成后停下来让用户确认！一气呵成！
- 服务端会自动注入 ffmpeg 的输入视频路径与输出文件路径，不允许向用户再次索要。
- 导出视频时：应先调用 derive_clip_segments，再调用 run_video_edit_subagent 交给专门的剪辑导出子代理执行。
- 只有当你认为本轮所有物理操作已全部完成，才执行 finalize。
""".strip()
        current_state = (
            "[当前剪辑状态 - 权威事实]\n"
            f"视频路径: {session.video_path}\n"
            f"导出目录: {os.path.join(settings.export_dir, session.session_id)}\n"
            f"平台: {session.platform}\n"
            f"说明书: {session.product_manual or '无'}\n"
            f"任务板: {self._serialize_task_board(self._get_turn(session, session.active_turn_id).task_board)}\n"
            f"视频摘要: {working_state.video_summary or '尚未分析'}\n"
            f"关键帧分析: {json.dumps(working_state.frame_analyses[:12], ensure_ascii=False) if working_state.frame_analyses else '尚未分析'}\n"
            f"字幕草稿: {working_state.subtitle_draft or '未生成'}\n"
            f"剪辑方案: {working_state.editing_plan or '未生成'}\n"
            f"片段映射: {self._summarize_clip_segments(working_state.executable_edit.segments) or '未生成'}\n"
            f"英文标题: {working_state.english_title or '未生成'}\n"
            f"标签: {json.dumps(working_state.tags, ensure_ascii=False) if working_state.tags else '未生成'}\n"
            f"导出视频地址: {working_state.edited_video.download_url or '尚未导出'}\n"
            f"导出错误: {working_state.edited_video.error_message or '无'}"
        )
        return f"[历史对话记忆]\n{history}\n\n{instruction}\n\n{current_state}"

    def _build_video_edit_task_brief(
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
            f"\n用户目标：{user_prompt.strip() or '执行视频导出'}"
            f"\n平台：{session.platform}"
            f"\n字幕是否可用：{bool(working_state.subtitle_draft.strip())}"
        )

    def _build_video_edit_context_prompt(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
    ) -> str:
        return (
            f"输入视频路径：{session.video_path}"
            f"\n输出目录：{os.path.join(settings.export_dir, session.session_id)}"
            f"\n当前任务板：{self._serialize_task_board(turn.task_board)}"
            f"\n片段映射摘要：\n{self._summarize_clip_segments(working_state.executable_edit.segments) or '无'}"
            f"\n片段渲染状态：\n{self._summarize_rendered_segments(working_state.executable_edit) or '无'}"
            f"\n字幕草稿预览：{working_state.subtitle_draft[:1200] if working_state.subtitle_draft else '无'}"
            f"\n字幕开关：{working_state.executable_edit.burn_subtitles}"
            f"\n目标比例：{working_state.executable_edit.aspect_ratio}"
            f"\n上一次失败命令：{working_state.edited_video.command or '无'}"
            f"\n上一次错误：{working_state.edited_video.error_message or '无'}"
            f"\n片段合并错误：{working_state.executable_edit.merge_error_message or '无'}"
        )

    def _build_video_edit_completion_guard(self, working_state: GlobalEditingState):
        def guard(_scratchpad: List[Dict[str, str]]) -> bool:
            return bool(working_state.edited_video.download_url)

        return guard

    def _build_video_edit_fallback_step(
        self,
        session: CaptionSession,
        turn: AgentTurn,
        working_state: GlobalEditingState,
    ):
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
                and self._observation_has_failure(str(item.get("observation", "")))
            ]
            if (
                last_action == "render_clip_segment"
                and self._observation_has_failure(last_observation)
                and self._count_identical_action_attempts(scratchpad, "render_clip_segment", last_input) >= 2
            ):
                payload = self._parse_json_object(last_input)
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
            next_segment = self._next_pending_segment(working_state.executable_edit)
            if next_segment is not None:
                return ReActStep(
                    f"还有未完成片段 {next_segment.id}，需要先逐段渲染。",
                    "render_clip_segment",
                    json.dumps({"segment_id": next_segment.id}, ensure_ascii=False),
                )
            if self._all_segments_rendered(working_state.executable_edit) and not working_state.edited_video.download_url:
                return ReActStep(
                    "所有片段都已渲染完成，下一步应合并片段并在需要时烧录字幕。",
                    "merge_rendered_segments",
                    json.dumps({"burn_subtitles": working_state.executable_edit.burn_subtitles}, ensure_ascii=False),
                )
            if repeated_render_failures:
                latest_failure = repeated_render_failures[-1]
                return ReActStep(
                    "render_clip_segment 已连续报错，不能再重复原参数；必须修改 vf_override、af_override 或 drop_audio 后继续渲染。",
                    "read_video_edit_context",
                    "",
                )
            if working_state.edited_video.error_message or working_state.executable_edit.merge_error_message:
                return ReActStep("上一次导出失败，需要重新读取上下文并修正参数。", "read_video_edit_context", "")
            return ReActStep("已经具备导出结果。", "finalize", "")

        return fallback

    def _build_video_edit_step_skipper(self):
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
            if any(self._observation_has_failure(str(item.get("observation", ""))) for item in matched_items):
                return False
            return any(
                item.get("action") == step.action
                and str(item.get("action_input", "")).strip() == normalized_input
                for item in scratchpad
            )

        return should_skip

    def _observation_has_failure(self, observation: str) -> bool:
        normalized = observation.strip().lower()
        return any(keyword in normalized for keyword in ["错误", "失败", "error", "failed", "invalid"])

    def _count_identical_action_attempts(
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

    def _build_completion_guard(self, turn: AgentTurn, targets: Dict[str, Any], working_state: GlobalEditingState):
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

    def _build_fallback_step(self, turn: AgentTurn, targets: Dict[str, Any]):
        def fallback(scratchpad: List[Dict[str, str]]) -> ReActStep:
            action_names = {str(item.get("action", "")).strip() for item in scratchpad}
            if turn.task_board.blocked_reason and "run_video_edit_subagent" in action_names:
                return ReActStep("导出子代理执行失败，请检查上下文错误并修正重试。", "run_video_edit_subagent", "")
            if not scratchpad:
                return ReActStep("未检测到工具调用，请直接输出对用户的回答，或者调用所需工具。", "finalize", "")
            return ReActStep("操作已结束或陷入未知状态，请整理结果回复用户。", "finalize", "")

        return fallback

    def _build_step_skipper(self):
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
            ("clip_segments", targets.get("update_edited_video"), "正在建立原视频片段映射。"),
            ("english_title", targets.get("update_title"), "正在生成或更新英文标题。"),
            ("tags", targets.get("update_tags"), "正在生成或更新标签。"),
            ("edited_video", targets.get("update_edited_video"), "正在由剪辑导出子代理执行视频导出。"),
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
        action_names: set[str],
    ) -> str:
        sections: List[str] = []
        if "run_keyframe_vision_subagent" in action_names and working_state.video_summary:
            sections.append(f"视频摘要：\n{working_state.video_summary.strip()}")
        if "write_subtitles" in action_names and working_state.subtitle_draft:
            sections.append(f"字幕草稿：\n{working_state.subtitle_draft.strip()}")
        if "write_edit_plan" in action_names and working_state.editing_plan:
            sections.append(f"剪辑方案：\n{working_state.editing_plan.strip()}")
        if "derive_clip_segments" in action_names and working_state.executable_edit.segments:
            sections.append("片段映射：\n" + self._summarize_clip_segments(working_state.executable_edit.segments))
        if "write_title" in action_names and working_state.english_title:
            sections.append(f"英文标题：\n{working_state.english_title.strip()}")
        if "write_tags" in action_names and working_state.tags:
            sections.append(
                "标签：\n" + "\n".join(f"- {tag}" for tag in working_state.tags if str(tag).strip())
            )
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

    def _build_turn_summary(self, turn: AgentTurn, working_state: GlobalEditingState) -> str:
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

    def _build_error_turn_summary(self, turn: AgentTurn, error_message: str) -> str:
        return (
            f"用户需求：{turn.user_prompt.strip()[:180]}"
            f"\n计划摘要：{turn.plan_summary.strip()[:400] or '无'}"
            f"\n结果：执行失败"
            f"\n错误：{error_message[:500]}"
        )

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
