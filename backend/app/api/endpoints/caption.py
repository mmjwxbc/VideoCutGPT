import json
import os
import subprocess
import tempfile
from typing import Annotated
from typing import Any
from typing import Literal
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


def _probe_media_streams(video_path: str) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        video_path,
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=settings.ffmpeg_execution_timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="ffprobe 未安装，无法探测上传视频") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="ffprobe 探测视频超时") from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"无法读取上传视频信息: {exc.stderr.strip()}",
        ) from exc

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="ffprobe 返回了无效结果") from exc

    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )
    if not video_stream:
        raise HTTPException(
            status_code=400,
            detail=f"文件 {os.path.basename(video_path)} 不包含视频流",
        )

    return {
        "video": video_stream,
        "audio": audio_stream,
    }


def _parse_frame_rate(rate_value: str | None) -> int:
    if not rate_value or rate_value == "0/0":
        return 30
    numerator, _, denominator = rate_value.partition("/")
    try:
        numerator_value = float(numerator)
        denominator_value = float(denominator) if denominator else 1.0
        if denominator_value <= 0:
            return 30
        frame_rate = numerator_value / denominator_value
    except ValueError:
        return 30
    return max(1, min(int(round(frame_rate)), 60))


def _normalize_dimension(value: Any, fallback: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = fallback
    normalized = max(normalized, 2)
    return normalized if normalized % 2 == 0 else normalized + 1


def _normalize_clip_for_concat(
    input_path: str,
    output_path: str,
    width: int,
    height: int,
    frame_rate: int,
    sample_rate: int,
    has_audio: bool,
) -> None:
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={frame_rate}"
    )
    command = ["ffmpeg", "-y", "-i", input_path]
    if has_audio:
        command.extend(["-map", "0:v:0", "-map", "0:a:0"])
    else:
        command.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=stereo:sample_rate={sample_rate}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
            ]
        )
    command.extend(
        [
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=settings.ffmpeg_execution_timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="ffmpeg 未安装，无法合并上传视频") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="ffmpeg 规范化视频超时") from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"规范化上传视频失败: {exc.stderr.strip()}",
        ) from exc


def _merge_videos(video_paths: list[str]) -> str:
    if len(video_paths) == 1:
        return video_paths[0]

    ensure_directory(settings.upload_dir)
    probe_results = [_probe_media_streams(video_path) for video_path in video_paths]
    first_video_stream = probe_results[0]["video"]
    first_audio_stream = probe_results[0]["audio"] or {}
    target_width = _normalize_dimension(first_video_stream.get("width"), 1280)
    target_height = _normalize_dimension(first_video_stream.get("height"), 720)
    target_frame_rate = _parse_frame_rate(
        first_video_stream.get("avg_frame_rate") or first_video_stream.get("r_frame_rate")
    )
    target_sample_rate = _normalize_dimension(first_audio_stream.get("sample_rate"), 48000)
    merged_path = os.path.join(settings.upload_dir, f"{uuid4().hex}_merged.mp4")

    with tempfile.TemporaryDirectory(prefix="merge_", dir=settings.upload_dir) as temp_dir:
        normalized_paths: list[str] = []
        for index, video_path in enumerate(video_paths):
            normalized_path = os.path.join(temp_dir, f"normalized_{index}.mp4")
            _normalize_clip_for_concat(
                input_path=video_path,
                output_path=normalized_path,
                width=target_width,
                height=target_height,
                frame_rate=target_frame_rate,
                sample_rate=target_sample_rate,
                has_audio=probe_results[index]["audio"] is not None,
            )
            normalized_paths.append(normalized_path)

        concat_list_path = os.path.join(temp_dir, "concat_inputs.txt")
        with open(concat_list_path, "w", encoding="utf-8") as concat_file:
            for normalized_path in normalized_paths:
                concat_file.write(f"file '{normalized_path}'\n")

        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            merged_path,
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=settings.ffmpeg_execution_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="ffmpeg 未安装，无法合并上传视频") from exc
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=500, detail="ffmpeg 合并视频超时") from exc
        except subprocess.CalledProcessError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"合并上传视频失败: {exc.stderr.strip()}",
            ) from exc

    return merged_path


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/assistant/session")
async def create_caption_session(
    platform: Annotated[str, Form(...)],
    prompt: Annotated[str, Form(...)],
    product_manual: Annotated[str | None, Form()] = None,
    analysis_mode: Annotated[Literal["keyframe", "every_second"], Form()] = "keyframe",
    videos: Annotated[list[UploadFile] | None, File()] = None,
    video: Annotated[UploadFile | None, File()] = None,
):
    """
    创建字幕与剪辑助手会话，并异步开始处理。
    """
    uploads = videos or ([video] if video else [])
    if not uploads:
        raise HTTPException(status_code=400, detail="请至少上传一个视频文件")

    uploaded_paths = [await _persist_upload(upload) for upload in uploads]
    video_path = _merge_videos(uploaded_paths)
    return await caption_assistant.create_session(
        video_path=video_path,
        platform=platform,
        product_manual=product_manual,
        user_prompt=prompt,
        analysis_mode=analysis_mode,
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
