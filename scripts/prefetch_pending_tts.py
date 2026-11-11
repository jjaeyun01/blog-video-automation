#!/usr/bin/env python3
"""Synthesize every missing raw TTS take before timeline allocation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.providers.tts import (
    _probe_duration,
    _raw_audio_fingerprint,
    create_tts_provider,
)
from fevercoach_shorts.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--end-index", type=int)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    posts = manifest["posts"]
    start = max(1, args.start_index)
    end = args.end_index if args.end_index is not None else len(posts)
    settings = Settings.from_env()
    generated = 0
    reused = 0

    for post in posts[start - 1 : min(end, len(posts))]:
        key = str(post["key"])
        for language in manifest.get("languages", ["ko", "en", "es"]):
            config_path = args.config_dir / f"{key}.production.{language}.json"
            spec = ProductionSpec.load(config_path, check_files=False)
            job_dir = args.jobs_dir / spec.slug / spec.language
            if current_pass(job_dir, spec):
                continue
            provider = create_tts_provider("gemini", settings, spec.language)
            raw_dir = job_dir / "audio" / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = job_dir / "audio" / "manifest.json"
            try:
                audio_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                audio_manifest = {"scenes": {}}
            audio_manifest.setdefault("scenes", {})

            for scene in spec.scenes:
                fingerprint = _raw_audio_fingerprint(scene, provider.cache_key)
                raw_path = raw_dir / f"scene_{scene.index:02}.mp3"
                entry = audio_manifest["scenes"].get(str(scene.index), {})
                if entry.get("raw_fingerprint") == fingerprint and raw_path.exists():
                    reused += 1
                    continue
                provider.synthesize(scene, raw_path)
                duration = _probe_duration(raw_path)
                audio_manifest["scenes"][str(scene.index)] = {
                    **entry,
                    "raw_fingerprint": fingerprint,
                    "raw_seconds": round(duration, 3),
                }
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(
                    json.dumps(audio_manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                generated += 1
                print(
                    f"TTS {key} [{language}] scene {scene.index}: {duration:.2f}s",
                    flush=True,
                )
    print(f"Raw TTS ready: generated {generated}, reused {reused}.")


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


if __name__ == "__main__":
    main()
