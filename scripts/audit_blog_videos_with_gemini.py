from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from fevercoach_shorts.article import load_article
from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.review_rules import (
    SUBMISSION_FEEDBACK_CALIBRATION_RULES, REVIEW_GUIDELINE_VERSION, extend_review_schema,
)
from fevercoach_shorts.settings import Settings


_CALIBRATION_STATUS = {"type": "string", "enum": ["PASS", "FAIL", "NOT_APPLICABLE"]}

AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "video_id", "language", "overall_verdict", "medical_accuracy",
        "source_fidelity", "av_integrity", "medication_route_review", "issues",
        "review_summary_ko", "requires_human_medical_review", "calibration_checks",
        "scene_av_checks",
    ],
    "properties": {
        "video_id": {"type": "string"},
        "language": {"type": "string", "enum": ["ko", "en", "es"]},
        "overall_verdict": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "medical_accuracy": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "source_fidelity": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "av_integrity": {"type": "string", "enum": ["PASS", "WARN", "FAIL"]},
        "spoken_transcript": {"type": "string"},
        "expected_narration_matches_audio": {"type": "boolean"},
        "visible_captions_match_audio": {"type": "boolean"},
        "speaker_voice_consistent": {"type": "boolean"},
        "korean_hallucination_detected": {"type": "boolean"},
        "unexpected_generated_text_detected": {"type": "boolean"},
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
        "medication_route_review": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "timestamp", "depicted_item", "depicted_route", "intended_route",
                    "is_error", "reason_ko", "confidence",
                ],
                "properties": {
                    "timestamp": {"type": "string"},
                    "depicted_item": {"type": "string"},
                    "depicted_route": {"type": "string"},
                    "intended_route": {"type": "string"},
                    "is_error": {"type": "boolean"},
                    "reason_ko": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "severity", "category", "timestamp", "scene", "evidence",
                    "problem_ko", "source_comparison_ko", "recommended_fix_ko", "confidence",
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
                            "TTS_CAPTION_MISMATCH", "TRANSLATION_ERROR", "KOREAN_HALLUCINATION",
                            "GENERATED_TEXT_ERROR", "VOICE_INCONSISTENCY", "AUDIO_VIDEO_ERROR",
                            "OTHER_VISUAL_ERROR", "INCOMPLETE_SPEECH", "CAPTION_OMISSION",
                            "TRIAGE_OMISSION", "MEDICATION_TIMING_RISK",
                            "CLINICAL_DISTINCTION_MISSING",
                        ],
                    },
                    "timestamp": {"type": "string"},
                    "scene": {"type": "integer", "minimum": 1, "maximum": 10},
                    "evidence": {"type": "string"},
                    "problem_ko": {"type": "string"},
                    "source_comparison_ko": {"type": "string"},
                    "recommended_fix_ko": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "review_summary_ko": {"type": "string"},
        "requires_human_medical_review": {"type": "boolean"},
        "limitations_ko": {"type": "array", "items": {"type": "string"}},
    },
}


extend_review_schema(AUDIT_SCHEMA)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit FeverCoach final videos against source articles with Gemini."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("GEMINI_AUDIT_MODEL"))
    parser.add_argument("--languages", nargs="+", choices=["ko", "en", "es"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-uploaded-files", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required.")
    model = args.model or settings.gemini_text_model
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    languages = args.languages or manifest.get("languages", ["ko", "en", "es"])
    output = args.output_dir
    for name in ("raw", "prompts", "articles", "local_checks"):
        (output / name).mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=settings.gemini_api_key)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for post_index, post in enumerate(manifest["posts"], start=1):
        article_path = output / "articles" / f"{post['key']}.md"
        if article_path.exists() and not args.force:
            article_text = article_path.read_text(encoding="utf-8")
        else:
            article = load_article(url=post["url"])
            article_text = f"# {article.title}\n\nSource: {article.source}\n\n{article.text}\n"
            article_path.write_text(article_text, encoding="utf-8")

        for language in languages:
            video_id = f"{post['key']}.{language}"
            config_path = args.config_dir / f"{post['key']}.production.{language}.json"
            spec = ProductionSpec.load(config_path)
            video_path = settings.jobs_dir / spec.slug / language / spec.final_video_filename
            raw_path = output / "raw" / f"{video_id}.json"
            if raw_path.exists() and not args.force:
                try:
                    result = json.loads(raw_path.read_text(encoding="utf-8"))
                    metadata = result.get("audit_metadata", {})
                    if (metadata.get("review_guideline_version") == REVIEW_GUIDELINE_VERSION
                            and metadata.get("model") == model and video_path.is_file()
                            and metadata.get("video_sha256") == sha256(video_path)
                            and metadata.get("config_sha256") == sha256(config_path)
                            and metadata.get("source_sha256") == hashlib.sha256(article_text.encode()).hexdigest()):
                        results.append(result)
                        print(f"SKIP {video_id}", flush=True)
                        continue
                except json.JSONDecodeError:
                    pass

            local_check = inspect_local_artifacts(spec, video_path, settings.jobs_dir / spec.slug / language)
            (output / "local_checks" / f"{video_id}.json").write_text(
                json.dumps(local_check, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            prompt = build_prompt(video_id, article_text, spec, local_check)
            (output / "prompts" / f"{video_id}.txt").write_text(prompt, encoding="utf-8")

            print(
                f"AUDIT {post_index}/{len(manifest['posts'])} {video_id} with {model}",
                flush=True,
            )
            uploaded = None
            try:
                uploaded = upload_and_wait(client, video_path, args.max_attempts)
                result = request_audit(
                    client, model, uploaded, prompt, video_id, language, args.max_attempts
                )
                result["audit_metadata"] = {
                    "review_guideline_version": REVIEW_GUIDELINE_VERSION,
                    "model": model,
                    "video": str(video_path.resolve()),
                    "config": str(config_path.resolve()),
                    "config_sha256": sha256(config_path),
                    "source_sha256": hashlib.sha256(article_text.encode()).hexdigest(),
                    "source_url": post["url"],
                    "audited_at": datetime.now(timezone.utc).isoformat(),
                    "video_sha256": sha256(video_path),
                    "local_check": local_check,
                }
                raw_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                results.append(result)
                print(
                    f"DONE {video_id}: {result.get('overall_verdict')} "
                    f"({len(result.get('issues', []))} issue(s))",
                    flush=True,
                )
            except Exception as error:
                failure = {"video_id": video_id, "error": str(error)}
                failures.append(failure)
                print(f"FAILED {video_id}: {error}", flush=True)
            finally:
                if uploaded is not None and not args.keep_uploaded_files:
                    try:
                        client.files.delete(name=uploaded.name)
                    except Exception:
                        pass
            write_aggregate(output, results, failures, model)

    write_aggregate(output, results, failures, model)
    if failures:
        raise SystemExit(f"{len(failures)} audit(s) failed; rerun to resume.")


def build_prompt(
    video_id: str,
    article_text: str,
    spec: ProductionSpec,
    local_check: dict[str, Any],
) -> str:
    scene_data = [
        {
            "scene": scene.index,
            "time_seconds": [
                sum(getattr(item, "timeline_seconds", 6) for item in spec.scenes[:position]),
                sum(getattr(item, "timeline_seconds", 6) for item in spec.scenes[:position + 1]),
            ],
            "narration": scene.narration,
            "caption_chunks": scene.caption_chunks,
            "medical_claim": scene.medical_claim,
            "visual_prompt": scene.prompt,
            "overlays": scene.overlays,
        }
        for position, scene in enumerate(spec.scenes)
    ]
    return f"""You are a conservative pediatric medical content auditor and audiovisual QA reviewer.
Audit the attached FINAL 60-second video itself, including every visible frame, burned-in caption,
overlay, generated object, and the complete audio track. Compare it with the source article and
the expected production specification below. Return only the requested JSON.

Audit identity: {video_id}
Language: {spec.language}
Distribution country (not inferred from language): {getattr(spec, 'metadata', {}).get('distribution_country', 'unknown')}
Review guideline version: {REVIEW_GUIDELINE_VERSION}

Mandatory review rules:
1. Source fidelity: flag facts, thresholds, diagnoses, treatment claims, or certainty not supported
   by the clinician answer. Patient questions and assumptions are context, not medical facts.
2. Independent medical safety: flag dangerous, misleading, obsolete, overly broad, or internally
   inconsistent pediatric advice even if it appears in the source. Distinguish a definite error
   from a reasonable simplification. Do not invent a problem just to be cautious.
3. Medication route (strict FeverCoach publishing rule): inspect every medicine-related visual.
   Any syringe in or near a mouth is an automatic FAIL, including a needleless oral dosing syringe.
   Swallowed medicine must appear as an age-appropriate tablet/capsule when supported by the source,
   or liquid medicine sipped from a purpose-made dosing cup. A needle and syringe are allowed only
   when the source explicitly requires injection and must point to an appropriate skin, muscle, or IV
   site, never the mouth. Generic words such as give, administer, dose, medicine, or medication do
   not establish an injection route. Also flag kitchen spoons presented as dosing tools.
4. Hallucination: transcribe what is actually spoken. Compare it with the expected narration and
   visible captions. For Korean, explicitly detect added, omitted, garbled, or semantically changed
   Korean TTS. Do not treat ordinary pronunciation variation as hallucination.
5. Visual hallucination: flag generated readable text, wrong numbers/units, malformed anatomy,
   impossible devices, medicine containers that falsely imply a route, or visuals contradicting
   narration. Ignore harmless decorative artifacts.
6. Voice consistency: determine whether the narrator identity changes unexpectedly within this
   video. A tonal or prosodic change alone is not a different speaker.
7. Captions: check semantic agreement with spoken audio and obvious timing/readability failures.
   Captions intentionally have no background panel; that is not an error.
8. Severity: critical = imminent serious harm; high = materially unsafe/false; medium = meaningful
   correction needed; low = minor clarity/visual issue. Use timestamps and observable evidence.
9. If evidence is ambiguous, state the limitation and reduce confidence instead of asserting error.
10. This is a screening audit, not final physician approval. Set requires_human_medical_review true
    for any medical issue or uncertain high-impact claim.

Reviewer-derived regression checklist:
{SUBMISSION_FEEDBACK_CALIBRATION_RULES}

Before choosing the verdict, fill every calibration_checks field. Use NOT_APPLICABLE only when the
topic is absent. Judge the actual final audio and burned-in captions—not just the expected JSON.
For caption coverage, compare every spoken medical clause, negation, number, interval, red flag, and
recommended action with what actually appears on screen. A clipped or unfinished spoken sentence is
INCOMPLETE_SPEECH. A missing safety-relevant caption clause is CAPTION_OMISSION. Unsupported two-hour
alternating antipyretic advice is MEDICATION_TIMING_RISK. Missing care urgency that could delay
evaluation is TRIAGE_OMISSION.

Mandatory scene-by-scene audiovisual pass:
- Return exactly ten scene_av_checks entries, one for each scene in chronological order.
- Transcribe what is actually audible and what is actually visible; never copy the expected text
  into these fields unless you confirmed it in the final video.
- Listen through each scene transition. Mark speech_complete false for a cut-off final syllable,
  unfinished grammar, abandoned clause, abrupt edit, or missing end of the planned sentence.
- caption_covers_speech is false when any spoken medical condition, negation, number, unit, interval,
  red flag, uncertainty qualifier, or recommended action is absent from the visible captions.
- numbers_and_units_match requires spoken audio, visible captions, and expected narration to agree.
  Check 2 versus 12, ranges, decimals, °C, hours, days, kilograms, and milliliters carefully.
- declared_language_only is false for unintended Korean in English/Spanish, unintended English or
  Spanish in Korean, garbled phonemes, encoding artifacts, or a mid-video language switch.
- caption_timing_readable is false for captions that appear too late, vanish before their words are
  spoken, overlap the next clause, are clipped off-screen, or fail to appear at all.

SOURCE ARTICLE (Korean clinician-reviewed content):
{article_text[:18000]}

EXPECTED PRODUCTION SPECIFICATION:
{json.dumps(scene_data, ensure_ascii=False, indent=2)}

DETERMINISTIC LOCAL MEDIA CHECKS:
{json.dumps(local_check, ensure_ascii=False, indent=2)}
"""


def upload_and_wait(client: genai.Client, path: Path, max_attempts: int):
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        uploaded = None
        try:
            uploaded = client.files.upload(
                file=path, config=types.UploadFileConfig(mime_type="video/mp4")
            )
            processing_deadline = time.monotonic() + 300
            while str(getattr(uploaded, "state", "")) in {
                "FileState.PROCESSING", "PROCESSING"
            }:
                if time.monotonic() >= processing_deadline:
                    raise TimeoutError(
                        f"Gemini file processing exceeded 300 seconds for {path.name}"
                    )
                time.sleep(5)
                uploaded = client.files.get(name=uploaded.name)
            state = str(getattr(uploaded, "state", ""))
            if state in {"FileState.FAILED", "FAILED"}:
                raise RuntimeError(f"Gemini file processing failed: {uploaded}")
            return uploaded
        except Exception as error:
            last_error = error
            if uploaded is not None:
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    pass
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Video upload failed after {max_attempts} attempts: {last_error}")


def request_audit(
    client: genai.Client,
    model: str,
    uploaded: Any,
    prompt: str,
    video_id: str,
    language: str,
    max_attempts: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[uploaded, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=AUDIT_SCHEMA,
                    temperature=0.1,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty audit response.")
            result = json.loads(response.text)
            validate_scene_av_checks(result)
            result["video_id"] = video_id
            result["language"] = language
            return result
        except Exception as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Gemini audit failed after {max_attempts} attempts: {last_error}")


def validate_scene_av_checks(result: dict[str, Any]) -> None:
    """Reject audits that did not independently account for all ten final scenes."""
    checks = result.get("scene_av_checks", [])
    scenes = [int(item.get("scene", 0)) for item in checks]
    if scenes != list(range(1, 11)):
        raise RuntimeError(
            "Gemini returned an invalid scene_av_checks order; "
            f"expected 1..10 exactly once, received {scenes}"
        )


def inspect_local_artifacts(
    spec: ProductionSpec, video_path: Path, job_dir: Path
) -> dict[str, Any]:
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,width,height", "-of", "json", str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    media = json.loads(probe.stdout)
    streams = media.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    captions_match = all(
        scene.subtitle == scene.narration
        and normalize(" ".join(scene.caption_chunks)) == normalize(scene.narration)
        for scene in spec.scenes
    )
    caption_alpha_checks = []
    try:
        from PIL import Image

        for path in sorted((job_dir / "caption_images").glob("*.png")):
            with Image.open(path).convert("RGBA") as image:
                corners = [
                    image.getpixel((0, 0))[3], image.getpixel((image.width - 1, 0))[3],
                    image.getpixel((0, image.height - 1))[3],
                    image.getpixel((image.width - 1, image.height - 1))[3],
                ]
                caption_alpha_checks.append({"file": path.name, "transparent_corners": corners})
    except Exception as error:
        caption_alpha_checks.append({"error": str(error)})
    return {
        "duration_seconds": float(media["format"]["duration"]),
        "width": video.get("width"),
        "height": video.get("height"),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "scene_count": len(spec.scenes),
        "captions_equal_expected_narration": captions_match,
        "caption_images_checked": len(caption_alpha_checks),
        "all_caption_image_corners_transparent": all(
            all(alpha == 0 for alpha in item.get("transparent_corners", []))
            for item in caption_alpha_checks
            if "transparent_corners" in item
        ),
        "video_sha256": sha256(video_path),
        "reviewer_feedback_focus": reviewer_feedback_focus(spec),
    }


def reviewer_feedback_focus(spec: ProductionSpec) -> list[dict[str, Any]]:
    """Surface feedback-derived risk topics without making a medical verdict locally."""
    patterns = {
        "TWO_HOUR_ALTERNATING_MEDICINE": (
            r"(?:2\s*(?:시간|hours?|horas?)[^.]{0,80}(?:교차|alternat|alternar))|"
            r"(?:(?:교차|alternat|alternar)[^.]{0,80}2\s*(?:시간|hours?|horas?))"
        ),
        "VERY_HIGH_FEVER_40C": r"40\s*(?:°\s*)?(?:c|도|grados?)",
        "RESPIRATORY_RED_FLAGS": (
            r"호흡|숨쉬|쌕쌕|쇳소리|천명|흉부\s*함몰|breath|wheez|stridor|retraction|"
            r"respira|sibilan|estridor|retracci"
        ),
        "SLEEP_VS_LETHARGY": r"기면|깨우|반응|letharg|difficult\s+to\s+wake|somnol|despertar|responde",
        "DEHYDRATION_OR_POOR_INTAKE": (
            r"탈수|수분\s*섭취|소변량|못\s*마|dehydrat|unable\s+to\s+drink|urine|"
            r"deshidrat|no\s+puede\s+beber|orina"
        ),
        "NEW_OR_MIGRATING_PAIN": (
            r"가슴\s*통증|흉통|귀\s*통증|통증\s*부위|chest\s+pain|ear\s+pain|"
            r"dolor\s+(?:de\s+)?pecho|dolor\s+de\s+o[ií]do"
        ),
        "TWELVE_HOUR_INTERVAL": r"12\s*(?:시간|hours?|horas?)",
        "DRUG_SPECIFIC_REDOSING": r"토하|토하면|구토|재투여|재복용|vomit|redose|repeat.*dose|v[oó]mit|repetir.*dosis",
        "CROSS_SCENE_URGENCY": r"저녁|내일|6\s*시간|tonight|tomorrow|six\s+hours|esta\s+noche|mañana|seis\s+horas",
        "DOSE_CONCENTRATION_CONTEXT": r"밀리리터|농도|\bml\b|concentration|concentraci[oó]n",
        "SAFE_SLEEP_AND_SWALLOWING": r"베개|이불|수면|삼킬|pillow|blanket|sleep|swallow|almohada|manta|dormir|tragar",
        "EMERGENCY_LOCALE": r"119|911|112|응급|emergency|emergencia",
        "TREATMENT_CLAIM_UNCERTAINTY": r"스테로이드|항바이러스|이온음료|steroid|antiviral|sports\s+drink|esteroide|deportiva",
        "FEED_REFUSAL_WAIT": r"수유\s*거부|분유\s*거부|12\s*시간|refus.{0,15}feed|no\s+come|rechaz.{0,15}aliment",
        "FORMULA_AMOUNT_VS_CONCENTRATION": r"분유|희석|formula|dilut|f[oó]rmula|dilui",
        "POWDER_MEDICINE_STORAGE": r"가루\s*약|가루\s*해열|분말|powder|polvo|냉장|refriger",
        "NASAL_IRRIGATION_POSTURE": r"코\s*세척|비강\s*세척|nasal\s*(?:rinse|irrigat)|lavado\s+nasal|irrigaci[oó]n\s+nasal",
        "CASE_TIMELINE_REASSESSMENT": r"퇴원|폐렴|10\s*일|3\s*주|discharg|pneumonia|three\s+weeks|alta|neumon[ií]a",
        "MEDICINE_STOP_RESTART": r"다시\s*먹|중단|재복용|restart|resume|stop|reanudar|suspender",
    }
    focus: list[dict[str, Any]] = []
    for scene in spec.scenes:
        text = " ".join(
            [scene.title, scene.narration, scene.medical_claim, getattr(scene, 'prompt', '')]
            + [str(value) for value in scene.caption_chunks]
            + [str(value) for value in getattr(scene, 'overlays', [])]
        )
        matches = [
            label for label, pattern in patterns.items()
            if re.search(pattern, text, flags=re.IGNORECASE)
        ]
        if matches:
            focus.append({"scene": scene.index, "checks": matches})
    return focus


def write_aggregate(
    output: Path,
    results: list[dict[str, Any]],
    failures: list[dict[str, str]],
    model: str,
) -> None:
    ordered = sorted(results, key=lambda item: item.get("video_id", ""))
    issue_counts = Counter(
        issue.get("severity", "unknown")
        for result in ordered
        for issue in result.get("issues", [])
    )
    verdicts = Counter(result.get("overall_verdict", "UNKNOWN") for result in ordered)
    summary = {
        "model": model,
        "completed": len(ordered),
        "failed": len(failures),
        "verdict_counts": dict(verdicts),
        "issue_severity_counts": dict(issue_counts),
        "failures": failures,
        "results": [
            {
                "video_id": result.get("video_id"),
                "verdict": result.get("overall_verdict"),
                "issue_count": len(result.get("issues", [])),
                "summary_ko": result.get("review_summary_ko", ""),
            }
            for result in ordered
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Gemini 영상 의학·오류 감사 결과",
        "",
        f"- Model: `{model}`",
        f"- 완료: {len(ordered)} / 실패: {len(failures)}",
        f"- 판정: {dict(verdicts)}",
        f"- 이슈 심각도: {dict(issue_counts)}",
        "",
        "> Gemini 검토는 선별 검사이며 최종 게시 전 소아청소년과 전문의 검수를 대체하지 않습니다.",
        "",
    ]
    for result in ordered:
        lines.extend(
            [
                f"## {result.get('video_id')} — {result.get('overall_verdict')}",
                "",
                result.get("review_summary_ko", ""),
                "",
            ]
        )
        for issue in result.get("issues", []):
            lines.append(
                f"- **{issue.get('severity')} / {issue.get('category')} / "
                f"{issue.get('timestamp')}**: {issue.get('problem_ko')} "
                f"(수정: {issue.get('recommended_fix_ko')})"
            )
        checks = result.get("calibration_checks", {})
        failed_checks = [
            name for name, status in checks.items()
            if name != "evidence_ko" and status == "FAIL"
        ]
        if failed_checks:
            lines.append(
                f"- **피드백 회귀 체크 실패**: {', '.join(failed_checks)} — "
                f"{checks.get('evidence_ko', '')}"
            )
        if not result.get("issues"):
            lines.append("- 감지된 이슈 없음")
        lines.append("")
    if failures:
        lines.extend(["## 실패한 감사", ""])
        lines.extend(f"- {item['video_id']}: {item['error']}" for item in failures)
    (output / "gemini_answers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize(value: str) -> str:
    return " ".join(value.split()).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
