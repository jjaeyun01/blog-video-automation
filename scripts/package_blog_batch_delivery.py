#!/usr/bin/env python3
"""Package a completed multilingual blog batch with descriptive filenames."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    packaged: list[dict[str, str | int]] = []
    failures: list[str] = []

    for post in manifest["posts"]:
        key = str(post["key"])
        for language in manifest.get("languages", ["ko", "en", "es"]):
            config_path = args.config_dir / f"{key}.production.{language}.json"
            spec = ProductionSpec.load(config_path, check_files=False)
            job_dir = args.jobs_dir / spec.slug / language
            source = job_dir / spec.final_video_filename
            report_path = job_dir / "audit" / "final_report.json"
            snapshot_path = job_dir / "production.snapshot.json"
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                failures.append(f"{key} [{language}]: incomplete job ({error})")
                continue
            if not source.exists():
                failures.append(f"{key} [{language}]: missing final video")
                continue
            if str(report.get("overall_verdict", "")).upper() != "PASS":
                failures.append(
                    f"{key} [{language}]: final verdict is {report.get('overall_verdict')}"
                )
                continue
            if snapshot != spec.to_dict():
                failures.append(f"{key} [{language}]: production snapshot is stale")
                continue

            destination = args.output_dir / f"{key}_{language.upper()}.mp4"
            shutil.copy2(source, destination)
            packaged.append(
                {
                    "topic_key": key,
                    "language": language.upper(),
                    "source_url": str(post["url"]),
                    "file": str(destination.resolve()),
                    "bytes": destination.stat().st_size,
                    "sha256": sha256(destination),
                    "verdict": "PASS",
                }
            )
            print(f"PACKAGED {destination}")

    delivery = {
        "expected": len(manifest["posts"]) * len(manifest.get("languages", [])),
        "packaged": len(packaged),
        "failures": failures,
        "videos": packaged,
    }
    (args.output_dir / "delivery_manifest.json").write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures or len(packaged) != delivery["expected"]:
        raise SystemExit(
            f"Packaging incomplete: {len(packaged)}/{delivery['expected']} ready; "
            f"{len(failures)} failure(s)."
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
