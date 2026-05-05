from __future__ import annotations

import asyncio
from typing import List

from app.core.config import settings
from app.core.utils import extract_keyframes, select_keyframes_for_analysis
from app.models import AgentTurn, CaptionSession, GlobalEditingState
from app.services.caption_assistant_runtime.completion import CompletionService
from app.services.caption_assistant_runtime.prompts import (
    VIDEO_SUMMARY_SYSTEM_PROMPT,
)
from app.services.caption_assistant_runtime.shared import prompt_block
from app.services.caption_assistant_runtime.task_board import TaskBoardService


class VideoContextService:
    def __init__(
        self,
        completion_service: CompletionService,
        task_board_service: TaskBoardService,
    ) -> None:
        self._completion_service = completion_service
        self._task_board_service = task_board_service

    async def run_keyframe_vision_subagent(
        self,
        turn: AgentTurn,
        session: CaptionSession,
        working_state: GlobalEditingState,
    ) -> str:
        analysis_label = "逐秒分析" if session.analysis_mode == "every_second" else "关键帧分析"
        self._task_board_service.set_task_status(
            turn,
            "keyframe_analysis",
            "doing",
            notes=f"正在执行{analysis_label}。",
        )
        if (
            working_state.video_summary
            and working_state.frame_analyses
            and not working_state.workflow.keyframe_analysis.needs_refresh
        ):
            self._task_board_service.set_task_status(
                turn,
                "keyframe_analysis",
                "done",
                notes=f"视频上下文已存在，跳过重复{analysis_label}。",
            )
            return f"视频上下文已存在，跳过重复{analysis_label}。"

        working_state.keyframes = []
        working_state.frame_analyses = []
        working_state.video_summary = ""
        await self.prepare_video_context(session, working_state)
        self._task_board_service.set_task_status(
            turn,
            "keyframe_analysis",
            "done",
            notes=f"{analysis_label}与视频摘要已完成。",
        )
        return (
            f"{analysis_label}已完成。"
            f"\n分析帧数量：{len(working_state.keyframes)}"
            f"\n分析结果数量：{len(working_state.frame_analyses)}"
            f"\n视频摘要：{working_state.video_summary or '无'}"
        )

    async def prepare_video_context(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
        *,
        interval_seconds: int | None = None,
        max_frames: int | None = None,
    ) -> None:
        is_every_second_mode = session.analysis_mode == "every_second"
        effective_interval = interval_seconds if interval_seconds is not None else (
            1 if is_every_second_mode else settings.keyframe_interval_seconds
        )
        effective_max_frames = max_frames if max_frames is not None else (
            None if is_every_second_mode else settings.max_keyframes
        )
        effective_scene_threshold = None if is_every_second_mode else settings.keyframe_scene_threshold
        analysis_label = "逐秒分析" if is_every_second_mode else "关键帧分析"

        self._task_board_service.update_workflow_artifact(
            working_state,
            "keyframe_analysis",
            status="in_progress",
            detail=f"正在提取{analysis_label}所需画面并进行分析。",
            requested=True,
            needs_refresh=False,
        )
        self._task_board_service.update_workflow_artifact(
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
            effective_interval,
            None,
            effective_scene_threshold,
            not is_every_second_mode,
        )
        working_state.frame_analyses = await self.analyze_video_frames(
            working_state,
            max_frames=effective_max_frames,
            analysis_mode=session.analysis_mode,
        )
        working_state.video_summary = await self.summarize_video(session, working_state)
        self._task_board_service.complete_workflow_artifact(
            working_state,
            "keyframe_analysis",
            f"已完成 {len(working_state.frame_analyses)} 条{analysis_label}理解。",
        )
        self._task_board_service.complete_workflow_artifact(
            working_state,
            "video_summary",
            "视频摘要已生成。",
        )

    async def analyze_video_frames(
        self,
        working_state: GlobalEditingState,
        *,
        max_frames: int | None = None,
        analysis_mode: str = "keyframe",
    ) -> List[str]:
        if analysis_mode == "every_second":
            analysis_frames = working_state.keyframes
        else:
            analysis_frames = select_keyframes_for_analysis(
                working_state.keyframes,
                max_frames=max_frames or settings.max_keyframes,
            )
        tasks = []
        for index, keyframe in enumerate(analysis_frames, start=1):
            tasks.append(
                self.analyze_single_frame(
                    index,
                    str(keyframe.get("image_base64", "")),
                )
            )

        results = await asyncio.gather(*tasks)

        analyses: List[str] = []
        for i, analysis in enumerate(results):
            keyframe = analysis_frames[i]
            index = i + 1
            timestamp = keyframe.get("timestamp_seconds")
            source = keyframe.get("source", "unknown")
            analyses.append(f"关键帧{index}（{timestamp}s, 来源: {source}）: {analysis}")

        return analyses

    async def analyze_single_frame(self, frame_index: int, frame_base64: str) -> str:
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
        return await self._completion_service.vision_complete(prompt, frame_base64, trace_label=f"keyframe_{frame_index}")

    async def summarize_video(
        self,
        session: CaptionSession,
        working_state: GlobalEditingState,
    ) -> str:
        prompt = (
            "任务：总结视频的核心内容、产品卖点、适合人群、镜头节奏，以及适合做字幕和剪辑决策的信息。"
            + prompt_block("平台", session.platform)
            + prompt_block("说明书", session.product_manual or "无说明书")
            + prompt_block("关键帧分析", "\n".join(working_state.frame_analyses))
        )
        return await self._completion_service.text_complete(
            prompt,
            system_prompt=VIDEO_SUMMARY_SYSTEM_PROMPT,
        )

    async def tool_read_video_context(self, working_state: GlobalEditingState) -> str:
        return (
            f"视频摘要：{working_state.video_summary or '暂无'}\n关键帧分析：\n"
            + "\n".join(working_state.frame_analyses or ["暂无"])
        )

    async def tool_read_manual(self, session: CaptionSession) -> str:
        return session.product_manual or "用户未提供说明书。"
