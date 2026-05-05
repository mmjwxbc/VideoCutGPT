from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List

from app.models import AgentTurn, EditedVideoArtifact, GlobalEditingState, TaskBoardItem, TurnTaskBoard, utcnow
from app.services.caption_assistant_runtime.shared import parse_json_object


class TaskBoardService:
    def create_turn_task_board(
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
            updated_at=utcnow(),
        )

    def serialize_task_board(self, task_board: TurnTaskBoard) -> str:
        return json.dumps(asdict(task_board), ensure_ascii=False)

    def selected_ids_from_targets(self, targets: Dict[str, Any]) -> List[str]:
        mapping = [
            ("keyframe_analysis", targets.get("run_keyframe_analysis")),
            ("subtitle_draft", targets.get("update_subtitles")),
            ("editing_plan", targets.get("update_editing_plan")),
            ("english_title", targets.get("update_title")),
            ("tags", targets.get("update_tags")),
            ("edited_video", targets.get("update_edited_video")),
        ]
        return [task_id for task_id, enabled in mapping if enabled]

    def find_task_item(self, turn: AgentTurn, task_id: str) -> TaskBoardItem | None:
        for item in turn.task_board.tasks:
            if item.id == task_id:
                return item
        return None

    def set_task_status(
        self,
        turn: AgentTurn,
        task_id: str,
        status: str,
        *,
        notes: str = "",
        current_focus: str | None = None,
        blocked_reason: str = "",
    ) -> None:
        item = self.find_task_item(turn, task_id)
        if item is None:
            return
        item.status = status
        if notes:
            item.notes = notes
        item.updated_at = utcnow()
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
        turn.task_board.updated_at = utcnow()

    def update_workflow_artifact(
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
        item.updated_at = utcnow()
        working_state.updated_at = item.updated_at

    def complete_workflow_artifact(
        self,
        working_state: GlobalEditingState,
        artifact: str,
        detail: str,
    ) -> None:
        self.update_workflow_artifact(
            working_state,
            artifact,
            status="completed",
            detail=detail,
            requested=True,
            needs_refresh=False,
        )

    def mark_selected_items_in_progress(
        self,
        working_state: GlobalEditingState,
        targets: Dict[str, Any],
    ) -> None:
        if targets.get("run_keyframe_analysis"):
            self.update_workflow_artifact(
                working_state,
                "keyframe_analysis",
                status="in_progress",
                detail="正在提取并分析关键帧。",
                requested=True,
                needs_refresh=False,
            )
            self.update_workflow_artifact(
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
                self.update_workflow_artifact(
                    working_state,
                    key,
                    status="in_progress",
                    detail=detail,
                    requested=True,
                    needs_refresh=False,
                )

    def invalidate_edited_video_due_to_upstream_change(
        self,
        working_state: GlobalEditingState,
        *,
        detail: str,
    ) -> None:
        working_state.edited_video = EditedVideoArtifact()
        self.update_workflow_artifact(
            working_state,
            "edited_video",
            status="idle",
            detail=detail,
            requested=True,
            needs_refresh=True,
        )

    async def tool_create_task_board(
        self,
        turn: AgentTurn,
        action_input: str,
    ) -> str:
        payload = parse_json_object(action_input)
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
        turn.task_board = self.create_turn_task_board(summary, selected_ids, export_intent=export_intent)
        return self.serialize_task_board(turn.task_board)

    async def tool_read_task_board(self, turn: AgentTurn) -> str:
        if not turn.task_board.tasks:
            return "当前轮次任务板为空。请先调用 create_task_board。"
        return self.serialize_task_board(turn.task_board)

    async def tool_update_task_status(self, turn: AgentTurn, action_input: str) -> str:
        payload = parse_json_object(action_input)
        task_id = str(payload.get("task_id", "")).strip() if isinstance(payload, dict) else ""
        status = str(payload.get("status", "")).strip() if isinstance(payload, dict) else ""
        notes = str(payload.get("notes", "")).strip() if isinstance(payload, dict) else ""
        current_focus = str(payload.get("current_focus", "")).strip() if isinstance(payload, dict) else ""
        blocked_reason = str(payload.get("blocked_reason", "")).strip() if isinstance(payload, dict) else ""
        if not task_id or not status:
            raise RuntimeError("update_task_status 需要传入 task_id 和 status。")
        self.set_task_status(
            turn,
            task_id,
            status,
            notes=notes,
            current_focus=current_focus or None,
            blocked_reason=blocked_reason,
        )
        return self.serialize_task_board(turn.task_board)
