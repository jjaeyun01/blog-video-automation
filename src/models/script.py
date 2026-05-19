from __future__ import annotations

from dataclasses import asdict, dataclass

from .scene import Scene


@dataclass
class VideoScript:
    article_id: str
    title: str
    format: str
    target_duration_sec: int
    hook: str
    narration: str
    outro: str
    disclaimer: str
    scenes: list[Scene]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["scenes"] = [scene.to_dict() for scene in self.scenes]
        return data
