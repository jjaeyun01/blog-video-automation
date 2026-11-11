from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path

from google import genai
from google.genai import types

from ..models import ProductionSpec


class CharacterReferenceGenerator:
    """Create and cache the anthropomorphic reference used by character scenes."""

    def __init__(self, api_key: str, model: str, client=None):
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=120_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self.model = model

    def generate(self, spec: ProductionSpec, visual_dir: Path) -> ProductionSpec:
        if spec.character_image is not None:
            if not spec.character_image.exists():
                raise ValueError(f"Character image not found: {spec.character_image}")
            return spec

        concept = spec.metadata.get("character_concept")
        if not isinstance(concept, dict):
            raise ValueError(
                "Automatic character generation requires metadata.character_concept."
            )
        subject = str(concept.get("subject", "")).strip()
        if not subject:
            raise ValueError("Automatic character concept requires a concrete subject.")

        prompt = _character_prompt(concept)
        character_dir = visual_dir / "character"
        character_dir.mkdir(parents=True, exist_ok=True)
        output_path = character_dir / "reference.png"
        manifest_path = character_dir / "manifest.json"
        fingerprint = hashlib.sha256(
            f"{self.model}\n{prompt}".encode("utf-8")
        ).hexdigest()
        manifest = _read_json(manifest_path, {})

        if manifest.get("fingerprint") != fingerprint or not output_path.exists():
            image_part = None
            for attempt in range(1, 4):
                try:
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=[prompt],
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                            image_config=types.ImageConfig(aspect_ratio="9:16", image_size="1K"),
                        ),
                    )
                except Exception:
                    if attempt < 3:
                        time.sleep(attempt * 2)
                        continue
                    raise
                image_part = next(
                    (
                        part.inline_data
                        for part in (getattr(response, "parts", None) or ())
                        if getattr(part, "inline_data", None)
                        and getattr(part.inline_data, "data", None)
                    ),
                    None,
                )
                if image_part is not None:
                    break
                if attempt < 3:
                    time.sleep(attempt * 2)
            if image_part is None:
                raise RuntimeError("Gemini returned no automatic character image after 3 attempts.")
            output_path.write_bytes(image_part.data)
            _write_json(
                manifest_path,
                {
                    "model": self.model,
                    "fingerprint": fingerprint,
                    "subject": subject,
                    "prompt": prompt,
                    "path": str(output_path.resolve()),
                },
            )

        return replace(spec, character_image=output_path.resolve())


def _character_prompt(concept: dict) -> str:
    subject = str(concept.get("subject", "")).strip()
    source_basis = str(concept.get("source_basis", "")).strip()
    visual_identity = str(concept.get("visual_identity", "")).strip()
    primary_color = str(concept.get("primary_color", "")).strip()
    surface_texture = str(concept.get("surface_texture", "")).strip()
    return f"""Create one reusable anthropomorphic 3D character based on this concrete subject:
Subject: {subject}
Why it represents the article: {source_basis}
Recognizable visual identity: {visual_identity}
Primary color: {primary_color}
Surface texture: {surface_texture}

Character direction:
- Transform the subject itself into one living character; do not place a separate mascot beside it.
- Preserve the subject's medically or visually identifying shape, color, texture, and details.
- Premium theatrical-quality stylized 3D animation, dimensional tactile materials, polished global illumination, cinematic rim light, detailed but readable silhouette.
- Extremely angry and unfairly accused expression, exceptionally large expressive eyes, tense raised eyebrows, and one wide-open shouting mouth.
- One compact body with exactly two small rounded arms and two short legs.
- Centered full-body front three-quarter view, vertical 9:16, generous clean safe space.
- Simple topic-relevant environment that does not compete with the character.
- Design a stable identity that can be reproduced consistently across later scenes.

Strict exclusions:
- no text, letters, Korean glyphs, numbers, units, subtitles, labels, signs, speech bubbles, logos, watermarks, UI, or typographic marks
- no extra characters, duplicate body, extra limbs, detached parts, malformed hands, collage, storyboard, split screen, or multiple poses
- no imitation of a named studio, franchise, copyrighted character, or living artist
"""


def _read_json(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
