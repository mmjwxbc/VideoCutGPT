import base64
import io
import json
import os
import subprocess
from typing import Any, Dict, List, Optional

import cv2
from PIL import Image

try:
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import ContentDetector
except ImportError:  # pragma: no cover - optional dependency fallback
    SceneManager = None
    ContentDetector = None
    open_video = None


def _encode_frame_to_base64(frame) -> str:
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_frame)
    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _build_frame_record(
    frame,
    timestamp_seconds: float,
    frame_number: Optional[int],
    source: str,
) -> Dict[str, Any]:
    height, width = frame.shape[:2]
    return {
        "timestamp_seconds": round(max(timestamp_seconds, 0.0), 3),
        "frame_number": int(frame_number) if frame_number is not None else None,
        "source": source,
        "image_base64": _encode_frame_to_base64(frame),
        "width": int(width),
        "height": int(height),
    }


def _frame_hash(frame) -> str:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    mean_value = resized.mean()
    bits = "".join("1" if pixel >= mean_value else "0" for pixel in resized.flatten())
    return hex(int(bits, 2))[2:].zfill(16)


def _extract_frame_at(cap: cv2.VideoCapture, timestamp_seconds: float):
    cap.set(cv2.CAP_PROP_POS_MSEC, max(timestamp_seconds, 0.0) * 1000)
    ret, frame = cap.read()
    if not ret or frame is None:
        return None, None
    frame_number = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    return frame, frame_number


def _extract_iframe_timestamps(video_path: str) -> List[float]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        "frame=key_frame,best_effort_timestamp_time,pict_type",
        "-of",
        "json",
        video_path,
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return []

    timestamps: List[float] = []
    for frame in payload.get("frames", []):
        if not isinstance(frame, dict):
            continue
        is_keyframe = frame.get("key_frame") == 1 or frame.get("pict_type") == "I"
        timestamp = frame.get("best_effort_timestamp_time")
        if not is_keyframe or timestamp is None:
            continue
        try:
            timestamps.append(float(timestamp))
        except (TypeError, ValueError):
            continue
    return timestamps


def _extract_scene_timestamps(video_path: str, threshold: float) -> List[float]:
    if not (SceneManager and ContentDetector and open_video):
        return []

    try:
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video=video, show_progress=False)
        scenes = scene_manager.get_scene_list()
    except Exception:
        return []

    timestamps: List[float] = []
    for start_time, _ in scenes:
        try:
            timestamps.append(float(start_time.get_seconds()))
        except Exception:
            continue
    return timestamps


def _extract_interval_timestamps(video_path: str, interval_seconds: int) -> List[float]:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()

    fps = fps if fps and fps > 0 else 1
    frame_count = frame_count if frame_count and frame_count > 0 else 0
    duration_seconds = frame_count / fps if frame_count else 0
    if duration_seconds <= 0:
        return [0.0]

    timestamps: List[float] = []
    current = 0.0
    step = max(float(interval_seconds), 1.0)
    while current < duration_seconds:
        timestamps.append(round(current, 3))
        current += step
    return timestamps or [0.0]


def extract_keyframes(
    video_path: str,
    interval: int = 5,
    max_frames: Optional[int] = None,
    scene_threshold: Optional[float] = 30.0,
    deduplicate_similar_frames: bool = True,
) -> List[Dict[str, Any]]:
    """
    从视频中提取关键帧。
    优先合并 FFmpeg I 帧和 SceneDetect 场景帧；若不可用，则回退到固定间隔抽帧。
    :param video_path: 视频文件路径
    :param interval: 回退方案的提取间隔（秒）
    :param max_frames: 最多提取多少帧
    :param scene_threshold: SceneDetect 内容检测阈值
    :return: 关键帧列表
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    frame_candidates: List[Dict[str, Any]] = []
    iframe_timestamps = _extract_iframe_timestamps(video_path)
    scene_timestamps = (
        _extract_scene_timestamps(video_path, scene_threshold)
        if scene_threshold is not None
        else []
    )

    for timestamp in iframe_timestamps:
        frame, frame_number = _extract_frame_at(cap, timestamp)
        if frame is None:
            continue
        frame_candidates.append(
            {
                "timestamp_seconds": timestamp,
                "frame_number": frame_number,
                "source": "ffmpeg",
                "frame": frame,
                "hash": _frame_hash(frame),
            }
        )

    for timestamp in scene_timestamps:
        frame, frame_number = _extract_frame_at(cap, timestamp)
        if frame is None:
            continue
        frame_candidates.append(
            {
                "timestamp_seconds": timestamp,
                "frame_number": frame_number,
                "source": "scenedetect",
                "frame": frame,
                "hash": _frame_hash(frame),
            }
        )

    if not frame_candidates:
        for timestamp in _extract_interval_timestamps(video_path, interval):
            frame, frame_number = _extract_frame_at(cap, timestamp)
            if frame is None:
                continue
            frame_candidates.append(
                {
                    "timestamp_seconds": timestamp,
                    "frame_number": frame_number,
                    "source": "interval",
                    "frame": frame,
                    "hash": _frame_hash(frame),
                }
            )

    cap.release()

    frame_candidates.sort(key=lambda item: item["timestamp_seconds"])
    deduplicated: List[Dict[str, Any]] = []
    for candidate in frame_candidates:
        timestamp = round(candidate["timestamp_seconds"], 3)
        merged = False
        for existing in deduplicated:
            same_moment = abs(existing["timestamp_seconds"] - timestamp) <= 0.2
            same_frame = deduplicate_similar_frames and existing["hash"] == candidate["hash"]
            if same_moment or same_frame:
                if candidate["source"] not in existing["source"].split("+"):
                    existing["source"] = f'{existing["source"]}+{candidate["source"]}'
                merged = True
                break
        if merged:
            continue
        deduplicated.append(candidate)

    if max_frames is not None and max_frames > 0 and len(deduplicated) > max_frames:
        deduplicated = deduplicated[:max_frames]

    return [
        _build_frame_record(
            frame=item["frame"],
            timestamp_seconds=item["timestamp_seconds"],
            frame_number=item["frame_number"],
            source=item["source"],
        )
        for item in deduplicated
    ]


def select_keyframes_for_analysis(
    keyframes: List[Dict[str, Any]],
    max_frames: Optional[int],
) -> List[Dict[str, Any]]:
    """
    从全量关键帧中均匀采样，用于多模态分析，避免输入过多导致成本失控。
    """
    if not keyframes or max_frames is None or max_frames <= 0 or len(keyframes) <= max_frames:
        return keyframes

    if max_frames == 1:
        return [keyframes[0]]

    last_index = len(keyframes) - 1
    indices = {
        round(position * last_index / (max_frames - 1))
        for position in range(max_frames)
    }
    return [frame for index, frame in enumerate(keyframes) if index in indices]


def encode_image(image_path):
    """
    将图片编码为base64
    :param image_path: 图片文件路径
    :return: base64编码字符串
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def ensure_directory(directory):
    """
    确保目录存在
    :param directory: 目录路径
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
