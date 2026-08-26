from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_text_model: str
    gemini_image_model: str
    gemini_video_model: str
    gemini_video_fallback_model: str | None
    gemini_tts_model: str
    gemini_tts_voice: str
    veo_poll_interval_sec: int
    elevenlabs_api_key: str | None
    elevenlabs_model: str
    elevenlabs_voice_id: str | None
    jobs_dir: Path

    @classmethod
    def from_env(cls, env_path: Path = Path(".env")) -> "Settings":
        _load_env(env_path)
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            gemini_text_model=os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash"),
            gemini_image_model=os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            gemini_video_model=os.getenv("GEMINI_VIDEO_MODEL", "veo-3.1-generate-preview"),
            gemini_video_fallback_model=(
                os.getenv("GEMINI_VIDEO_FALLBACK_MODEL", "veo-3.1-fast-generate-preview") or None
            ),
            gemini_tts_model=os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts"),
            gemini_tts_voice=os.getenv("GEMINI_TTS_VOICE", "Kore"),
            veo_poll_interval_sec=max(5, int(os.getenv("VEO_POLL_INTERVAL_SEC", "10"))),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY") or None,
            elevenlabs_model=os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID") or None,
            jobs_dir=Path(os.getenv("JOBS_DIR", "jobs")),
        )


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"").strip("'"))
