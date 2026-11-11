from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import threading
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.providers.assets import SceneAssetGenerator
from fevercoach_shorts.providers.prompt_refiner import VeoPromptRefiner
from fevercoach_shorts.providers.tts import build_timeline_audio, create_tts_provider
from fevercoach_shorts.providers.veo import VeoGenerator
from fevercoach_shorts.renderer import ShortsRenderer
from fevercoach_shorts.settings import Settings
from fevercoach_shorts.subtitles import write_srt


ORAL_SYRINGE = re.compile(
    r"oral\s+(?:dosing\s+)?syringe|needleless\s+(?:oral\s+)?syringe|"
    r"syringe[^.]{0,100}(?:mouth|cheek)|(?:mouth|cheek)[^.]{0,100}syringe|"
    r"경구용?\s*주사기|바늘\s*없는\s*주사기|주사기[^.]{0,60}(?:입|볼)|"
    r"jeringa\s+oral|jeringa[^.]{0,100}(?:boca|mejilla)",
    re.IGNORECASE,
)
ANY_SYRINGE = re.compile(r"syringe|주사기|jeringa", re.IGNORECASE)
INJECTION = re.compile(
    r"injection|inject|intramuscular|intravenous|iv\s+(?:site|line)|vaccination|vaccine|"
    r"근육|정맥|접종|해열주사|inyecci[oó]n|inyectar|intramuscular|intravenosa|vacuna",
    re.IGNORECASE,
)
MALFORMED_ROUTE = re.compile(
    r"계량컵\s*없이|dosing\s+cup\s+without|dosificador[^.]{0,30}sin\s+aguja",
    re.IGNORECASE,
)
NO_TEXT = (
    "All screens, containers, cups, clocks, calendars, charts, and signs stay completely blank "
    "and unmarked. Render no text, letters, digits, numbers, units, labels, arrows, captions, "
    "logos, or watermarks."
)
ROUTE_LOCK = (
    "Absolute route lock: the open-rimmed cup is the only dosing implement in the frame. No "
    "tube-shaped, plunger-style, needle-like, dropper-style, or pipette-style object or character "
    "appears. Nothing except the wide cup rim approaches the mouth."
)
_print_lock = threading.Lock()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate only scenes confirmed to contain a syringe in/near a mouth."
    )
    parser.add_argument(
        "summary", type=Path, default=Path("outputs/oral_syringe_visual_audit/summary.json"), nargs="?"
    )
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    parser.add_argument("--config-dir", type=Path, default=Path("inputs/route_repairs"))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--slugs", nargs="+")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required.")
    data = json.loads(args.summary.read_text(encoding="utf-8"))
    requested = set(args.slugs or ())
    repairs: dict[str, set[int]] = {}
    for row in data.get("results", []):
        if row.get("final_verdict") != "FAIL":
            continue
        slug = str(row["slug"])
        if requested and slug not in requested:
            continue
        repairs[slug] = {int(issue["scene"]) for issue in row.get("issues", [])}
    if not repairs:
        raise SystemExit("No FAIL scenes found in the audit summary.")

    args.config_dir.mkdir(parents=True, exist_ok=True)
    prepared: dict[str, dict[str, Path]] = {}
    repaired_scenes: dict[str, list[int]] = {}
    for slug, confirmed in repairs.items():
        prepared[slug], repaired_scenes[slug] = prepare_configs(
            slug, confirmed, args.jobs_dir, args.config_dir
        )

    results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                rebuild_topic,
                slug,
                configs,
                set(repaired_scenes[slug]),
                settings,
                args.jobs_dir,
            ): slug
            for slug, configs in prepared.items()
        }
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            slug = futures[future]
            try:
                outputs = future.result()
                results[slug] = {"status": "REBUILT", "outputs": outputs}
            except Exception as error:
                results[slug] = {"status": "ERROR", "error": str(error)}
            with _print_lock:
                print(
                    f"REPAIR {index}/{len(futures)} {slug}: {results[slug]['status']}", flush=True
                )
            write_manifest(args.config_dir, repaired_scenes, results)

    write_manifest(args.config_dir, repaired_scenes, results)
    failures = [slug for slug, result in results.items() if result["status"] == "ERROR"]
    if failures:
        raise SystemExit(f"Repair failed for {len(failures)} topic(s): {', '.join(failures)}")


def prepare_configs(
    slug: str,
    confirmed: set[int],
    jobs_dir: Path,
    config_dir: Path,
) -> tuple[dict[str, Path], list[int]]:
    configs: dict[str, Path] = {}
    expanded = set(confirmed)
    raw_by_language: dict[str, dict[str, Any]] = {}
    for language in ("ko", "en", "es"):
        snapshot = jobs_dir / slug / language / "production.snapshot.json"
        raw = json.loads(snapshot.read_text(encoding="utf-8"))
        raw_by_language[language] = raw
        for scene in raw.get("scenes", []):
            visual_text = " ".join(
                str(scene.get(key, ""))
                for key in (
                    "title", "narration", "subtitle", "medical_claim", "prompt", "asset_prompt",
                    "shot_design",
                )
            )
            wrong_iv = (
                "Show two clearly separate, non-contact treatment symbols" in str(scene.get("prompt", ""))
                and not is_intended_iv_scene(slug, int(scene["index"]))
            )
            if requires_route_repair(visual_text) or wrong_iv or MALFORMED_ROUTE.search(visual_text):
                expanded.add(int(scene["index"]))

    for language, raw in raw_by_language.items():
        for scene in raw.get("scenes", []):
            index = int(scene["index"])
            if index not in expanded:
                continue
            old_prompt = str(scene.get("prompt", ""))
            wrong_iv = (
                "Show two clearly separate, non-contact treatment symbols" in old_prompt
                and not is_intended_iv_scene(slug, index)
            )
            already_safe = "Absolute route lock:" in old_prompt and not wrong_iv
            originally_oral = ANY_SYRINGE.search(
                f"{scene.get('prompt', '')} {scene.get('asset_prompt', '')}"
            ) is not None or wrong_iv
            if not already_safe:
                scene["prompt"] = safe_video_prompt(scene, originally_oral)
                scene["asset_prompt"] = safe_asset_prompt(scene, originally_oral)
            scene["mode"] = "i2v"
            scene["image"] = None
            scene["shot_design"] = safe_shot_design(scene.get("shot_design"))
            for key in ("title", "medical_claim"):
                scene[key] = replace_route_word(str(scene.get(key, "")), language)
            narration = str(scene.get("narration", ""))
            if ANY_SYRINGE.search(narration) or MALFORMED_ROUTE.search(narration):
                narration = safe_narration(language)
                scene["narration"] = narration
                scene["subtitle"] = narration
                scene["caption_chunks"] = [narration]
            negative = str(scene.get("negative_prompt", "")).strip()
            scene["negative_prompt"] = ", ".join(
                value for value in (
                    negative,
                    "syringe, oral syringe, dosing syringe, plunger, needle, injection device, "
                    "dropper, pipette, tube at mouth, medicine applicator at mouth",
                ) if value
            )
        output = config_dir / f"{slug}.production.{language}.json"
        output.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        # Loading now is a deterministic guard that no forbidden oral-syringe instruction remains.
        ProductionSpec.load(output, check_files=False)
        configs[language] = output
    return configs, sorted(expanded)


def safe_video_prompt(scene: dict[str, Any], originally_oral: bool) -> str:
    title = str(scene.get("title", "medicine guidance"))
    claim = str(scene.get("medical_claim", ""))
    if not originally_oral:
        original = str(scene.get("prompt", "")).strip()
        return (
            f"{original}\nThe intended subject is {title}. Preserve that action and composition, but "
            "show no medicine administration or medical dosing implement. "
            f"{ROUTE_LOCK} {NO_TEXT}"
        )
    if re.search(
        r"\bIV\b|intravenous|수액|정맥|intravenosa",
        str(scene.get("prompt", "")) + " " + claim,
        flags=re.IGNORECASE,
    ):
        action = (
            "Show two clearly separate, non-contact treatment symbols: a standard IV fluid bag with "
            "tubing already connected to a properly dressed child's forearm by a small clinical "
            "adhesive dressing, and a purpose-made translucent dosing cup containing a small amount "
            "of amber liquid medicine resting on a table. No puncture action is shown."
        )
    else:
        action = (
            "A calm upright child holds a small purpose-made translucent medicine dosing cup with a "
            "small amount of amber liquid. The child lifts the open cup to the lips, takes one gentle "
            "sip, lowers it, and swallows comfortably. A caregiver supports the child without holding "
            "any dosing implement. The medicine bottle remains closed on a distant table."
        )
    return (
        f"Vertical 9:16 polished semi-stylized 3D pediatric medical scene about {title}. {action} "
        f"{ROUTE_LOCK} Keep every child fully clothed and the mood reassuring. {NO_TEXT}"
    )


def requires_route_repair(value: str) -> bool:
    if ORAL_SYRINGE.search(value):
        return True
    if not ANY_SYRINGE.search(value):
        return False
    without_object_name = ANY_SYRINGE.sub("", value)
    return INJECTION.search(without_object_name) is None


def is_intended_iv_scene(slug: str, scene: int) -> bool:
    # This topic explicitly contrasts IV fluid with swallowed antipyretic. Only
    # its comparison scene needs the already-connected IV line visual.
    return slug == "pediatric-fever-iv-antipyretic" and scene == 4


def safe_asset_prompt(scene: dict[str, Any], originally_oral: bool) -> str:
    title = str(scene.get("title", "medicine guidance"))
    if not originally_oral:
        original = str(scene.get("asset_prompt", "")).strip()
        return f"{original} {ROUTE_LOCK} {NO_TEXT}"
    return (
        f"Clean text-free vertical 9:16 reference image for {title}. An upright fully clothed child "
        "holds a small purpose-made translucent medicine dosing cup containing a little amber liquid. "
        "The cup is below the chin and clearly cup-shaped with a wide open rim. The caregiver's hands "
        f"are empty. {ROUTE_LOCK} Soft clinical daylight, reassuring 3D illustration. {NO_TEXT}"
    )


def safe_shot_design(current: Any) -> dict[str, str]:
    profile = "hero_pullback"
    if isinstance(current, dict) and str(current.get("camera_profile", "")) in {
        "lateral_reveal", "macro_dive", "top_down_drop", "parallax_arc",
        "pov_travel", "comparison_track", "xray_push", "hero_pullback",
    }:
        profile = str(current["camera_profile"])
    return {
        "camera_profile": profile,
        "beat_one": "0.0-1.5 seconds: establish a calm, fully clothed upright child and caregiver.",
        "beat_two": (
            "1.5-4.5 seconds: the child independently lifts a wide open-rimmed medicine dosing "
            "cup, takes one small sip, and lowers it. The caregiver's hands remain empty."
        ),
        "payoff_frame": "4.5-6.0 seconds: hold on the child comfortable beside the lowered cup.",
        "depth_layers": "Cup in foreground, child in midground, softly blurred room behind.",
        "overlay_safe_zone": "Upper left quadrant remains visually quiet.",
        "sound_cues": "Soft cup movement and one gentle swallow; no dialogue.",
        "transition_out": "Slow reassuring pullback.",
    }


def replace_route_word(value: str, language: str) -> str:
    replacement = {
        "ko": "전용 계량컵",
        "en": "purpose-made dosing cup",
        "es": "vaso dosificador específico",
    }[language]
    patterns = (
        r"anthropomorphic\s+oral\s+syringe\s+character",
        r"needleless\s+oral\s+syringe",
        r"oral\s+dosing\s+syringe",
        r"oral\s+syringe",
        r"needleless\s+syringe",
        r"dosing\s+syringe",
        r"경구용?\s*주사기",
        r"바늘(?:이)?\s*없는\s*주사기",
        r"주사기",
        r"jeringa\s+oral",
        r"jeringa\s+sin\s+aguja",
        r"jeringa",
        r"syringe",
    )
    result = value
    for pattern in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def safe_narration(language: str) -> str:
    return {
        "ko": "정해진 양의 액상 약은 전용 계량컵으로 천천히 복용하게 하세요.",
        "en": "Give the prescribed liquid medicine slowly in a purpose-made dosing cup.",
        "es": "Dé el medicamento líquido indicado lentamente en un vaso dosificador.",
    }[language]


def rebuild_topic(
    slug: str,
    configs: dict[str, Path],
    scene_numbers: set[int],
    settings: Settings,
    jobs_dir: Path,
) -> dict[str, str]:
    base_spec = ProductionSpec.load(configs["ko"], check_files=False)
    # A legacy scene may identify the forbidden applicator itself as the recurring
    # character. Do not feed that character reference into replacement assets.
    selected = [
        replace(scene, include_character=False)
        for scene in base_spec.scenes
        if scene.index in scene_numbers
    ]
    mini = replace(base_spec, scenes=selected)
    visual_dir = jobs_dir / slug / "visuals"

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

    clips = [visual_dir / "clips" / f"scene_{index:02}.mp4" for index in range(1, 11)]
    renderer = ShortsRenderer()
    outputs: dict[str, str] = {}
    for language in ("ko", "en", "es"):
        spec = ProductionSpec.load(configs[language], check_files=False)
        job_dir = jobs_dir / slug / language
        provider = create_tts_provider("gemini", settings, language)
        narration = build_timeline_audio(spec, provider, job_dir)
        subtitles = write_srt(spec, job_dir / "subtitles.srt")
        output = renderer.render(spec, clips, narration, subtitles, job_dir)
        (job_dir / "production.snapshot.json").write_text(
            json.dumps(spec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        outputs[language] = str(output.resolve())
    return outputs


def safe_print(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


def write_manifest(
    config_dir: Path, repaired_scenes: dict[str, list[int]], results: dict[str, Any]
) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route_policy": "No syringe in or near a mouth; oral liquid uses a dosing cup.",
        "repaired_scenes": repaired_scenes,
        "results": results,
    }
    (config_dir / "repair_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
