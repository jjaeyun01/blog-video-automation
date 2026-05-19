from __future__ import annotations

import argparse
from pathlib import Path

from src.ai.safety_reviewer import SafetyReviewer
from src.ai.scene_generator import SceneGenerator
from src.ai.script_generator import OpenAiScriptGenerator, ScriptGenerator
from src.config.settings import Settings
from src.extractors.article_extractor import ArticleExtractor
from src.extractors.text_cleaner import TextCleaner
from src.extractors.wix_rss_discovery import WixRssDiscovery
from src.media.subtitle_generator import SubtitleGenerator
from src.media.tts_provider import DryRunTtsProvider, LocalSayTtsProvider, OpenAiTtsProvider
from src.media.video_renderer import (
    AnimatedFfmpegVideoRenderer,
    CharacterFfmpegVideoRenderer,
    DryRunVideoRenderer,
    FfmpegVideoRenderer,
    RemotionManifestRenderer,
    StoryFfmpegVideoRenderer,
)
from src.pipeline.orchestrator import BlogVideoPipeline
from src.pipeline.storage import Storage
from src.pipeline.time_tracker import TimeTracker


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate video assets from FeverCoach blog posts.")
    parser.add_argument("--source", default="https://www.fevercoach.us/ko/blog")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument(
        "--script-provider",
        choices=["rules", "openai"],
        default="rules",
        help="Use rules for offline generation or openai for LLM script writing.",
    )
    parser.add_argument(
        "--tts-provider",
        choices=["dry-run", "local", "openai"],
        default="local",
        help="Use dry-run text voiceover, local macOS say, or OpenAI TTS mp3 generation.",
    )
    parser.add_argument(
        "--renderer",
        choices=["dry-run", "ffmpeg", "animated", "character", "story", "remotion"],
        default="story",
        help="Use dry-run, basic FFmpeg, animated card, presenter, story animation, or prepare a Remotion manifest.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    time_tracker = TimeTracker()
    try:
        pipeline = build_pipeline(
            settings,
            time_tracker,
            script_provider=args.script_provider,
            tts_provider=args.tts_provider,
            renderer=args.renderer,
        )
    except ValueError as error:
        parser.error(str(error))

    if args.input_file:
        results = [pipeline.run_from_file(args.input_file)]
    else:
        results = pipeline.run_from_source(args.source, limit=args.limit)

    time_tracker.flush(settings.output_dir / "logs" / "time_report.csv")

    for result in results:
        print(f"Job: {result.job_id}")
        print(f"Script: {result.script_path}")
        print(f"Scenes: {result.scenes_path}")
        print(f"Subtitles: {result.subtitles_path}")
        print(f"Render manifest: {result.render_manifest_path}")
        print(f"Final video target: {result.final_video_path}")


def build_pipeline(
    settings: Settings,
    time_tracker: TimeTracker,
    script_provider: str = "rules",
    tts_provider: str = "dry-run",
    renderer: str = "dry-run",
) -> BlogVideoPipeline:
    script_generator = (
        OpenAiScriptGenerator(settings)
        if script_provider == "openai"
        else ScriptGenerator(settings)
    )
    if tts_provider == "openai":
        tts = OpenAiTtsProvider(settings)
    elif tts_provider == "local":
        tts = LocalSayTtsProvider()
    else:
        tts = DryRunTtsProvider()

    if renderer == "remotion":
        video_renderer = RemotionManifestRenderer()
    elif renderer == "story":
        video_renderer = StoryFfmpegVideoRenderer()
    elif renderer == "character":
        video_renderer = CharacterFfmpegVideoRenderer()
    elif renderer == "animated":
        video_renderer = AnimatedFfmpegVideoRenderer()
    elif renderer == "ffmpeg":
        video_renderer = FfmpegVideoRenderer()
    else:
        video_renderer = DryRunVideoRenderer()

    return BlogVideoPipeline(
        discovery=WixRssDiscovery(settings),
        extractor=ArticleExtractor(),
        cleaner=TextCleaner(),
        script_generator=script_generator,
        scene_generator=SceneGenerator(settings),
        tts_provider=tts,
        subtitle_generator=SubtitleGenerator(),
        renderer=video_renderer,
        storage=Storage(settings),
        time_tracker=time_tracker,
        safety_reviewer=SafetyReviewer(),
    )


if __name__ == "__main__":
    main()
