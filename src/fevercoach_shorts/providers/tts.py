from __future__ import annotations

import base64
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
FEVERCOACH_TTS_VOICE = "Kore"
_VOICE_PROFILE_VERSION = 3
_VOICE_TEMPERATURE = 0.0
_MAX_DURATION_REGENERATION_ATTEMPTS = 3


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
        self.client = client or genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=60_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self.model = settings.gemini_tts_model
        # One canonical narrator is shared by every FeverCoach production.
        self.voice = FEVERCOACH_TTS_VOICE
        self.language = language
        self.sleep = sleep
        self.max_attempts = max(1, max_attempts)
        self.cache_key = (
            f"gemini:{self.model}:{self.voice}:{language}:"
            f"profile-{_VOICE_PROFILE_VERSION}:temperature-{_VOICE_TEMPERATURE}"
        )

    def synthesize(self, scene: SceneSpec, output_path: Path) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                if self.model.startswith("gemini-3.1-"):
                    self._synthesize_streaming(scene, output_path)
                    return
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=f"{_tts_direction(self.language)}\n{scene.narration}",
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        temperature=_VOICE_TEMPERATURE,
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

    def _synthesize_streaming(self, scene: SceneSpec, output_path: Path) -> None:
        """Receive 3.1 TTS incrementally so long audio cannot hit a header timeout."""
        stream = self.client.interactions.create(
            model=self.model,
            input=f"{_tts_direction(self.language)}\n{scene.narration}",
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": self.voice}]},
            stream=True,
            timeout=60.0,
        )
        chunks: list[bytes] = []
        for event in stream:
            delta = getattr(event, "delta", None)
            if getattr(delta, "type", None) != "audio":
                continue
            data = getattr(delta, "data", None)
            if not data:
                continue
            chunks.append(base64.b64decode(data) if isinstance(data, str) else data)
        if not chunks:
            raise RuntimeError("Gemini streaming TTS returned an empty audio response.")
        _write_audio(b"".join(chunks), "audio/L16", output_path)


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
        "ko": (
            "FeverCoach의 고정 성인 여성 내레이터로, 따뜻하고 또렷한 한국어 건강 교육 톤과 "
            "일정한 속도로 읽어주세요:"
        ),
        "es": (
            "Use the fixed FeverCoach adult female narrator. Read warmly and clearly in neutral "
            "Latin American Spanish at a steady pace:"
        ),
        "en": (
            "Use the fixed FeverCoach adult female narrator. Read warmly and clearly in US English "
            "at a steady pace:"
        ),
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
        raw_fingerprint = _raw_audio_fingerprint(scene, provider.cache_key)
        alignment_fingerprint = _audio_fingerprint(scene, provider.cache_key)
        raw_path = raw_dir / f"scene_{scene.index:02}.mp3"
        aligned_path = aligned_dir / f"scene_{scene.index:02}.mp3"
        entry = manifest["scenes"].get(str(scene.index), {})
        legacy_timeline = entry.get("timeline_seconds")
        legacy_fingerprint = (
            _legacy_audio_fingerprint(
                scene.narration, int(legacy_timeline), provider.cache_key
            )
            if legacy_timeline is not None
            else None
        )
        raw_is_current = (
            entry.get("raw_fingerprint") == raw_fingerprint
            or (
                legacy_fingerprint is not None
                and entry.get("fingerprint") == legacy_fingerprint
            )
        )
        # Timeline-only edits must reuse the exact same voice take. A raw file
        # without any matching content fingerprint remains untrusted.
        needs_synthesis = not raw_is_current or not raw_path.exists()
        duration: float | None = None
        if needs_synthesis:
            for synthesis_attempt in range(1, _MAX_DURATION_REGENERATION_ATTEMPTS + 1):
                provider.synthesize(scene, raw_path)
                duration = _probe_duration(raw_path)
                entry = {
                    **entry,
                    "raw_fingerprint": raw_fingerprint,
                    "raw_seconds": round(duration, 3),
                }
                manifest["scenes"][str(scene.index)] = entry
                _write_json(manifest_path, manifest)
                if duration / scene.timeline_seconds <= 1.5:
                    break
                if synthesis_attempt == _MAX_DURATION_REGENERATION_ATTEMPTS:
                    raise ValueError(
                        f"Scene {scene.index} narration is {duration:.1f}s but the timeline is "
                        f"{scene.timeline_seconds}s after {synthesis_attempt} TTS attempts; "
                        "automatic speed-up would sound unnatural. Shorten the narration."
                    )
        needs_alignment = (
            needs_synthesis
            or not aligned_path.exists()
            or entry.get("processing_version") != _AUDIO_PROCESSING_VERSION
            or entry.get("alignment_fingerprint") != alignment_fingerprint
            or int(entry.get("timeline_seconds", -1)) != scene.timeline_seconds
        )
        if needs_alignment:
            duration = duration if duration is not None else _probe_duration(raw_path)
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
                "fingerprint": alignment_fingerprint,
                "raw_fingerprint": raw_fingerprint,
                "alignment_fingerprint": alignment_fingerprint,
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
    return _legacy_audio_fingerprint(scene.narration, scene.timeline_seconds, provider_key)


def _raw_audio_fingerprint(scene: SceneSpec, provider_key: str) -> str:
    value = f"{provider_key}\n{scene.narration}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _legacy_audio_fingerprint(
    narration: str, timeline_seconds: int, provider_key: str
) -> str:
    value = f"{provider_key}\n{timeline_seconds}\n{narration}"
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
