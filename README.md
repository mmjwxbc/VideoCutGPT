# Oversea Agent

An editing-state-driven conversational video editing agent.

Oversea Agent is not a one-shot subtitle generator and not a generic chat wrapper around video tools. It is a session-based editing system where the agent advances a video project by moving explicit editing artifacts through a controlled workflow: video understanding, subtitle drafting, editing plan generation, clip derivation, and final export.

The core idea is simple: the conversation does not directly edit a file. It edits the **global editing state**, and the state drives the next editing step.

## What This Project Is

Oversea Agent is built for short-form commerce and growth video production. A user uploads a video, provides product context and intent, then works with the agent through a continuous dialogue. Each round updates a persistent session instead of restarting from zero.

The system keeps three layers aligned:

- `turns`: the conversational history and agent events for each request.
- `global_editing_state`: the durable editing artifacts accumulated across the session.
- `workflow`: the explicit status model that tells the agent what is ready, stale, blocked, or exportable.

This makes the product closer to an editing runtime than a prompt box.

## Editing State Model

The session state is designed around composable editing artifacts, not raw model output.

- `keyframe_analysis`: extracted keyframes and frame-level vision analysis.
- `video_summary`: a compact understanding of the source footage.
- `subtitle_draft`: the current working subtitle draft.
- `editing_plan`: the current shot-level editing plan.
- `clip_segments`: executable segment mappings from source timeline to output timeline.
- `english_title`: title generation for publish-ready assets.
- `tags`: tag generation for distribution.
- `edited_video`: exported output and download metadata.

Every artifact has workflow metadata such as `status`, `requested`, `needs_refresh`, and `updated_at`. This is what lets the agent reason about what should happen next instead of regenerating everything on every turn.

## How The Agent Works

The agent progresses through editing by reading and mutating the session state through tool calls.

Typical flow:

1. Create a session with video, platform, prompt, and optional product manual.
2. Run video understanding on keyframes or per-second analysis.
3. Draft subtitles and a shot-level editing plan.
4. Derive executable clip segments from the plan.
5. Run the export sub-agent to assemble and render with `ffmpeg`.
6. Continue the same thread with follow-up prompts to refine any artifact.

Because the session is stateful, a follow-up like "make the hook sharper" or "export a faster version for TikTok" updates the relevant artifact instead of rebuilding the entire project blindly.

## Product Surface

The current UI is a conversational caption and editing workspace:

- upload a source video
- choose a target platform
- select an analysis mode
- provide product or campaign context
- iterate in a single conversation thread
- inspect workflow progress through SSE-driven session updates
- export the edited video from the same session

## Architecture

### Backend

- `FastAPI` for session and streaming APIs
- session-oriented runtime for conversational editing
- multimodal analysis for keyframe understanding
- tool-based agent orchestration for subtitles, editing plans, and export
- `ffmpeg` / `ffprobe` execution for rendering and verification

Key runtime areas:

- [backend/app/api/endpoints/caption.py](/home/jhli/oversea-agent/backend/app/api/endpoints/caption.py)
- [backend/app/models/caption.py](/home/jhli/oversea-agent/backend/app/models/caption.py)
- [backend/app/services/caption_assistant_runtime/assistant.py](/home/jhli/oversea-agent/backend/app/services/caption_assistant_runtime/assistant.py)
- [backend/app/services/caption_assistant_runtime/tools.py](/home/jhli/oversea-agent/backend/app/services/caption_assistant_runtime/tools.py)
- [backend/app/services/caption_assistant_runtime/video_export.py](/home/jhli/oversea-agent/backend/app/services/caption_assistant_runtime/video_export.py)

### Frontend

- `React + Vite + TypeScript`
- session-driven workspace UI
- SSE subscription for live turn events and state snapshots
- split panels for conversation, workspace state, and history

Key UI areas:

- [frontend/src/pages/CaptionGenerator.tsx](/home/jhli/oversea-agent/frontend/src/pages/CaptionGenerator.tsx)
- [frontend/src/components/caption-studio/ConversationPanel.tsx](/home/jhli/oversea-agent/frontend/src/components/caption-studio/ConversationPanel.tsx)
- [frontend/src/components/caption-studio/WorkspaceSidebar.tsx](/home/jhli/oversea-agent/frontend/src/components/caption-studio/WorkspaceSidebar.tsx)
- [frontend/src/components/caption-studio/HistorySidebar.tsx](/home/jhli/oversea-agent/frontend/src/components/caption-studio/HistorySidebar.tsx)

## API Shape

Core session endpoints:

- `POST /api/caption/assistant/session`
- `GET /api/caption/assistant/session/{session_id}`
- `GET /api/caption/assistant/session/{session_id}/events`
- `POST /api/caption/assistant/session/{session_id}/message`
- `GET /api/caption/assistant/session/{session_id}/exported-video`

The event stream emits authoritative session snapshots and turn-level events so the frontend can render long-running editing work without polling as the primary transport.

## Local Development

### Requirements

- Python `3.12+`
- Node.js `18+`
- `ffmpeg` and `ffprobe` available in `PATH`
- model provider credentials for the configured adapters

### Backend

Install Python dependencies:

```bash
uv sync
```

Run the API:

```bash
cd backend
uv run uvicorn main:app --reload
```

### Frontend

Install frontend dependencies:

```bash
cd frontend
npm install
```

Run the frontend:

```bash
npm run dev
```

## Configuration

Runtime settings live in [backend/app/core/config.py](/home/jhli/oversea-agent/backend/app/core/config.py).

Important configuration areas:

- model credentials such as `OPENAI_API_KEY`, `GLM_API_KEY`, `DEEPSEEK_API_KEY`
- model routing such as `MULTIMODAL_PROVIDER`, `MULTIMODAL_MODEL`
- media controls such as `KEYFRAME_INTERVAL_SECONDS`, `MAX_KEYFRAMES`
- export controls such as `EXPORT_DIR`, `FFMPEG_EXECUTION_TIMEOUT_SECONDS`

The project reads environment variables from `.env`.

## Why This Design

Most AI video tools collapse planning, generation, and export into a single opaque step. This project does the opposite.

It exposes the editing process as a state machine the agent can inspect and update. That makes the system better suited for:

- iterative editing
- partial regeneration
- export retries
- workflow observability
- future multi-agent specialization around distinct editing stages

## Status

The current product center is the conversational caption and editing studio. The architecture already reflects an agent runtime with explicit editing state, live task progression, and export tooling, which makes it a strong base for broader editing automation.

For Chinese documentation, see [README_zh.md](/home/jhli/oversea-agent/README_zh.md).
