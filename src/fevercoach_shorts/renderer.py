from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .captions import render_caption_chunk_images
from .models import ProductionSpec


_RENDER_VERSION = 4


class ShortsRenderer:
    width = 1080
    height = 1920

    def render(
        self,
        spec: ProductionSpec,
        clips: list[Path],
        narration: Path,
        subtitles: Path,
        job_dir: Path,
    ) -> Path:
        _require_ffmpeg()
        if len(clips) != len(spec.scenes):
            raise ValueError("One generated clip is required for every scene.")
        manifest_path = job_dir / "render_manifest.json"
        previous_manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.exists()
            else {}
        )
        force_dubbed_render = previous_manifest.get("render_version") != _RENDER_VERSION
        normalized_dir = job_dir / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        caption_paths = render_caption_chunk_images(
            spec, job_dir / "caption_images", width=self.width, height=self.height
        )
        normalized: list[Path] = []

        for scene, clip, captions in zip(spec.scenes, clips, caption_paths):
            source_duration = _probe_duration(clip)
            speed_ratio = scene.timeline_seconds / source_duration
            target = normalized_dir / f"scene_{scene.index:02}.mp4"
            video_filter = (
                f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height},setpts={speed_ratio:.8f}*PTS,"
                f"fps={spec.fps},format=rgba[base];"
            )
            caption_timings = _caption_timings(
                scene.caption_chunks or [scene.narration], scene.timeline_seconds
            )
            previous = "base"
            for chunk_index, (start, end) in enumerate(caption_timings):
                output = "out" if chunk_index == len(captions) - 1 else f"caption{chunk_index}"
                video_filter += (
                    f"[{previous}][{chunk_index + 1}:v]overlay=0:0:format=auto:"
                    f"enable='between(t,{start:.3f},{end:.3f})'[{output}];"
                )
                previous = output
            video_filter += "[out]format=yuv420p[final]"
            if not _is_current(target, [clip, *captions], scene.timeline_seconds):
                command = ["ffmpeg", "-y", "-xerror", "-i", str(clip)]
                for caption in captions:
                    command.extend(["-i", str(caption)])
                command.extend(
                    [
                        "-filter_complex", video_filter, "-map", "[final]", "-an",
                        "-t", str(scene.timeline_seconds), "-c:v", "libx264", "-crf", "18",
                        "-preset", "veryfast", "-movflags", "+faststart",
                    ]
                )
                _run_to_target(
                    command,
                    target,
                )
            normalized.append(target)

        dubbed_dir = job_dir / "dubbed_clips"
        dubbed_dir.mkdir(parents=True, exist_ok=True)
        dubbed: list[Path] = []
        for scene, normalized_clip in zip(spec.scenes, normalized):
            voice = job_dir / "audio" / "aligned" / f"scene_{scene.index:02}.mp3"
            if not voice.exists():
                raise RuntimeError(f"Aligned scene narration is missing: {voice}")
            target = dubbed_dir / f"scene_{scene.index:02}.mp4"
            if not force_dubbed_render and _is_current(
                target,
                [normalized_clip, voice],
                scene.timeline_seconds,
                require_audio=True,
            ):
                dubbed.append(target)
                continue
            command = [
                "ffmpeg", "-y", "-xerror", "-i", str(normalized_clip), "-i", str(voice),
                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                "-b:a", "192k", "-t", str(scene.timeline_seconds),
                "-movflags", "+faststart",
            ]
            _run_to_target(command, target, require_audio=True)
            dubbed.append(target)

        concat_path = job_dir / "video_concat.txt"
        concat_path.write_text(
            "\n".join(f"file '{path.resolve()}'" for path in normalized) + "\n",
            encoding="utf-8",
        )
        silent_path = job_dir / "silent.mp4"
        _run_to_target(
            ["ffmpeg", "-y", "-xerror", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy"],
            silent_path,
        )

        output_path = job_dir / "final_shorts.mp4"
        dubbed_concat_path = job_dir / "dubbed_concat.txt"
        dubbed_concat_path.write_text(
            "\n".join(f"file '{path.resolve()}'" for path in dubbed) + "\n",
            encoding="utf-8",
        )
        _run_to_target(
            [
                "ffmpeg", "-y", "-xerror", "-fflags", "+genpts",
                "-f", "concat", "-safe", "0", "-i", str(dubbed_concat_path),
                "-map", "0:v", "-map", "0:a", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-af", "aresample=async=1:first_pts=0",
                "-t", str(spec.duration_seconds), "-movflags", "+faststart",
            ],
            output_path,
            require_audio=True,
        )
        manifest = {
            "render_version": _RENDER_VERSION,
            "width": self.width,
            "height": self.height,
            "fps": spec.fps,
            "duration_seconds": spec.duration_seconds,
            "clips": [str(path.resolve()) for path in clips],
            "dubbed_clips": [str(path.resolve()) for path in dubbed],
            "narration": str(narration.resolve()),
            "subtitles": str(subtitles.resolve()),
            "output": str(output_path.resolve()),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return output_path


def _caption_timings(chunks: list[str], duration: float) -> list[tuple[float, float]]:
    """Allocate caption time by spoken-text length while covering the whole scene."""
    weights = [max(1, len("".join(chunk.split()))) for chunk in chunks]
    total_weight = sum(weights)
    boundaries = [0.0]
    elapsed_weight = 0
    for weight in weights[:-1]:
        elapsed_weight += weight
        boundaries.append(duration * elapsed_weight / total_weight)
    boundaries.append(duration)
    return list(zip(boundaries, boundaries[1:]))


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or result.stderr.strip():
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr[-500:]}")
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise RuntimeError(f"Clip has invalid duration: {path}")
    return duration


def _has_audio(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _is_current(
    target: Path,
    inputs: list[Path],
    duration: float,
    require_audio: bool = False,
) -> bool:
    if not target.exists() or any(not path.exists() for path in inputs):
        return False
    if target.stat().st_mtime_ns < max(path.stat().st_mtime_ns for path in inputs):
        return False
    try:
        _validate_media(target, require_audio=require_audio)
        return abs(_probe_duration(target) - duration) < 0.08
    except (RuntimeError, ValueError):
        return False


def _require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg and ffprobe are required. Install them with: brew install ffmpeg")


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-1200:]}")


def _run_to_target(
    command: list[str], target: Path, require_audio: bool = False
) -> None:
    temporary = target.with_name(f"{target.stem}.tmp{target.suffix}")
    try:
        _run([*command, str(temporary)])
        _validate_media(temporary, require_audio=require_audio)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _validate_media(path: Path, require_audio: bool = False) -> None:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or result.stderr.strip() or "video" not in result.stdout:
        raise RuntimeError(f"Rendered file has no valid video stream: {path}")
    if require_audio and not _has_audio(path):
        raise RuntimeError(f"Rendered file has no audio stream: {path}")
