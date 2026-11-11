from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fevercoach_shorts.models import ProductionSpec, SceneSpec
from fevercoach_shorts.providers.prompt_refiner import VeoPromptRefiner


class _TextModels:
    def __init__(self) -> None:
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            text=json.dumps(
                {
                    "visual_observation": "A teal thermometer character in a layered clinic set",
                    "subject_action": "The thermometer raises one arm, points once, and stops",
                    "camera_beat_one": "Track quickly past a blurred foreground rail",
                    "camera_beat_two": "Push toward the blank thermometer screen and settle",
                    "payoff_hold": "Hold the blank screen and pointing hand fully visible",
                    "stationary_elements": ["clinic wall", "floor markers"],
                    "sound_cues": ["soft plastic tap", "brief air rush"],
                    "risk_flags": [
                        {
                            "severity": "low",
                            "type": "overlay_collision",
                            "reason": "Keep the upper-right area clear.",
                        }
                    ],
                }
            )
        )


class VeoPromptRefinerTest(unittest.TestCase):
    def test_generated_numbers_in_reference_block_veo_even_if_correct(self) -> None:
        class _NumberModels:
            def generate_content(self, **_kwargs):
                return SimpleNamespace(text=json.dumps({
                    "visual_observation": "Tooth with visible numeric age markers",
                    "subject_action": "Hold still",
                    "risk_flags": [{"severity": "high", "type": "generated_text", "reason": "Visible digits on age markers"}],
                }))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "scene.png"
            image.write_bytes(b"image")
            scene = SceneSpec(
                index=1, title="Tooth", mode="i2v", timeline_seconds=60,
                generation_seconds=6, narration="Consult a doctor.",
                subtitle="Consult a doctor.", prompt="Tooth diagram.",
                negative_prompt="text", image=image, medical_claim="Source fact.",
            )
            spec = ProductionSpec(slug="numbers", title="Numbers", source="source.md",
                                  character_image=None, scenes=[scene], language="en")
            refiner = VeoPromptRefiner("key", "text-model", client=SimpleNamespace(models=_NumberModels()))
            with self.assertRaisesRegex(RuntimeError, "Visible digits"):
                refiner.refine(spec, root / "visuals")

    def test_high_medical_risk_reference_blocks_veo(self) -> None:
        class _UnsafeModels:
            def generate_content(self, **_kwargs):
                return SimpleNamespace(text=json.dumps({
                    "visual_observation": "Infant lying with loose pillow in crib",
                    "subject_action": "Sleep",
                    "risk_flags": [{
                        "severity": "high", "type": "medical_ambiguity",
                        "reason": "Loose pillow in infant sleep reference",
                    }],
                }))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "scene.png"
            image.write_bytes(b"image")
            scene = SceneSpec(
                index=1, title="Infant sleep", mode="i2v", timeline_seconds=60,
                generation_seconds=6, narration="Consult a doctor.",
                subtitle="Consult a doctor.", prompt="Infant resting.",
                negative_prompt="text, logo", image=image, medical_claim="Sleep safely.",
            )
            spec = ProductionSpec(
                slug="unsafe-reference", title="Unsafe reference", source="source.md",
                character_image=None, scenes=[scene], language="en",
            )
            refiner = VeoPromptRefiner("key", "text-model", client=SimpleNamespace(models=_UnsafeModels()))
            with self.assertRaisesRegex(RuntimeError, "Loose pillow"):
                refiner.refine(spec, root / "visuals")

    def test_refines_from_scene_and_character_images_then_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scene_image = root / "scene.png"
            character_image = root / "character.png"
            scene_image.write_bytes(b"scene-image")
            character_image.write_bytes(b"character-image")
            scene = SceneSpec(
                index=1,
                title="Fever hook",
                mode="i2v",
                timeline_seconds=60,
                generation_seconds=6,
                narration="Consult a doctor.",
                subtitle="Consult a doctor.",
                prompt="Raise one arm.",
                negative_prompt="text, logo",
                image=scene_image,
                medical_claim="Measure temperature correctly.",
                include_character=True,
                narrative_role="hook",
                shot_design={
                    "camera_profile": "lateral_reveal",
                    "depth_layers": "foreground rail, midground character, background wall",
                    "overlay_safe_zone": "upper-right quadrant",
                    "transition_out": "finish pointing toward the next scene",
                },
            )
            spec = ProductionSpec(
                slug="refine",
                title="Refine",
                source="article.md",
                character_image=character_image,
                scenes=[scene],
                language="en",
            )
            models = _TextModels()
            refiner = VeoPromptRefiner(
                "key", "text-model", client=SimpleNamespace(models=models)
            )

            first = refiner.refine(spec, root / "visuals")
            second = refiner.refine(spec, root / "visuals")

            self.assertEqual(len(models.calls), 1)
            self.assertEqual(first.scenes[0].prompt, second.scenes[0].prompt)
            self.assertIn("A teal thermometer", first.scenes[0].prompt)
            self.assertIn("CAMERA BEAT ONE, 0.0-1.5 seconds", first.scenes[0].prompt)
            self.assertIn("PAYOFF HOLD, 4.5-6.0 seconds", first.scenes[0].prompt)
            self.assertIn("upper-right quadrant", first.scenes[0].prompt)
            self.assertIn("no letters in any language", first.scenes[0].prompt)
            self.assertIn("must not move, speak, or lip-sync", first.scenes[0].prompt)
            contents = models.calls[0]["contents"]
            self.assertEqual(len(contents), 3)
            manifest = json.loads(
                (root / "visuals" / "refined_prompts.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["scenes"]["1"]["base_prompt"], "Raise one arm.")
            self.assertEqual(
                manifest["scenes"]["1"]["risk_flags"][0]["type"],
                "overlay_collision",
            )
            self.assertEqual(manifest["risk_summary"]["low"], 1)

            # An old multilingual cache must not bypass updated medical guardrails.
            spec.metadata["multilingual"] = True
            manifest["scenes"]["1"]["format_version"] = 4
            manifest["scenes"]["1"]["fingerprint"] = "old-policy-fingerprint"
            (root / "visuals" / "refined_prompts.json").write_text(json.dumps(manifest))
            refreshed = refiner.refine(spec, root / "visuals")
            self.assertEqual(len(models.calls), 2)
            self.assertIn("Jaeyoon FAIL-derived visual guardrails", refreshed.scenes[0].prompt)

            # v5 motion stays reusable only AFTER the stricter v6 inspection runs.
            manifest_path = root / "visuals" / "refined_prompts.json"
            manifest = json.loads(manifest_path.read_text())
            old_motion = manifest["scenes"]["1"]["prompt"] + " Original cached motion."
            manifest["scenes"]["1"].update(format_version=5, fingerprint="old-v5", prompt=old_motion)
            manifest_path.write_text(json.dumps(manifest))
            inspected = refiner.refine(spec, root / "visuals")
            self.assertEqual(len(models.calls), 3)
            self.assertEqual(inspected.scenes[0].prompt, old_motion)


if __name__ == "__main__":
    unittest.main()
