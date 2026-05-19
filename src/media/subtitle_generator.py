from __future__ import annotations

from pathlib import Path

from src.models import VideoScript


class SubtitleGenerator:
    def generate(self, script: VideoScript, output_dir: Path) -> Path:
        path = output_dir / "subtitles.srt"
        current = 0.0
        blocks: list[str] = []

        for scene in script.scenes:
            start = _srt_time(current)
            current += scene.duration_sec
            end = _srt_time(current)
            blocks.append(f"{scene.index}\n{start} --> {end}\n{scene.subtitle}\n")

        path.write_text("\n".join(blocks), encoding="utf-8")
        return path


def _srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"
