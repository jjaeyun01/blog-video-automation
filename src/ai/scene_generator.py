from __future__ import annotations

import math
import re

from src.config.settings import Settings
from src.models import Article, Scene, VideoScript


class SceneGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, article: Article, script: VideoScript) -> list[Scene]:
        if _is_dialogue_script(script):
            return _dialogue_scenes(article, script, self.settings)

        sentences = _split_sentences(script.narration)
        chunks = _chunk_sentences(sentences, self.settings.max_scenes)
        duration = max(4.0, script.target_duration_sec / max(1, len(chunks)))

        scenes: list[Scene] = []
        for index, chunk in enumerate(chunks, start=1):
            narration = " ".join(chunk)
            scenes.append(
                Scene(
                    index=index,
                    duration_sec=round(duration, 2),
                    narration=narration,
                    subtitle=_subtitle(narration),
                    visual_prompt=_visual_prompt(article.title, narration),
                    visual_type="thumbnail" if index == 1 and article.thumbnail_url else "text_card",
                )
            )
        return scenes


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+|(?<=요\.)\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _is_dialogue_script(script: VideoScript) -> bool:
    return "부모:" in script.narration or "의사:" in script.narration


def _dialogue_scenes(article: Article, script: VideoScript, settings: Settings) -> list[Scene]:
    lines: list[tuple[str, str]] = []
    for part in re.split(r"\s+(?=(?:부모|의사):)", script.narration):
        match = re.match(r"^(부모|의사):\s*(.+)$", part.strip())
        if match:
            lines.append((match.group(1), match.group(2).strip()))

    if not lines:
        return []

    duration = max(4.0, script.target_duration_sec / max(1, len(lines)))
    scenes: list[Scene] = []
    for index, (speaker, line) in enumerate(lines, start=1):
        scenes.append(
            Scene(
                index=index,
                duration_sec=round(duration, 2),
                narration=f"{speaker}: {line}",
                subtitle=_subtitle(line, max_chars=48),
                visual_prompt=_dialogue_visual_prompt(article.title, speaker, line),
                visual_type="dialogue",
            )
        )
    return scenes


def _chunk_sentences(sentences: list[str], max_chunks: int) -> list[list[str]]:
    if len(sentences) <= max_chunks:
        return [[sentence] for sentence in sentences]

    chunk_size = math.ceil(len(sentences) / max_chunks)
    return [sentences[i : i + chunk_size] for i in range(0, len(sentences), chunk_size)]


def _subtitle(text: str, max_chars: int = 42) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "..."


def _visual_prompt(title: str, narration: str) -> str:
    return (
        "Clean warm pediatric health explainer visual, Korean mobile short-form style. "
        f"Topic: {title}. Scene meaning: {narration[:160]}"
    )


def _dialogue_visual_prompt(title: str, speaker: str, line: str) -> str:
    return (
        "Realistic Korean pediatric clinic conversation, warm natural lighting. "
        f"Topic: {title}. Speaker: {speaker}. Dialogue meaning: {line[:160]}"
    )
