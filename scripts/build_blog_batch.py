from __future__ import annotations

import argparse
import json
from pathlib import Path

from fevercoach_shorts.pipeline import ShortsPipeline
from fevercoach_shorts.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a planned multilingual FeverCoach batch.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--tts-provider", choices=["gemini", "elevenlabs"], default="gemini")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    languages = manifest.get("languages", ["ko", "en", "es"])
    posts = manifest["posts"]
    pipeline = ShortsPipeline(Settings.from_env())
    failures: list[str] = []

    for post_index, post in enumerate(posts, start=1):
        for language in languages:
            config = args.config_dir / f"{post['key']}.production.{language}.json"
            print(
                f"BUILDING {post_index}/{len(posts)} {post['key']} [{language}]",
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


if __name__ == "__main__":
    main()
