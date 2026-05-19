from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Scene:
    index: int
    duration_sec: float
    narration: str
    subtitle: str
    visual_prompt: str
    visual_type: str = "text_card"
    safety_note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
