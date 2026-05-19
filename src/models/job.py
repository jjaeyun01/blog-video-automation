from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class JobResult:
    job_id: str
    article_path: Path
    script_path: Path
    scenes_path: Path
    voice_path: Path
    subtitles_path: Path
    render_manifest_path: Path
    final_video_path: Path

    def to_dict(self) -> dict:
        return {key: str(value) for key, value in asdict(self).items()}
