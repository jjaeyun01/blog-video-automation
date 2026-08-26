from __future__ import annotations

import argparse
import json
from pathlib import Path

from .article import load_article
from .pipeline import ShortsPipeline, read_status
from .planner import ScenePlanner
from .settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fevercoach-shorts",
        description="Turn a weekly pediatric health article and character image into a 60-second Short.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser(
        "plan", help="Create a reviewable ten-scene multilingual medical production plan."
    )
    source = plan_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--article-file", type=Path)
    plan_parser.add_argument("--character-image", type=Path, required=True)
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument(
        "--languages", nargs="+", choices=["ko", "es", "en"],
        default=["ko", "es", "en"],
        help="Localized versions to create (default: ko es en).",
    )

    build_parser = subparsers.add_parser("build", help="Generate clips, narration, subtitles, and final MP4.")
    build_parser.add_argument("--config", type=Path, nargs="+", required=True)
    build_parser.add_argument("--tts-provider", choices=["gemini", "elevenlabs"], default="gemini")
    build_parser.add_argument("--plan-only", action="store_true")
    build_parser.add_argument("--clips-only", action="store_true")

    status_parser = subparsers.add_parser("status", help="Print persisted Veo operation status.")
    status_parser.add_argument("--config", type=Path, required=True)

    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "plan":
            article = load_article(url=args.url, file_path=args.article_file)
            results = ScenePlanner(settings).create_multilingual(
                article, args.character_image, args.output, tuple(args.languages)
            )
            for language, (path, spec) in results.items():
                print(f"Created [{language}]: {path}")
                print(f"Scenes: {len(spec.scenes)}, duration: {spec.duration_seconds}s")
            return
        if args.command == "status":
            print(json.dumps(read_status(args.config, settings), ensure_ascii=False, indent=2))
            return
        for config in args.config:
            output = ShortsPipeline(settings).build(
                config,
                tts_provider=args.tts_provider,
                plan_only=args.plan_only,
                clips_only=args.clips_only,
            )
            print(f"Output [{config}]: {output}")
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
