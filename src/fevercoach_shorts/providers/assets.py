from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import replace
from pathlib import Path

from google import genai
from google.genai import types

from ..models import ProductionSpec


class SceneAssetGenerator:
    """Generate deterministic, resumable I2V reference images for planned scenes."""

    def __init__(self, api_key: str, model: str, client=None):
        self.client = client or genai.Client(api_key=api_key)
        self.model = model

    def generate(self, spec: ProductionSpec, visual_dir: Path) -> ProductionSpec:
        assets_dir = visual_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = assets_dir / "manifest.json"
        manifest = _read_json(manifest_path, {"model": self.model, "scenes": {}})
        scenes = []

        for scene in spec.scenes:
            if not scene.asset_prompt:
                scenes.append(scene)
                continue
            output_path = assets_dir / f"scene_{scene.index:02}.png"
            fingerprint = _fingerprint(scene.asset_prompt, spec.character_image, scene.include_character, self.model)
            entry = manifest.get("scenes", {}).get(str(scene.index), {})
            if entry.get("fingerprint") != fingerprint or not output_path.exists():
                contents: list[object] = [_asset_prompt(scene.asset_prompt)]
                if scene.include_character:
                    mime_type = mimetypes.guess_type(spec.character_image.name)[0] or "image/png"
                    contents.append(
                        types.Part.from_bytes(
                            data=spec.character_image.read_bytes(), mime_type=mime_type
                        )
                    )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio="9:16", image_size="1K"),
                    ),
                )
                image_part = next(
                    (
                        part.inline_data
                        for part in response.parts
                        if getattr(part, "inline_data", None)
                        and getattr(part.inline_data, "data", None)
                    ),
                    None,
                )
                if image_part is None:
                    raise RuntimeError(f"Image model returned no asset for scene {scene.index}.")
                output_path.write_bytes(image_part.data)
                manifest.setdefault("scenes", {})[str(scene.index)] = {
                    "fingerprint": fingerprint,
                    "path": str(output_path.resolve()),
                    "visual_type": scene.visual_type,
                }
                _write_json(manifest_path, manifest)
            scenes.append(replace(scene, mode="i2v", image=output_path.resolve()))
        return replace(spec, scenes=scenes)


def _asset_prompt(prompt: str) -> str:
    return f"""{prompt}

Global FeverCoach visual contract:
- Vertical 9:16, polished clean 3D pediatric medical education render.
- One explanatory subject only, centered in the safe area with generous negative space.
- Neutral gray, cream, and pale teal environment; red-orange only for medically relevant emphasis.
- Accurate anatomy and realistic object proportions, reassuring rather than frightening.
- No text, letters, numbers, units, labels, arrows, measurement marks, logos, or watermarks.
- No gore, no extra objects, no deformed anatomy or limbs.
"""


def _fingerprint(prompt: str, character_image: Path, include_character: bool, model: str) -> str:
    payload = {"prompt": prompt, "model": model, "include_character": include_character}
    if include_character:
        payload["character_sha256"] = hashlib.sha256(character_image.read_bytes()).hexdigest()
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
