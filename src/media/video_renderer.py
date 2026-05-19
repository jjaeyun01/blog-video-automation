from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.models import Article, VideoScript


class DryRunVideoRenderer:
    def render(
        self,
        article: Article,
        script: VideoScript,
        voice_path: Path,
        subtitles_path: Path,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        manifest_path = output_dir / "render_manifest.json"
        final_path = output_dir / "final_video.placeholder.txt"

        manifest = {
            "renderer": "dry_run",
            "format": script.format,
            "article": article.to_dict(),
            "script": script.to_dict(),
            "voice_path": str(voice_path),
            "subtitles_path": str(subtitles_path),
            "final_video_path": str(final_path),
            "next_step": "Replace DryRunVideoRenderer with Remotion or FFmpeg renderer.",
        }

        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        final_path.write_text(
            "Dry-run placeholder. Use render_manifest.json to render MP4 with Remotion.\n",
            encoding="utf-8",
        )
        return manifest_path, final_path


class RemotionManifestRenderer:
    def __init__(self, remotion_dir: Path = Path("remotion")):
        self.remotion_dir = remotion_dir

    def render(
        self,
        article: Article,
        script: VideoScript,
        voice_path: Path,
        subtitles_path: Path,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        job_id = output_dir.name
        public_job_dir = self.remotion_dir / "public" / "jobs" / job_id
        public_job_dir.mkdir(parents=True, exist_ok=True)

        audio_static_path = None
        if voice_path.suffix.lower() == ".mp3" and voice_path.exists():
            audio_target = public_job_dir / "voice.mp3"
            shutil.copyfile(voice_path, audio_target)
            audio_static_path = f"jobs/{job_id}/voice.mp3"

        final_path = output_dir / "final_video.mp4"
        manifest = {
            "renderer": "remotion",
            "format": script.format,
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "article": article.to_dict(),
            "script": script.to_dict(),
            "audio_static_path": audio_static_path,
            "subtitles_path": str(subtitles_path),
            "final_video_path": str(final_path),
        }

        manifest_path = output_dir / "render_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        remotion_manifest_path = public_job_dir / "manifest.json"
        remotion_manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        command_path = output_dir / "render_command.txt"
        command_path.write_text(
            "\n".join(
                [
                    "cd /Users/jaeyoonlee/FeverCoach/remotion",
                    "npm install",
                    (
                        "npx remotion render src/Root.tsx BlogVideo "
                        f"../{final_path} "
                        f"--props public/jobs/{job_id}/manifest.json"
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return manifest_path, final_path
