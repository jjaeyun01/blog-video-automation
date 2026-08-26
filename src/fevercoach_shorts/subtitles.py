from __future__ import annotations

from pathlib import Path

from .models import ProductionSpec


def write_srt(spec: ProductionSpec, output_path: Path) -> Path:
    current = 0.0
    blocks: list[str] = []
    for scene in spec.scenes:
        start = _timestamp(current)
        current += scene.timeline_seconds
        end = _timestamp(current)
        blocks.append(f"{scene.index}\n{start} --> {end}\n{scene.subtitle}\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(blocks), encoding="utf-8")
    return output_path


def _timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"
