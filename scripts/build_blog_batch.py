from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.pipeline import ShortsPipeline
from fevercoach_shorts.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a planned multilingual FeverCoach batch.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path)
    parser.add_argument("--tts-provider", choices=["gemini", "elevenlabs"], default="gemini")
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="1-based first manifest post to build (useful for resumable batch workers).",
    )
    parser.add_argument(
        "--end-index",
        type=int,
        help="1-based last manifest post to build, inclusive.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    languages = manifest.get("languages", ["ko", "en", "es"])
    all_posts = manifest["posts"]
    start = max(1, args.start_index)
    end = args.end_index if args.end_index is not None else len(all_posts)
    if end < start or start > len(all_posts):
        raise SystemExit(
            f"Invalid post range {start}..{end}; manifest contains {len(all_posts)} posts."
        )
    posts = all_posts[start - 1 : min(end, len(all_posts))]
    settings = Settings.from_env()
    if args.jobs_dir:
        settings = replace(settings, jobs_dir=args.jobs_dir)
    pipeline = ShortsPipeline(settings)
    failures: list[str] = []

    for post_index, post in enumerate(posts, start=start):
        for language in languages:
            config = args.config_dir / f"{post['key']}.production.{language}.json"
            completed = _completed_output(config, settings)
            if completed is not None:
                print(f"SKIP PASS {post['key']} [{language}]: {completed}", flush=True)
                continue
            print(
                f"BUILDING {post_index}/{len(all_posts)} {post['key']} [{language}]",
                flush=True,
            )
            try:
                output = pipeline.build(config, tts_provider=args.tts_provider)
                print(f"DONE {post['key']} [{language}]: {output}", flush=True)
            except Exception as error:  # preserve resumable work and continue the batch
                failures.append(f"{post['key']} [{language}]: {error}")
                print(f"FAILED {post['key']} [{language}]: {error}", flush=True)

    if failures:
        raise SystemExit("Batch build failures:\n- " + "\n- ".join(failures))


def _completed_output(config: Path, settings: Settings) -> Path | None:
    """Reuse only a final video that already has a persisted Gemini PASS report."""
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        # The pipeline persists ProductionSpec.to_dict(), which includes normalized
        # defaults. Compare the same canonical representation so formatting or
        # omitted optional defaults do not force an unnecessary rebuild.
        spec = ProductionSpec.load(config, check_files=False)
        canonical = spec.to_dict()
        job_dir = settings.jobs_dir / str(data["slug"]) / str(data["language"])
        output = job_dir / spec.final_video_filename
        report_path = job_dir / "audit" / "final_report.json"
        snapshot_path = job_dir / "production.snapshot.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if (
            output.exists()
            and snapshot == canonical
            and str(report.get("overall_verdict", "")).upper() == "PASS"
        ):
            return output
    except (KeyError, OSError, ValueError, json.JSONDecodeError):
        return None
    return None


if __name__ == "__main__":
    main()
