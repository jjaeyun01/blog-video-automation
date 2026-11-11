#!/usr/bin/env python3
"""Promote safe Gemini repair copy from an interrupted build back to source configs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec


VISUAL_CATEGORIES = {
    "MEDICATION_ROUTE_ERROR",
    "ANATOMY_ERROR",
    "GENERATED_TEXT_ERROR",
    "BLACK_FRAME",
    "DUPLICATE_OUTPUT",
    "OTHER_VISUAL_ERROR",
    "AUDIO_VIDEO_ERROR",
    "NUMERIC_ERROR",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    args = parser.parse_args()
    promoted = 0

    for config_path in sorted(args.config_dir.glob("*.json")):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        spec = ProductionSpec.load(config_path, check_files=False)
        job_dir = args.jobs_dir / spec.slug / spec.language
        if current_pass(job_dir, spec):
            continue
        repaired_files = sorted(
            (job_dir / "audit").glob("repaired_round_*.production.json"),
            key=round_number,
        )
        if not repaired_files:
            continue
        changed = False
        for repaired_path in repaired_files:
            round_index = round_number(repaired_path)
            round_path = job_dir / "audit" / f"round_{round_index:02}.json"
            if not round_path.exists():
                continue
            result = json.loads(round_path.read_text(encoding="utf-8"))
            repaired = json.loads(repaired_path.read_text(encoding="utf-8"))
            repaired_by_scene = {
                int(scene["index"]): scene for scene in repaired.get("scenes", [])
            }
            issues_by_scene: dict[int, list[dict]] = {}
            for issue in result.get("issues", []):
                if not issue.get("requires_regeneration"):
                    continue
                issues_by_scene.setdefault(int(issue.get("scene", 0)), []).append(issue)
            for index, issues in issues_by_scene.items():
                if not 1 <= index <= len(config.get("scenes", [])):
                    continue
                source_scene = repaired_by_scene.get(index)
                if not source_scene:
                    continue
                target_scene = config["scenes"][index - 1]
                for field in (
                    "narration",
                    "subtitle",
                    "caption_chunks",
                    "medical_claim",
                    "overlays",
                ):
                    target_scene[field] = source_scene[field]
                if any(str(issue.get("category")) in VISUAL_CATEGORIES for issue in issues):
                    target_scene["prompt"] = source_scene["prompt"]
                    target_scene["image"] = None
                changed = True
                print(
                    f"PROMOTED {config_path.name} round {round_index} scene {index}",
                    flush=True,
                )
        if changed:
            config_path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            promoted += 1
    print(f"Promoted pending audit repairs into {promoted} config(s).")


def current_pass(job_dir: Path, spec: ProductionSpec) -> bool:
    try:
        report = json.loads(
            (job_dir / "audit" / "final_report.json").read_text(encoding="utf-8")
        )
        snapshot = json.loads(
            (job_dir / "production.snapshot.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        (job_dir / spec.final_video_filename).exists()
        and snapshot == spec.to_dict()
        and str(report.get("overall_verdict", "")).upper() == "PASS"
    )


def round_number(path: Path) -> int:
    match = re.search(r"round_(\d+)", path.name)
    return int(match.group(1)) if match else 0


if __name__ == "__main__":
    main()
