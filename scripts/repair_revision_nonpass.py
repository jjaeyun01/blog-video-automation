"""Stage and rebuild only the eight non-PASS Revision exports from the 2026-09-22 audit.

The working videos are rebuilt in Revision/work_jobs first. This script never
publishes over Revision/videos; a fresh Gemini audit must pass before release.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.settings import Settings
from repair_failed_video_audits import build_topic, force_tts_scenes


ROOT = Path("Revision")
REPAIR = ROOT / "pass_repair"
COPY_FIXES = {
    "baby-40c-fever-no-other-symptoms": {
        5: "큰 아이도 40도 넘는 열이 반복되거나 3일 넘게 지속되면 진료받으세요.",
        7: "발진, 귀·목 통증, 소변량 변화도 살피세요.",
        8: "불편할 때만 해열제를 쓰고, 연령·체중별 용량과 간격을 확인하세요.",
        9: "열성 경련, 8시간 무뇨, 발진과 관절통은 응급 신호입니다.",
        10: "열이 지속되거나 악화되면 소아청소년과 진료를 받으세요.",
    },
    "baby-fever-threshold": {
        7: "손발만 보지 말고 체온, 수유, 활력, 호흡을 확인하세요.",
    },
    "influenza-a-high-fever-management": {
        2: "독감 바이러스는 아이를 힘들게 합니다.",
        9: "호흡 곤란·가슴 통증·열성 경련·의식 저하·8시간 넘게 소변이 없으면 응급실로 가세요.",
    },
    "pediatric-fever-alternating-meds": {
        3: "동시·정기 교차 복용은 피하고, 계속 불편하면 의료진과 상의하세요.",
        4: "약마다 투여 간격과 하루 최대량이 달라요. 복용 시간을 기록하세요.",
        5: "40킬로 아이도 시럽 용량은 제품 농도와 처방에 따르세요.",
        6: "성분·농도·1회량·하루 최대량을 확인하고, 모르면 약사에게 물으세요.",
        7: "타이레놀은 4~6시간, 부루펜은 6~8시간 간격입니다.",
        10: "증상이 낫지 않으면 진료받으세요.",
    },
    "pediatric-tamiflu-dosing-flexibility": {
        2: "타미플루는 보통 하루 두 번, 약 12시간 간격으로 먹습니다.",
        3: "첫날 간격을 임의로 줄이지 말고 의료진과 상의하세요.",
        5: "오후 2시 첫 복용 뒤에는 다음 시간을 의료진에게 확인하세요.",
        7: "증상 시작 48시간 안에 치료를 시작하는 게 좋습니다.",
        8: "먹고 30분 안에 토하면 같은 용량을 다시 주고, 그 뒤면 다음 복용까지 기다리세요. 또 토하면 문의하세요.",
        9: "고열이 3일 넘거나 숨차면 진료받으세요.",
        10: "증상이 심해지면 소아청소년과 진료를 받으세요.",
    },
}
TIMELINE_FIXES = {
    "influenza-a-high-fever-management": {2: 4, 9: 8},
    "pediatric-tamiflu-dosing-flexibility": {2: 6, 4: 5, 5: 5, 8: 10},
}
FORMULA_SLUG = "baby-formula-refusal-cold"
FORMULA_ES_SCENE_6 = (
    "Ofrezca tomas pequeñas y frecuentes de fórmula, ajustadas a la edad y a lo que tolere su bebé."
)
FORMULA_VISUAL = {
    "prompt": (
        "A worried caregiver gently holds a fully clothed, awake infant upright with secure head "
        "and trunk support, while an unused plain baby bottle rests on a bare table nearby. "
        "The caregiver attentively checks the infant's alertness and comfort. Slow, calm camera "
        "push toward the caregiver and baby. No clock, timer, countdown, circular tokens, "
        "calendar, medical equipment, markings, digits, text, symbols, or graphic overlays."
    ),
    "asset_prompt": (
        "Vertical 9:16 reassuring pediatric-care scene. A fully clothed awake infant is held "
        "upright with secure head and trunk support by a concerned caregiver. A plain unmarked "
        "baby bottle sits off to one side on a bare table. No clock, timer, countdown, circular "
        "tokens, calendar, numbers, text, symbols, measuring marks, or graphic overlay."
    ),
    "negative_prompt": (
        "clock, digital display, countdown, timer, circular tokens, numbers, digits, letters, "
        "text, symbols, unit markings, logo, label, subtitle, watermark, medicine, syringe, "
        "unsafe infant hold, bare infant torso, extra fingers"
    ),
    "visual_type": "caregiver_observation",
    "shot_design": {
        "camera_profile": "macro_dive",
        "beat_one": "0.0-1.5 seconds: approach a plain unmarked bottle beside a caregiver.",
        "beat_two": "1.5-4.5 seconds: caregiver carefully supports the awake infant and checks responsiveness.",
        "payoff_frame": "4.5-6.0 seconds: reassuring close view of infant safely supported in caregiver's arms.",
        "depth_layers": "Bottle in foreground, caregiver and infant in midground, plain soft background.",
        "overlay_safe_zone": "Uncluttered top-center area reserved for deterministic captions only.",
        "sound_cues": "Quiet room ambience without speech or electronic beeps.",
        "transition_out": "Gentle cut to the next caregiving scene.",
    },
}
FORMULA_FEEDING_VISUAL = {
    "prompt": (
        "Continue from the supplied image of the same caregiver and fully clothed awake infant. "
        "The caregiver seats the infant safely in her lap with head and trunk supported, picks "
        "up the plain unmarked baby bottle containing opaque off-white prepared formula, and "
        "offers a few gentle sips through its soft nipple. Show small pauses, no forcing. "
        "The liquid remains milky white, never amber, orange, or transparent. No medicine, "
        "dosing cup, medical equipment, dilution, text, numbers, marks, or symbols."
    ),
    "asset_prompt": "",
    "negative_prompt": (
        "amber liquid, orange liquid, medicine, dosing cup, open cup, IV bag, syringe, "
        "needle, dropper, powder mixing, diluted formula, clock, text, digits, numbers, "
        "measurement marks, label, logo, watermark, unsafe infant hold"
    ),
    "visual_type": "infant_formula_feeding",
    "shot_design": {
        "camera_profile": "top_down_drop",
        "beat_one": "0.0-1.5 seconds: same caregiver supports same awake infant in her lap.",
        "beat_two": "1.5-4.5 seconds: caregiver offers small sips of milky formula from the plain bottle.",
        "payoff_frame": "4.5-6.0 seconds: infant remains safely supported, bottle gently lowered.",
        "depth_layers": "Milky bottle in foreground, infant and caregiver in midground, soft plain background.",
        "overlay_safe_zone": "Uncluttered upper center reserved for deterministic captions only.",
        "sound_cues": "Quiet room ambience with no speech or electronic sound.",
        "transition_out": "Gentle cut to the next feeding guidance scene.",
    },
}


def stage() -> dict:
    repair_manifest = REPAIR / "repair_manifest.json"
    if repair_manifest.exists():
        return json.loads(repair_manifest.read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "final_audit" / "final_pass_manifest.json").read_text(encoding="utf-8"))
    expected = {(slug, "ko") for slug in COPY_FIXES} | {
        (FORMULA_SLUG, language) for language in ("ko", "en", "es")
    }
    actual = {
        tuple(row["video_id"].rsplit(".", 1))
        for row in audit["rows"] if row["status"] != "PASS"
    }
    if actual != expected:
        raise ValueError(f"Non-PASS scope changed: expected={expected}, actual={actual}")
    (REPAIR / "configs").mkdir(parents=True, exist_ok=True)
    (REPAIR / "original_videos").mkdir(parents=True, exist_ok=True)
    original_clip = ROOT / "work_jobs" / FORMULA_SLUG / "visuals" / "clips" / "scene_05.mp4"
    shutil.copy2(original_clip, REPAIR / "original_formula_scene_05.mp4")
    prepared = {}
    for slug in sorted(set(COPY_FIXES) | {FORMULA_SLUG}):
        configs = {}
        for language in ("ko", "en", "es"):
            job_dir = ROOT / "work_jobs" / slug / language
            raw = json.loads((job_dir / "production.snapshot.json").read_text(encoding="utf-8"))
            fixes = COPY_FIXES.get(slug, {}) if language == "ko" else {}
            if slug == FORMULA_SLUG and language == "es":
                fixes = {6: FORMULA_ES_SCENE_6}
            timings = TIMELINE_FIXES.get(slug, {}) if language == "ko" else {}
            for scene in raw["scenes"]:
                index = int(scene["index"])
                if index in fixes:
                    narration = fixes[index]
                    scene["narration"] = narration
                    scene["subtitle"] = narration
                    scene["caption_chunks"] = [narration]
                    scene["medical_claim"] = narration
                if index in timings:
                    scene["timeline_seconds"] = timings[index]
                if slug == FORMULA_SLUG and index == 5:
                    scene.update(FORMULA_VISUAL)
                    scene["mode"] = "i2v"
                    scene["image"] = None
            config_path = REPAIR / "configs" / f"{slug}.production.{language}.json"
            config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            ProductionSpec.load(config_path, check_files=False)
            configs[language] = str(config_path.resolve())
            if (slug, language) in actual:
                video = ROOT / "videos" / f"{slug}_{language.upper()}.mp4"
                shutil.copy2(video, REPAIR / "original_videos" / video.name)
            if fixes:
                force_tts_scenes(job_dir, ProductionSpec.load(config_path, check_files=False), set(fixes))
        prepared[slug] = {
            "configs": configs,
            "failed_languages": ["ko", "en", "es"] if slug == FORMULA_SLUG else ["ko"],
            "copy_scenes": {
                "ko": sorted(COPY_FIXES.get(slug, {})),
                "es": [6] if slug == FORMULA_SLUG else [],
            },
            "visual_scenes": [5] if slug == FORMULA_SLUG else [],
        }
    value = {"targets": sorted(f"{slug}.{language}" for slug, language in expected), "prepared": prepared, "results": {}}
    repair_manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


def refresh_formula_feeding_visual() -> None:
    """Replace the shared medicine-like scene with a formula-bottle scene."""
    manifest_path = REPAIR / "repair_manifest.json"
    data = stage()
    clip = ROOT / "work_jobs" / FORMULA_SLUG / "visuals" / "clips" / "scene_06.mp4"
    backup = REPAIR / "original_formula_scene_06.mp4"
    if not backup.exists():
        shutil.copy2(clip, backup)
    scene_five_asset = ROOT / "work_jobs" / FORMULA_SLUG / "visuals" / "assets" / "scene_05.png"
    if not scene_five_asset.is_file():
        raise FileNotFoundError(scene_five_asset)
    for language in ("ko", "en", "es"):
        path = REPAIR / "configs" / f"{FORMULA_SLUG}.production.{language}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        scene = next(row for row in raw["scenes"] if row["index"] == 6)
        scene.update(FORMULA_FEEDING_VISUAL)
        scene["image"] = str(scene_five_asset.resolve())
        scene["mode"] = "i2v"
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        ProductionSpec.load(path, check_files=True)
    data["prepared"][FORMULA_SLUG]["visual_scenes"] = [5, 6]
    data["results"].pop(FORMULA_SLUG, None)
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build(workers: int, slugs: set[str], force: bool) -> None:
    manifest_path = REPAIR / "repair_manifest.json"
    data = stage()
    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required")
    pending = {slug: value for slug, value in data["prepared"].items()
               if (not slugs or slug in slugs)
               and (force or data["results"].get(slug, {}).get("status") != "REBUILT")}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(build_topic, slug, value, ROOT / "work_jobs", settings): slug
            for slug, value in pending.items()
        }
        for future in concurrent.futures.as_completed(futures):
            slug = futures[future]
            try:
                outputs = future.result()
                data["results"][slug] = {"status": "REBUILT", "outputs": outputs}
            except Exception as error:
                data["results"][slug] = {"status": "ERROR", "error": str(error)}
            manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{slug}: {data['results'][slug]['status']}", flush=True)
    failed = [slug for slug, result in data["results"].items() if result["status"] != "REBUILT"]
    if failed:
        raise RuntimeError(f"Build incomplete: {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "build", "refresh-formula-visual"])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--slugs", nargs="*", default=[])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "stage":
        staged = stage()
        print(f"Staged {len(staged['targets'])} non-PASS videos", flush=True)
    elif args.command == "build":
        build(args.workers, set(args.slugs), args.force)
    else:
        refresh_formula_feeding_visual()
        print("Refreshed shared formula-feeding scene 6", flush=True)


if __name__ == "__main__":
    main()
