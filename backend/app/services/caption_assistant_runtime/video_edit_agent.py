from __future__ import annotations

from dataclasses import dataclass

from app.agent.runtime import LightPlanningReActRuntime
from app.core.config import settings
from app.models import AgentTurn, CaptionSession, GlobalEditingState


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

        assistant.task_board_service.set_task_status(
            turn,
            "run_video_edit_subagent",
            "doing",
            notes="导出子代理正在读取上下文并尝试执行 ffmpeg。",
            current_focus="run_video_edit_subagent",
        )

        if not working_state.executable_edit.segments:
            await assistant.tool_derive_clip_segments(
                turn,
                session,
                working_state,
                user_prompt,
                user_prompt,
            )

        registry = assistant.build_video_edit_tool_registry(
            session=session,
            turn=turn,
            working_state=working_state,
            user_prompt=user_prompt,
        )
        runtime = LightPlanningReActRuntime(
            adapter=assistant.completion_service.adapter_factory.get_text_adapter(),
            model=settings.deepseek_chat_model,
            tool_registry=registry,
            max_steps=20,
            timeout_seconds=settings.glm_request_timeout_seconds,
        )
        result = await runtime.run(
            user_prompt=user_prompt,
            task_brief=assistant.build_video_edit_task_brief(session, turn, working_state, user_prompt),
            context_prompt=assistant.build_video_edit_context_prompt(session, turn, working_state),
            completion_guard=assistant.build_video_edit_completion_guard(working_state),
            fallback_step=assistant.build_video_edit_fallback_step(session, turn, working_state),
            should_skip_step=assistant.build_video_edit_step_skipper(),
            progress=assistant.noop_progress,
            trace=lambda thought, _action, observation: assistant.append_turn_thought(
                session,
                turn,
                thought,
                observation,
            ),
        )
        if working_state.edited_video.download_url:
            assistant.task_board_service.set_task_status(
                turn,
                "run_video_edit_subagent",
                "done",
                notes="导出子代理已完成视频拼接与导出。",
                current_focus="verify_export",
            )
            return result.scratchpad[-1]["observation"] if result.scratchpad else "导出子代理已完成视频导出。"

        last_error = working_state.edited_video.error_message or turn.task_board.blocked_reason or "导出子代理执行失败。"
        assistant.task_board_service.set_task_status(
            turn,
            "run_video_edit_subagent",
            "blocked",
            notes=last_error,
            current_focus="run_video_edit_subagent",
            blocked_reason=last_error,
        )
        return last_error
