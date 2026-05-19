from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Asset:
    scene_index: int
    kind: str
    path_or_url: str
    prompt: str | None = None
    source: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
