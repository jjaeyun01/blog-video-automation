from __future__ import annotations

import hashlib
import json
import subprocess
import time
import wave
from pathlib import Path
from typing import Protocol

import requests
from google import genai
from google.genai import types

from ..models import ProductionSpec, SceneSpec
from ..settings import Settings


_AUDIO_PROCESSING_VERSION = 2


class TtsProvider(Protocol):
    cache_key: str

    def synthesize(self, scene: SceneSpec, output_path: Path) -> None: ...


class GeminiTtsProvider:
    def __init__(
        self,
        settings: Settings,
        language: str = "ko",
        client=None,
        sleep=time.sleep,
        max_attempts: int = 4,
    ):
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for Gemini TTS.")
        self.client = client or genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_tts_model
        self.voice = settings.gemini_tts_voice
        self.language = language
        self.sleep = sleep
        self.max_attempts = max(1, max_attempts)
        self.cache_key = f"gemini:{self.model}:{self.voice}:{language}"

    def synthesize(self, scene: SceneSpec, output_path: Path) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=f"{_tts_direction(self.language)}\n{scene.narration}",
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voice)
                            )
                        ),
                    ),
                )
                candidates = getattr(response, "candidates", None) or []
                content = getattr(candidates[0], "content", None) if candidates else None
                parts = getattr(content, "parts", None) or []
                inline = next(
                    (
                        part.inline_data
                        for part in parts
                        if getattr(part, "inline_data", None)
                        and getattr(part.inline_data, "data", None)
                    ),
                    None,
                )
                if inline is None:
                    raise RuntimeError("Gemini TTS returned an empty audio response.")
                _write_audio(inline.data, inline.mime_type or "audio/L16", output_path)
                return
            except Exception as error:
                last_error = error
                if attempt < self.max_attempts:
                    self.sleep(min(2 ** (attempt - 1), 8))
        raise RuntimeError(
            f"Gemini TTS failed for scene {scene.index} after {self.max_attempts} attempts: "
            f"{last_error}"
        ) from last_error


class ElevenLabsTtsProvider:
    def __init__(self, settings: Settings, language: str = "ko"):
        if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
            raise ValueError("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required.")
        self.api_key = settings.elevenlabs_api_key
        self.voice_id = settings.elevenlabs_voice_id
        self.model = settings.elevenlabs_model
        self.cache_key = f"elevenlabs:{self.model}:{self.voice_id}:{language}"

    def synthesize(self, scene: SceneSpec, output_path: Path) -> None:
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
            json={
                "text": scene.narration,
                "model_id": self.model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
            },
            timeout=120,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"ElevenLabs TTS failed ({response.status_code}): {response.text[:400]}")
        output_path.write_bytes(response.content)


def create_tts_provider(name: str, settings: Settings, language: str = "ko") -> TtsProvider:
    if name == "gemini":
        return GeminiTtsProvider(settings, language)
    if name == "elevenlabs":
        return ElevenLabsTtsProvider(settings, language)
    raise ValueError("tts_provider must be gemini or elevenlabs")


def _tts_direction(language: str) -> str:
    directions = {
        "ko": "자연스럽고 따뜻하며 또렷한 한국어 소아 건강 교육 나레이션으로 읽어주세요:",
        "es": "Lee con una voz cálida, natural y clara, como narración educativa de salud pediátrica en español latinoamericano neutro:",
        "en": "Read in a warm, natural, and clear US English pediatric health education narration style:",
    }
    if language not in directions:
        raise ValueError(f"Unsupported TTS language: {language}")
    return directions[language]


def build_timeline_audio(
    spec: ProductionSpec,
    provider: TtsProvider,
    job_dir: Path,
) -> Path:
    _require_ffmpeg()
    audio_dir = job_dir / "audio"
    raw_dir = audio_dir / "raw"
    aligned_dir = audio_dir / "aligned"
    raw_dir.mkdir(parents=True, exist_ok=True)
    aligned_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = audio_dir / "manifest.json"
    manifest = _read_json(manifest_path, {"scenes": {}})
    aligned_paths: list[Path] = []

    for scene in spec.scenes:
        fingerprint = _audio_fingerprint(scene, provider.cache_key)
        raw_path = raw_dir / f"scene_{scene.index:02}.mp3"
        aligned_path = aligned_dir / f"scene_{scene.index:02}.mp3"
        entry = manifest["scenes"].get(str(scene.index), {})
        # A raw file without a matching manifest cannot be trusted: the previous
        # attempt may have failed because that exact narration was too long, and
        # the script may since have changed. Regenerate rather than reusing stale TTS.
        needs_synthesis = entry.get("fingerprint") != fingerprint or not raw_path.exists()
        if needs_synthesis:
            provider.synthesize(scene, raw_path)
        needs_alignment = (
            needs_synthesis
            or not aligned_path.exists()
            or entry.get("processing_version") != _AUDIO_PROCESSING_VERSION
        )
        if needs_alignment:
            duration = _probe_duration(raw_path)
            speed = duration / scene.timeline_seconds
            if speed > 1.5:
                raise ValueError(
                    f"Scene {scene.index} narration is {duration:.1f}s but the timeline is "
                    f"{scene.timeline_seconds}s; automatic speed-up would sound unnatural. "
                    "Shorten the narration."
                )
            timing_filter = f"atempo={speed:.6f}," if speed > 1.0 else ""
            audio_filter = f"{timing_filter}loudnorm=I=-16:TP=-1.5:LRA=7,apad"
            _run(
                [
                    "ffmpeg", "-y", "-i", str(raw_path), "-af", audio_filter,
                    "-t", str(scene.timeline_seconds), "-codec:a", "libmp3lame",
                    "-b:a", "160k", str(aligned_path),
                ]
            )
            manifest["scenes"][str(scene.index)] = {
                "fingerprint": fingerprint,
                "raw_seconds": round(duration, 3),
                "speed_factor": round(max(1.0, speed), 4),
                "processing_version": _AUDIO_PROCESSING_VERSION,
                "timeline_seconds": scene.timeline_seconds,
                "path": str(aligned_path.resolve()),
            }
            _write_json(manifest_path, manifest)
        aligned_paths.append(aligned_path)

    concat_path = audio_dir / "concat.txt"
    concat_path.write_text(
        "\n".join(f"file '{path.resolve()}'" for path in aligned_paths) + "\n",
        encoding="utf-8",
    )
    output_path = audio_dir / "voice_timeline.mp3"
    _run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-codec:a", "copy", str(output_path),
        ]
    )
    return output_path


def _write_audio(data: bytes, mime_type: str, output_path: Path) -> None:
    if "mpeg" in mime_type or data[:3] == b"ID3":
        output_path.write_bytes(data)
        return
    wav_path = output_path.with_suffix(".wav")
    if data[:4] == b"RIFF":
        wav_path.write_bytes(data)
    else:
        with wave.open(str(wav_path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(24000)
            target.writeframes(data)
    _run(["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "160k", str(output_path)])


def _audio_fingerprint(scene: SceneSpec, provider_key: str) -> str:
    value = f"{provider_key}\n{scene.timeline_seconds}\n{scene.narration}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[-500:]}")
    return float(result.stdout.strip())


def _require_ffmpeg() -> None:
    import shutil

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required. Install them with: brew install ffmpeg")


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Media command failed: {result.stderr[-1000:]}")


def _read_json(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
