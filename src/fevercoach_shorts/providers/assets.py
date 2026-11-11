from __future__ import annotations

import hashlib
import json
import mimetypes
import time
from dataclasses import replace
from pathlib import Path

from google import genai
from google.genai import types

from ..models import ProductionSpec
from ..review_rules import JAEYOON_VISUAL_SAFETY_RULES


class SceneAssetGenerator:
    """Generate deterministic, resumable I2V reference images for planned scenes."""

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
            fingerprint = _fingerprint(
                _asset_prompt(scene.asset_prompt),
                spec.character_image,
                scene.include_character,
                self.model,
            )
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
                image_part = None
                for attempt in range(1, 4):
                    attempt_contents = list(contents)
                    if attempt > 1:
                        attempt_contents[0] = (
                            f"{contents[0]}\n\nSafety correction for this retry: every minor must be "
                            "fully covered in age-appropriate opaque clothing or pajamas. "
                            "Do not show a bare torso, chest, abdomen, underwear, bathing, or "
                            "any sensitive framing. Keep the scene reassuring and clinical."
                        )
                    try:
                        response = self.client.models.generate_content(
                            model=self.model,
                            contents=attempt_contents,
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
                    raise RuntimeError(
                        f"Image model returned no asset for scene {scene.index} after 3 safe retries."
                    )
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
{JAEYOON_VISUAL_SAFETY_RULES}
- Vertical 9:16 polished semi-stylized 3D pediatric medical visualization, halfway between clean
  modeled illustration and restrained photorealism.
- One dominant explanatory subject with intentional foreground, midground, and background depth.
- Use a camera-ready start frame with directional composition and one clear focal target rather than
  a flat centered catalog pose.
- Tactile modeled detail, smooth shading, soft contact shadows, subtle ambient occlusion, cinematic
  depth, clean daylight, rich color, and no desaturated gray wash.
- Cream, pale teal, clean blue, natural anatomical pink, and warm amber palette. Pure saturated red is
  reserved for code-rendered overlays and must not appear, except as an existing locked character color.
- Accurate anatomy and realistic object proportions, reassuring rather than frightening.
- Every infant and child is fully covered in age-appropriate opaque clothing or pajamas; never show
  a bare torso, chest, abdomen, underwear, bathing, or sensitive framing.
- Keep the planned overlay safe zone visually quiet and free of important anatomy or objects.
- Strict medication-route rule: never place any syringe in or near a mouth, including a needleless
  oral dosing syringe. Depict oral liquid medicine with a purpose-made dosing cup and depict a
  tablet/capsule only when the source supports that age-appropriate form. A needle and syringe may
  appear only for an explicitly sourced injection and must be directed to skin, muscle, or an IV
  site, never the mouth. Generic medication wording never authorizes an injection visual.
- For infant sleep, show a baby supine on a firm flat surface with only a fitted sheet; no pillow,
  soft bumper, elevated cushion, loose blanket, or soft toy. A raised pillow belongs only to an
  older child when the scene explicitly supports it.
- When demonstrating infant feeding, keep head and trunk supported and the baby awake enough to
  swallow. If vomiting changes a feed, keep formula mixed at label concentration; show only a
  smaller serving from a correctly prepared feed, never drops of mystery liquid diluting a bottle.
- For nasal care, never point a bottle into the nose of a child lying flat with head tilted back.
  A cooperative older child may lean forward over a sink using the appropriate product; infant
  saline drops/gentle suction are a distinct procedure. Do not imply unverified water is safe.
- A dosing example for a 40-41 kg child must look age/size appropriate. Show the actual supported
  delivery device and graduated markings only as accurate code-rendered overlays, never generated
  numbers, and never transfer the same volume to a much smaller infant.
- No text, letters, numbers, units, labels, arrows, measurement marks, logos, or watermarks.
- No gore, no extra objects, no deformed anatomy or limbs.
"""


def _fingerprint(
    prompt: str,
    character_image: Path | None,
    include_character: bool,
    model: str,
) -> str:
    payload = {"prompt": prompt, "model": model, "include_character": include_character}
    if include_character:
        if character_image is None:
            raise ValueError("A character reference is required for character scenes.")
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
