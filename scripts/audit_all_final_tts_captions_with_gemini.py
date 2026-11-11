from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from google import genai

from audit_blog_videos_with_gemini import (
    build_prompt,
    inspect_local_artifacts,
    request_audit,
    sha256,
    upload_and_wait,
    validate_scene_av_checks,
    write_aggregate,
)
from fevercoach_shorts.settings import Settings
from fevercoach_shorts.review_rules import REVIEW_GUIDELINE_VERSION


_print_lock = threading.Lock()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audit TTS and burned-in captions in every completed KO/EN/ES FeverCoach final video."
        )
    )
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/all_final_tts_caption_audit")
    )
    parser.add_argument("--languages", nargs="+", choices=["ko", "en", "es"])
    parser.add_argument("--slugs", nargs="+")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model")
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-uploaded-files", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required.")
    model = args.model or settings.gemini_audit_model
    languages = set(args.languages or ("ko", "en", "es"))
    wanted_slugs = set(args.slugs or ())
    output = args.output_dir
    for name in ("raw", "prompts", "local_checks"):
        (output / name).mkdir(parents=True, exist_ok=True)

    targets = discover_targets(args.jobs_dir, languages, wanted_slugs)
    print(
        f"Found {len(targets)} final videos across "
        f"{len({target['slug'] for target in targets})} topics.",
        flush=True,
    )
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    pending = []
    for target in targets:
        raw_path = output / "raw" / f"{target['video_id']}.json"
        if raw_path.exists() and not args.force:
            try:
                cached = json.loads(raw_path.read_text(encoding="utf-8"))
                if cached_audit_is_current(cached, target, model):
                    results.append(cached)
                    continue
            except json.JSONDecodeError:
                pass
        pending.append(target)
    write_aggregate(output, results, failures, model)
    write_specialized_report(output, results, failures, model)
    print(f"Resume state: {len(results)} complete, {len(pending)} pending.", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                audit_target,
                target,
                output,
                model,
                settings.gemini_api_key or "",
                args.max_attempts,
                args.keep_uploaded_files,
            ): target
            for target in pending
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            target = futures[future]
            try:
                result = future.result()
                results.append(result)
                status = result.get("overall_verdict", "UNKNOWN")
                detail = f"{len(result.get('issues', []))} issue(s)"
            except Exception as error:
                failures.append({"video_id": target["video_id"], "error": str(error)})
                status = "ERROR"
                detail = str(error)
            with _print_lock:
                print(
                    f"AUDIT {index}/{len(pending)} {target['video_id']}: {status} ({detail})",
                    flush=True,
                )
            write_aggregate(output, results, failures, model)
            write_specialized_report(output, results, failures, model)

    write_aggregate(output, results, failures, model)
    write_specialized_report(output, results, failures, model)
    if failures:
        raise SystemExit(f"{len(failures)} audit(s) failed; rerun without --force to resume.")


def discover_targets(
    jobs_dir: Path, languages: set[str], wanted_slugs: set[str]
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    discovered_slugs: set[str] = set()
    for clips_dir in sorted(jobs_dir.glob("*/visuals/clips")):
        if len(list(clips_dir.glob("scene_*.mp4"))) != 10:
            continue
        slug = clips_dir.parents[1].name
        if wanted_slugs and slug not in wanted_slugs:
            continue
        discovered_slugs.add(slug)
        for language in ("ko", "en", "es"):
            if language not in languages:
                continue
            job_dir = jobs_dir / slug / language
            video = job_dir / f"{slug}_{language.upper()}.mp4"
            snapshot = job_dir / "production.snapshot.json"
            if not video.exists() or not snapshot.exists():
                # Some planned batches intentionally use a different visual slug per
                # language. Audit every concrete language job that exists instead of
                # assuming each visual slug must contain all three locales.
                continue
            targets.append(
                {
                    "slug": slug,
                    "language": language,
                    "video_id": f"{slug}.{language}",
                    "job_dir": job_dir,
                    "video": video,
                    "snapshot": snapshot,
                }
            )
    missing = sorted(wanted_slugs - discovered_slugs)
    if missing:
        raise ValueError(f"Unknown or incomplete topic(s): {', '.join(missing)}")
    return targets


def cached_audit_is_current(result: dict, target: dict, model: str) -> bool:
    """A renamed file, changed spec, or old rubric must not inherit an earlier verdict."""
    metadata = result.get("audit_metadata", {})
    return (
        metadata.get("review_guideline_version") == REVIEW_GUIDELINE_VERSION
        and metadata.get("model") == model
        and metadata.get("video_sha256") == sha256(target["video"])
        and metadata.get("snapshot_sha256") == sha256(target["snapshot"])
    )


def audit_target(
    target: dict[str, Any],
    output: Path,
    model: str,
    api_key: str,
    max_attempts: int,
    keep_uploaded: bool,
) -> dict[str, Any]:
    raw = json.loads(target["snapshot"].read_text(encoding="utf-8"))
    spec = loose_spec(raw)
    local_check = inspect_local_artifacts(spec, target["video"], target["job_dir"])
    local_check.update(detailed_local_caption_audio_checks(raw, target["job_dir"]))
    local_path = output / "local_checks" / f"{target['video_id']}.json"
    local_path.write_text(json.dumps(local_check, ensure_ascii=False, indent=2), encoding="utf-8")
    article_text = source_context(raw)
    prompt = build_prompt(target["video_id"], article_text, spec, local_check)
    prompt += """

This is an exhaustive regression run prompted by real reviewer feedback. Do not return PASS until
you have independently watched and listened to all ten scenes. The scene_av_checks array is an
evidence log: use the actual audible and visible wording. Recheck the last second of every scene for
clipped speech and compare safety-critical caption clauses word-for-word in meaning. If the media is
too unclear to verify a field, record the limitation and use WARN rather than assuming it passed.
"""
    prompt_path = output / "prompts" / f"{target['video_id']}.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    client = genai.Client(api_key=api_key)
    uploaded = None
    try:
        uploaded = upload_and_wait(client, target["video"], max_attempts)
        result = request_audit(
            client,
            model,
            uploaded,
            prompt,
            target["video_id"],
            target["language"],
            max_attempts,
        )
        result["audit_metadata"] = {
            "model": model,
            "video": str(target["video"].resolve()),
            "snapshot": str(target["snapshot"].resolve()),
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "video_sha256": sha256(target["video"]),
            "snapshot_sha256": sha256(target["snapshot"]),
            "review_guideline_version": REVIEW_GUIDELINE_VERSION,
            "local_check": local_check,
            "review_basis": "September 13 MC/Sam set1-set8 adjudication (25 filenames, 50 reviews)",
        }
        raw_path = output / "raw" / f"{target['video_id']}.json"
        raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if uploaded is not None and not keep_uploaded:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass


def loose_spec(raw: dict[str, Any]) -> SimpleNamespace:
    scenes = []
    for position, scene in enumerate(raw.get("scenes", []), start=1):
        narration = str(scene.get("narration", "")).strip()
        scenes.append(
            SimpleNamespace(
                index=int(scene.get("index", position)),
                title=str(scene.get("title", f"Scene {position}")),
                timeline_seconds=int(scene.get("timeline_seconds", 6)),
                narration=narration,
                subtitle=str(scene.get("subtitle", narration)).strip(),
                caption_chunks=[str(value) for value in scene.get("caption_chunks", [])],
                medical_claim=str(scene.get("medical_claim", "")),
                prompt=str(scene.get("prompt", "")),
                overlays=list(scene.get("overlays", [])),
            )
        )
    if len(scenes) != 10:
        raise ValueError(f"Expected 10 scenes, found {len(scenes)}")
    return SimpleNamespace(
        slug=str(raw.get("slug", "")),
        language=str(raw.get("language", "")),
        source=str(raw.get("source", "")),
        scenes=scenes,
        metadata=dict(raw.get("metadata", {})),
    )


def detailed_local_caption_audio_checks(raw: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    expected = " ".join(
        str(scene.get("narration", "")) for scene in raw.get("scenes", [])
    )
    srt_path = job_dir / "subtitles.srt"
    srt_text = srt_path.read_text(encoding="utf-8") if srt_path.exists() else ""
    visible_text = " ".join(
        line.strip()
        for line in srt_text.splitlines()
        if line.strip() and not line.strip().isdigit() and "-->" not in line
    )
    expected_numbers = number_tokens(expected)
    subtitle_numbers = number_tokens(visible_text)
    manifest_path = job_dir / "audio" / "manifest.json"
    audio_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists() else {"scenes": {}}
    )
    audio_scenes = []
    for index in range(1, 11):
        entry = audio_manifest.get("scenes", {}).get(str(index), {})
        audio_scenes.append(
            {
                "scene": index,
                "raw_seconds": entry.get("raw_seconds"),
                "timeline_seconds": entry.get("timeline_seconds"),
                "speed_factor": entry.get("speed_factor"),
                "requires_close_listen": float(entry.get("speed_factor", 1) or 1) >= 1.25,
            }
        )
    return {
        "srt_exists": srt_path.exists(),
        "srt_semantically_expected_by_normalized_text": normalize_text(visible_text)
        == normalize_text(expected),
        "expected_number_tokens": expected_numbers,
        "srt_number_tokens": subtitle_numbers,
        "srt_numbers_match_expected": expected_numbers == subtitle_numbers,
        "audio_scene_timing": audio_scenes,
    }


def source_context(raw: dict[str, Any]) -> str:
    metadata = raw.get("metadata", {})
    excerpt = str(metadata.get("source_excerpt", "")).strip()
    facts = metadata.get("medical_facts", [])
    return (
        f"Source: {raw.get('source', '')}\n\n"
        f"Source excerpt:\n{excerpt or 'Not embedded in this legacy snapshot.'}\n\n"
        f"Source-grounded facts:\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )


def number_tokens(value: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", value)


def normalize_text(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def write_specialized_report(
    output: Path,
    results: list[dict[str, Any]],
    failures: list[dict[str, str]],
    model: str,
) -> None:
    av_categories = {
        "INCOMPLETE_SPEECH", "CAPTION_OMISSION", "TTS_CAPTION_MISMATCH",
        "KOREAN_HALLUCINATION", "WRONG_LANGUAGE", "TRANSLATION_ERROR",
        "VOICE_INCONSISTENCY", "AUDIO_VIDEO_ERROR",
    }
    verdicts: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    severities: Counter[str] = Counter()
    scene_failures: Counter[str] = Counter()
    calibration_failures: Counter[str] = Counter()
    av_issues: list[dict[str, Any]] = []
    medical_issues: list[dict[str, Any]] = []
    invalid_scene_logs: list[str] = []
    local_srt_mismatches: list[str] = []
    affected_by_scene_check: defaultdict[str, set[str]] = defaultdict(set)

    for result in results:
        video_id = str(result.get("video_id", ""))
        verdicts[str(result.get("overall_verdict", "UNKNOWN"))] += 1
        scene_checks = result.get("scene_av_checks", [])
        if [int(item.get("scene", 0)) for item in scene_checks] != list(range(1, 11)):
            invalid_scene_logs.append(video_id)
        for check in scene_checks:
            for field in (
                "speech_complete", "caption_covers_speech", "numbers_and_units_match",
                "declared_language_only", "caption_timing_readable",
            ):
                if check.get(field) is False:
                    scene_failures[field] += 1
                    affected_by_scene_check[field].add(video_id)
        for name, status in result.get("calibration_checks", {}).items():
            if name != "evidence_ko" and status == "FAIL":
                calibration_failures[name] += 1
        for issue in result.get("issues", []):
            category = str(issue.get("category", "UNKNOWN"))
            categories[category] += 1
            severities[str(issue.get("severity", "unknown"))] += 1
            row = {
                "video_id": video_id,
                "scene": issue.get("scene"),
                "timestamp": issue.get("timestamp"),
                "severity": issue.get("severity"),
                "category": category,
                "problem_ko": issue.get("problem_ko", ""),
                "recommended_fix_ko": issue.get("recommended_fix_ko", ""),
            }
            (av_issues if category in av_categories else medical_issues).append(row)
        local = result.get("audit_metadata", {}).get("local_check", {})
        if local and (
            not local.get("srt_semantically_expected_by_normalized_text", True)
            or not local.get("srt_numbers_match_expected", True)
        ):
            local_srt_mismatches.append(video_id)

    summary = {
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "completed_videos": len(results),
        "failed_requests": failures,
        "scene_logs": sum(len(result.get("scene_av_checks", [])) for result in results),
        "invalid_scene_logs": invalid_scene_logs,
        "verdict_counts": dict(verdicts),
        "issue_category_counts": dict(categories),
        "issue_severity_counts": dict(severities),
        "scene_check_failure_counts": dict(scene_failures),
        "scene_check_affected_video_counts": {
            key: len(value) for key, value in affected_by_scene_check.items()
        },
        "calibration_failure_counts": dict(calibration_failures),
        "deterministic_srt_mismatch_videos": local_srt_mismatches,
        "tts_caption_av_issues": av_issues,
        "medical_visual_and_triage_issues": medical_issues,
    }
    (output / "tts_caption_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# 전체 최종 영상 TTS·자막 재검사",
        "",
        f"- 모델: `{model}`",
        f"- 완료 영상: {len(results)} / 요청 실패: {len(failures)}",
        f"- 장면별 검사 로그: {summary['scene_logs']}",
        f"- 판정: {dict(verdicts)}",
        f"- 이슈 범주: {dict(categories)}",
        f"- 실제 TTS·자막·오디오 이슈: {len(av_issues)}건",
        f"- 의료·시각·진료기준 이슈: {len(medical_issues)}건",
        f"- 로컬 SRT/대본 불일치: {len(local_srt_mismatches)}개 영상",
        f"- 잘못된 1~10 장면 로그: {len(invalid_scene_logs)}개 영상",
        "",
        "## 장면별 회귀 체크 집계",
        "",
        f"- 실패 장면 수: {dict(scene_failures)}",
        f"- 영향받은 영상 수: {summary['scene_check_affected_video_counts']}",
        f"- 피드백 기준별 FAIL 영상 수: {dict(calibration_failures)}",
        "",
        "## 로컬 SRT·대본 불일치 후보",
        "",
    ]
    lines.extend(f"- `{video_id}`" for video_id in sorted(local_srt_mismatches))
    if not local_srt_mismatches:
        lines.append("- 없음")
    lines.extend([
        "",
        "## TTS·자막·오디오 수정 후보",
        "",
        "| 영상 | 장면 | 시각 | 심각도 | 범주 | 문제 |",
        "|---|---:|---|---|---|---|",
    ])
    for issue in sorted(av_issues, key=lambda row: (row["video_id"], int(row["scene"] or 0))):
        problem = str(issue["problem_ko"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {issue['video_id']} | {issue['scene']} | {issue['timestamp']} | "
            f"{issue['severity']} | {issue['category']} | {problem} |"
        )
    if not av_issues:
        lines.append("| - | - | - | - | - | 감지된 이슈 없음 |")
    lines.extend(
        [
            "",
            "## 의료·시각·진료기준 수정 후보",
            "",
            "| 영상 | 장면 | 심각도 | 범주 | 문제 |",
            "|---|---:|---|---|---|",
        ]
    )
    for issue in sorted(
        medical_issues, key=lambda row: (row["video_id"], int(row["scene"] or 0))
    ):
        problem = str(issue["problem_ko"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {issue['video_id']} | {issue['scene']} | {issue['severity']} | "
            f"{issue['category']} | {problem} |"
        )
    if not medical_issues:
        lines.append("| - | - | - | - | 감지된 이슈 없음 |")
    (output / "tts_caption_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
