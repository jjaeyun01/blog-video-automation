from __future__ import annotations

import hashlib
import json
import mimetypes
import time
from dataclasses import replace
from pathlib import Path

from google import genai
from google.genai import types

from ..models import ProductionSpec, SceneSpec
from ..review_rules import JAEYOON_VISUAL_SAFETY_RULES


_PROMPT_FORMAT_VERSION = 6


class VeoPromptRefiner:
    """Inspect generated references and turn each planned motion into a grounded Veo prompt."""

    def __init__(self, api_key: str, model: str, client=None):
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=120_000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self.model = model

    def refine(self, spec: ProductionSpec, visual_dir: Path) -> ProductionSpec:
        visual_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = visual_dir / "refined_prompts.json"
        manifest = _read_json(manifest_path, {"model": self.model, "scenes": {}})
        if manifest.get("model") != self.model:
            manifest = {"model": self.model, "scenes": {}}

        refined_scenes: list[SceneSpec] = []
        for scene in spec.scenes:
            if scene.image is None or not scene.image.exists():
                refined_scenes.append(scene)
                continue

            reference_paths = [scene.image]
            if (
                scene.include_character
                and spec.character_image is not None
                and spec.character_image.exists()
                and spec.character_image.resolve() != scene.image.resolve()
            ):
                reference_paths.append(spec.character_image)

            fingerprint = _fingerprint(scene, reference_paths, self.model)
            reference_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in reference_paths]
            key = str(scene.index)
            cached = manifest["scenes"].get(key, {})
            shared_multilingual_visual = (
                bool(spec.metadata.get("multilingual"))
                and cached.get("format_version") == _PROMPT_FORMAT_VERSION
                and cached.get("base_prompt") == scene.prompt
                and cached.get("scene_image") == str(scene.image.resolve())
                and cached.get("reference_hashes") == reference_hashes
                and cached.get("prompt")
            )
            if (
                cached.get("fingerprint") == fingerprint or shared_multilingual_visual
            ) and cached.get("prompt"):
                refined_prompt = str(cached["prompt"])
            else:
                contents: list[object] = [_refinement_request(scene, len(reference_paths))]
                contents.extend(_image_part(path) for path in reference_paths)
                payload = None
                last_error: Exception | None = None
                for attempt in range(1, 4):
                    try:
                        response = self.client.models.generate_content(
                            model=self.model,
                            contents=contents,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                temperature=0.2,
                            ),
                        )
                        response_text = str(getattr(response, "text", "") or "").strip()
                        if not response_text:
                            raise RuntimeError("Gemini returned an empty refinement response.")
                        candidate = json.loads(response_text)
                        if not isinstance(candidate, dict):
                            raise RuntimeError("Gemini returned a non-object refinement response.")
                        payload = candidate
                        break
                    except Exception as error:
                        last_error = error
                        if attempt < 3:
                            time.sleep(attempt * 2)
                if payload is None:
                    print(
                        f"Scene {scene.index}: Gemini refinement unavailable after 3 attempts; "
                        "using the source-grounded conservative prompt fallback.",
                        flush=True,
                    )
                    payload = {
                        "visual_observation": (
                            scene.asset_prompt
                            or "Use only the subjects and objects visible in the exact reference image"
                        ),
                        "subject_action": scene.prompt,
                        "stationary_elements": [
                            "all background elements and every text-free surface"
                        ],
                        "sound_cues": ["quiet room ambience"],
                        "risk_flags": [
                            {
                                "severity": "medium",
                                "type": "refinement_fallback",
                                "reason": str(last_error or "empty model response")[:300],
                            }
                        ],
                    }
                refined_prompt = _compose_refined_prompt(payload, scene)
                raw_risks = payload.get("risk_flags", [])
                risk_flags = raw_risks if isinstance(raw_risks, list) else []
                # Version 6 adds reference-text inspection, not a new motion contract.
                # Inspect old v5 images again, but keep a safe unchanged motion request
                # so already-submitted Veo operations remain resumable.
                if (
                    cached.get("format_version") == 5
                    and cached.get("base_prompt") == scene.prompt
                    and cached.get("scene_image") == str(scene.image.resolve())
                    and cached.get("reference_hashes") == reference_hashes
                    and JAEYOON_VISUAL_SAFETY_RULES in str(cached.get("prompt", ""))
                    and not any(isinstance(flag, dict) and flag.get("severity") == "high" for flag in risk_flags)
                ):
                    refined_prompt = str(cached["prompt"])
                manifest["scenes"][key] = {
                    "format_version": _PROMPT_FORMAT_VERSION,
                    "fingerprint": fingerprint,
                    "reference_hashes": reference_hashes,
                    "base_prompt": scene.prompt,
                    "prompt": refined_prompt,
                    "risk_flags": risk_flags,
                    "scene_image": str(scene.image.resolve()),
                    "character_image": (
                        str(spec.character_image.resolve())
                        if scene.include_character and spec.character_image else None
                    ),
                }
                _write_json(manifest_path, manifest)

            unsafe_reference = [
                flag for flag in manifest["scenes"].get(key, {}).get("risk_flags", [])
                if isinstance(flag, dict)
                and str(flag.get("severity", "")).lower() == "high"
                and str(flag.get("type", "")).lower() in {"medical_ambiguity", "generated_text"}
            ]
            if unsafe_reference:
                reasons = "; ".join(str(flag.get("reason", "")) for flag in unsafe_reference)
                raise RuntimeError(
                    f"Scene {scene.index} reference image has a high medical safety risk: "
                    f"{reasons}. Correct the source reference before Veo generation."
                )
            refined_scenes.append(replace(scene, prompt=refined_prompt))

        manifest["risk_summary"] = _risk_summary(manifest.get("scenes", {}))
        _write_json(manifest_path, manifest)
        return replace(spec, scenes=refined_scenes)


def _refinement_request(scene: SceneSpec, reference_count: int) -> str:
    character_note = (
        "The second image is the canonical character reference. Preserve its exact identity, "
        "colors, material, face, body proportions, and number of limbs."
        if scene.include_character and reference_count > 1
        else "Do not introduce a recurring character that is not visible in the scene reference."
    )
    return f"""You are the medical cinematography director refining one image-to-video shot after
inspecting the actual generated images. Use the high-retention visual grammar of premium 3D
engineering explainers, adapted for accurate pediatric medical education.

Return JSON only in this format:
{{
  "visual_observation": "only visible grounded details from the first image",
  "subject_action": "one physically plausible action with start and end states",
  "camera_beat_one": "0.0-1.5 second move grounded in visible depth",
  "camera_beat_two": "1.5-4.5 second move toward the medical focal target",
  "payoff_hold": "stable readable frame from 4.5-6.0 seconds",
  "stationary_elements": ["specific element that must not move"],
  "sound_cues": ["precise diegetic sound, never speech or music"],
  "risk_flags": [
    {{"severity": "low|medium|high", "type": "medical_ambiguity|generated_text|camera_occlusion|character_drift|overlay_collision|unsupported_object", "reason": "brief explanation"}}
  ]
}}

Scene number: {scene.index}
Scene purpose: {scene.title}
Narrative role: {scene.narrative_role}
Grounded medical claim: {scene.medical_claim}
Original planned motion: {scene.prompt}
Planned shot design: {json.dumps(scene.shot_design, ensure_ascii=False)}
Planned code-rendered overlays: {json.dumps(scene.overlays, ensure_ascii=False)}
The first attached image is the exact scene starting frame.
{character_note}

Design the structured fields so the compiled Veo prompt will:
{JAEYOON_VISUAL_SAFETY_RULES}
- inspect the first image for ACTUALLY VISIBLE letters, digits, units or writing. If present,
  report severity=high, type=generated_text and describe the visible location. Even a correct
  numeral is forbidden in generated reference pixels: text belongs in later code overlays.
  Never claim camera motion can erase the starting-frame text. Do not invent visible text from
  a number mentioned only in the planned prompt or a future overlay specification.
- describe only subjects, objects, colors, materials, lighting, and composition actually visible in the attached reference
- preserves the first frame exactly and never redesigns, replaces, duplicates, or removes its main subject
- keeps the original medical meaning without inventing a diagnosis, number, treatment, or object
- gives the main subject one clear action with physically readable start and end states
- uses exactly two camera beats: a brief spatial reveal, then a motivated move to the medical focal target
- varies the selected camera profile from adjacent shots while honoring the planned shot design
- completes subject and camera motion by 4.5 seconds, then holds a stable payoff through 6.0 seconds
- creates foreground, midground, and background parallax without handheld shake, random orbit, whip pan, or spinning
- explicitly states which background elements stay stationary
- preserves an attached character exactly; an open angry mouth may hold still but must not animate or lip-sync
- requests ambient foley only, with no generated speech, dialogue, voice-over, or music
- never requests visible text, Korean or Latin letters, numbers, units, labels, arrows, subtitles, signs, logos, watermarks, screens, or UI
- leaves the planned overlay region uncluttered but does not draw the overlay itself
- keeps pure saturated red absent from generated pixels except when it already belongs to the locked character
- never places any syringe in or near a mouth; oral liquid uses a purpose-made dosing cup, while a
  syringe appears only for an explicitly sourced injection aimed at skin, muscle, or an IV site
- reports any conflict between camera spectacle, medical clarity, character identity, and overlay placement in risk_flags
- never animate ear pain travelling to the chest along nerves or vessels; new chest pain is a
  separate symptom, not a moving object. Do not depict auscultation as a definitive pneumonia test.
- infant sleep references must have a firm flat surface, supine infant, fitted sheet, no pillows,
  loose blankets or soft toys. Never show oral fluids given to a sleeping/unresponsive infant.
  If the starting image is unsafe, report a high medical_ambiguity risk requiring reference repair;
  do not conceal the unsafe object or claim a motion prompt alone repaired the starting frame.
- if nasal irrigation is demonstrated, never show a bottle to a child supine with head tipped back;
  use an age-appropriate cooperative child leaning toward a sink, or infant saline drops as a
  separate procedure. If the reference starts with the unsafe posture, flag high medical_ambiguity.
- for vomiting/feeding, depict normal-concentration formula and a smaller per-feed amount, never
  bottle dilution; an infant being held for a feed needs supported head and trunk.
- match child's apparent age/size to any weight-specific medication example. Do not portray a
  40-41 kg example with a small infant or promise that the volume applies to other weights.
"""


def _compose_refined_prompt(payload: dict, scene: SceneSpec) -> str:
    design = scene.shot_design
    observation = str(
        payload.get("visual_observation") or payload.get("prompt") or scene.prompt
    ).strip()
    action = str(payload.get("subject_action") or scene.prompt).strip()
    beat_one = str(
        payload.get("camera_beat_one")
        or design.get("beat_one")
        or "Track laterally through the foreground to establish depth and reveal the focal subject."
    ).strip()
    beat_two = str(
        payload.get("camera_beat_two")
        or design.get("beat_two")
        or "Move decisively toward the medical focal target and arrive by 4.5 seconds."
    ).strip()
    payoff = str(
        payload.get("payoff_hold")
        or design.get("payoff_frame")
        or "Hold a stable, unobstructed view of the completed relationship."
    ).strip()
    stationary = payload.get("stationary_elements") or [
        "all background architecture, labels-free surfaces, and secondary props"
    ]
    if isinstance(stationary, str):
        stationary = [stationary]
    stationary_text = ", ".join(str(value).strip() for value in stationary if str(value).strip())
    sounds = payload.get("sound_cues") or design.get("sound_cues") or ["quiet room air"]
    if isinstance(sounds, str):
        sounds = [sounds]
    sound_text = ", ".join(str(value).strip() for value in sounds if str(value).strip())
    depth = str(
        design.get("depth_layers")
        or "a close foreground occluder, the medical subject in midground, and a quiet contextual background"
    ).strip()
    safe_zone = str(
        design.get("overlay_safe_zone")
        or "the upper-middle measurement area and the lower caption-safe region"
    ).strip()
    camera_profile = str(design.get("camera_profile") or "motivated spatial reveal").strip()
    transition = str(
        design.get("transition_out") or "end on a clean visual direction for the next cut"
    ).strip()
    medical_claim = str(scene.medical_claim or scene.title).strip().rstrip(".!?")
    character_rule = (
        "CHARACTER LOCK: Preserve the exact character identity, colors, tactile material, facial "
        "features, body proportions, and exactly two arms and two legs. The angry open-mouth "
        "expression may hold, but the mouth must not move, speak, or lip-sync. "
        if scene.include_character else ""
    )
    overlay_note = (
        f"OVERLAY COMPOSITION: Keep {safe_zone} visually quiet so deterministic red measurement "
        "graphics and localized labels can be composited later; do not render those overlays in the generated video. "
    )
    return (
        "A 6-second vertical 9:16 premium semi-stylized 3D pediatric medical visualization, "
        "halfway between clean modeled illustration and restrained photorealism. "
        f"SUBJECT AND START FRAME: {observation}. "
        "STYLE AND MATERIALS: simplified readable geometry with real modeled detail, smooth shading, "
        "tactile surfaces, soft contact shadows, mild ambient occlusion, cinematic depth, rich clean "
        "color, and soft directional daylight; no flat gray wash. "
        f"COMPOSITION AND DEPTH: use {depth}, one dominant focal target, and clear negative space. "
        f"CAMERA PROFILE: {camera_profile}. "
        f"CAMERA BEAT ONE, 0.0-1.5 seconds: {beat_one}. "
        f"CAMERA BEAT TWO, 1.5-4.5 seconds: {beat_two}. "
        f"SUBJECT MOTION: {action}. Complete the action by 4.5 seconds. "
        f"PAYOFF HOLD, 4.5-6.0 seconds: {payoff}; {transition}. "
        f"FIXED ELEMENTS: {stationary_text} remain completely stationary. "
        f"MEDICAL CLARITY: communicate only this source-grounded claim: {medical_claim}. "
        f"{JAEYOON_VISUAL_SAFETY_RULES}\n"
        "Do not imply a diagnosis, dosage, threshold, outcome, or treatment not explicitly stated. "
        "MEDICATION ROUTE LOCK: Never put any syringe in or near a mouth, including a needleless oral "
        "dosing syringe. Show swallowed liquid medicine with a purpose-made dosing cup; show a tablet "
        "or capsule only when the source supports that form. Show a needle and syringe only for an "
        "explicitly sourced injection, aimed at skin, muscle, or an IV site and never the mouth. "
        f"{character_rule}{overlay_note}"
        "COLOR RULE: use cream, pale teal, clean blue, natural anatomical pink, and warm amber; "
        "pure saturated red is reserved for later code-rendered overlays, except an existing locked "
        "character color. "
        f"SOUND: {sound_text}; subtle diegetic foley only. "
        "STRICT EXCLUSIONS: no letters in any language, Korean glyphs, digits, numbers, units, labels, "
        "arrows, captions, subtitles, signs, logos, watermarks, speech bubbles, screens, UI, dialogue, "
        "voice, narration, lip-sync, background music, extra characters, duplicate subjects, extra "
        "limbs, deformed anatomy, handheld shake, random orbit, whip pan, spinning camera, lens flare, "
        "film grain, vignette, collage, or split screen."
    )


def _enforce_video_contract(prompt: str, scene: SceneSpec) -> str:
    """Backward-compatible contract helper for callers using a precomposed prompt."""
    character_rule = (
        "Preserve the exact character identity, colors, material, facial features, body "
        "proportions, and exactly two arms and two legs; hold any open-mouth expression still "
        "with no speaking or lip-sync. "
        if scene.include_character else ""
    )
    return (
        f"{prompt.strip()} {character_rule}"
        f"{JAEYOON_VISUAL_SAFETY_RULES}\n"
        "All generated frames must remain text-free: no letters in any language, Korean glyphs, "
        "digits, numbers, units, labels, arrows, captions, subtitles, signs, logos, watermarks, "
        "speech bubbles, screens, or UI. Ambient foley only; no dialogue, voice, narration, "
        "lip-sync, or music. Never place a syringe in or near a mouth. Oral liquid medicine uses a "
        "purpose-made dosing cup; a syringe is allowed only for an explicitly sourced injection and "
        "must point to skin, muscle, or an IV site. Do not add extra characters, duplicate subjects, "
        "or extra limbs."
    )


def _image_part(path: Path):
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)


def _fingerprint(scene: SceneSpec, paths: list[Path], model: str) -> str:
    payload = {
        "format_version": _PROMPT_FORMAT_VERSION,
        "model": model,
        "scene": scene.index,
        "title": scene.title,
        "medical_claim": scene.medical_claim,
        "base_prompt": scene.prompt,
        "include_character": scene.include_character,
        "images": [
            {
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in paths
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path, default: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _risk_summary(scenes: dict) -> dict[str, int]:
    counts = {"low": 0, "medium": 0, "high": 0}
    for entry in scenes.values():
        for risk in entry.get("risk_flags", []):
            if isinstance(risk, dict):
                severity = str(risk.get("severity", "")).lower()
                if severity in counts:
                    counts[severity] += 1
    return counts
