from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import subprocess
import threading
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.providers.assets import SceneAssetGenerator
from fevercoach_shorts.providers.prompt_refiner import VeoPromptRefiner
from fevercoach_shorts.providers.tts import build_timeline_audio, create_tts_provider
from fevercoach_shorts.providers.veo import VeoGenerator
from fevercoach_shorts.renderer import ShortsRenderer
from fevercoach_shorts.settings import Settings
from fevercoach_shorts.review_rules import (
    SEPTEMBER_13_REVIEW_RULES, WEEK8_REVIEW_RULES, JAEYOON_FAIL_ONLY_RULES,
)
from fevercoach_shorts.subtitles import write_srt

from repair_oral_syringe_scenes import (
    ANY_SYRINGE,
    MALFORMED_ROUTE,
    NO_TEXT,
    ROUTE_LOCK,
    replace_route_word,
    requires_route_repair,
    safe_asset_prompt,
    safe_narration,
    safe_shot_design,
    safe_video_prompt,
)


_COPY_CATEGORIES = {
    "MEDICAL_ERROR", "SOURCE_CONTRADICTION", "UNSUPPORTED_CLAIM", "NUMERIC_ERROR",
    "TTS_CAPTION_MISMATCH", "TRANSLATION_ERROR", "KOREAN_HALLUCINATION",
    "INCOMPLETE_SPEECH", "CAPTION_OMISSION", "TRIAGE_OMISSION",
    "MEDICATION_TIMING_RISK", "CLINICAL_DISTINCTION_MISSING",
}
_VISUAL_CATEGORIES = {
    "MEDICATION_ROUTE_ERROR", "ANATOMY_ERROR", "GENERATED_TEXT_ERROR", "BLACK_FRAME",
    "DUPLICATE_OUTPUT", "OTHER_VISUAL_ERROR", "AUDIO_VIDEO_ERROR",
}
_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["repairs"],
    "properties": {
        "repairs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "scene", "corrected_medical_claim", "corrected_narration",
                    "caption_chunks", "replace_overlays", "overlays",
                    "regenerate_visual", "visual_prompt_addendum", "reason_ko",
                ],
                "properties": {
                    "scene": {"type": "integer", "minimum": 1, "maximum": 10},
                    "corrected_medical_claim": {"type": "string"},
                    "corrected_narration": {"type": "string"},
                    "caption_chunks": {"type": "array", "items": {"type": "string"}},
                    "replace_overlays": {"type": "boolean"},
                    "overlays": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["type", "text"],
                            "properties": {
                                "type": {
                                    "type": "string", "enum": ["label", "arrow", "dimension"]
                                },
                                "text": {"type": "string"},
                                "color": {"type": "string"},
                                "from": {"type": "array", "items": {"type": "number"}},
                                "to": {"type": "array", "items": {"type": "number"}},
                                "position": {"type": "array", "items": {"type": "number"}},
                                "label_position": {
                                    "type": "array", "items": {"type": "number"}
                                },
                            },
                        },
                    },
                    "regenerate_visual": {"type": "boolean"},
                    "visual_prompt_addendum": {"type": "string"},
                    "reason_ko": {"type": "string"},
                },
            },
        }
    },
}
_print_lock = threading.Lock()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply every Gemini FAIL finding, rebuild affected scenes, and preserve checkpoints."
    )
    parser.add_argument(
        "--audit-dir", type=Path,
        default=Path("outputs/all_final_tts_caption_audit_2026-09-09"),
    )
    parser.add_argument(
        "--work-dir", type=Path, default=Path("outputs/fail_repairs_2026-09-09")
    )
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    parser.add_argument(
        "--config-source-dir", type=Path,
        help="Immutable source snapshots for repeatable repair configs; defaults to --jobs-dir.",
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--model")
    parser.add_argument("--slugs", nargs="+")
    parser.add_argument(
        "--overrides", type=Path,
        help="Optional clinician-reviewed scene narration overrides keyed by slug/language/scene.",
    )
    parser.add_argument(
        "--visual-overrides", type=Path,
        help="Optional replacement visual prompts keyed by slug/scene.",
    )
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required.")
    model = args.model or settings.gemini_text_model
    args.work_dir.mkdir(parents=True, exist_ok=True)
    (args.work_dir / "plans").mkdir(exist_ok=True)
    (args.work_dir / "configs").mkdir(exist_ok=True)

    failed = collect_failed(args.audit_dir, set(args.slugs or ()))
    if not failed:
        raise SystemExit("No FAIL videos found in the supplied audit directory.")
    print(
        f"Repair scope: {len(failed)} language videos across "
        f"{len({item['slug'] for item in failed})} topics.", flush=True,
    )

    plans: dict[str, dict[str, Any]] = {}
    if not args.build_only:
        plans = plan_all(failed, args, settings, model)
    else:
        for item in failed:
            path = args.work_dir / "plans" / f"{item['video_id']}.json"
            plans[item["video_id"]] = json.loads(path.read_text(encoding="utf-8"))

    overrides = (
        json.loads(args.overrides.read_text(encoding="utf-8"))
        if args.overrides else {}
    )
    visual_overrides = (
        json.loads(args.visual_overrides.read_text(encoding="utf-8"))
        if args.visual_overrides else {}
    )
    prepared = prepare_configs(
        failed, plans, args.work_dir, args.config_source_dir or args.jobs_dir,
        overrides, visual_overrides,
    )
    write_manifest(args.work_dir, failed, prepared, {}, model)
    if args.plan_only:
        return

    results = build_all(prepared, args, settings)
    write_manifest(args.work_dir, failed, prepared, results, model)
    failures = [slug for slug, result in results.items() if result["status"] == "ERROR"]
    if failures:
        raise SystemExit(f"Repair build failed for {len(failures)} topic(s): {', '.join(failures)}")


def collect_failed(audit_dir: Path, wanted: set[str]) -> list[dict[str, Any]]:
    failed = []
    for path in sorted((audit_dir / "raw").glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if str(result.get("overall_verdict", "")).upper() != "FAIL":
            continue
        slug, language = path.stem.rsplit(".", 1)
        if wanted and slug not in wanted:
            continue
        failed.append(
            {
                "slug": slug,
                "language": language,
                "video_id": f"{slug}.{language}",
                "issues": result.get("issues", []),
            }
        )
    return failed


def plan_all(
    failed: list[dict[str, Any]], args: argparse.Namespace, settings: Settings, model: str
) -> dict[str, dict[str, Any]]:
    plans: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(plan_one, item, args, settings, model): item for item in failed
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            item = futures[future]
            plan = future.result()
            plans[item["video_id"]] = plan
            safe_print(f"PLAN {index}/{len(futures)} {item['video_id']}: {len(plan['repairs'])} scenes")
    return plans


def plan_one(
    item: dict[str, Any], args: argparse.Namespace, settings: Settings, model: str
) -> dict[str, Any]:
    output = args.work_dir / "plans" / f"{item['video_id']}.json"
    if output.exists():
        return json.loads(output.read_text(encoding="utf-8"))
    snapshot = args.jobs_dir / item["slug"] / item["language"] / "production.snapshot.json"
    raw = json.loads(snapshot.read_text(encoding="utf-8"))
    issue_scenes = sorted({int(issue["scene"]) for issue in item["issues"]})
    scenes = [scene for scene in raw.get("scenes", []) if int(scene["index"]) in issue_scenes]
    prompt = repair_prompt(raw, scenes, item["issues"])
    client = genai.Client(api_key=settings.gemini_api_key)
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=_PLAN_SCHEMA,
                    temperature=0.0,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty repair plan.")
            plan = json.loads(response.text)
            returned = sorted({int(row["scene"]) for row in plan.get("repairs", [])})
            if returned != issue_scenes:
                raise RuntimeError(f"Expected repair scenes {issue_scenes}, received {returned}")
            plan["video_id"] = item["video_id"]
            plan["model"] = model
            plan["source_issues"] = item["issues"]
            output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            return plan
        except Exception as error:
            last_error = error
            if attempt == 4:
                break
    raise RuntimeError(f"Could not plan {item['video_id']}: {last_error}")


def repair_prompt(raw: dict[str, Any], scenes: list[dict], issues: list[dict]) -> str:
    language = raw.get("language", "")
    metadata = raw.get("metadata", {})
    return f"""You are repairing a completed pediatric FeverCoach short that failed final QA.
Return one consolidated repair object for every affected scene, in scene order. Write narration and
captions in the declared language {language}. Use only the supplied article excerpt, medical facts,
and existing supported scene meaning. Never invent a dose, interval, diagnosis, treatment, or test.

For copy, medical, source, numeric, caption, pronunciation, language, timing, triage, dehydration,
respiratory, or sleep/lethargy findings, corrected_narration must be a complete replacement sentence
that resolves every finding for that scene. Keep it concise enough for the existing scene duration.
caption_chunks must concatenate to exactly the corrected narration, with no omitted medical clause,
number, unit, negation, warning sign, or action. If no copy change is required, return empty strings
and an empty caption list.

For a visual defect set regenerate_visual true and write a precise English prompt addendum that
removes the defect without asking the video model to render any text or number. Any syringe in or
near a mouth is forbidden and must be replaced with an open-rimmed purpose-made dosing cup for oral
liquid. A syringe is allowed only for an explicitly sourced injection directed to skin, muscle, or
an IV site, never the mouth. Generated surfaces must remain blank. For copy-only defects set
regenerate_visual false. Replace overlays only when a deterministic overlay itself is wrong.

SOURCE URL:
{raw.get('source', '')}

ARTICLE EXCERPT:
{metadata.get('source_excerpt', '')}

SOURCE-GROUNDED FACTS:
{json.dumps(metadata.get('medical_facts', []), ensure_ascii=False, indent=2)}

CURRENT AFFECTED SCENES:
{json.dumps(scenes, ensure_ascii=False, indent=2)}

FINAL QA FINDINGS TO FIX:
{json.dumps(issues, ensure_ascii=False, indent=2)}

Apply these adjudicated safety rules when evaluating findings and writing corrections. An audit
finding is evidence to examine, not permission to introduce a new unsafe threshold or omit meaning:
{SEPTEMBER_13_REVIEW_RULES}
{WEEK8_REVIEW_RULES}
{JAEYOON_FAIL_ONLY_RULES}
"""


def prepare_configs(
    failed: list[dict[str, Any]],
    plans: dict[str, dict[str, Any]],
    work_dir: Path,
    jobs_dir: Path,
    overrides: dict[str, Any] | None = None,
    visual_overrides: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    overrides = overrides or {}
    visual_overrides = visual_overrides or {}
    failed_languages: defaultdict[str, set[str]] = defaultdict(set)
    for item in failed:
        failed_languages[item["slug"]].add(item["language"])

    prepared: dict[str, dict[str, Any]] = {}
    for slug, languages in sorted(failed_languages.items()):
        raws = {
            language: json.loads(
                (jobs_dir / slug / language / "production.snapshot.json").read_text(
                    encoding="utf-8"
                )
            )
            for language in ("ko", "en", "es")
        }
        visual_addenda: defaultdict[int, list[str]] = defaultdict(list)
        copy_scenes: defaultdict[str, set[int]] = defaultdict(set)
        visual_scenes: set[int] = set()
        for language in languages:
            plan = plans[f"{slug}.{language}"]
            raw = raws[language]
            by_scene = {int(scene["index"]): scene for scene in raw["scenes"]}
            # A human-reported visual safety defect is mandatory work even if the
            # copy-focused planner neglects to set regenerate_visual itself.
            for issue in next(
                item["issues"] for item in failed
                if item["slug"] == slug and item["language"] == language
            ):
                if issue.get("category") in _VISUAL_CATEGORIES:
                    index = int(issue["scene"])
                    visual_scenes.add(index)
                    addendum = str(issue.get("visual_prompt_addendum", "")).strip()
                    if addendum:
                        visual_addenda[index].append(addendum)
            for repair in plan["repairs"]:
                index = int(repair["scene"])
                scene = by_scene[index]
                narration = str(repair.get("corrected_narration", "")).strip()
                if narration:
                    chunks = [str(value).strip() for value in repair.get("caption_chunks", [])]
                    joined = " ".join(" ".join(chunks).split())
                    if joined != " ".join(narration.split()):
                        chunks = [narration]
                    scene["narration"] = narration
                    scene["subtitle"] = narration
                    scene["caption_chunks"] = chunks
                    copy_scenes[language].add(index)
                claim = str(repair.get("corrected_medical_claim", "")).strip()
                if claim:
                    scene["medical_claim"] = claim
                if repair.get("replace_overlays"):
                    overlays = repair.get("overlays", [])
                    if all(
                        overlay.get("type") in {"label", "arrow", "dimension"}
                        and isinstance(overlay.get("text"), str)
                        for overlay in overlays
                    ):
                        scene["overlays"] = overlays
                if repair.get("regenerate_visual"):
                    visual_scenes.add(index)
                    addendum = str(repair.get("visual_prompt_addendum", "")).strip()
                    if addendum:
                        visual_addenda[index].append(addendum)

            for index_text, narration in overrides.get(slug, {}).get(language, {}).items():
                index = int(index_text)
                if index not in by_scene or not str(narration).strip():
                    raise ValueError(f"Invalid narration override: {slug}.{language}.{index}")
                scene = by_scene[index]
                scene["narration"] = str(narration).strip()
                scene["subtitle"] = scene["narration"]
                scene["caption_chunks"] = [scene["narration"]]
                scene["medical_claim"] = scene["narration"]
                copy_scenes[language].add(index)

        # All three languages share one visual clip. Put every visual correction on every config,
        # then use Korean as the canonical generation spec.
        for language, raw in raws.items():
            for scene in raw["scenes"]:
                index = int(scene["index"])
                if index in visual_addenda:
                    fixes = " ".join(dict.fromkeys(visual_addenda[index]))
                    scene["prompt"] = f"{scene.get('prompt', '')} FINAL QA REPAIR: {fixes} {NO_TEXT}"
                    scene["asset_prompt"] = (
                        f"{scene.get('asset_prompt', '')} FINAL QA REPAIR: {fixes} {NO_TEXT}"
                    )
                    scene["image"] = None
                    scene["mode"] = "i2v"

                route_text = " ".join(
                    str(scene.get(key, ""))
                    for key in ("prompt", "asset_prompt", "shot_design", "title", "medical_claim")
                )
                if requires_route_repair(route_text) or MALFORMED_ROUTE.search(route_text):
                    visual_scenes.add(index)
                    originally_oral = ANY_SYRINGE.search(route_text) is not None
                    scene["prompt"] = safe_video_prompt(scene, originally_oral)
                    scene["asset_prompt"] = safe_asset_prompt(scene, originally_oral)
                    scene["shot_design"] = safe_shot_design(scene.get("shot_design"))
                    scene["image"] = None
                    scene["mode"] = "i2v"
                    for key in ("title", "medical_claim"):
                        scene[key] = replace_route_word(str(scene.get(key, "")), language)
                    narration = str(scene.get("narration", ""))
                    if ANY_SYRINGE.search(narration) or MALFORMED_ROUTE.search(narration):
                        narration = safe_narration(language)
                        scene["narration"] = narration
                        scene["subtitle"] = narration
                        scene["caption_chunks"] = [narration]
                        copy_scenes[language].add(index)
                    negative = str(scene.get("negative_prompt", ""))
                    scene["negative_prompt"] = (
                        f"{negative}, syringe, oral syringe, dosing syringe, plunger, needle, "
                        "dropper, pipette, tube at mouth, medicine applicator at mouth"
                    ).strip(", ")
                elif index in visual_scenes:
                    scene["prompt"] = f"{scene.get('prompt', '')} {ROUTE_LOCK}"

                replacement = visual_overrides.get(slug, {}).get(str(index))
                if replacement:
                    for key in ("prompt", "asset_prompt", "include_character", "shot_design"):
                        if key in replacement:
                            scene[key] = replacement[key]
                    scene["image"] = None
                    scene["mode"] = "i2v"
                    visual_scenes.add(index)

            output = work_dir / "configs" / f"{slug}.production.{language}.json"
            output.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            ProductionSpec.load(output, check_files=False)

        prepared[slug] = {
            "configs": {
                language: str(
                    (work_dir / "configs" / f"{slug}.production.{language}.json").resolve()
                )
                for language in ("ko", "en", "es")
            },
            "failed_languages": sorted(languages),
            "copy_scenes": {key: sorted(value) for key, value in copy_scenes.items()},
            "visual_scenes": sorted(visual_scenes),
        }
    return prepared


def build_all(
    prepared: dict[str, dict[str, Any]], args: argparse.Namespace, settings: Settings
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(build_topic, slug, data, args.jobs_dir, settings): slug
            for slug, data in prepared.items()
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            slug = futures[future]
            try:
                outputs = future.result()
                results[slug] = {"status": "REBUILT", "outputs": outputs}
            except Exception as error:
                results[slug] = {"status": "ERROR", "error": str(error)}
            safe_print(f"BUILD {index}/{len(futures)} {slug}: {results[slug]['status']}")
            write_manifest(args.work_dir, [], prepared, results, settings.gemini_text_model)
    return results


def build_topic(
    slug: str, data: dict[str, Any], jobs_dir: Path, settings: Settings
) -> dict[str, str]:
    config_paths = {key: Path(value) for key, value in data["configs"].items()}
    visual_scenes = set(data["visual_scenes"])
    visual_dir = jobs_dir / slug / "visuals"
    if visual_scenes:
        base = ProductionSpec.load(config_paths["ko"], check_files=False)
        character_reference = visual_dir / "character" / "reference.png"
        if base.character_image is None and character_reference.exists():
            base = replace(base, character_image=character_reference.resolve())
        selected = [scene for scene in base.scenes if scene.index in visual_scenes]
        mini = replace(base, scenes=selected)
        mini = SceneAssetGenerator(
            api_key=settings.gemini_api_key or "", model=settings.gemini_image_model
        ).generate(mini, visual_dir)
        mini = VeoPromptRefiner(
            api_key=settings.gemini_api_key or "", model=settings.gemini_text_model
        ).refine(mini, visual_dir)
        VeoGenerator(
            api_key=settings.gemini_api_key or "",
            model=settings.gemini_video_model,
            fallback_model=settings.gemini_video_fallback_model,
            poll_interval_seconds=settings.veo_poll_interval_sec,
        ).generate(mini, visual_dir, status=lambda message: safe_print(f"{slug}: {message}"))

    languages = {"ko", "en", "es"} if visual_scenes else set(data["failed_languages"])
    clips = [visual_dir / "clips" / f"scene_{index:02}.mp4" for index in range(1, 11)]
    renderer = ShortsRenderer()
    outputs: dict[str, str] = {}
    for language in sorted(languages):
        job_dir = jobs_dir / slug / language
        provider = create_tts_provider("gemini", settings, language)
        for attempt in range(3):
            rebalance_for_cached_audio(config_paths[language], job_dir)
            spec = ProductionSpec.load(config_paths[language], check_files=False)
            force_tts_scenes(
                job_dir, spec, set(data.get("copy_scenes", {}).get(language, []))
            )
            try:
                narration = build_timeline_audio(spec, provider, job_dir)
                break
            except ValueError as error:
                if "narration is" not in str(error) or attempt == 2:
                    raise
                safe_print(
                    f"{slug}.{language}: rebalancing scene timings after TTS "
                    f"duration check ({attempt + 1}/2)"
                )
        subtitles = write_srt(spec, job_dir / "subtitles.srt")
        output = renderer.render(spec, clips, narration, subtitles, job_dir)
        (job_dir / "production.snapshot.json").write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        outputs[language] = str(output.resolve())
    return outputs


def rebalance_for_cached_audio(config_path: Path, job_dir: Path) -> None:
    """Use already synthesized raw audio to keep every scene below the 1.5x speed guard."""
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    marker_path = job_dir / "audio" / "repair_forced_scenes.json"
    marker = (
        json.loads(marker_path.read_text(encoding="utf-8"))
        if marker_path.exists() else {}
    )
    required: list[int] = []
    for scene in raw["scenes"]:
        index = int(scene["index"])
        audio = job_dir / "audio" / "raw" / f"scene_{index:02}.mp3"
        narration_digest = hashlib.sha256(
            str(scene.get("narration", "")).encode("utf-8")
        ).hexdigest()
        stale_repair_audio = (
            str(index) in marker and marker[str(index)] != narration_digest
        )
        if audio.exists() and not stale_repair_audio:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(audio),
                ],
                capture_output=True, text=True, check=True,
            )
            # Match build_timeline_audio's hard ceiling. A tiny tolerance avoids
            # promoting an exact 1.500x duration because of MP3 probe rounding.
            required.append(
                max(4, math.ceil((float(probe.stdout.strip()) - 0.02) / 1.5))
            )
        else:
            required.append(int(scene["timeline_seconds"]))
    if sum(required) > 60:
        raise ValueError(
            f"Cached narration needs at least {sum(required)} seconds for {raw['slug']} "
            f"[{raw['language']}]; shorten the flagged copy."
        )
    allocation = list(required)
    preferred = [int(scene["timeline_seconds"]) for scene in raw["scenes"]]
    while sum(allocation) < 60:
        candidates = [i for i in range(len(allocation)) if allocation[i] < preferred[i]]
        if not candidates:
            candidates = list(range(len(allocation)))
        index = max(candidates, key=lambda i: (preferred[i] - allocation[i], -i))
        allocation[index] += 1
    if allocation != preferred:
        for scene, seconds in zip(raw["scenes"], allocation):
            scene["timeline_seconds"] = seconds
        config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def force_tts_scenes(job_dir: Path, spec: ProductionSpec, scenes: set[int]) -> None:
    if not scenes:
        return
    marker_path = job_dir / "audio" / "repair_forced_scenes.json"
    marker = (
        json.loads(marker_path.read_text(encoding="utf-8"))
        if marker_path.exists() else {}
    )
    manifest_path = job_dir / "audio" / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists() else {"scenes": {}}
    )
    by_index = {scene.index: scene for scene in spec.scenes}
    changed = False
    for index in scenes:
        fingerprint = hashlib.sha256(
            by_index[index].narration.encode("utf-8")
        ).hexdigest()
        if marker.get(str(index)) == fingerprint:
            continue
        manifest.get("scenes", {}).pop(str(index), None)
        for directory in ("raw", "aligned"):
            path = job_dir / "audio" / directory / f"scene_{index:02}.mp3"
            if path.exists():
                path.unlink()
        marker[str(index)] = fingerprint
        changed = True
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if changed:
        marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")


def write_manifest(
    work_dir: Path,
    failed: list[dict[str, Any]],
    prepared: dict[str, dict[str, Any]],
    results: dict[str, dict[str, Any]],
    model: str,
) -> None:
    path = work_dir / "repair_manifest.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    value = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "failed_video_count": len(failed) if failed else previous.get("failed_video_count"),
        "prepared": {**previous.get("prepared", {}), **prepared},
        "results": {**previous.get("results", {}), **results},
    }
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def safe_print(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


if __name__ == "__main__":
    main()
