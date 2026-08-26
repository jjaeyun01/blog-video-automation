from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from fevercoach_shorts.settings import Settings


AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "video_id", "language", "overall_verdict", "medical_accuracy",
        "source_fidelity", "av_integrity", "medication_route_review", "issues",
        "review_summary_ko", "requires_human_medical_review",
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
                            "OTHER_VISUAL_ERROR",
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
            raw_path = output / "raw" / f"{video_id}.json"
            if raw_path.exists() and not args.force:
                try:
                    result = json.loads(raw_path.read_text(encoding="utf-8"))
                    results.append(result)
                    print(f"SKIP {video_id}", flush=True)
                    continue
                except json.JSONDecodeError:
                    pass

            config_path = args.config_dir / f"{post['key']}.production.{language}.json"
            spec = ProductionSpec.load(config_path)
            video_path = settings.jobs_dir / spec.slug / language / "final_shorts.mp4"
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
                    "model": model,
                    "video": str(video_path.resolve()),
                    "config": str(config_path.resolve()),
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
            "time": f"{(scene.index - 1) * 6:02d}-{scene.index * 6:02d}s",
            "narration": scene.narration,
            "caption_chunks": scene.caption_chunks,
            "medical_claim": scene.medical_claim,
            "visual_prompt": scene.prompt,
            "overlays": scene.overlays,
        }
        for scene in spec.scenes
    ]
    return f"""You are a conservative pediatric medical content auditor and audiovisual QA reviewer.
Audit the attached FINAL 60-second video itself, including every visible frame, burned-in caption,
overlay, generated object, and the complete audio track. Compare it with the source article and
the expected production specification below. Return only the requested JSON.

Audit identity: {video_id}
Language: {spec.language}

Mandatory review rules:
1. Source fidelity: flag facts, thresholds, diagnoses, treatment claims, or certainty not supported
   by the clinician answer. Patient questions and assumptions are context, not medical facts.
2. Independent medical safety: flag dangerous, misleading, obsolete, overly broad, or internally
   inconsistent pediatric advice even if it appears in the source. Distinguish a definite error
   from a reasonable simplification. Do not invent a problem just to be cautious.
3. Medication route: inspect every medicine-related visual. A needleless oral dosing syringe placed
   toward the mouth is CORRECT for liquid oral medicine and must not be called an injection. Flag a
   route mismatch only when a needle, injection site, IV line, intramuscular action, or other clear
   parenteral context depicts medicine intended to be swallowed, or vice versa. Also flag kitchen
   spoons presented as calibrated dosing tools.
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
        try:
            uploaded = client.files.upload(
                file=path, config=types.UploadFileConfig(mime_type="video/mp4")
            )
            while str(getattr(uploaded, "state", "")) in {
                "FileState.PROCESSING", "PROCESSING"
            }:
                time.sleep(5)
                uploaded = client.files.get(name=uploaded.name)
            state = str(getattr(uploaded, "state", ""))
            if state in {"FileState.FAILED", "FAILED"}:
                raise RuntimeError(f"Gemini file processing failed: {uploaded}")
            return uploaded
        except Exception as error:
            last_error = error
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
            result["video_id"] = video_id
            result["language"] = language
            return result
        except Exception as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Gemini audit failed after {max_attempts} attempts: {last_error}")


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
    }


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
