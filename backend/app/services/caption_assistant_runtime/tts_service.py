from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings


@dataclass(slots=True)
class SubtitleCue:
    index: int
    start_seconds: float
    end_seconds: float
    text: str

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


class KokoroTtsService:
    sample_rate = 24000
    _PROJECT_ROOT = Path(__file__).resolve().parents[4]
    _LANGUAGE_PROFILE_MAP = {
        "zh": ("z", "zf_xiaobei"),
        "zh-cn": ("z", "zf_xiaobei"),
        "zh_hans": ("z", "zf_xiaobei"),
        "zh-chs": ("z", "zf_xiaobei"),
        "chinese": ("z", "zf_xiaobei"),
        "mandarin": ("z", "zf_xiaobei"),
        "cn": ("z", "zf_xiaobei"),
        "中文": ("z", "zf_xiaobei"),
        "汉语": ("z", "zf_xiaobei"),
        "普通话": ("z", "zf_xiaobei"),
        "english": ("a", "af_heart"),
        "en": ("a", "af_heart"),
        "en-us": ("a", "af_heart"),
        "en_us": ("a", "af_heart"),
    }

    def __init__(self) -> None:
        self._pipelines: Dict[str, Any] = {}
        self._assets = self._resolve_assets()

    def is_enabled(self) -> bool:
        return settings.caption_tts_enabled

    def parse_timeline_subtitles(self, subtitle_draft: str) -> List[SubtitleCue]:
        import re

        pattern = re.compile(
            r"^[\s\*\-\.]*(?P<start>\d{1,2}:\d{2}(?::\d{2})?)[\s\*]*[-—–~to]+[\s\*]*(?P<end>\d{1,2}:\d{2}(?::\d{2})?)[\s\*:]+(?P<text>.+)$"
        )
        cues: List[SubtitleCue] = []
        for line in subtitle_draft.splitlines():
            normalized_line = line.strip().strip("\"'“”‘’")
            match = pattern.match(normalized_line)
            if not match:
                continue
            text = match.group("text").strip().strip("\"'“”‘’")
            if not text:
                continue
            start_seconds = self._timestamp_to_seconds(match.group("start"))
            end_seconds = self._timestamp_to_seconds(match.group("end"))
            if end_seconds <= start_seconds:
                continue
            cues.append(
                SubtitleCue(
                    index=len(cues) + 1,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    text=text,
                )
            )
        return cues

    def synthesize_timeline_audio(
        self,
        *,
        subtitle_draft: str,
        output_path: str,
        target_duration_seconds: float,
        language_hint: str | None = None,
        voice_hint: str | None = None,
    ) -> Dict[str, Any]:
        if not self.is_enabled():
            raise RuntimeError("当前环境已关闭 caption TTS 功能。")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("当前运行环境未安装 ffmpeg，无法合成 TTS 时间轴音频。")

        cues = self.parse_timeline_subtitles(subtitle_draft)
        if not cues:
            raise RuntimeError("当前字幕草稿中没有可用于 TTS 的时间轴字幕。")

        pipeline_cls = self._load_pipeline_class()
        np = importlib.import_module("numpy")
        profile = self.resolve_language_profile(
            " ".join(cue.text for cue in cues),
            preferred_language=language_hint,
            preferred_voice=voice_hint,
        )
        pipeline = self._get_pipeline(pipeline_cls, profile["lang_code"])

        cue_dir = os.path.join(
            os.path.dirname(output_path),
            f"{os.path.splitext(os.path.basename(output_path))[0]}_cues",
        )
        os.makedirs(cue_dir, exist_ok=True)

        cue_audio_paths: List[str] = []
        total_voice_seconds = 0.0
        truncated_count = 0
        speed_adjusted_count = 0

        for cue in cues:
            audio, used_speed, truncated = self._synthesize_single_cue(
                pipeline=pipeline,
                text=cue.text,
                voice=profile["voice"],
                cue_duration_seconds=cue.duration_seconds,
                numpy_module=np,
            )
            if used_speed > 1.0 + 1e-6:
                speed_adjusted_count += 1
            if truncated:
                truncated_count += 1
            cue_audio_path = os.path.join(cue_dir, f"cue_{cue.index:03d}.wav")
            self._write_wav_pcm16(cue_audio_path, audio, np)
            cue_audio_paths.append(cue_audio_path)
            total_voice_seconds += round(len(audio) / self.sample_rate, 4)

        self._mix_timeline_audio(
            cue_audio_paths=cue_audio_paths,
            cues=cues,
            output_path=output_path,
            target_duration_seconds=target_duration_seconds,
        )
        return {
            "path": output_path,
            "cue_count": len(cues),
            "target_duration_seconds": round(target_duration_seconds, 4),
            "voice_duration_seconds": round(total_voice_seconds, 4),
            "lang_code": profile["lang_code"],
            "voice": profile["voice"],
            "speed_adjusted_count": speed_adjusted_count,
            "truncated_count": truncated_count,
        }

    def resolve_language_profile(
        self,
        text: str,
        *,
        preferred_language: str | None = None,
        preferred_voice: str | None = None,
    ) -> Dict[str, str]:
        explicit = self._profile_from_language_hint(preferred_language, preferred_voice)
        if explicit is not None:
            return explicit

        contains_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)
        if contains_cjk:
            return {
                "lang_code": settings.kokoro_chinese_lang_code,
                "voice": self._resolve_preferred_voice(
                    preferred_voice,
                    settings.kokoro_chinese_lang_code,
                    settings.kokoro_chinese_voice,
                ),
            }
        return {
            "lang_code": settings.kokoro_default_lang_code,
            "voice": self._resolve_preferred_voice(
                preferred_voice,
                settings.kokoro_default_lang_code,
                settings.kokoro_default_voice,
            ),
        }

    def _load_pipeline_class(self) -> Any:
        try:
            module = importlib.import_module("kokoro")
        except Exception as exc:
            raise RuntimeError(
                "无法导入 kokoro。请先安装 kokoro 及其语言依赖；中文需要 `misaki[zh]`，并确保系统可用 espeak-ng。"
            ) from exc
        pipeline_cls = getattr(module, "KPipeline", None)
        if pipeline_cls is None:
            raise RuntimeError("当前 kokoro 安装缺少 KPipeline，无法执行 TTS。")
        return pipeline_cls

    def _get_pipeline(self, pipeline_cls: Any, lang_code: str) -> Any:
        if lang_code not in self._pipelines:
            repo_id = self._assets["repo_id"]
            model = True
            if self._assets["config_path"] and self._assets["model_path"]:
                kmodel_cls = getattr(importlib.import_module("kokoro.model"), "KModel")
                model = kmodel_cls(
                    repo_id=repo_id,
                    config=self._assets["config_path"],
                    model=self._assets["model_path"],
                )
            self._pipelines[lang_code] = pipeline_cls(
                lang_code=lang_code,
                repo_id=repo_id,
                model=model,
            )
        return self._pipelines[lang_code]

    def _synthesize_single_cue(
        self,
        *,
        pipeline: Any,
        text: str,
        voice: str,
        cue_duration_seconds: float,
        numpy_module: Any,
    ) -> tuple[Any, float, bool]:
        resolved_voice = self._resolve_voice_path(voice)
        audio = self._run_pipeline(
            pipeline=pipeline,
            text=text,
            voice=resolved_voice,
            speed=1.0,
            numpy_module=numpy_module,
        )
        used_speed = 1.0
        limit = cue_duration_seconds + settings.kokoro_overflow_tolerance_seconds
        if cue_duration_seconds > 0 and len(audio) / self.sample_rate > limit:
            used_speed = min(
                settings.kokoro_max_speed,
                max(1.0, (len(audio) / self.sample_rate) / cue_duration_seconds),
            )
            if used_speed > 1.0 + 1e-6:
                audio = self._run_pipeline(
                    pipeline=pipeline,
                    text=text,
                    voice=resolved_voice,
                    speed=used_speed,
                    numpy_module=numpy_module,
                )

        truncated = False
        max_samples = int(max(cue_duration_seconds, 0.0) * self.sample_rate)
        if max_samples > 0 and len(audio) > max_samples:
            audio = audio[:max_samples]
            truncated = True
        return audio, used_speed, truncated

    def _run_pipeline(
        self,
        *,
        pipeline: Any,
        text: str,
        voice: str,
        speed: float,
        numpy_module: Any,
    ) -> Any:
        chunks: List[Any] = []
        try:
            generator = pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+")
            for _graphemes, _phonemes, audio in generator:
                chunks.append(numpy_module.asarray(audio, dtype=numpy_module.float32))
        except Exception as exc:
            raise RuntimeError(
                f"Kokoro 生成失败，lang_code/voice 可能与安装的模型不匹配：voice={voice}, speed={speed:.2f}, error={exc}"
            ) from exc
        if not chunks:
            raise RuntimeError("Kokoro 没有返回任何音频帧。")
        return numpy_module.concatenate(chunks)

    def _resolve_assets(self) -> Dict[str, str | None]:
        repo_id = settings.kokoro_repo_id
        model_dir = self._normalize_dir(settings.kokoro_model_dir)
        if model_dir is None:
            model_dir = self._discover_hf_snapshot_dir(repo_id)

        config_path = self._first_existing_file(
            settings.kokoro_config_path,
            os.path.join(model_dir, "config.json") if model_dir else None,
        )
        model_path = self._first_existing_file(
            settings.kokoro_model_path,
            os.path.join(model_dir, "kokoro-v1_0.pth") if model_dir else None,
        )
        voices_dir = self._first_existing_dir(
            settings.kokoro_voices_dir,
            os.path.join(model_dir, "voices") if model_dir else None,
        )

        if settings.kokoro_local_files_only and (not config_path or not model_path):
            raise RuntimeError(
                "Kokoro 本地模型未找到。请配置 kokoro_model_dir 或 kokoro_config_path/kokoro_model_path。"
            )

        return {
            "repo_id": repo_id,
            "model_dir": model_dir,
            "config_path": config_path,
            "model_path": model_path,
            "voices_dir": voices_dir,
        }

    def _resolve_voice_path(self, voice: str) -> str:
        if voice.endswith(".pt"):
            return voice
        voices_dir = self._assets.get("voices_dir")
        if voices_dir:
            voice_path = os.path.join(voices_dir, f"{voice}.pt")
            if os.path.isfile(voice_path):
                return voice_path
        if settings.kokoro_local_files_only:
            raise RuntimeError(f"Kokoro 本地 voice 不存在：{voice}")
        return voice

    def _profile_from_language_hint(
        self,
        preferred_language: str | None,
        preferred_voice: str | None,
    ) -> Dict[str, str] | None:
        if not preferred_language and not preferred_voice:
            return None

        normalized_language = (preferred_language or "").strip().lower().replace("_", "-")
        mapped = self._LANGUAGE_PROFILE_MAP.get(normalized_language)
        if mapped is not None:
            lang_code, default_voice = mapped
            return {
                "lang_code": lang_code,
                "voice": self._resolve_preferred_voice(preferred_voice, lang_code, default_voice),
            }

        if preferred_voice:
            inferred_lang_code = self._infer_lang_code_from_voice(preferred_voice)
            if inferred_lang_code:
                return {
                    "lang_code": inferred_lang_code,
                    "voice": self._resolve_preferred_voice(preferred_voice, inferred_lang_code, preferred_voice),
                }
        return None

    def _resolve_preferred_voice(
        self,
        preferred_voice: str | None,
        lang_code: str,
        fallback_voice: str,
    ) -> str:
        if preferred_voice:
            normalized_voice = preferred_voice.strip()
            if normalized_voice and self._voice_matches_lang_code(normalized_voice, lang_code):
                return normalized_voice
        return fallback_voice

    def _voice_matches_lang_code(self, voice: str, lang_code: str) -> bool:
        voice_name = os.path.splitext(os.path.basename(voice))[0]
        return voice_name.startswith(f"{lang_code}f_") or voice_name.startswith(f"{lang_code}m_")

    def _infer_lang_code_from_voice(self, voice: str) -> str | None:
        voice_name = os.path.splitext(os.path.basename(voice.strip()))[0]
        if len(voice_name) >= 2 and voice_name[1] in {"f", "m"}:
            return voice_name[0]
        return None

    def _discover_hf_snapshot_dir(self, repo_id: str) -> str | None:
        repo_cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{repo_id.replace('/', '--')}"
        snapshots_dir = repo_cache_dir / "snapshots"
        if not snapshots_dir.is_dir():
            return None
        snapshots = sorted((path for path in snapshots_dir.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True)
        if not snapshots:
            return None
        return str(snapshots[0])

    def _normalize_dir(self, path: str | None) -> str | None:
        if not path:
            return None
        for expanded in self._candidate_paths(path):
            if os.path.isdir(expanded):
                return expanded
        return None

    def _first_existing_file(self, *candidates: str | None) -> str | None:
        for candidate in candidates:
            if not candidate:
                continue
            for expanded in self._candidate_paths(candidate):
                if os.path.isfile(expanded):
                    return expanded
        return None

    def _first_existing_dir(self, *candidates: str | None) -> str | None:
        for candidate in candidates:
            if not candidate:
                continue
            for expanded in self._candidate_paths(candidate):
                if os.path.isdir(expanded):
                    return expanded
        return None

    def _candidate_paths(self, path: str) -> List[str]:
        expanded = os.path.expanduser(path)
        candidate_paths: List[str] = []
        if os.path.isabs(expanded):
            candidate_paths.append(os.path.abspath(expanded))
        else:
            candidate_paths.append(os.path.abspath(expanded))
            candidate_paths.append(str((self._PROJECT_ROOT / expanded).resolve()))

        deduped: List[str] = []
        seen: set[str] = set()
        for candidate in candidate_paths:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped

    def _write_wav_pcm16(self, output_path: str, audio: Any, numpy_module: Any) -> None:
        clipped = numpy_module.clip(audio, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(numpy_module.int16)
        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm16.tobytes())

    def _mix_timeline_audio(
        self,
        *,
        cue_audio_paths: List[str],
        cues: List[SubtitleCue],
        output_path: str,
        target_duration_seconds: float,
    ) -> None:
        command_args: List[str] = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-t",
            f"{target_duration_seconds:.4f}",
            "-i",
            f"anullsrc=r={self.sample_rate}:cl=mono",
        ]
        for cue_audio_path in cue_audio_paths:
            command_args.extend(["-i", cue_audio_path])

        filter_parts: List[str] = []
        mix_inputs = ["[0:a]"]
        for index, cue in enumerate(cues, start=1):
            delay_ms = max(0, int(round(cue.start_seconds * 1000)))
            filter_parts.append(f"[{index}:a]adelay={delay_ms}|{delay_ms}[a{index}]")
            mix_inputs.append(f"[a{index}]")
        filter_parts.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[aout]"
        )
        command_args.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[aout]",
                "-ar",
                str(self.sample_rate),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                output_path,
            ]
        )

        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            check=False,
            timeout=settings.ffmpeg_execution_timeout_seconds,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"TTS 时间轴音频合成失败：{stderr[-3000:]}")

    def _timestamp_to_seconds(self, value: str) -> float:
        parts = value.split(":")
        if len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        else:
            hours, minutes, seconds = parts
        return float(int(hours) * 3600 + int(minutes) * 60 + int(seconds))
