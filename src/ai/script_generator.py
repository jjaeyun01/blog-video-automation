from __future__ import annotations

import re

from src.config.settings import Settings
from src.models import Article, VideoScript

from .openai_client import OpenAiClient


class ScriptGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, article: Article) -> VideoScript:
        facts = _compress_article(article.cleaned_text)
        hook = _make_hook(article.title)
        disclaimer = "이 영상은 일반 정보이며 진료를 대신하지 않습니다."
        outro = "아이 상태가 심하거나 걱정된다면 소아청소년과 의료진과 상담하세요."
        narration = " ".join(
            [
                hook,
                facts,
                outro,
                disclaimer,
            ]
        )

        return VideoScript(
            article_id=article.id,
            title=article.title,
            format="short_vertical",
            target_duration_sec=self.settings.target_duration_sec,
            hook=hook,
            narration=narration,
            outro=outro,
            disclaimer=disclaimer,
            scenes=[],
        )


class OpenAiScriptGenerator:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI script generation.")
        self.settings = settings
        self.client = OpenAiClient(settings.openai_api_key)

    def generate(self, article: Article) -> VideoScript:
        fallback = ScriptGenerator(self.settings).generate(article)
        system = (
            "You are a Korean pediatric health video script editor. "
            "Return strict JSON only. Do not add diagnosis, dosage, treatment changes, "
            "or emergency criteria unless present in the source. Keep content informational."
        )
        user = f"""
Create a Korean vertical short-form video script from this FeverCoach blog article.

Required JSON shape:
{{
  "hook": "string",
  "narration": "string",
  "outro": "string",
  "disclaimer": "string"
}}

Rules:
- Target duration: {self.settings.target_duration_sec} seconds.
- Speak naturally to Korean parents.
- Preserve the source meaning.
- Include a disclaimer that the video is general information and does not replace medical care.
- Do not invent diagnosis, medication dosage, or treatment instructions.

Title:
{article.title}

Cleaned article:
{article.cleaned_text}
"""
        data = self.client.chat_json(self.settings.openai_text_model, system, user)
        return VideoScript(
            article_id=article.id,
            title=article.title,
            format="short_vertical",
            target_duration_sec=self.settings.target_duration_sec,
            hook=str(data.get("hook") or fallback.hook),
            narration=str(data.get("narration") or fallback.narration),
            outro=str(data.get("outro") or fallback.outro),
            disclaimer=str(data.get("disclaimer") or fallback.disclaimer),
            scenes=[],
        )


def _make_hook(title: str) -> str:
    cleaned = re.sub(r"^Q:\s*", "", title).strip()
    if cleaned.endswith("?") or cleaned.endswith("까요?"):
        return f"{cleaned} 부모님이 가장 먼저 확인할 점을 정리해볼게요."
    return f"{cleaned}에 대해 부모님이 확인할 점을 정리해볼게요."


def _compress_article(text: str, max_chars: int = 900) -> str:
    selected: list[str] = []
    capture_answer = False

    for line in text.splitlines():
        line = line.strip()
        if not line or _is_boilerplate(line):
            continue
        if line in {"질문:", "답변:"}:
            capture_answer = line == "답변:"
            continue
        if line.endswith(":") and len(line) < 24:
            selected.append(line)
            continue
        if capture_answer or _is_priority_line(line):
            selected.append(line)

    if not selected:
        selected = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not _is_boilerplate(line.strip())
        ]

    compressed = " ".join(selected)
    compressed = re.sub(r"\s+", " ", compressed).strip()
    if len(compressed) <= max_chars:
        return compressed
    truncated = compressed[:max_chars].rstrip()
    last_sentence_end = max(truncated.rfind("."), truncated.rfind("?"), truncated.rfind("요."))
    if last_sentence_end > max_chars * 0.65:
        return truncated[: last_sentence_end + 1].rstrip()
    return truncated


def _is_priority_line(line: str) -> bool:
    markers = ("병원", "진료", "필요", "경우", "상담", "도와", "확인")
    return any(marker in line for marker in markers)


def _is_boilerplate(line: str) -> bool:
    boilerplate_markers = (
        "이 게시물은 실제 의료 검토자의",
        "이 콘텐츠는 정보 제공 목적으로만",
        "FeverCoach 앱이 항상 도움",
    )
    return any(marker in line for marker in boilerplate_markers)
