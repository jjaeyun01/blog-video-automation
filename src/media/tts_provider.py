from __future__ import annotations

from pathlib import Path

from src.ai.openai_client import OpenAiClient
from src.config.settings import Settings
from src.models import VideoScript


class DryRunTtsProvider:
    def generate(self, script: VideoScript, output_dir: Path) -> Path:
        path = output_dir / "voiceover.txt"
        path.write_text(script.narration, encoding="utf-8")
        return path


class OpenAiTtsProvider:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI TTS.")
        self.settings = settings
        self.client = OpenAiClient(settings.openai_api_key)

    def generate(self, script: VideoScript, output_dir: Path) -> Path:
        path = output_dir / "voice.mp3"
        audio = self.client.speech_mp3(
            model=self.settings.openai_tts_model,
            voice=self.settings.openai_tts_voice,
            text=script.narration,
        )
        path.write_bytes(audio)
        return path
