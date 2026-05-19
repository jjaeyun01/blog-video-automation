from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class PostRef:
    id: str
    title: str
    url: str
    published_at: str | None = None
    thumbnail_url: str | None = None
    excerpt: str | None = None
    language: str = "ko"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Article:
    id: str
    url: str
    title: str
    raw_text: str
    cleaned_text: str = ""
    published_at: str | None = None
    thumbnail_url: str | None = None
    excerpt: str | None = None
    language: str = "ko"

    def to_dict(self) -> dict:
        return asdict(self)
