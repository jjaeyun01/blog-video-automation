from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.providers.tts import GeminiTtsProvider, _raw_audio_fingerprint
from fevercoach_shorts.settings import Settings

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebalance pending 60-second productions around narration density."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    changed = 0
    skipped = 0
    posts = manifest["posts"]
    start = max(1, args.start_index)
    end = args.end_index if args.end_index is not None else len(posts)
    if end < start or start > len(posts):
        raise SystemExit(f"Invalid post range {start}..{end}; manifest has {len(posts)} posts.")
    for post in posts[start - 1 : min(end, len(posts))]:
        for language in manifest.get("languages", ["ko", "en", "es"]):
            path = args.config_dir / f"{post['key']}.production.{language}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            if _is_current_pass(data, args.jobs_dir, path):
                skipped += 1
                continue
            allocation = _allocation(data, args.jobs_dir)
            previous = [int(scene["timeline_seconds"]) for scene in data["scenes"]]
            if allocation != previous:
                for scene, seconds in zip(data["scenes"], allocation):
                    scene["timeline_seconds"] = seconds
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                changed += 1
                print(f"REBALANCED {post['key']} [{language}]: {previous} -> {allocation}")
    print(f"Rebalanced {changed} pending configs; preserved {skipped} current PASS configs.")


def _allocation(data: dict, jobs_dir: Path) -> list[int]:
    language = str(data["language"])
    scenes = data["scenes"]
    cached = _cached_raw_seconds(data, jobs_dir)
    durations = [
        cached.get(int(scene["index"]), _estimated_raw_seconds(str(scene["narration"]), language))
        for scene in scenes
    ]
    required = [max(3, math.ceil(seconds / 1.48)) for seconds in durations]
    if sum(required) > 60:
        raise ValueError(
            f"Narration is too dense to fit 60 seconds safely for {data['slug']} [{language}]: "
            f"minimum {sum(required)} seconds at 1.48x"
        )

    allocation = list(required)
    while sum(allocation) < 60:
        index = max(
            range(len(scenes)),
            key=lambda item: (durations[item] / allocation[item], -item),
        )
        allocation[index] += 1
    return allocation


def _estimated_raw_seconds(narration: str, language: str) -> float:
    if language in {"en", "es"}:
        units = len(narration.split())
        return max(3.0, units / 2.8)
    units = len(re.sub(r"\s+", "", narration))
    return max(3.0, units / 5.5)


def _density(narration: str, language: str) -> int:
    return len(narration.split()) if language in {"en", "es"} else len(re.sub(r"\s+", "", narration))


def _cached_raw_seconds(data: dict, jobs_dir: Path) -> dict[int, float]:
    """Use TTS already synthesized for unchanged narration, including failed attempts."""
    job_dir = jobs_dir / str(data["slug"]) / str(data["language"])
    snapshot_path = job_dir / "production.snapshot.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    snapshot_scenes = {
        int(scene["index"]): str(scene.get("narration", ""))
        for scene in snapshot.get("scenes", [])
    }
    repaired_scenes: dict[int, str] = {}
    repaired_files = sorted((job_dir / "audit").glob("repaired_round_*.production.json"))
    if repaired_files:
        try:
            latest_repair = json.loads(repaired_files[-1].read_text(encoding="utf-8"))
            repaired_scenes = {
                int(scene["index"]): str(scene.get("narration", ""))
                for scene in latest_repair.get("scenes", [])
            }
        except (OSError, ValueError, json.JSONDecodeError):
            repaired_scenes = {}
    manifest_path = job_dir / "audio" / "manifest.json"
    try:
        audio_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        audio_manifest = {"scenes": {}}
    try:
        provider_key = GeminiTtsProvider(
            Settings.from_env(), str(data["language"])
        ).cache_key
    except ValueError:
        provider_key = ""
    seconds: dict[int, float] = {}
    for scene in data["scenes"]:
        index = int(scene["index"])
        old_narration = snapshot_scenes.get(index, "")
        new_narration = str(scene.get("narration", ""))
        entry = audio_manifest.setdefault("scenes", {}).setdefault(str(index), {})
        current_fingerprint = (
            _raw_audio_fingerprint(SimpleNamespace(narration=new_narration), provider_key)
            if provider_key
            else ""
        )
        raw_path = job_dir / "audio" / "raw" / f"scene_{index:02}.mp3"
        if not raw_path.exists():
            continue
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(raw_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            duration = float(result.stdout.strip())
            trusted_current_take = (
                old_narration == new_narration
                or repaired_scenes.get(index) == new_narration
                or (
                    bool(current_fingerprint)
                    and entry.get("raw_fingerprint") == current_fingerprint
                )
            )
            if old_narration and not trusted_current_take:
                old_units = max(1, _density(old_narration, str(data["language"])))
                new_units = max(1, _density(new_narration, str(data["language"])))
                duration *= new_units / old_units
            elif trusted_current_take and provider_key:
                entry["raw_fingerprint"] = current_fingerprint
                entry["raw_seconds"] = round(duration, 3)
            seconds[index] = duration
        except (OSError, ValueError, subprocess.CalledProcessError):
            continue
    if provider_key and audio_manifest.get("scenes"):
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(audio_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return seconds


def _is_current_pass(data: dict, jobs_dir: Path, config_path: Path) -> bool:
    job_dir = jobs_dir / str(data["slug"]) / str(data["language"])
    final_name = f"{data['slug']}_{str(data['language']).upper()}.mp4"
    try:
        report = json.loads((job_dir / "audit" / "final_report.json").read_text(encoding="utf-8"))
        snapshot = json.loads((job_dir / "production.snapshot.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    canonical = ProductionSpec.load(config_path, check_files=False).to_dict()
    return (
        (job_dir / final_name).exists()
        and snapshot == canonical
        and str(report.get("overall_verdict", "")).upper() == "PASS"
    )


if __name__ == "__main__":
    main()
