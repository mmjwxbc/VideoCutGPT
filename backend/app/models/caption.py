from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal


AnalysisMode = Literal["keyframe", "every_second"]


def utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="microseconds") + "Z"


@dataclass
class WorkflowArtifactState:
    label: str
    status: str = "idle"
    detail: str = ""
    requested: bool = False
    needs_refresh: bool = False
    updated_at: str = field(default_factory=utcnow)


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
    created_at: str = field(default_factory=utcnow)


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
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)


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
    updated_at: str = field(default_factory=utcnow)


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
    updated_at: str = field(default_factory=utcnow)


@dataclass
class TurnEventItem:
    type: str
    content: str = ""
    tool_name: str = ""
    arguments: str = ""
    created_at: str = field(default_factory=utcnow)


@dataclass
class TaskBoardItem:
    id: str
    title: str
    status: str = "todo"
    notes: str = ""
    updated_at: str = field(default_factory=utcnow)


@dataclass
class TurnTaskBoard:
    summary: str = ""
    current_focus: str = ""
    blocked_reason: str = ""
    tasks: List[TaskBoardItem] = field(default_factory=list)
    updated_at: str = field(default_factory=utcnow)


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
    started_at: str = field(default_factory=utcnow)
    finished_at: str = ""


@dataclass
class CaptionSession:
    session_id: str
    video_path: str
    platform: str
    product_manual: str
    analysis_mode: AnalysisMode = "keyframe"
    turns: List[AgentTurn] = field(default_factory=list)
    global_editing_state: GlobalEditingState = field(default_factory=GlobalEditingState)
    status: str = "idle"
    active_turn_id: str = ""
    error_message: str = ""
    version: int = 0
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)


def serialize_session(session: CaptionSession) -> Dict[str, Any]:
    editing_state = asdict(session.global_editing_state)
    if isinstance(editing_state.get("edited_video"), dict):
        editing_state["edited_video"].pop("storage_path", None)
    return {
        "session_id": session.session_id,
        "platform": session.platform,
        "analysis_mode": session.analysis_mode,
        "turns": [asdict(turn) for turn in session.turns],
        "global_editing_state": editing_state,
        "status": session.status,
        "active_turn_id": session.active_turn_id,
        "error_message": session.error_message,
        "version": session.version,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }
