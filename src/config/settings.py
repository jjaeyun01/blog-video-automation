from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    fevercoach_rss_url: str = "https://www.fevercoach.us/ko/blog-feed.xml"
    output_dir: Path = Path("output")
    target_duration_sec: int = 55
    max_scenes: int = 7
    language: str = "ko"
    openai_api_key: str | None = None
    openai_text_model: str = "gpt-4o-mini"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    elevenlabs_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(Path(".env"))
        return cls(
            fevercoach_rss_url=os.getenv(
                "FEVERCOACH_RSS_URL",
                "https://www.fevercoach.us/ko/blog-feed.xml",
            ),
            output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
            target_duration_sec=int(os.getenv("TARGET_DURATION_SEC", "55")),
            max_scenes=int(os.getenv("MAX_SCENES", "7")),
            language=os.getenv("LANGUAGE", "ko"),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_text_model=os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini"),
            openai_tts_model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            openai_tts_voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY") or None,
        )


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
