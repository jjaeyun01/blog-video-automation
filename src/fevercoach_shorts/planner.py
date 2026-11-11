from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path

from google import genai
from google.genai import types

from .article import Article
from .models import ProductionSpec
from .review_rules import (
    HISTORICAL_FAIL_PREVENTION_RULES, SEPTEMBER_13_REVIEW_RULES, WEEK8_REVIEW_RULES,
    JAEYOON_FAIL_ONLY_RULES,
)
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
        character_image: Path | None,
        output_path: Path,
        languages: tuple[str, ...] = ("ko", "es", "en"),
        validation_feedback: str | None = None,
    ) -> dict[str, tuple[Path, ProductionSpec]]:
        if character_image is not None and not character_image.exists():
            raise ValueError(f"Character image not found: {character_image}")
        unsupported = set(languages) - {"ko", "es", "en"}
        if unsupported:
            raise ValueError(f"Unsupported languages: {', '.join(sorted(unsupported))}")
        contents: list[object] = [
            _multilingual_planning_prompt(
                article, languages, has_character_image=character_image is not None
            )
        ]
        if validation_feedback:
            contents.append(
                "A previous production plan failed local validation. Return a complete corrected "
                "plan grounded in the SAME source article; do not change medical facts to satisfy "
                "format rules. Count include_character=true scenes: exactly 2 to 4 are permitted "
                "across all 10 scenes, and all other prompts must omit the recurring character. "
                "Fix these validation errors:\n" + validation_feedback
            )
        if character_image is not None:
            mime_type = mimetypes.guess_type(character_image.name)[0] or "image/png"
            contents.append(
                types.Part.from_bytes(
                    data=character_image.read_bytes(), mime_type=mime_type
                )
            )
        response = self.client.models.generate_content(
            model=self.settings.gemini_text_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini did not return a multilingual scene plan.")
        plan = json.loads(response.text)
        character_concept = _validate_character_concept(
            plan.get("character_concept"), required=character_image is None
        )
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
                "character_image": (
                    str(character_image.resolve()) if character_image is not None else None
                ),
                "aspect_ratio": "9:16",
                "resolution": "720p",
                "fps": 30,
                "disclaimer": localized.get("disclaimer", ""),
                "metadata": {
                    "multilingual": True,
                    "languages": list(languages),
                    "medical_facts": list(plan.get("medical_facts", [])),
                    "source_excerpt": article.text[:16000],
                    "visual_system": "fevercoach-explainer-v3",
                    "character_mode": "provided" if character_image else "automatic",
                    "character_concept": character_concept,
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
                        "narrative_role": visual.get("narrative_role", "explanation"),
                        "shot_design": _sanitize_shot_design(visual.get("shot_design", {})),
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

Reviewer-derived medical and visual constraints:
{SEPTEMBER_13_REVIEW_RULES}
{WEEK8_REVIEW_RULES}
{JAEYOON_FAIL_ONLY_RULES}

Article title: {article.title}
Article source: {article.source}
Article content:
{article.text[:16000]}
"""


def _multilingual_planning_prompt(
    article: Article,
    languages: tuple[str, ...],
    has_character_image: bool = True,
) -> str:
    requested = ", ".join(languages)
    schema = {
        "slug": "lowercase-url-slug",
        "character_concept": {
            "subject": "one concrete object, organism, or anatomical subject",
            "source_basis": "why this subject is central to the article",
            "visual_identity": "recognizable shape and medically relevant features",
            "primary_color": "one stable dominant color",
            "surface_texture": "one stable tactile material description",
        },
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
                "narrative_role": "hook|context|misconception|mechanism|evidence|decision|action|red_flag|takeaway",
                "medical_claim": "one source-grounded claim only",
                "include_character": False,
                "shot_design": {
                    "camera_profile": "lateral_reveal|macro_dive|top_down_drop|parallax_arc|pov_travel|comparison_track|xray_push|hero_pullback",
                    "beat_one": "0.0-1.5 second establishing camera move",
                    "beat_two": "1.5-4.5 second subject-focused camera move and action",
                    "payoff_frame": "4.5-6.0 second clear final hold",
                    "depth_layers": "distinct foreground, midground, and background elements",
                    "overlay_safe_zone": "uncluttered screen region for code-rendered data",
                    "sound_cues": "two or three precise diegetic sounds",
                    "transition_out": "visual direction that motivates the next cut",
                },
                "asset_prompt": "English prompt for one clean text-free 9:16 reference image",
                "prompt": "English I2V prompt with one bounded action and locked camera",
                "negative_prompt": "text, numbers, labels, dialogue, logo, deformation",
                "overlays": [
                    {
                        "type": "dimension|arrow|label",
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
    character_instruction = (
        "An existing character reference image is attached. Describe its stable visual identity "
        "in character_concept and preserve that supplied character."
        if has_character_image
        else
        "No character image is attached. Select one concrete representative object, organism, "
        "medicine form, or anatomical subject explicitly grounded in the article. It must be the "
        "single best visual embodiment of the topic and suitable for transformation into a reusable "
        "anthropomorphic character. Do not select a patient, child, clinician, or abstract concept."
    )
    return f"""You are the medical fact checker and visual director for FeverCoach.
Produce localized versions of one precise, clean, 60-second pediatric health explainer.

Return one JSON object only.
{character_instruction}
Create shared visuals and localized copy for these language codes: {requested}.

The top-level JSON format must be:
{json.dumps(schema, ensure_ascii=False, indent=2)}

First extract only facts supported by the article. If the source is a Q&A, case report,
testimonial, or contains headings such as 질문/답변:
- Treat the patient's question, reported hearsay, assumptions, and requested options as context only.
- Use a medical claim or threshold only when the clinician/expert answer explicitly confirms it.
- Never turn a number mentioned only in the question into a general rule or recommendation.
- Preserve case-specific details as case-specific; do not generalize them to every child.

Character concept rules:
- character_concept.subject must name exactly one tangible subject central to the article.
- Write every character_concept value as a concise English visual description even when the article is Korean.
- Keep its identity medically recognizable through stable shape, color, and surface features.
- The later renderer will make it an angry, expressive 3D anthropomorphic character.
- Do not request any visible text, number, unit, symbol, sign, logo, or watermark on the character.
- Do not mention named animation studios, franchises, copyrighted characters, or living artists.

Then create exactly 10 shared scenes. Build a medical retention arc rather than a list of facts.
Every scene has timeline_seconds 6 and generation_seconds 6. Use these narrative roles:
1. hook: show the most visually surprising source-supported consequence or question immediately
2. context: locate the body system, medicine, symptom, or clinical situation
3. misconception: stage the tempting assumption as a question, never as a medical fact
4. mechanism: reveal what is actually happening with a clean cutaway or causal visualization
5. evidence: visualize the article's most important supported threshold, time, or comparison
6. decision: contrast two paths and show why context changes the appropriate next step
7. reassessment: show what new information a clinician may need without asserting a diagnosis
8. action: show a safe source-supported action as a short physical sequence
9. red_flag: isolate urgent warning signs without gore or panic
10. takeaway: resolve the opening question and recommend appropriate pediatric consultation

Narrative rules:
- Every scene must advance the question raised by the previous scene.
- Use problem -> tempting assumption -> mechanism reveal -> evidence -> decision -> action -> takeaway.
- Put one open loop in scenes 1-3 and resolve it no later than scene 5.
- Do not manufacture conflict, failed treatment, history, or a reversal not supported by the article.
- narration must explain the medical claim; camera spectacle may never replace or contradict it.

Visual direction rules:
- Each scene communicates one variable or causal relationship only.
- Choose the visual_type from hook, location, mechanism, quantity, comparison, sequence, red_flag.
- Fill every shot_design field. Adjacent scenes must not repeat camera_profile.
- Design each six-second shot as exactly two camera beats plus a readable payoff hold:
  beat one from 0.0-1.5 seconds, beat two from 1.5-4.5 seconds, hold from 4.5-6.0 seconds.
- Choose camera movement for meaning: lateral reveal for comparison, macro dive or POV travel for
  mechanism, top-down drop for spatial relationships, parallax arc for a hero object, x-ray push for
  internal anatomy, and hero pullback for the final synthesis.
- Use clear foreground, midground, and background separation with one dominant focal target.
- Motion should feel energetic but physically plausible. No handheld shake, random orbit, crash zoom,
  whip pan, spinning camera, or more than two camera moves in one shot.
- Reserve the final 1.5 seconds for a stable frame that makes the medical relationship easy to read.
- asset_prompt creates a clean, text-free, vertical 9:16 still image tailored to this article.
- Set include_character true only when the recurring character improves comprehension; use it in 2-4 scenes,
  not in anatomy cutaways, calibrated measurements, or red-flag diagrams.
- Every prompt is image-to-video. Animate one subject only with a measurable start and end state.
- State which objects remain completely stationary. Finish subject motion within 4.5 seconds and hold.
- Use polished semi-stylized 3D medical visualization halfway between clean modeled illustration and
  restrained photorealism: smooth geometry, tactile material detail, soft contact shadows, subtle
  ambient occlusion, cinematic depth, and clean daylight. Avoid a flat gray wash.
- Use cream, pale teal, clean blue, natural anatomical pink, and warm amber. Pure saturated red is
  reserved for deterministic code-rendered measurement or warning overlays and must not be generated
  into the scene, except when it is an inseparable color of the locked recurring character.
- Never generate text, numbers, units, labels, arrows, captions, signs, dialogue, voice, or music.
- Do not put quoted words or values in asset_prompt or prompt. Never ask a thermometer, calendar,
  clock, chart, bottle, or screen to display, show, read, or mark a value; keep it blank and unmarked.
- Accurate numbers and units belong in simple text-only label overlays. Use arrows or dimension
  brackets only when their endpoints identify a specific anatomical location or measured distance.
- Never use a generic X/cross over a medical object. Never draw a line through or directly behind
  an overlay label; it can be mistaken for cancellation or strikethrough.
- shot_design.overlay_safe_zone must reserve clean negative space for those later code overlays; the
  asset and video prompts must not draw the overlay themselves.
- Overlay coordinates are normalized 0..1 and must remain above y=0.72 to avoid captions.
- Use exact source values. Never invent a dose, duration, temperature, percentage, or diagnosis.
- Do not convert mass to volume unless the source explicitly provides the substance and conversion.
- For medication quantities, show a calibrated medical device or digital scale, never a kitchen spoon.
- Avoid gore, frightening anatomy, trademarked styles, clutter, and decorative motion.

Localization and safety rules:
{HISTORICAL_FAIL_PREVENTION_RULES}
{SEPTEMBER_13_REVIEW_RULES}
{WEEK8_REVIEW_RULES}
{JAEYOON_FAIL_ONLY_RULES}

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
- End the final scene of every language with explicit pediatric consultation advice.
  To make that instruction unambiguous, the final narration must naturally contain
  at least one of these terms in the matching language: Korean "진료", English
  "pediatrician", Spanish "pediatra". Do not leave the consultation advice only in
  the disclaimer or title; it must be spoken in scene 10.
- Character motion prompts preserve the supplied/generated character exactly. They may hold its
  wide-open angry expression, but must request no speaking, mouth animation, dialogue, or lip-sync.
- Do not diagnose, promise outcomes, recommend stopping prescribed medicine, or state certainty.
- Every negative_prompt must include text, numbers, subtitles, logo, watermark, dialogue, voice,
  deformation, extra limbs, and character redesign.
- Only include localization keys requested above: {requested}.

Article title: {article.title}
Article source: {article.source}
Article content:
{article.text[:16000]}
"""


def _validate_character_concept(value: object, required: bool) -> dict:
    if not isinstance(value, dict):
        if required:
            raise ValueError("Gemini response is missing character_concept.")
        return {}
    concept = {
        key: str(value.get(key, "")).strip()
        for key in (
            "subject", "source_basis", "visual_identity", "primary_color", "surface_texture"
        )
    }
    if required and any(not concept[key] for key in ("subject", "visual_identity")):
        raise ValueError(
            "Automatic character_concept requires subject and visual_identity."
        )
    return concept


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
    # Strip common numeric drawing requests even when the planning model ignores
    # the overlay contract. Exact values are composited later by Pillow.
    prompt = re.sub(
        r"\b(?:exactly\s+)?\d+(?:\.\d+)?(?:\s*[-~–]\s*\d+(?:\.\d+)?)?\s+drops?\b",
        "a few uncounted clear drops",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"\b\d+(?:\.\d+)?(?:\s*[-~–]\s*\d+(?:\.\d+)?)?\s+days?\b",
        "an unmarked calendar interval",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"\b\d+(?:\.\d+)?(?:\s*[-~–]\s*\d+(?:\.\d+)?)?\s*(?:°\s*C|%)",
        "an unlabeled threshold",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"\b\d+(?:\.\d+)?(?:\s*[-~–]\s*\d+(?:\.\d+)?)?\s+(?:hours?|minutes?|seconds?|times?|breaths?(?:\s*/\s*min(?:ute)?)?)\b",
        "an unlabeled interval",
        prompt,
        flags=re.IGNORECASE,
    )
    prompt = re.sub(
        r"(['\"])[^'\"]+\1",
        "a completely blank and unmarked surface",
        prompt,
    )
    prompt = re.sub(
        r"\bwith\s+(?:black|white|red|blue)\s+text\b",
        "with a completely blank surface",
        prompt,
        flags=re.IGNORECASE,
    )
    return (
        f"{prompt} All screens, calendars, charts, medicine containers, clock faces, "
        "and signs remain completely blank and unmarked. Render no text, letters, "
        "digits, numbers, units, labels, arrows, captions, typographic symbols, logos, or watermarks."
    )


def _sanitize_shot_design(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    result = dict(value)
    for key in ("beat_one", "beat_two", "payoff_frame", "depth_layers", "transition_out"):
        if key not in result:
            continue
        text = str(result[key])
        text = re.sub(
            r"\b(?:exactly\s+)?\d+(?:\.\d+)?(?:\s*[-~–]\s*\d+(?:\.\d+)?)?\s+drops?\b",
            "a few uncounted clear drops",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b\d+(?:\.\d+)?(?:\s*[-~–]\s*\d+(?:\.\d+)?)?\s+days?\b",
            "an unmarked calendar interval",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b\d+(?:\.\d+)?(?:\s*[-~–]\s*\d+(?:\.\d+)?)?\s*(?:°\s*C|%)",
            "an unlabeled threshold",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"(['\"])[^'\"]+\1", "an unmarked surface", text)
        result[key] = text
    return result


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
    # Legacy/generated threshold and cross graphics are visually ambiguous.
    # Preserve their localized text but normalize them to text-only labels.
    if overlay.get("type") in {"threshold", "cross"}:
        overlay["type"] = "label"
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
    return overlay


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9가-힣]+", "-", text.lower()).strip("-")
    return slug[:64] or "weekly-short"
