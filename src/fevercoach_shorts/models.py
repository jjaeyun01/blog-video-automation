from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SceneSpec:
    index: int
    title: str
    mode: str
    timeline_seconds: int
    generation_seconds: int
    narration: str
    subtitle: str
    prompt: str
    negative_prompt: str
    image: Path | None = None
    visual_type: str = "general"
    medical_claim: str = ""
    asset_prompt: str = ""
    include_character: bool = False
    overlays: list[dict] = field(default_factory=list)
    caption_chunks: list[str] = field(default_factory=list)

    def to_dict(self, base_dir: Path | None = None) -> dict:
        data = asdict(self)
        if self.image:
            data["image"] = _display_path(self.image, base_dir)
        return data


@dataclass(frozen=True)
class ProductionSpec:
    slug: str
    title: str
    source: str
    character_image: Path
    scenes: list[SceneSpec]
    language: str = "ko"
    aspect_ratio: str = "9:16"
    resolution: str = "720p"
    fps: int = 30
    disclaimer: str = "이 영상은 일반적인 건강 정보이며 진단이나 처방을 대신하지 않습니다."
    schema_version: int = 1
    metadata: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path, check_files: bool = True) -> "ProductionSpec":
        source_path = path.resolve()
        data = json.loads(source_path.read_text(encoding="utf-8"))
        base_dir = source_path.parent
        character_image = _resolve_path(data["character_image"], base_dir)
        scenes: list[SceneSpec] = []
        for position, raw in enumerate(data.get("scenes", []), start=1):
            mode = str(raw.get("mode", "t2v")).lower()
            image_value = raw.get("image")
            image = _resolve_path(image_value, base_dir) if image_value else None
            asset_prompt = str(raw.get("asset_prompt", "")).strip()
            if mode == "i2v" and image is None and not asset_prompt:
                image = character_image
            narration = str(raw.get("narration", "")).strip()
            caption_chunks = [
                str(value).strip() for value in raw.get("caption_chunks", [])
                if str(value).strip()
            ]
            # Generated chunk boundaries are only timing hints. If a model ever
            # changes, omits, or adds a word, fall back to the full TTS script so
            # the visible caption can never disagree with the spoken narration.
            if _normalized_text(" ".join(caption_chunks)) != _normalized_text(narration):
                caption_chunks = _balanced_caption_chunks(narration)
            caption_chunks = _merge_caption_chunks(caption_chunks, max_chunks=3)
            scenes.append(
                SceneSpec(
                    index=int(raw.get("index", position)),
                    title=str(raw.get("title", f"Scene {position}")).strip(),
                    mode=mode,
                    timeline_seconds=int(raw.get("timeline_seconds", 8)),
                    generation_seconds=int(raw.get("generation_seconds", 8)),
                    narration=narration,
                    # Captions must match the spoken TTS script exactly. Keep accepting
                    # legacy subtitle fields, but do not allow them to diverge on load.
                    subtitle=narration,
                    prompt=str(raw.get("prompt", "")).strip(),
                    negative_prompt=str(raw.get("negative_prompt", "text, logo, watermark")).strip(),
                    image=image,
                    visual_type=str(raw.get("visual_type", "general")).strip(),
                    medical_claim=str(raw.get("medical_claim", "")).strip(),
                    asset_prompt=asset_prompt,
                    include_character=bool(raw.get("include_character", False)),
                    overlays=list(raw.get("overlays", [])),
                    caption_chunks=caption_chunks or [narration],
                )
            )
        spec = cls(
            slug=str(data["slug"]).strip(),
            title=str(data["title"]).strip(),
            source=str(data.get("source", "")).strip(),
            character_image=character_image,
            scenes=scenes,
            language=str(data.get("language", "ko")),
            aspect_ratio=str(data.get("aspect_ratio", "9:16")),
            resolution=str(data.get("resolution", "720p")),
            fps=int(data.get("fps", 30)),
            disclaimer=str(data.get("disclaimer", cls.disclaimer)),
            schema_version=int(data.get("schema_version", 1)),
            metadata=dict(data.get("metadata", {})),
        )
        spec.validate(check_files=check_files)
        return spec

    def validate(self, check_files: bool = True) -> None:
        errors: list[str] = []
        if not self.slug:
            errors.append("slug is required")
        if self.aspect_ratio != "9:16":
            errors.append("aspect_ratio must be 9:16")
        if not 6 <= len(self.scenes) <= 15:
            errors.append("between 6 and 15 scenes are required")
        if self.duration_seconds != 60:
            errors.append("scene timeline must total exactly 60 seconds")
        indexes = [scene.index for scene in self.scenes]
        if indexes != list(range(1, len(self.scenes) + 1)):
            errors.append("scene indexes must be consecutive from 1")
        for scene in self.scenes:
            if scene.mode not in {"t2v", "i2v"}:
                errors.append(f"scene {scene.index}: mode must be t2v or i2v")
            if scene.generation_seconds not in {4, 6, 8}:
                errors.append(f"scene {scene.index}: generation_seconds must be 4, 6, or 8")
            if not scene.narration or not scene.prompt:
                errors.append(f"scene {scene.index}: narration and prompt are required")
            if scene.mode == "i2v" and scene.image is None and not scene.asset_prompt:
                errors.append(f"scene {scene.index}: i2v requires an image or asset_prompt")
            if check_files and scene.mode == "i2v" and scene.image and not scene.image.exists():
                errors.append(f"scene {scene.index}: image not found: {scene.image}")
            for overlay in scene.overlays:
                if not isinstance(overlay, dict) or overlay.get("type") not in {
                    "label", "arrow", "dimension", "threshold", "cross"
                }:
                    errors.append(f"scene {scene.index}: invalid overlay type")
        if errors:
            raise ValueError("Invalid production spec:\n- " + "\n- ".join(errors))

    @property
    def duration_seconds(self) -> int:
        return sum(scene.timeline_seconds for scene in self.scenes)

    def to_dict(self, base_dir: Path | None = None) -> dict:
        return {
            "schema_version": self.schema_version,
            "slug": self.slug,
            "title": self.title,
            "source": self.source,
            "language": self.language,
            "character_image": _display_path(self.character_image, base_dir),
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "fps": self.fps,
            "disclaimer": self.disclaimer,
            "metadata": self.metadata,
            "scenes": [scene.to_dict(base_dir) for scene in self.scenes],
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(path.parent.resolve()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def _resolve_path(value: object, base_dir: Path) -> Path:
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def _display_path(path: Path, base_dir: Path | None) -> str:
    if base_dir:
        try:
            return str(path.resolve().relative_to(base_dir.resolve()))
        except ValueError:
            pass
    return str(path)


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _merge_caption_chunks(chunks: list[str], max_chunks: int) -> list[str]:
    merged = list(chunks)
    while len(merged) > max_chunks:
        index = min(
            range(len(merged) - 1),
            key=lambda position: len(merged[position]) + len(merged[position + 1]),
        )
        merged[index:index + 2] = [f"{merged[index]} {merged[index + 1]}".strip()]
    return merged


def _balanced_caption_chunks(narration: str) -> list[str]:
    words = narration.split()
    if len(words) <= 7:
        return [narration]
    count = 2 if len(words) <= 14 else 3
    chunks: list[str] = []
    start = 0
    for remaining_chunks in range(count, 0, -1):
        remaining_words = len(words) - start
        size = (remaining_words + remaining_chunks - 1) // remaining_chunks
        chunks.append(" ".join(words[start:start + size]))
        start += size
    return chunks
