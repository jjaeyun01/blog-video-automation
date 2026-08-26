from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path

from google import genai
from google.genai import types

from .article import Article
from .models import ProductionSpec
from .safety import validate_medical_copy
from .settings import Settings


class ScenePlanner:
    def __init__(self, settings: Settings):
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for scene planning.")
        self.settings = settings
        self.client = genai.Client(api_key=settings.gemini_api_key)

    def create(self, article: Article, character_image: Path, output_path: Path) -> ProductionSpec:
        if not character_image.exists():
            raise ValueError(f"Character image not found: {character_image}")
        mime_type = mimetypes.guess_type(character_image.name)[0] or "image/png"
        prompt = _planning_prompt(article)
        response = self.client.models.generate_content(
            model=self.settings.gemini_text_model,
            contents=[
                prompt,
                types.Part.from_bytes(data=character_image.read_bytes(), mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini did not return a scene plan.")
        data = json.loads(response.text)
        data.update(
            {
                "schema_version": 1,
                "slug": data.get("slug") or _slugify(article.title),
                "title": data.get("title") or article.title,
                "source": article.source,
                "language": "ko",
                "character_image": str(character_image.resolve()),
                "aspect_ratio": "9:16",
                "resolution": "720p",
                "fps": 30,
            }
        )
        for index, scene in enumerate(data.get("scenes", []), start=1):
            scene["index"] = index
            scene.setdefault("generation_seconds", 8)
            scene["subtitle"] = scene.get("narration", "")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        spec = ProductionSpec.load(output_path, check_files=True)
        validate_medical_copy(spec)
        spec.save(output_path)
        return spec

    def create_multilingual(
        self,
        article: Article,
        character_image: Path,
        output_path: Path,
        languages: tuple[str, ...] = ("ko", "es", "en"),
    ) -> dict[str, tuple[Path, ProductionSpec]]:
        if not character_image.exists():
            raise ValueError(f"Character image not found: {character_image}")
        unsupported = set(languages) - {"ko", "es", "en"}
        if unsupported:
            raise ValueError(f"Unsupported languages: {', '.join(sorted(unsupported))}")
        mime_type = mimetypes.guess_type(character_image.name)[0] or "image/png"
        response = self.client.models.generate_content(
            model=self.settings.gemini_text_model,
            contents=[
                _multilingual_planning_prompt(article, languages),
                types.Part.from_bytes(data=character_image.read_bytes(), mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini did not return a multilingual scene plan.")
        plan = json.loads(response.text)
        slug = plan.get("slug") or _slugify(article.title)
        results: dict[str, tuple[Path, ProductionSpec]] = {}
        for language in languages:
            localized = plan.get("localizations", {}).get(language)
            if not isinstance(localized, dict):
                raise ValueError(f"Gemini response is missing localization: {language}")
            localized_scenes = localized.get("scenes", [])
            visual_scenes = plan.get("scenes", [])
            if len(localized_scenes) != 10 or len(visual_scenes) != 10:
                raise ValueError("Medical visual plan must contain exactly 10 visual and localized scenes.")
            data = {
                "schema_version": 1,
                "slug": slug,
                "title": localized.get("title") or article.title,
                "source": article.source,
                "language": language,
                "character_image": str(character_image.resolve()),
                "aspect_ratio": "9:16",
                "resolution": "720p",
                "fps": 30,
                "disclaimer": localized.get("disclaimer", ""),
                "metadata": {
                    "multilingual": True,
                    "languages": list(languages),
                    "medical_facts": list(plan.get("medical_facts", [])),
                    "visual_system": "fevercoach-explainer-v2",
                },
                "scenes": [],
            }
            for index, (visual, copy) in enumerate(
                zip(visual_scenes, localized_scenes), start=1
            ):
                narration = copy.get("narration", "")
                overlay_labels = dict(copy.get("overlay_labels", {}))
                overlays = []
                for overlay in visual.get("overlays", []):
                    item = dict(overlay)
                    key = str(item.pop("text_key", ""))
                    if key:
                        item["text"] = overlay_labels.get(key, item.get("text", ""))
                    overlays.append(_normalize_overlay(item))
                data["scenes"].append(
                    {
                        "index": index,
                        "title": copy.get("title", visual.get("title", f"Scene {index}")),
                        "mode": visual.get("mode"),
                        "timeline_seconds": visual.get("timeline_seconds"),
                        "generation_seconds": visual.get("generation_seconds", 8),
                        "narration": narration,
                        "subtitle": narration,
                        "prompt": _text_free_visual_prompt(visual.get("prompt", "")),
                        "negative_prompt": _negative_prompt(visual.get("negative_prompt", "")),
                        "visual_type": visual.get("visual_type", "general"),
                        "medical_claim": visual.get("medical_claim", ""),
                        "asset_prompt": _text_free_visual_prompt(visual.get("asset_prompt", "")),
                        "include_character": bool(visual.get("include_character", False)),
                        "overlays": overlays,
                        "caption_chunks": copy.get("caption_chunks", [narration]),
                    }
                )
            language_path = _language_output_path(output_path, language)
            language_path.parent.mkdir(parents=True, exist_ok=True)
            language_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            spec = ProductionSpec.load(language_path, check_files=True)
            validate_medical_copy(spec)
            spec.save(language_path)
            results[language] = (language_path, spec)
        return results


def _planning_prompt(article: Article) -> str:
    return f"""You are producing a one-minute Korean pediatric health YouTube Short.

Return one JSON object only. Use the attached character image as the recurring character.
The JSON must contain: slug, title, disclaimer, scenes.

Create exactly 6 scenes with these fixed values:
1. i2v, timeline_seconds 8, generation_seconds 8: strong character hook
2. i2v, timeline_seconds 10, generation_seconds 8: explain identity/core concept
3. i2v, timeline_seconds 10, generation_seconds 8: character demonstrates a dynamic mechanism or misconception
4. t2v, timeline_seconds 12, generation_seconds 8: anatomy/medical insert without the character
5. i2v, timeline_seconds 12, generation_seconds 8: safe home-care actions
6. i2v, timeline_seconds 8, generation_seconds 8: red flags and specialist consultation

Every scene must contain title, mode, timeline_seconds, generation_seconds,
narration, subtitle, prompt, negative_prompt.

Rules:
- Narration and subtitle are Korean and must contain exactly the same text.
  Keep the shared text short enough for its timeline and for at most three caption lines.
- Video prompts are detailed English and contain subject, action, camera, environment, lighting.
- I2V prompts prioritize motion and preserve the exact character colors, proportions, face, and texture.
- Every scene containing the recurring character must use i2v with the attached image; never recreate it with t2v.
- Character prompts keep the mouth naturally closed and explicitly request no speaking or lip-sync.
- Request only subtle environmental foley: no generated dialogue, voice, or music. Korean narration is added later.
- Do not ask the model to draw readable text; captions are added later.
- Do not diagnose, promise outcomes, recommend stopping prescribed medicine, or state certainty.
- Distinguish general information from advice and end with appropriate pediatric consultation.
- Avoid Pixar and other trademarked style names. Describe the visual traits directly.
- negative_prompt must include text, subtitles, logo, watermark, deformation, extra limbs.

Article title: {article.title}
Article source: {article.source}
Article content:
{article.text[:16000]}
"""


def _multilingual_planning_prompt(article: Article, languages: tuple[str, ...]) -> str:
    requested = ", ".join(languages)
    schema = {
        "slug": "lowercase-url-slug",
        "medical_facts": [
            {
                "claim": "source-grounded medical claim",
                "numeric_values": ["40°C", "3 days"],
                "safety_qualification": "uncertainty or consultation condition",
            }
        ],
        "scenes": [
            {
                "mode": "i2v",
                "timeline_seconds": 6,
                "generation_seconds": 6,
                "visual_type": "quantity|location|mechanism|comparison|sequence|red_flag|hook",
                "medical_claim": "one source-grounded claim only",
                "include_character": False,
                "asset_prompt": "English prompt for one clean text-free 9:16 reference image",
                "prompt": "English I2V prompt with one bounded action and locked camera",
                "negative_prompt": "text, numbers, labels, dialogue, logo, deformation",
                "overlays": [
                    {
                        "type": "dimension|arrow|threshold|label|cross",
                        "from": [0.25, 0.35],
                        "to": [0.75, 0.35],
                        "label_position": [0.5, 0.25],
                        "text_key": "exact_value",
                        "color": "#E5482F",
                    }
                ],
            }
        ],
        "localizations": {
            language: {
                "title": "...",
                "disclaimer": "...",
                "scenes": [
                    {
                        "title": "...",
                        "narration": "...",
                        "caption_chunks": ["short spoken phrase", "next spoken phrase"],
                        "overlay_labels": {"exact_value": "40°C"},
                    }
                ],
            }
            for language in languages
        },
    }
    return f"""You are the medical fact checker and visual director for FeverCoach.
Produce localized versions of one precise, clean, 60-second pediatric health explainer.

Return one JSON object only. Use the attached character image as the recurring character.
Create shared visuals and localized copy for these language codes: {requested}.

The top-level JSON format must be:
{json.dumps(schema, ensure_ascii=False, indent=2)}

First extract only facts supported by the article. If the source is a Q&A, case report,
testimonial, or contains headings such as 질문/답변:
- Treat the patient's question, reported hearsay, assumptions, and requested options as context only.
- Use a medical claim or threshold only when the clinician/expert answer explicitly confirms it.
- Never turn a number mentioned only in the question into a general rule or recommendation.
- Preserve case-specific details as case-specific; do not generalize them to every child.

Then create exactly 10 shared scenes.
Every scene has timeline_seconds 6 and generation_seconds 6. Use these narrative roles:
1. visual hook showing the main question or surprising threshold
2. locate the relevant body part or clinical context
3. explain the core disease mechanism with a clean cutaway
4. show what the treatment is intended to do
5. visualize the article's most important time or temperature threshold
6. show one quantity, comparison, or decision point only when the source supports it
7. show why reassessment may be needed without asserting a diagnosis
8. show safe supportive care as a short sequence
9. show urgent red flags with clear individual symbols
10. return to the whole context and recommend appropriate pediatric consultation

Visual direction rules:
- Each scene communicates one variable or causal relationship only.
- Choose the visual_type from hook, location, mechanism, quantity, comparison, sequence, red_flag.
- asset_prompt creates a clean, text-free, vertical 9:16 still image tailored to this article.
- Set include_character true only when the recurring character improves comprehension; use it in 2-4 scenes,
  not in anatomy cutaways, calibrated measurements, or red-flag diagrams.
- Every prompt is image-to-video. Animate one subject only with a measurable start and end state.
- Keep the camera locked or use a slow push-in of no more than 8 percent.
- State which objects remain completely stationary. Finish the action within 4 seconds and hold.
- Use clean 3D pediatric medical education visuals: neutral gray, cream, pale teal; red-orange for
  warnings and dimensions; blue for fluid, cooling, or airflow.
- Never generate text, numbers, units, labels, arrows, captions, signs, dialogue, voice, or music.
- Do not put quoted words or values in asset_prompt or prompt. Never ask a thermometer, calendar,
  clock, chart, bottle, or screen to display, show, read, or mark a value; keep it blank and unmarked.
- Accurate numbers, units, arrows, brackets, and threshold marks belong only in overlays.
- Overlay coordinates are normalized 0..1 and must remain above y=0.72 to avoid captions.
- Use exact source values. Never invent a dose, duration, temperature, percentage, or diagnosis.
- Do not convert mass to volume unless the source explicitly provides the substance and conversion.
- For medication quantities, show a calibrated medical device or digital scale, never a kitchen spoon.
- Avoid gore, frightening anatomy, trademarked styles, clutter, and decorative motion.

Localization and safety rules:
- Each localization must have exactly 10 scene entries matching the shared visuals by position.
- Write ko naturally in Korean, es naturally in neutral Latin American Spanish, and en naturally in US English.
- Localize meaning rather than translating word-for-word. Keep each narration natural within 6 seconds:
  target at most 38 Korean characters excluding spaces, or 18 Spanish/English words.
- When advice belongs to the specific case in a Q&A, explicitly say "in this case" (or its natural
  localized equivalent) and retain every condition and required follow-up from the expert answer.
- caption_chunks must partition the narration in spoken order into 1-3 short phrases without adding,
  omitting, or changing words.
- overlay_labels localize only the exact vector labels requested by text_key. Preserve numeric values and units.
- Preserve the same medical meaning and safety qualifications in every language.
- End every language with appropriate pediatric consultation advice.
- Character prompts keep the mouth naturally closed and request no speaking or lip-sync.
- Do not diagnose, promise outcomes, recommend stopping prescribed medicine, or state certainty.
- Every negative_prompt must include text, numbers, subtitles, logo, watermark, dialogue, voice,
  deformation, extra limbs, and character redesign.
- Only include localization keys requested above: {requested}.

Article title: {article.title}
Article source: {article.source}
Article content:
{article.text[:16000]}
"""


def _language_output_path(path: Path, language: str) -> Path:
    return path.with_name(f"{path.stem}.{language}{path.suffix}")


def _text_free_visual_prompt(value: object) -> str:
    prompt = str(value).strip()
    # Models occasionally repeat an exact overlay label inside a display request.
    # Remove that contradiction deterministically: exact copy is rendered later by
    # our overlay compositor, never by the image or video model.
    prompt = re.sub(
        r"\bdisplay(?:ing|s)?\s+(['\"])[^'\"]+\1",
        "with a blank, unlit display",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"\bshow(?:ing|s)?\s+(['\"])[^'\"]+\1(?:\s+highlighted)?",
        "with all visible surfaces blank and unmarked",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"\bcalendar\s+marking\s+\w+\s+days?",
        "calendar with three blank raised day tiles",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"\bclock\s+showing\s+time\s+passing\s+for\s+\w+\s+hours?",
        "blank analog clock face whose hands make one slow partial rotation",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(r"(['\"])\s*[xX]\s*\1", "warning glow", prompt)
    return (
        f"{prompt} All screens, calendars, charts, medicine containers, clock faces, "
        "and signs remain completely blank and unmarked. Render no text, letters, "
        "digits, numbers, units, labels, arrows, captions, typographic symbols, logos, or watermarks."
    )


def _negative_prompt(value: object) -> str:
    required = (
        "text, letters, digits, numbers, units, labels, arrows, subtitles, logo, "
        "watermark, dialogue, voice, lip-sync, deformation, extra limbs, character redesign"
    )
    values = [*str(value).split(","), *required.split(",")]
    unique: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = raw.strip()
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            unique.append(item)
    return ", ".join(unique)


def _normalize_overlay(value: dict) -> dict:
    overlay = dict(value)
    for key in ("from", "to", "position", "label_position"):
        point = overlay.get(key)
        if isinstance(point, list) and len(point) == 2:
            try:
                overlay[key] = [
                    max(0.04, min(0.96, float(point[0]))),
                    max(0.06, min(0.68, float(point[1]))),
                ]
            except (TypeError, ValueError):
                overlay[key] = [0.5, 0.25]
    if overlay.get("type") == "threshold" and "from" in overlay and "to" in overlay:
        start, end = overlay["from"], overlay["to"]
        if abs(start[0] - end[0]) < 0.08:
            center_x = (start[0] + end[0]) / 2
            center_y = min(start[1], end[1])
            overlay["from"] = [max(0.08, center_x - 0.18), center_y]
            overlay["to"] = [min(0.92, center_x + 0.18), center_y]
    return overlay


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", text.lower()).strip("-")
    return slug[:64] or "weekly-short"
