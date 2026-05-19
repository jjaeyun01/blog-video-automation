from __future__ import annotations

import json
import math
import shutil
import subprocess
from textwrap import wrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


class FfmpegVideoRenderer:
    width = 1080
    height = 1920

    def render(
        self,
        article: Article,
        script: VideoScript,
        voice_path: Path,
        subtitles_path: Path,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "ffmpeg is required for --renderer ffmpeg. Install it with: brew install ffmpeg"
            )

        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        frame_paths = self._write_scene_frames(article, script, frames_dir)

        final_path = output_dir / "final_video.mp4"
        audio_duration = _probe_duration(voice_path) if voice_path.exists() else None
        scene_durations = self._scene_durations(script, audio_duration)
        segment_paths = self._render_segments(frame_paths, scene_durations, output_dir)
        silent_video_path = self._concat_segments(segment_paths, output_dir)
        self._mux_audio(silent_video_path, voice_path, final_path)

        manifest_path = output_dir / "render_manifest.json"
        manifest = {
            "renderer": "ffmpeg",
            "format": script.format,
            "width": self.width,
            "height": self.height,
            "article": article.to_dict(),
            "script": script.to_dict(),
            "voice_path": str(voice_path),
            "audio_duration_sec": audio_duration,
            "subtitles_path": str(subtitles_path),
            "frames_dir": str(frames_dir),
            "segments": [str(path) for path in segment_paths],
            "final_video_path": str(final_path),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return manifest_path, final_path

    def _render_segments(
        self,
        frame_paths: list[Path],
        scene_durations: list[float],
        output_dir: Path,
    ) -> list[Path]:
        segments_dir = output_dir / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        segment_paths: list[Path] = []
        for index, (frame_path, duration) in enumerate(zip(frame_paths, scene_durations), start=1):
            segment_path = segments_dir / f"segment_{index:02}.mp4"
            command = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(frame_path),
                "-vf",
                "format=yuv420p",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                str(segment_path),
            ]
            subprocess.run(command, check=True, capture_output=True)
            segment_paths.append(segment_path)
        return segment_paths

    def _concat_segments(self, segment_paths: list[Path], output_dir: Path) -> Path:
        concat_path = output_dir / "segments.txt"
        concat_path.write_text(
            "\n".join(f"file '{path.resolve()}'" for path in segment_paths) + "\n",
            encoding="utf-8",
        )
        silent_video_path = output_dir / "silent_video.mp4"
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            str(silent_video_path),
        ]
        subprocess.run(command, check=True, capture_output=True)
        return silent_video_path

    def _mux_audio(self, silent_video_path: Path, voice_path: Path, final_path: Path) -> None:
        command = ["ffmpeg", "-y", "-i", str(silent_video_path)]
        if voice_path.exists() and voice_path.suffix.lower() in {".aiff", ".aif", ".mp3", ".m4a", ".wav"}:
            command.extend(["-i", str(voice_path)])
            command.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest"])
        else:
            command.extend(["-c", "copy"])
        command.extend(["-movflags", "+faststart", str(final_path)])
        subprocess.run(command, check=True, capture_output=True)

    def _write_scene_frames(
        self,
        article: Article,
        script: VideoScript,
        frames_dir: Path,
    ) -> list[Path]:
        if not script.scenes:
            raise ValueError("Cannot render video without scenes.")

        paths: list[Path] = []
        for scene in script.scenes:
            image = self._draw_scene(article.title, scene.index, scene.subtitle, scene.narration, script.disclaimer)
            path = frames_dir / f"scene_{scene.index:02}.png"
            image.save(path)
            paths.append(path)
        return paths

    def _draw_scene(
        self,
        title: str,
        index: int,
        subtitle: str,
        narration: str,
        disclaimer: str,
    ) -> Image.Image:
        colors = {
            "ink": "#17202A",
            "muted": "#506170",
            "teal": "#0B8F8A",
            "mint": "#D9F4EF",
            "yellow": "#F7C948",
            "white": "#FFFFFF",
            "line": "#D7E6E1",
        }
        image = Image.new("RGB", (self.width, self.height), colors["white"])
        draw = ImageDraw.Draw(image)
        title_font = _font(58)
        subtitle_font = _font(50)
        body_font = _font(34)
        small_font = _font(26)
        logo_font = _font(34)

        draw.rounded_rectangle((64, 54, 118, 108), radius=14, fill=colors["teal"])
        draw.text((83, 58), "F", font=logo_font, fill=colors["white"])
        draw.text((136, 62), "FeverCoach", font=logo_font, fill=colors["teal"])

        card = (70, 170, 1010, 1748)
        draw.rounded_rectangle(card, radius=32, fill=colors["mint"], outline=colors["line"], width=3)
        draw.rounded_rectangle((128, 234, 322, 292), radius=28, fill=colors["yellow"])
        draw.text((150, 246), "부모 건강 정보", font=small_font, fill=colors["ink"])

        y = 330
        clean_title = title.replace("Q:", "").strip()
        y = _draw_wrapped(draw, clean_title, (128, y), title_font, colors["ink"], max_chars=17, line_gap=14)
        draw.rounded_rectangle((128, y + 28, 224, y + 36), radius=4, fill=colors["teal"])
        y += 76
        y = _draw_wrapped(draw, subtitle, (128, y), subtitle_font, colors["teal"], max_chars=18, line_gap=16)
        y += 28
        _draw_wrapped(draw, narration, (128, y), body_font, colors["muted"], max_chars=25, line_gap=14, max_lines=12)

        draw.text((874, 1660), f"{index:02}", font=_font(48), fill=colors["line"])
        draw.line((64, 1808, 1016, 1808), fill=colors["line"], width=2)
        _draw_wrapped(draw, disclaimer, (64, 1832), small_font, colors["muted"], max_chars=42, line_gap=8, max_lines=2)
        return image

    def _scene_durations(
        self,
        script: VideoScript,
        audio_duration: float | None,
    ) -> list[float]:
        scenes = script.scenes
        scene_durations = [max(1.0, scene.duration_sec) for scene in scenes]
        if audio_duration and audio_duration > sum(scene_durations):
            per_scene = audio_duration / len(scenes)
            scene_durations = [per_scene for _ in scenes]
        return scene_durations


class AnimatedFfmpegVideoRenderer(FfmpegVideoRenderer):
    def _render_segments(
        self,
        frame_paths: list[Path],
        scene_durations: list[float],
        output_dir: Path,
    ) -> list[Path]:
        segments_dir = output_dir / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        segment_paths: list[Path] = []
        for index, (frame_path, duration) in enumerate(zip(frame_paths, scene_durations), start=1):
            segment_path = segments_dir / f"animated_segment_{index:02}.mp4"
            frames = max(1, int(duration * 30))
            zoom_direction = "+0.00028" if index % 2 else "-0.00022"
            zoom_expr = (
                "min(zoom+0.00028,1.035)"
                if zoom_direction.startswith("+")
                else "max(1.035-on*0.00022,1.0)"
            )
            fade_out_start = max(0.1, duration - 0.35)
            filter_chain = (
                f"scale={self.width}:{self.height},"
                f"zoompan=z='{zoom_expr}':"
                "x='iw/2-(iw/zoom/2)':"
                "y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={self.width}x{self.height}:fps=30,"
                "fade=t=in:st=0:d=0.35,"
                f"fade=t=out:st={fade_out_start:.2f}:d=0.35,"
                "format=yuv420p"
            )
            command = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(frame_path),
                "-vf",
                filter_chain,
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                str(segment_path),
            ]
            subprocess.run(command, check=True, capture_output=True)
            segment_paths.append(segment_path)
        return segment_paths

    def _draw_scene(
        self,
        title: str,
        index: int,
        subtitle: str,
        narration: str,
        disclaimer: str,
    ) -> Image.Image:
        palettes = [
            {"bg": "#FFF7E8", "card": "#FFFFFF", "accent": "#FF6B6B", "accent2": "#4ECDC4", "ink": "#17202A"},
            {"bg": "#EAF7FF", "card": "#FFFFFF", "accent": "#118AB2", "accent2": "#FFD166", "ink": "#17202A"},
            {"bg": "#F2F0FF", "card": "#FFFFFF", "accent": "#7C3AED", "accent2": "#06D6A0", "ink": "#17202A"},
            {"bg": "#ECFFF3", "card": "#FFFFFF", "accent": "#0B8F8A", "accent2": "#F7C948", "ink": "#17202A"},
        ]
        palette = palettes[(index - 1) % len(palettes)]
        muted = "#506170"
        image = Image.new("RGB", (self.width, self.height), palette["bg"])
        draw = ImageDraw.Draw(image)

        title_font = _font(58)
        subtitle_font = _font(46)
        body_font = _font(34)
        small_font = _font(27)
        logo_font = _font(36)
        number_font = _font(96)

        _draw_blob(draw, (780, 80), 300, palette["accent2"], 0.55)
        _draw_blob(draw, (-120, 1260), 360, palette["accent"], 0.35)
        _draw_sparkles(draw, index, palette["accent"], palette["accent2"])

        draw.rounded_rectangle((64, 54, 126, 116), radius=18, fill=palette["accent"])
        draw.text((85, 60), "F", font=logo_font, fill="#FFFFFF")
        draw.text((148, 68), "FeverCoach", font=logo_font, fill=palette["ink"])

        draw.rounded_rectangle((760, 214, 948, 402), radius=94, fill=palette["accent2"])
        _draw_face(draw, (854, 308), 82, palette["ink"])
        draw.rounded_rectangle((760, 420, 948, 470), radius=25, fill="#FFFFFF")
        draw.text((804, 426), "CHECK", font=small_font, fill=palette["accent"])

        card = (68, 210, 1012, 1766)
        shadow = (82, 226, 1026, 1782)
        image = _tint_shadow(image, shadow, opacity=22)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(card, radius=46, fill=palette["card"], outline="#E6EEF0", width=4)

        draw.rounded_rectangle((126, 278, 352, 342), radius=32, fill=palette["accent2"])
        draw.text((152, 292), "오늘의 포인트", font=small_font, fill=palette["ink"])

        draw.text((760, 278), f"{index:02}", font=number_font, fill="#EEF2F4")

        y = 392
        clean_title = title.replace("Q:", "").strip()
        y = _draw_wrapped(draw, clean_title, (126, y), title_font, palette["ink"], max_chars=16, line_gap=14, max_lines=3)
        draw.rounded_rectangle((126, y + 18, 266, y + 30), radius=6, fill=palette["accent"])
        y += 72

        draw.rounded_rectangle((126, y, 950, y + 246), radius=34, fill="#F6FAFB")
        _draw_wrapped(draw, subtitle, (164, y + 34), subtitle_font, palette["accent"], max_chars=19, line_gap=14, max_lines=3)
        y += 286

        _draw_wrapped(draw, narration, (126, y), body_font, muted, max_chars=25, line_gap=14, max_lines=10)

        progress_left = 126
        progress_top = 1654
        for dot in range(7):
            fill = palette["accent"] if dot < index else "#DDE7EA"
            draw.ellipse(
                (
                    progress_left + dot * 48,
                    progress_top,
                    progress_left + dot * 48 + 22,
                    progress_top + 22,
                ),
                fill=fill,
            )
        draw.line((64, 1810, 1016, 1810), fill="#DCE8EA", width=2)
        _draw_wrapped(draw, disclaimer, (64, 1834), small_font, muted, max_chars=42, line_gap=8, max_lines=2)
        return image


class CharacterFfmpegVideoRenderer(FfmpegVideoRenderer):
    animation_fps = 10

    def render(
        self,
        article: Article,
        script: VideoScript,
        voice_path: Path,
        subtitles_path: Path,
        output_dir: Path,
    ) -> tuple[Path, Path]:
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "ffmpeg is required for --renderer character. Install it with: brew install ffmpeg"
            )

        final_path = output_dir / "final_video.mp4"
        audio_duration = _probe_duration(voice_path) if voice_path.exists() else None
        scene_durations = self._scene_durations(script, audio_duration)
        segment_paths = self._render_character_segments(article, script, scene_durations, output_dir)
        silent_video_path = self._concat_segments(segment_paths, output_dir)
        self._mux_audio(silent_video_path, voice_path, final_path)

        manifest_path = output_dir / "render_manifest.json"
        manifest = {
            "renderer": "character_ffmpeg",
            "format": script.format,
            "width": self.width,
            "height": self.height,
            "animation_fps": self.animation_fps,
            "article": article.to_dict(),
            "script": script.to_dict(),
            "voice_path": str(voice_path),
            "audio_duration_sec": audio_duration,
            "subtitles_path": str(subtitles_path),
            "segments": [str(path) for path in segment_paths],
            "final_video_path": str(final_path),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path, final_path

    def _render_character_segments(
        self,
        article: Article,
        script: VideoScript,
        scene_durations: list[float],
        output_dir: Path,
    ) -> list[Path]:
        segments_dir = output_dir / "segments"
        frames_root = output_dir / "character_frames"
        segments_dir.mkdir(parents=True, exist_ok=True)
        frames_root.mkdir(parents=True, exist_ok=True)

        segment_paths: list[Path] = []
        for scene, duration in zip(script.scenes, scene_durations):
            scene_frame_dir = frames_root / f"scene_{scene.index:02}"
            scene_frame_dir.mkdir(parents=True, exist_ok=True)
            frame_count = max(2, int(duration * self.animation_fps))
            for frame in range(frame_count):
                progress = frame / max(1, frame_count - 1)
                image = self._draw_character_frame(
                    article.title,
                    scene.index,
                    scene.subtitle,
                    scene.narration,
                    script.disclaimer,
                    progress,
                    frame,
                )
                image.save(scene_frame_dir / f"frame_{frame:04}.png")

            segment_path = segments_dir / f"character_segment_{scene.index:02}.mp4"
            command = [
                "ffmpeg",
                "-y",
                "-framerate",
                str(self.animation_fps),
                "-i",
                str(scene_frame_dir / "frame_%04d.png"),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                str(segment_path),
            ]
            subprocess.run(command, check=True, capture_output=True)
            segment_paths.append(segment_path)
        return segment_paths

    def _draw_character_frame(
        self,
        title: str,
        index: int,
        subtitle: str,
        narration: str,
        disclaimer: str,
        progress: float,
        frame: int,
    ) -> Image.Image:
        palettes = [
            {"bg": "#FFF3E6", "accent": "#FF6B6B", "accent2": "#4ECDC4", "shirt": "#118AB2"},
            {"bg": "#EAF7FF", "accent": "#118AB2", "accent2": "#FFD166", "shirt": "#7C3AED"},
            {"bg": "#F3F0FF", "accent": "#7C3AED", "accent2": "#06D6A0", "shirt": "#0B8F8A"},
            {"bg": "#ECFFF3", "accent": "#0B8F8A", "accent2": "#F7C948", "shirt": "#FF6B6B"},
        ]
        palette = palettes[(index - 1) % len(palettes)]
        ink = "#17202A"
        muted = "#506170"
        image = Image.new("RGB", (self.width, self.height), palette["bg"])
        draw = ImageDraw.Draw(image)

        logo_font = _font(36)
        title_font = _font(50)
        bubble_font = _font(44)
        body_font = _font(30)
        small_font = _font(25)

        pulse = math.sin(frame * 0.55)
        bob = int(math.sin(frame * 0.42) * 10)
        arm_wave = math.sin(frame * 0.7)
        mouth_open = frame % 8 in {1, 2, 3, 6}

        _draw_blob(draw, (780, 76), 270, palette["accent2"])
        _draw_blob(draw, (-110, 1270), 330, palette["accent"])
        _draw_sparkles(draw, index + frame // 8, palette["accent"], palette["accent2"])

        draw.rounded_rectangle((56, 50, 122, 116), radius=18, fill=palette["accent"])
        draw.text((80, 57), "F", font=logo_font, fill="#FFFFFF")
        draw.text((146, 68), "FeverCoach", font=logo_font, fill=ink)

        draw.rounded_rectangle((760, 64, 1006, 126), radius=31, fill="#FFFFFF")
        draw.text((798, 80), f"Scene {index:02}", font=small_font, fill=palette["accent"])

        title_box = (70, 170, 1010, 430)
        draw.rounded_rectangle(title_box, radius=34, fill="#FFFFFF", outline="#E6EEF0", width=3)
        clean_title = title.replace("Q:", "").strip()
        _draw_wrapped(draw, clean_title, (112, 214), title_font, ink, max_chars=18, line_gap=12, max_lines=3)

        bubble = (92, 500, 988, 965)
        draw.rounded_rectangle((bubble[0] + 12, bubble[1] + 16, bubble[2] + 12, bubble[3] + 16), radius=42, fill="#000000")
        image = _tint_shadow(image, (bubble[0] + 12, bubble[1] + 16, bubble[2] + 12, bubble[3] + 16), opacity=20)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(bubble, radius=42, fill="#FFFFFF", outline="#E6EEF0", width=3)
        draw.polygon([(290, 965), (360, 965), (326, 1026)], fill="#FFFFFF", outline="#E6EEF0")

        typed_chars = max(18, int(len(subtitle) * min(1.0, progress * 2.4)))
        visible_subtitle = subtitle[:typed_chars]
        if typed_chars < len(subtitle):
            visible_subtitle = visible_subtitle.rstrip() + "..."
        draw.rounded_rectangle((132, 536, 384, 598), radius=31, fill=palette["accent2"])
        draw.text((162, 550), "핵심만 쉽게", font=small_font, fill=ink)
        _draw_wrapped(draw, visible_subtitle, (132, 638), bubble_font, palette["accent"], max_chars=20, line_gap=14, max_lines=4)

        caption_box = (92, 1028, 658, 1238)
        draw.rounded_rectangle(caption_box, radius=30, fill="#F7FBFC")
        _draw_wrapped(draw, narration, (130, 1060), body_font, muted, max_chars=19, line_gap=10, max_lines=4)

        _draw_presenter(draw, center=(765, 1290 + bob), palette=palette, ink=ink, arm_wave=arm_wave, mouth_open=mouth_open)

        meter_width = int(760 * progress)
        draw.rounded_rectangle((160, 1772, 920, 1792), radius=10, fill="#DDE7EA")
        draw.rounded_rectangle((160, 1772, 160 + meter_width, 1792), radius=10, fill=palette["accent"])
        draw.line((64, 1810, 1016, 1810), fill="#DCE8EA", width=2)
        _draw_wrapped(draw, disclaimer, (64, 1834), small_font, muted, max_chars=42, line_gap=8, max_lines=2)

        if frame % 16 < 8:
            draw.ellipse((884, 468, 904, 488), fill=palette["accent"])
            draw.ellipse((916, 446, 930, 460), fill=palette["accent2"])
        return image


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _draw_blob(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    size: int,
    fill: str,
    opacity: float = 1.0,
) -> None:
    del opacity
    x, y = xy
    draw.ellipse((x, y, x + size, y + size), fill=fill)


def _draw_sparkles(
    draw: ImageDraw.ImageDraw,
    seed: int,
    color_a: str,
    color_b: str,
) -> None:
    points = [
        (110, 180), (938, 160), (934, 728), (96, 920),
        (880, 1210), (160, 1500), (980, 1540), (520, 118),
    ]
    for index, (x, y) in enumerate(points):
        color = color_a if (index + seed) % 2 else color_b
        radius = 10 + ((index + seed) % 4) * 5
        if index % 3 == 0:
            draw.rounded_rectangle((x, y, x + radius * 4, y + radius), radius=radius // 2, fill=color)
        elif index % 3 == 1:
            draw.ellipse((x, y, x + radius * 2, y + radius * 2), fill=color)
        else:
            draw.polygon(
                [
                    (x + radius, y),
                    (x + radius * 1.35, y + radius * 0.65),
                    (x + radius * 2, y + radius),
                    (x + radius * 1.35, y + radius * 1.35),
                    (x + radius, y + radius * 2),
                    (x + radius * 0.65, y + radius * 1.35),
                    (x, y + radius),
                    (x + radius * 0.65, y + radius * 0.65),
                ],
                fill=color,
            )


def _draw_face(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    ink: str,
) -> None:
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill="#FFE4C7", outline=ink, width=4)
    draw.ellipse((cx - 34, cy - 18, cx - 20, cy - 4), fill=ink)
    draw.ellipse((cx + 20, cy - 18, cx + 34, cy - 4), fill=ink)
    draw.arc((cx - 34, cy - 4, cx + 34, cy + 48), start=18, end=162, fill=ink, width=5)
    draw.arc((cx - 70, cy - 82, cx + 70, cy - 18), start=205, end=335, fill=ink, width=5)


def _draw_presenter(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    palette: dict[str, str],
    ink: str,
    arm_wave: float,
    mouth_open: bool,
) -> None:
    cx, cy = center
    skin = "#FFE0BD"
    hair = "#3A2A22"
    pants = "#2B3A67"
    shirt = palette["shirt"]
    accent = palette["accent"]

    draw.ellipse((cx - 180, cy + 260, cx + 180, cy + 300), fill="#D8E1E5")

    draw.rounded_rectangle((cx - 92, cy + 52, cx + 92, cy + 280), radius=42, fill=shirt, outline=ink, width=5)
    draw.rounded_rectangle((cx - 72, cy + 278, cx - 20, cy + 448), radius=24, fill=pants, outline=ink, width=4)
    draw.rounded_rectangle((cx + 20, cy + 278, cx + 72, cy + 448), radius=24, fill=pants, outline=ink, width=4)
    draw.rounded_rectangle((cx - 94, cy + 432, cx - 12, cy + 468), radius=18, fill=ink)
    draw.rounded_rectangle((cx + 12, cy + 432, cx + 94, cy + 468), radius=18, fill=ink)

    left_hand = (cx - 170, cy + 128 + int(arm_wave * 26))
    right_hand = (cx + 170, cy + 92 - int(arm_wave * 42))
    draw.line((cx - 82, cy + 96, left_hand[0], left_hand[1]), fill=ink, width=20)
    draw.line((cx + 82, cy + 96, right_hand[0], right_hand[1]), fill=ink, width=20)
    draw.ellipse((left_hand[0] - 26, left_hand[1] - 26, left_hand[0] + 26, left_hand[1] + 26), fill=skin, outline=ink, width=4)
    draw.ellipse((right_hand[0] - 28, right_hand[1] - 28, right_hand[0] + 28, right_hand[1] + 28), fill=skin, outline=ink, width=4)
    draw.line((right_hand[0] + 34, right_hand[1] - 28, right_hand[0] + 74, right_hand[1] - 56), fill=accent, width=8)
    draw.line((right_hand[0] + 42, right_hand[1] + 0, right_hand[0] + 92, right_hand[1] - 4), fill=accent, width=8)

    draw.ellipse((cx - 104, cy - 172, cx + 104, cy + 36), fill=skin, outline=ink, width=5)
    draw.pieslice((cx - 116, cy - 198, cx + 116, cy - 36), start=188, end=352, fill=hair)
    draw.ellipse((cx - 50, cy - 78, cx - 30, cy - 56), fill=ink)
    draw.ellipse((cx + 30, cy - 78, cx + 50, cy - 56), fill=ink)
    draw.arc((cx - 62, cy - 104, cx - 18, cy - 66), start=205, end=335, fill=ink, width=5)
    draw.arc((cx + 18, cy - 104, cx + 62, cy - 66), start=205, end=335, fill=ink, width=5)
    if mouth_open:
        draw.ellipse((cx - 28, cy - 28, cx + 28, cy + 16), fill=ink)
        draw.ellipse((cx - 16, cy - 8, cx + 16, cy + 16), fill="#FF8FA3")
    else:
        draw.arc((cx - 34, cy - 36, cx + 34, cy + 18), start=25, end=155, fill=ink, width=6)
    draw.rounded_rectangle((cx - 54, cy + 74, cx + 54, cy + 106), radius=16, fill="#FFFFFF")
    draw.text((cx - 34, cy + 76), "Dr", font=_font(24), fill=accent)


def _tint_shadow(
    image: Image.Image,
    box: tuple[int, int, int, int],
    opacity: int,
) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(box, radius=46, fill=(0, 0, 0, opacity))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _probe_duration(path: Path) -> float | None:
    if not path.exists() or not shutil.which("ffprobe"):
        return None
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: str,
    max_chars: int,
    line_gap: int,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    lines = wrap(text, width=max_chars)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip("., ") + "..."
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += bbox[3] - bbox[1] + line_gap
    return y
