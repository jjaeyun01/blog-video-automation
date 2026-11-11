from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from google import genai
from google.genai import types

from ..models import ProductionSpec, SceneSpec
from ..review_rules import (
    HISTORICAL_FAIL_PREVENTION_RULES,
    SUBMISSION_FEEDBACK_CALIBRATION_RULES,
    REVIEW_GUIDELINE_VERSION,
    extend_review_schema,
)


# The delivery contract requires a clean PASS, so even a low-severity finding
# that Gemini explicitly marks for regeneration must enter the repair loop.
_ACTIONABLE_SEVERITIES = {"critical", "high", "medium", "low"}
_VISUAL_CATEGORIES = {
    "MEDICAL_ERROR", "SOURCE_CONTRADICTION", "UNSUPPORTED_CLAIM", "NUMERIC_ERROR",
    "MEDICATION_ROUTE_ERROR", "ANATOMY_ERROR", "GENERATED_TEXT_ERROR",
    "OTHER_VISUAL_ERROR", "BLACK_FRAME", "DUPLICATE_OUTPUT",
}

_CALIBRATION_STATUS = {"type": "string", "enum": ["PASS", "FAIL", "NOT_APPLICABLE"]}


AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "overall_verdict", "review_summary_ko", "calibration_checks", "scene_av_checks", "issues"
    ],
    "properties": {
        "overall_verdict": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "review_summary_ko": {"type": "string"},
        "calibration_checks": {
            "type": "object",
            "required": [
                "speech_completion", "caption_clause_coverage", "medication_timing",
                "triage_adequacy", "respiratory_red_flags", "high_fever_age_context",
                "sleep_vs_lethargy", "dehydration_guidance", "multilingual_integrity",
                "evidence_ko",
            ],
            "properties": {
                "speech_completion": _CALIBRATION_STATUS,
                "caption_clause_coverage": _CALIBRATION_STATUS,
                "medication_timing": _CALIBRATION_STATUS,
                "triage_adequacy": _CALIBRATION_STATUS,
                "respiratory_red_flags": _CALIBRATION_STATUS,
                "high_fever_age_context": _CALIBRATION_STATUS,
                "sleep_vs_lethargy": _CALIBRATION_STATUS,
                "dehydration_guidance": _CALIBRATION_STATUS,
                "multilingual_integrity": _CALIBRATION_STATUS,
                "evidence_ko": {"type": "string"},
            },
        },
        "scene_av_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "scene", "timestamp", "spoken_transcript", "speech_complete",
                    "visible_caption_transcript", "caption_covers_speech",
                    "numbers_and_units_match", "declared_language_only",
                    "caption_timing_readable", "findings_ko",
                ],
                "properties": {
                    "scene": {"type": "integer", "minimum": 1, "maximum": 10},
                    "timestamp": {"type": "string"},
                    "spoken_transcript": {"type": "string"},
                    "speech_complete": {"type": "boolean"},
                    "visible_caption_transcript": {"type": "string"},
                    "caption_covers_speech": {"type": "boolean"},
                    "numbers_and_units_match": {"type": "boolean"},
                    "declared_language_only": {"type": "boolean"},
                    "caption_timing_readable": {"type": "boolean"},
                    "findings_ko": {"type": "string"},
                },
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "severity", "category", "scene", "timestamp", "problem_ko",
                    "evidence", "confidence", "requires_regeneration", "repair",
                ],
                "properties": {
                    "severity": {
                        "type": "string", "enum": ["critical", "high", "medium", "low"]
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "MEDICAL_ERROR", "SOURCE_CONTRADICTION", "UNSUPPORTED_CLAIM",
                            "NUMERIC_ERROR", "MEDICATION_ROUTE_ERROR", "ANATOMY_ERROR",
                            "TTS_CAPTION_MISMATCH", "TRANSLATION_ERROR",
                            "KOREAN_HALLUCINATION", "GENERATED_TEXT_ERROR",
                            "VOICE_INCONSISTENCY", "WRONG_LANGUAGE", "BLACK_FRAME",
                            "DUPLICATE_OUTPUT", "AUDIO_VIDEO_ERROR", "OTHER_VISUAL_ERROR",
                            "INCOMPLETE_SPEECH", "CAPTION_OMISSION", "TRIAGE_OMISSION",
                            "MEDICATION_TIMING_RISK", "CLINICAL_DISTINCTION_MISSING",
                        ],
                    },
                    "scene": {"type": "integer", "minimum": 1, "maximum": 15},
                    "timestamp": {"type": "string"},
                    "problem_ko": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "requires_regeneration": {"type": "boolean"},
                    "repair": {
                        "type": "object",
                        "required": [
                            "repair_kind", "corrected_medical_claim", "corrected_narration",
                            "corrected_caption_chunks", "replace_overlays",
                            "corrected_overlays", "veo_prompt_addendum",
                        ],
                        "properties": {
                            "repair_kind": {
                                "type": "string",
                                "enum": ["visual", "copy", "overlay", "audio", "combined", "none"],
                            },
                            "corrected_medical_claim": {"type": "string"},
                            "corrected_narration": {"type": "string"},
                            "corrected_caption_chunks": {
                                "type": "array", "items": {"type": "string"}
                            },
                            "replace_overlays": {"type": "boolean"},
                            "corrected_overlays": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["type", "text"],
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["label", "arrow", "dimension"],
                                        },
                                        "text": {"type": "string"},
                                        "color": {"type": "string"},
                                        "from": {
                                            "type": "array", "items": {"type": "number"}
                                        },
                                        "to": {
                                            "type": "array", "items": {"type": "number"}
                                        },
                                        "position": {
                                            "type": "array", "items": {"type": "number"}
                                        },
                                        "label_position": {
                                            "type": "array", "items": {"type": "number"}
                                        },
                                    },
                                },
                            },
                            "veo_prompt_addendum": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


extend_review_schema(AUDIT_SCHEMA)


class FinalVideoAuditor:
    """Gemini final-video medical QA with scene-scoped repair instructions."""

    def __init__(
        self,
        api_key: str,
        model: str,
        min_confidence: float = 0.75,
        client=None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ):
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=120_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self.model = model
        self.min_confidence = min(1.0, max(0.0, min_confidence))
        self.sleep = sleep
        self.max_attempts = max(1, max_attempts)

    def audit(
        self,
        spec: ProductionSpec,
        video_path: Path,
        audit_dir: Path,
        round_index: int,
        source_text: str,
    ) -> dict[str, Any]:
        audit_dir.mkdir(parents=True, exist_ok=True)
        uploaded = None
        try:
            uploaded = self._upload_and_wait(video_path)
            prompt = _audit_prompt(spec, source_text, self.min_confidence)
            result = self._request(uploaded, prompt)
            result["audit_metadata"] = {
                "review_guideline_version": REVIEW_GUIDELINE_VERSION,
                "round": round_index,
                "model": self.model,
                "video": str(video_path.resolve()),
                "video_sha256": _sha256(video_path),
                "audited_at": datetime.now(timezone.utc).isoformat(),
            }
            path = audit_dir / f"round_{round_index:02}.json"
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result
        finally:
            if uploaded is not None:
                try:
                    self.client.files.delete(name=uploaded.name)
                except Exception:
                    pass

    def _upload_and_wait(self, path: Path):
        uploaded = self.client.files.upload(
            file=path, config=types.UploadFileConfig(mime_type="video/mp4")
        )
        while str(getattr(uploaded, "state", "")) in {
            "FileState.PROCESSING", "PROCESSING"
        }:
            self.sleep(5)
            uploaded = self.client.files.get(name=uploaded.name)
        if str(getattr(uploaded, "state", "")) in {"FileState.FAILED", "FAILED"}:
            raise RuntimeError("Gemini could not process the final video for medical QA.")
        return uploaded

    def _request(self, uploaded: Any, prompt: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[uploaded, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=AUDIT_SCHEMA,
                        temperature=0.0,
                    ),
                )
                if not response.text:
                    raise RuntimeError("Gemini returned an empty final-video audit.")
                return json.loads(response.text)
            except Exception as error:
                last_error = error
                if attempt < self.max_attempts:
                    self.sleep(min(2 ** attempt, 10))
        raise RuntimeError(
            f"Gemini final-video audit failed after {self.max_attempts} attempts: {last_error}"
        ) from last_error


def actionable_issues(result: dict[str, Any], min_confidence: float = 0.75) -> list[dict]:
    return [
        issue for issue in result.get("issues", [])
        if issue.get("severity") in _ACTIONABLE_SEVERITIES
        and bool(issue.get("requires_regeneration"))
        and float(issue.get("confidence", 0)) >= min_confidence
    ]


def find_duplicate_owner(
    registry_path: Path, spec: ProductionSpec, video_path: Path
) -> str | None:
    if not registry_path.exists():
        return None
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    identity = f"{spec.slug}:{spec.language}"
    digest = _sha256(video_path)
    for owner, entry in registry.get("videos", {}).items():
        if owner != identity and entry.get("sha256") == digest:
            return owner
    return None


def register_final_video(
    registry_path: Path, spec: ProductionSpec, video_path: Path
) -> None:
    registry = (
        json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_path.exists() else {"videos": {}}
    )
    registry.setdefault("videos", {})[f"{spec.slug}:{spec.language}"] = {
        "sha256": _sha256(video_path),
        "path": str(video_path.resolve()),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = registry_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(registry_path)


def apply_repairs(
    spec: ProductionSpec,
    issues: list[dict],
    round_index: int,
) -> tuple[ProductionSpec, set[int]]:
    by_scene: dict[int, list[dict]] = {}
    for issue in issues:
        scene_index = int(issue.get("scene", 0))
        if 1 <= scene_index <= len(spec.scenes):
            by_scene.setdefault(scene_index, []).append(issue)

    repaired: list[SceneSpec] = []
    changed: set[int] = set()
    for scene in spec.scenes:
        scene_issues = by_scene.get(scene.index, [])
        if not scene_issues:
            repaired.append(scene)
            continue

        narration = scene.narration
        claim = scene.medical_claim
        caption_chunks = scene.caption_chunks
        overlays = scene.overlays
        prompt_addenda: list[str] = []
        for issue in scene_issues:
            repair = issue.get("repair") or {}
            corrected_claim = str(repair.get("corrected_medical_claim", "")).strip()
            corrected_narration = str(repair.get("corrected_narration", "")).strip()
            corrected_chunks = [
                str(value).strip() for value in repair.get("corrected_caption_chunks", [])
                if str(value).strip()
            ]
            if corrected_claim:
                claim = corrected_claim
            if corrected_narration:
                narration = corrected_narration
                if " ".join(" ".join(corrected_chunks).split()) == " ".join(
                    corrected_narration.split()
                ):
                    caption_chunks = corrected_chunks
                else:
                    caption_chunks = [corrected_narration]
            if repair.get("replace_overlays"):
                overlays = list(repair.get("corrected_overlays", []))
            category = str(issue.get("category", "")).strip()
            addendum = str(repair.get("veo_prompt_addendum", "")).strip()
            if category in {"GENERATED_TEXT_ERROR", "NUMERIC_ERROR"}:
                addendum = (
                    "Remove every generated word, letter, digit, number, unit, measurement mark, "
                    "and typographic symbol from the scene. Keep all object surfaces completely "
                    "blank and unmarked. Exact values are added later only by deterministic code "
                    "overlays; do not render or imitate them in the generated video."
                )
            if addendum:
                prompt_addenda.append(addendum)
            elif category in _VISUAL_CATEGORIES:
                prompt_addenda.append(str(issue.get("problem_ko", "")).strip())

        prompt = scene.prompt
        if prompt_addenda:
            fixes = " ".join(dict.fromkeys(value for value in prompt_addenda if value))
            prompt += (
                f" QUALITY REPAIR ROUND {round_index}: {fixes}. Correct only this defect. "
                "Preserve the source-grounded medical claim, subject identity, composition, "
                "character design, and all other approved scene details."
            )
        repaired_scene = replace(
            scene,
            narration=narration,
            subtitle=narration,
            caption_chunks=caption_chunks,
            medical_claim=claim,
            overlays=overlays,
            prompt=prompt,
        )
        repaired.append(repaired_scene)
        if repaired_scene != scene:
            changed.add(scene.index)

    return replace(spec, scenes=repaired), changed


def _audit_prompt(spec: ProductionSpec, source_text: str, min_confidence: float) -> str:
    scenes = [
        {
            "scene": scene.index,
            "time_seconds": [
                sum(item.timeline_seconds for item in spec.scenes[: scene.index - 1]),
                sum(item.timeline_seconds for item in spec.scenes[: scene.index]),
            ],
            "narration": scene.narration,
            "captions": scene.caption_chunks,
            "medical_claim": scene.medical_claim,
            "overlays": scene.overlays,
        }
        for scene in spec.scenes
    ]
    facts = spec.metadata.get("medical_facts", [])
    return f"""You are the final conservative pediatric medical and audiovisual QA gate.
Inspect the attached completed video itself from start to finish, including visuals, spoken audio,
burned-in captions, numbers, units, devices, anatomy, medicine routes, and generated text.
Return only the requested JSON. Review guideline version: {REVIEW_GUIDELINE_VERSION}.
DECLARED LANGUAGE: {spec.language}
DISTRIBUTION COUNTRY: {spec.metadata.get('distribution_country', 'unknown')}

SOURCE URL: {spec.source}
SOURCE ARTICLE:
{source_text[:18000]}

SOURCE-GROUNDED FACTS FROM PLANNING:
{json.dumps(facts, ensure_ascii=False, indent=2)}

EXPECTED SCENES:
{json.dumps(scenes, ensure_ascii=False, indent=2)}

Rules:
{HISTORICAL_FAIL_PREVENTION_RULES}

Submission-feedback calibration:
{SUBMISSION_FEEDBACK_CALIBRATION_RULES}

Final gate instructions:
- Independently flag unsafe, false, obsolete, unsupported, numerically wrong, or visually
  contradictory pediatric information. A source statement is not automatically medically safe.
- Locate every issue to exactly one scene and timestamp. Do not request regeneration for harmless
  style preferences or uncertain observations.
- Complete every calibration_checks field before deciding the overall verdict. Use NOT_APPLICABLE
  only when that clinical topic truly does not occur in this video. A PASS check requires inspecting
  the final audio and burned-in captions, not trusting the expected scene specification.
- Return exactly ten chronological scene_av_checks entries. For every scene, transcribe the actual
  audible speech and visible burned-in caption independently, listen through the transition for a
  clipped or unfinished ending, compare every medical clause and qualifier, verify every number and
  unit, confirm the declared language, and judge caption onset/offset/readability. Do not populate
  transcripts by copying expected text without observing the completed video.
- Set requires_regeneration only for medium/high/critical defects with confidence at least
  {min_confidence:.2f} that are visible or audible in the final video.
- For a visual defect, provide a concise English veo_prompt_addendum describing only the correction.
- For copy, number, or medical wording defects, provide a source-supported corrected narration in
  the current language and caption chunks that reproduce it exactly. Never invent a fact or dose.
  Aim to fit the existing scene. For English or Spanish, use at most 2 spoken words per
  available second; for Korean, use at most 4 Hangul syllables per available second. Preserve the
  essential safety condition. If complete safe wording cannot fit, explicitly state that the scene
  needs replanning in problem_ko; never omit conditions or create ambiguous compressed lists.
- For an overlay defect, set replace_overlays and return the full corrected overlay list. Prefer
  clear text-only labels; never use a generic X or a line through text.
- Apply the strict FeverCoach publishing rule: any syringe in or near a mouth is an automatic FAIL,
  including a needleless oral dosing syringe. Oral liquid must be sipped from a purpose-made dosing
  cup; an age-appropriate tablet/capsule is allowed only when supported by the source. Show a syringe
  only for an explicitly sourced injection, aimed at an appropriate skin, muscle, or IV site and
  completely away from the mouth. Generic medication wording does not establish an injection route.
- Treat normal prosody variation as the same speaker. Flag actual narrator identity changes only.
- If no real defect exists, return PASS with an empty issues array.
- Maximize a genuine reviewer PASS by detecting the historical failure modes above; never hide,
  downgrade, or ignore a real defect merely to produce a PASS verdict.
- This automated gate does not replace final physician approval.
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
