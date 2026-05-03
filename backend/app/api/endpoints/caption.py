import json
import os
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.utils import ensure_directory
from app.services.caption_assistant import CaptionConversationAssistant

router = APIRouter()
caption_assistant = CaptionConversationAssistant()


class CaptionFollowUpRequest(BaseModel):
    prompt: str


async def _persist_upload(video: UploadFile) -> str:
    ensure_directory(settings.upload_dir)
    original_name = video.filename or "uploaded_video.mp4"
    unique_name = f"{uuid4().hex}_{original_name}"
    video_path = os.path.join(settings.upload_dir, unique_name)
    with open(video_path, "wb") as buffer:
        content = await video.read()
        buffer.write(content)
    return video_path


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.post("/assistant/session")
async def create_caption_session(
    video: Annotated[UploadFile, File(...)],
    platform: Annotated[str, Form(...)],
    prompt: Annotated[str, Form(...)],
    product_manual: Annotated[str | None, Form()] = None,
):
    """
    创建字幕与剪辑助手会话，并异步开始处理。
    """
    video_path = await _persist_upload(video)
    return await caption_assistant.create_session(
        video_path=video_path,
        platform=platform,
        product_manual=product_manual,
        user_prompt=prompt,
    )


@router.get("/assistant/session/{session_id}/events")
async def stream_caption_session_events(session_id: str, request: Request):
    """
    SSE 推送会话进度与结果。
    """
    try:
        caption_assistant.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def event_generator():
        async for message in caption_assistant.stream_session_events(session_id):
            if await request.is_disconnected():
                break
            yield _format_sse(message["event"], message["data"])

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/assistant/session/{session_id}/message")
async def continue_caption_session(session_id: str, request: CaptionFollowUpRequest):
    """
    继续字幕与剪辑助手会话，并异步开始处理。
    """
    try:
        return await caption_assistant.continue_session(session_id, request.prompt)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/assistant/session/{session_id}")
async def get_caption_session(session_id: str):
    """
    获取字幕与剪辑助手会话详情
    """
    try:
        return caption_assistant.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/assistant/session/{session_id}/exported-video")
async def download_exported_video(session_id: str):
    try:
        video_path = caption_assistant.get_exported_video_path(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"exported video not found: {exc}") from exc

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=os.path.basename(video_path),
    )
