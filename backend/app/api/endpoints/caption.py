import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path as FilePath
from typing import Annotated
from typing import Any
from typing import Literal
from urllib.parse import unquote
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Path, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.utils import ensure_directory
from app.models.caption import utcnow
from app.services.caption_assistant import CaptionConversationAssistant

router = APIRouter()
caption_assistant = CaptionConversationAssistant()
logger = logging.getLogger(__name__)

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}
UPLOAD_TMP_ROOT = os.path.join(settings.upload_dir, "tmp")
UPLOAD_FINAL_ROOT = os.path.join(settings.upload_dir, "final")
CHUNK_UPLOAD_DEFAULT_SIZE = settings.upload_chunk_size


class UploadInitRequest(BaseModel):
    filename: str
    file_size: int
    chunk_size: int
    total_chunks: int
    content_type: str


class UploadInitResponse(BaseModel):
    upload_id: str
    chunk_size: int
    total_chunks: int
    uploaded_chunks: list[int]


class UploadChunkResponse(BaseModel):
    upload_id: str
    chunk_index: int
    status: Literal["uploaded"]


class UploadStatusResponse(BaseModel):
    upload_id: str
    total_chunks: int
    uploaded_chunks: list[int]
    complete: bool


class UploadCompleteSuccessResponse(BaseModel):
    upload_id: str
    file_path: str
    task_id: str
    status: Literal["pending", "running", "done", "failed"]


class UploadCompleteErrorResponse(BaseModel):
    error: str
    missing_chunks: list[int]


class UploadTaskResponse(BaseModel):
    task_id: str
    status: Literal["pending", "running", "done", "failed"]
    progress: float
    result: dict[str, Any] | None = None
    error: str | None = None


class CaptionSessionCreateRequest(BaseModel):
    platform: str
    prompt: str
    product_manual: str | None = None
    analysis_mode: Literal["keyframe", "every_second"] = "keyframe"
    uploaded_file_paths: list[str] = []
    uploaded_file_ids: list[str] = []


class B2UploadUrlRequest(BaseModel):
    filename: str
    content_type: str
    file_size: int


class B2UploadUrlResponse(BaseModel):
    upload_url: str
    authorization_token: str
    file_name: str
    content_type: str


class UploadRecord(BaseModel):
    upload_id: str
    filename: str
    safe_filename: str
    file_size: int
    chunk_size: int
    total_chunks: int
    content_type: str
    final_file_path: str | None = None
    completed: bool = False
    task_id: str | None = None


class TaskRecord(BaseModel):
    task_id: str
    upload_id: str
    status: Literal["pending", "running", "done", "failed"] = "pending"
    progress: float = 0.0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str


upload_records: dict[str, UploadRecord] = {}
task_records: dict[str, TaskRecord] = {}
upload_locks: dict[str, asyncio.Lock] = {}


class CaptionFollowUpRequest(BaseModel):
    prompt: str


def _safe_filename(filename: str) -> str:
    base_name = os.path.basename(filename or "uploaded_video.mp4").strip()
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name).strip("._")
    return sanitized or "uploaded_video.mp4"


def _ensure_allowed_video_type(content_type: str) -> None:
    if content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 mp4/mov/webm/mkv 视频类型")


def _ensure_valid_upload_request(payload: UploadInitRequest) -> None:
    if payload.file_size <= 0:
        raise HTTPException(status_code=400, detail="file_size 必须大于 0")
    if payload.file_size > settings.max_upload_size:
        raise HTTPException(status_code=400, detail="视频文件超过允许的最大大小")
    if payload.chunk_size <= 0:
        raise HTTPException(status_code=400, detail="chunk_size 必须大于 0")
    if payload.total_chunks <= 0:
        raise HTTPException(status_code=400, detail="total_chunks 必须大于 0")
    expected_chunks = (payload.file_size + payload.chunk_size - 1) // payload.chunk_size
    if payload.total_chunks != expected_chunks:
        raise HTTPException(status_code=400, detail="total_chunks 与 file_size/chunk_size 不匹配")
    _ensure_allowed_video_type(payload.content_type)


def _get_upload_lock(upload_id: str) -> asyncio.Lock:
    lock = upload_locks.get(upload_id)
    if lock is None:
        lock = asyncio.Lock()
        upload_locks[upload_id] = lock
    return lock


def _chunk_directory(upload_id: str) -> str:
    return os.path.join(UPLOAD_TMP_ROOT, upload_id)


def _chunk_path(upload_id: str, chunk_index: int) -> str:
    return os.path.join(_chunk_directory(upload_id), f"{chunk_index}.part")


def _list_uploaded_chunks(upload_id: str, total_chunks: int) -> list[int]:
    chunk_dir = _chunk_directory(upload_id)
    if not os.path.isdir(chunk_dir):
        return []

    uploaded_chunks: list[int] = []
    for entry in os.listdir(chunk_dir):
        if not entry.endswith(".part"):
            continue
        try:
            chunk_index = int(entry[:-5])
        except ValueError:
            continue
        if 0 <= chunk_index < total_chunks:
            uploaded_chunks.append(chunk_index)
    uploaded_chunks.sort()
    return uploaded_chunks


def _get_upload_record_or_404(upload_id: str) -> UploadRecord:
    record = upload_records.get(upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"upload '{upload_id}' 不存在")
    return record


def _get_task_record_or_404(task_id: str) -> TaskRecord:
    record = task_records.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"task '{task_id}' 不存在")
    return record


def _assert_managed_final_path(file_path: str) -> str:
    normalized = os.path.abspath(file_path)
    final_root = os.path.abspath(UPLOAD_FINAL_ROOT)
    if not normalized.startswith(f"{final_root}{os.sep}") and normalized != final_root:
        raise HTTPException(status_code=400, detail="uploaded_file_paths 包含非法路径")
    if not os.path.exists(normalized):
        raise HTTPException(status_code=400, detail=f"上传文件不存在: {normalized}")
    return normalized


def _extract_b2_api_url(payload: dict[str, Any]) -> str | None:
    api_url = payload.get("apiUrl")
    if isinstance(api_url, str) and api_url:
        return api_url
    api_info = payload.get("apiInfo")
    if isinstance(api_info, dict):
        storage_api = api_info.get("storageApi")
        if isinstance(storage_api, dict):
            nested_api_url = storage_api.get("apiUrl")
            if isinstance(nested_api_url, str) and nested_api_url:
                return nested_api_url
    return None


def _extract_b2_auth_token(payload: dict[str, Any]) -> str | None:
    auth_token = payload.get("authorizationToken")
    if isinstance(auth_token, str) and auth_token:
        return auth_token
    api_info = payload.get("apiInfo")
    if isinstance(api_info, dict):
        storage_api = api_info.get("storageApi")
        if isinstance(storage_api, dict):
            nested_auth_token = storage_api.get("authorizationToken")
            if isinstance(nested_auth_token, str) and nested_auth_token:
                return nested_auth_token
    return None


def _require_b2_config() -> tuple[str, str, str]:
    if not settings.b2_key_id or not settings.b2_application_key or not settings.b2_bucket_id:
        raise HTTPException(status_code=500, detail="B2 配置缺失，请检查 B2_KEY_ID、B2_APPLICATION_KEY、B2_BUCKET_ID")
    return settings.b2_key_id, settings.b2_application_key, settings.b2_bucket_id


async def _b2_authorize_account() -> tuple[str, str]:
    key_id, application_key, _bucket_id = _require_b2_config()
    basic_token = base64.b64encode(f"{key_id}:{application_key}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {basic_token}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(settings.b2_authorize_url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("B2 authorize failed: status=%s body=%s", exc.response.status_code, exc.response.text)
            raise HTTPException(status_code=502, detail="B2 账号授权失败") from exc
        except httpx.HTTPError as exc:
            logger.exception("B2 authorize request failed")
            raise HTTPException(status_code=502, detail="无法连接到 B2 授权服务") from exc

    payload = response.json()
    api_url = _extract_b2_api_url(payload)
    auth_token = _extract_b2_auth_token(payload)
    if not api_url or not auth_token:
        logger.error("B2 authorize response missing apiUrl or authorizationToken: %s", payload)
        raise HTTPException(status_code=502, detail="B2 授权响应不完整")
    return api_url, auth_token


async def _b2_get_upload_url() -> tuple[str, str]:
    api_url, account_auth_token = await _b2_authorize_account()
    _key_id, _application_key, bucket_id = _require_b2_config()

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{api_url}/b2api/v4/b2_get_upload_url",
                headers={"Authorization": account_auth_token},
                json={"bucketId": bucket_id},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("B2 get upload url failed: status=%s body=%s", exc.response.status_code, exc.response.text)
            raise HTTPException(status_code=502, detail="获取 B2 上传地址失败") from exc
        except httpx.HTTPError as exc:
            logger.exception("B2 get upload url request failed")
            raise HTTPException(status_code=502, detail="无法连接到 B2 上传地址服务") from exc

    payload = response.json()
    upload_url = payload.get("uploadUrl")
    upload_auth_token = payload.get("authorizationToken")
    if not isinstance(upload_url, str) or not upload_url or not isinstance(upload_auth_token, str) or not upload_auth_token:
        logger.error("B2 get upload url response missing required fields: %s", payload)
        raise HTTPException(status_code=502, detail="B2 上传地址响应不完整")
    return upload_url, upload_auth_token


def _build_b2_object_name(filename: str) -> str:
    safe_filename = _safe_filename(filename)
    return f"caption-uploads/{uuid4().hex}_{safe_filename}"


async def _download_b2_file_by_id(file_id: str) -> str:
    api_url, account_auth_token = await _b2_authorize_account()
    ensure_directory(UPLOAD_FINAL_ROOT)

    async with httpx.AsyncClient(timeout=None) as client:
        try:
            response = await client.get(
                f"{api_url}/b2api/v4/b2_download_file_by_id",
                headers={"Authorization": account_auth_token},
                params={"fileId": file_id},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "B2 download by id failed: file_id=%s status=%s body=%s",
                file_id,
                exc.response.status_code,
                exc.response.text,
            )
            raise HTTPException(status_code=502, detail=f"B2 下载失败: {file_id}") from exc
        except httpx.HTTPError as exc:
            logger.exception("B2 download request failed for file_id=%s", file_id)
            raise HTTPException(status_code=502, detail="无法连接到 B2 下载服务") from exc

    content_type = response.headers.get("Content-Type", "")
    if content_type:
        _ensure_allowed_video_type(content_type.split(";")[0].strip())

    encoded_name = response.headers.get("X-Bz-File-Name") or f"{file_id}.mp4"
    safe_filename = _safe_filename(unquote(encoded_name))
    suffix = FilePath(safe_filename).suffix or ".mp4"
    final_file_path = os.path.join(UPLOAD_FINAL_ROOT, f"{file_id}_{uuid4().hex}{suffix}")

    with open(final_file_path, "wb") as target_file:
        target_file.write(response.content)

    if not os.path.exists(final_file_path) or os.path.getsize(final_file_path) <= 0:
        raise HTTPException(status_code=500, detail=f"B2 文件下载校验失败: {file_id}")

    _probe_media_streams(final_file_path)
    logger.info("Downloaded B2 file into managed path: file_id=%s path=%s", file_id, final_file_path)
    return final_file_path


async def _run_upload_processing_task(task_id: str, upload_id: str, file_path: str) -> None:
    task = _get_task_record_or_404(task_id)
    task.status = "running"
    task.progress = 0.1
    task.updated_at = utcnow()
    task_records[task_id] = task
    try:
        probe = await asyncio.to_thread(_probe_media_streams, file_path)
        task.status = "done"
        task.progress = 1.0
        task.result = {
            "upload_id": upload_id,
            "file_path": file_path,
            "probe": probe,
        }
        task.error = None
    except Exception as exc:
        logger.exception("Upload processing task failed: task_id=%s upload_id=%s", task_id, upload_id)
        task.status = "failed"
        task.progress = 1.0
        task.result = None
        task.error = str(exc)
    finally:
        task.updated_at = utcnow()
        task_records[task_id] = task


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
        logger.exception("ffprobe is not installed while probing uploaded video")
        raise HTTPException(status_code=500, detail="ffprobe 未安装，无法探测上传视频") from exc
    except subprocess.TimeoutExpired as exc:
        logger.exception("ffprobe timed out while probing uploaded video: %s", video_path)
        raise HTTPException(status_code=500, detail="ffprobe 探测视频超时") from exc
    except subprocess.CalledProcessError as exc:
        logger.error(
            "ffprobe failed for uploaded video %s: %s",
            video_path,
            (exc.stderr or "").strip(),
        )
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
        logger.error("Uploaded file does not contain a video stream: %s", video_path)
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
        logger.exception("ffmpeg is not installed while normalizing uploaded video")
        raise HTTPException(status_code=500, detail="ffmpeg 未安装，无法合并上传视频") from exc
    except subprocess.TimeoutExpired as exc:
        logger.exception("ffmpeg timed out while normalizing uploaded video: %s", input_path)
        raise HTTPException(status_code=500, detail="ffmpeg 规范化视频超时") from exc
    except subprocess.CalledProcessError as exc:
        logger.error(
            "ffmpeg normalize failed for %s -> %s: %s",
            input_path,
            output_path,
            (exc.stderr or "").strip(),
        )
        raise HTTPException(
            status_code=400,
            detail=f"规范化上传视频失败: {exc.stderr.strip()}",
        ) from exc


def _merge_videos(video_paths: list[str]) -> str:
    if len(video_paths) == 1:
        logger.info("Single uploaded video detected, skipping merge: %s", video_paths[0])
        return video_paths[0]

    ensure_directory(settings.upload_dir)
    logger.info("Merging %s uploaded videos", len(video_paths))
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
            logger.info(
                "Normalizing uploaded video %s/%s: %s",
                index + 1,
                len(video_paths),
                video_path,
            )
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
            logger.exception("ffmpeg is not installed while concatenating uploaded videos")
            raise HTTPException(status_code=500, detail="ffmpeg 未安装，无法合并上传视频") from exc
        except subprocess.TimeoutExpired as exc:
            logger.exception("ffmpeg timed out while concatenating uploaded videos into %s", merged_path)
            raise HTTPException(status_code=500, detail="ffmpeg 合并视频超时") from exc
        except subprocess.CalledProcessError as exc:
            logger.error(
                "ffmpeg concat failed for %s: %s",
                merged_path,
                (exc.stderr or "").strip(),
            )
            raise HTTPException(
                status_code=400,
                detail=f"合并上传视频失败: {exc.stderr.strip()}",
            ) from exc

    logger.info("Merged uploaded videos into %s", merged_path)
    return merged_path


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/uploads/init")
async def init_upload(payload: UploadInitRequest) -> UploadInitResponse:
    _ensure_valid_upload_request(payload)
    ensure_directory(UPLOAD_TMP_ROOT)
    ensure_directory(UPLOAD_FINAL_ROOT)

    upload_id = str(uuid4())
    record = UploadRecord(
        upload_id=upload_id,
        filename=payload.filename,
        safe_filename=_safe_filename(payload.filename),
        file_size=payload.file_size,
        chunk_size=payload.chunk_size or CHUNK_UPLOAD_DEFAULT_SIZE,
        total_chunks=payload.total_chunks,
        content_type=payload.content_type,
    )
    upload_records[upload_id] = record
    ensure_directory(_chunk_directory(upload_id))
    logger.info(
        "Initialized chunk upload: upload_id=%s filename=%s size=%s chunk_size=%s total_chunks=%s",
        upload_id,
        payload.filename,
        payload.file_size,
        payload.chunk_size,
        payload.total_chunks,
    )
    return UploadInitResponse(
        upload_id=upload_id,
        chunk_size=record.chunk_size,
        total_chunks=record.total_chunks,
        uploaded_chunks=[],
    )


@router.post("/uploads/{upload_id}/chunk")
async def upload_chunk(
    upload_id: Annotated[str, Path()],
    chunk_index: Annotated[int, Form()],
    chunk: Annotated[UploadFile, File()],
) -> UploadChunkResponse:
    record = _get_upload_record_or_404(upload_id)
    if chunk_index < 0 or chunk_index >= record.total_chunks:
        raise HTTPException(status_code=400, detail="chunk_index 超出范围")

    target_path = _chunk_path(upload_id, chunk_index)
    ensure_directory(_chunk_directory(upload_id))
    if os.path.exists(target_path):
        return UploadChunkResponse(upload_id=upload_id, chunk_index=chunk_index, status="uploaded")

    content = await chunk.read()
    expected_size = record.chunk_size
    if chunk_index == record.total_chunks - 1:
        remaining = record.file_size - (record.chunk_size * chunk_index)
        expected_size = remaining if remaining > 0 else record.chunk_size
    if len(content) > record.chunk_size or len(content) != expected_size:
        raise HTTPException(status_code=400, detail="chunk 大小不匹配")

    with open(target_path, "wb") as chunk_file:
        chunk_file.write(content)

    return UploadChunkResponse(upload_id=upload_id, chunk_index=chunk_index, status="uploaded")


@router.get("/uploads/{upload_id}/status")
async def get_upload_status(upload_id: Annotated[str, Path()]) -> UploadStatusResponse:
    record = _get_upload_record_or_404(upload_id)
    uploaded_chunks = (
        list(range(record.total_chunks))
        if record.completed
        else _list_uploaded_chunks(upload_id, record.total_chunks)
    )
    return UploadStatusResponse(
        upload_id=upload_id,
        total_chunks=record.total_chunks,
        uploaded_chunks=uploaded_chunks,
        complete=record.completed,
    )


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(
    upload_id: Annotated[str, Path()],
) -> UploadCompleteSuccessResponse:
    record = _get_upload_record_or_404(upload_id)
    async with _get_upload_lock(upload_id):
        if record.completed and record.final_file_path and record.task_id:
            task = _get_task_record_or_404(record.task_id)
            return UploadCompleteSuccessResponse(
                upload_id=record.upload_id,
                file_path=record.final_file_path,
                task_id=task.task_id,
                status=task.status,
            )

        uploaded_chunks = set(_list_uploaded_chunks(upload_id, record.total_chunks))
        missing_chunks = [
            chunk_index
            for chunk_index in range(record.total_chunks)
            if chunk_index not in uploaded_chunks
        ]
        if missing_chunks:
            return JSONResponse(
                status_code=400,
                content=UploadCompleteErrorResponse(
                    error="missing_chunks",
                    missing_chunks=missing_chunks,
                ).model_dump(),
            )

        ensure_directory(UPLOAD_FINAL_ROOT)
        final_file_path = os.path.join(
            UPLOAD_FINAL_ROOT,
            f"{record.upload_id}_{record.safe_filename}",
        )
        with open(final_file_path, "wb") as final_file:
            for chunk_index in range(record.total_chunks):
                with open(_chunk_path(upload_id, chunk_index), "rb") as chunk_file:
                    shutil.copyfileobj(chunk_file, final_file)

        if not os.path.exists(final_file_path) or os.path.getsize(final_file_path) != record.file_size:
            raise HTTPException(status_code=500, detail="合并后的最终文件校验失败")

        shutil.rmtree(_chunk_directory(upload_id), ignore_errors=True)
        record.completed = True
        record.final_file_path = final_file_path

        task_id = str(uuid4())
        record.task_id = task_id
        upload_records[upload_id] = record
        task_records[task_id] = TaskRecord(
            task_id=task_id,
            upload_id=upload_id,
            status="pending",
            progress=0.0,
            result=None,
            error=None,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        asyncio.create_task(_run_upload_processing_task(task_id, upload_id, final_file_path))

        return UploadCompleteSuccessResponse(
            upload_id=upload_id,
            file_path=final_file_path,
            task_id=task_id,
            status="pending",
        )


@router.get("/tasks/{task_id}")
async def get_upload_task(task_id: Annotated[str, Path()]) -> UploadTaskResponse:
    task = _get_task_record_or_404(task_id)
    return UploadTaskResponse(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress,
        result=task.result,
        error=task.error,
    )


@router.post("/storage/b2/upload-url")
async def create_b2_upload_url(request: B2UploadUrlRequest) -> B2UploadUrlResponse:
    if request.file_size <= 0:
        raise HTTPException(status_code=400, detail="file_size 必须大于 0")
    if request.file_size > settings.max_upload_size:
        raise HTTPException(status_code=400, detail="视频文件超过允许的最大大小")
    _ensure_allowed_video_type(request.content_type)

    upload_url, authorization_token = await _b2_get_upload_url()
    file_name = _build_b2_object_name(request.filename)
    return B2UploadUrlResponse(
        upload_url=upload_url,
        authorization_token=authorization_token,
        file_name=file_name,
        content_type=request.content_type,
    )


@router.post("/assistant/session")
async def create_caption_session(request: CaptionSessionCreateRequest):
    """
    创建字幕与剪辑助手会话，并异步开始处理。
    """
    if not request.uploaded_file_paths and not request.uploaded_file_ids:
        logger.warning("Caption session request rejected because no uploaded file references were provided")
        raise HTTPException(status_code=400, detail="请至少提供一个已上传的视频文件")

    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    logger.info(
        "Received caption session request: platform=%s analysis_mode=%s path_count=%s file_id_count=%s prompt_length=%s",
        request.platform,
        request.analysis_mode,
        len(request.uploaded_file_paths),
        len(request.uploaded_file_ids),
        len(request.prompt),
    )
    if request.uploaded_file_paths and request.uploaded_file_ids:
        raise HTTPException(status_code=400, detail="uploaded_file_paths 和 uploaded_file_ids 不能同时传入")

    if request.uploaded_file_paths:
        uploaded_paths = [_assert_managed_final_path(file_path) for file_path in request.uploaded_file_paths]
        logger.info("Using managed uploaded video paths: %s", uploaded_paths)
    else:
        uploaded_paths = [await _download_b2_file_by_id(file_id) for file_id in request.uploaded_file_ids]
        logger.info("Downloaded uploaded video ids into managed paths: %s", uploaded_paths)

    video_path = _merge_videos(uploaded_paths)
    logger.info("Starting caption assistant session with merged video path: %s", video_path)
    return await caption_assistant.create_session(
        video_path=video_path,
        platform=request.platform,
        product_manual=request.product_manual,
        user_prompt=request.prompt,
        analysis_mode=request.analysis_mode,
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
