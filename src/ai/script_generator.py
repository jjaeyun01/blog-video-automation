from __future__ import annotations

import re

from src.config.settings import Settings
from src.models import Article, VideoScript

from .openai_client import OpenAiClient


class ScriptGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, article: Article) -> VideoScript:
        if _is_face_hitting_article(article):
            return _face_hitting_dialogue_script(article, self.settings)

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


def _is_face_hitting_article(article: Article) -> bool:
    text = f"{article.title}\n{article.cleaned_text}"
    markers = ("얼굴을 때", "자기 얼굴", "5개월")
    return all(marker in text for marker in markers)


def _face_hitting_dialogue_script(article: Article, settings: Settings) -> VideoScript:
    disclaimer = "이 영상은 일반 정보이며 진료를 대신하지 않습니다."
    outro = "아이가 많이 힘들어 보이거나 얼굴이 붓고 붉어지면 소아청소년과에 상담해 주세요."
    hook = "아기가 자기 얼굴을 자꾸 때리면 부모님 입장에서는 당연히 걱정될 수 있어요."
    lines = [
        "부모: 요즘 우리 아기가 손으로 자기 얼굴을 자꾸 때려요. 어디가 불편한 걸까요?",
        "의사: 많이 놀라셨죠. 그런데 5개월 무렵에는 자기 손과 얼굴을 탐색하면서 이런 행동이 꽤 흔하게 보일 수 있어요.",
        "부모: 일부러 아파서 그러는 건 아닐 수도 있다는 말씀이세요?",
        "의사: 네. 아직 움직임을 섬세하게 조절하는 중이라 손이 얼굴 쪽으로 가는 과정에서 툭툭 닿을 수 있어요.",
        "의사: 또 이가 나려고 하거나, 졸리고 자극이 많을 때 얼굴을 만지거나 비비는 식으로 불편함을 표현하기도 해요.",
        "부모: 그럼 집에서는 어떻게 도와주면 좋을까요?",
        "의사: 손을 세게 막기보다는 부드럽게 방향을 바꿔 주세요. 치발기나 부드러운 장난감을 쥐여주는 것도 도움이 될 수 있어요.",
        f"의사: {outro} {disclaimer}",
    ]
    narration = " ".join(lines)
    return VideoScript(
        article_id=article.id,
        title=article.title,
        format="short_vertical_dialogue",
        target_duration_sec=settings.target_duration_sec,
        hook=hook,
        narration=narration,
        outro=outro,
        disclaimer=disclaimer,
        scenes=[],
    )


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
