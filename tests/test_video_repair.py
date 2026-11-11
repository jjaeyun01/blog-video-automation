from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec, SceneSpec
from fevercoach_shorts.providers.video_audit import (
    _audit_prompt,
    actionable_issues,
    apply_repairs,
    find_duplicate_owner,
    register_final_video,
)


def _scene(index: int) -> SceneSpec:
    return SceneSpec(
        index=index,
        title=f"Scene {index}",
        mode="i2v",
        timeline_seconds=30,
        generation_seconds=6,
        narration=f"Narration {index}",
        subtitle=f"Narration {index}",
        prompt=f"Prompt {index}",
        negative_prompt="text, logo",
        asset_prompt="Blank medical scene",
        medical_claim=f"Claim {index}",
        caption_chunks=[f"Narration {index}"],
    )


class VideoRepairTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = ProductionSpec(
            slug="audit-test",
            title="Audit",
            source="https://example.com/article",
            character_image=None,
            scenes=[_scene(1), _scene(2)],
            language="en",
            metadata={"medical_facts": [{"claim": "Source fact"}]},
        )

    def test_only_flagged_scene_changes(self) -> None:
        issue = {
            "scene": 2,
            "category": "ANATOMY_ERROR",
            "problem_ko": "도구 사용이 잘못됨",
            "repair": {
                "corrected_medical_claim": "",
                "corrected_narration": "",
                "corrected_caption_chunks": [],
                "replace_overlays": False,
                "corrected_overlays": [],
                "veo_prompt_addendum": "Show liquid medicine in a purpose-made dosing cup.",
            },
        }
        repaired, changed = apply_repairs(self.spec, [issue], 1)

        self.assertEqual(changed, {2})
        self.assertEqual(repaired.scenes[0], self.spec.scenes[0])
        self.assertIn("purpose-made dosing cup", repaired.scenes[1].prompt)

    def test_reference_repair_changes_only_flagged_image_not_medical_copy(self) -> None:
        from fevercoach_shorts.pipeline import repair_reference_prompts
        import json

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "refined_prompts.json").write_text(json.dumps({"scenes": {
                "1": {"risk_flags": [{"severity": "medium", "type": "overlay_collision", "reason": "Clutter"}]},
                "2": {"risk_flags": [{"severity": "high", "type": "generated_text", "reason": "Visible digits on age markers"}]},
            }}))
            repaired, changed = repair_reference_prompts(self.spec, root, 1)
        self.assertEqual(changed, {2})
        self.assertEqual(repaired.scenes[0], self.spec.scenes[0])
        self.assertEqual(repaired.scenes[1].narration, self.spec.scenes[1].narration)
        self.assertEqual(repaired.scenes[1].medical_claim, self.spec.scenes[1].medical_claim)
        self.assertIn("completely blank", repaired.scenes[1].asset_prompt)
        self.assertIsNone(repaired.scenes[1].image)

    def test_copy_repair_changes_tts_and_matching_captions_only(self) -> None:
        issue = {
            "scene": 1,
            "category": "TTS_CAPTION_MISMATCH",
            "problem_ko": "대본 오류",
            "repair": {
                "corrected_medical_claim": "Correct claim",
                "corrected_narration": "Correct narration.",
                "corrected_caption_chunks": ["Correct", "narration."],
                "replace_overlays": True,
                "corrected_overlays": [],
                "veo_prompt_addendum": "",
            },
        }
        repaired, changed = apply_repairs(self.spec, [issue], 1)

        self.assertEqual(changed, {1})
        self.assertEqual(repaired.scenes[0].prompt, self.spec.scenes[0].prompt)
        self.assertEqual(repaired.scenes[0].narration, "Correct narration.")
        self.assertEqual(repaired.scenes[0].subtitle, "Correct narration.")
        self.assertEqual(repaired.scenes[0].overlays, [])

    def test_numeric_repair_never_asks_veo_to_draw_corrected_text(self) -> None:
        issue = {
            "scene": 1,
            "category": "NUMERIC_ERROR",
            "problem_ko": "생성된 숫자가 틀림",
            "repair": {
                "corrected_medical_claim": "",
                "corrected_narration": "",
                "corrected_caption_chunks": [],
                "replace_overlays": False,
                "corrected_overlays": [],
                "veo_prompt_addendum": "Change 36 hours to 3-4 hours and 6 hours.",
            },
        }

        repaired, changed = apply_repairs(self.spec, [issue], 1)

        self.assertEqual(changed, {1})
        self.assertIn("surfaces completely blank and unmarked", repaired.scenes[0].prompt)
        self.assertNotIn("Change 36 hours", repaired.scenes[0].prompt)

    def test_actionable_filter_requires_severity_confidence_and_regeneration(self) -> None:
        result = {
            "issues": [
                {"severity": "high", "confidence": 0.9, "requires_regeneration": True},
                {"severity": "low", "confidence": 0.99, "requires_regeneration": True},
                {"severity": "high", "confidence": 0.5, "requires_regeneration": True},
            ]
        }
        # A requested final PASS treats even a high-confidence low-severity
        # regeneration finding as actionable.
        self.assertEqual(len(actionable_issues(result, 0.75)), 2)

    def test_prompt_contains_historical_fail_prevention_rules(self) -> None:
        prompt = _audit_prompt(self.spec, "source article", 0.75)
        self.assertIn("171 failed reviews", prompt)
        self.assertIn("Pronounce mL", prompt)
        self.assertIn("generic X", prompt)
        self.assertIn("black/frozen/missing sections", prompt)
        self.assertIn("September 2026", prompt)
        self.assertIn("INCOMPLETE_SPEECH", prompt)
        self.assertIn("MEDICATION_TIMING_RISK", prompt)
        self.assertIn("calibration_checks", prompt)
        self.assertIn("exactly ten chronological scene_av_checks", prompt)

    def test_schema_requires_feedback_calibration_checks(self) -> None:
        from fevercoach_shorts.providers.video_audit import AUDIT_SCHEMA

        self.assertIn("calibration_checks", AUDIT_SCHEMA["required"])
        categories = AUDIT_SCHEMA["properties"]["issues"]["items"]["properties"][
            "category"
        ]["enum"]
        self.assertIn("CAPTION_OMISSION", categories)
        self.assertIn("TRIAGE_OMISSION", categories)

    def test_duplicate_registry_allows_same_identity_and_blocks_another(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry.json"
            video = root / "video.mp4"
            video.write_bytes(b"same-final-video")
            register_final_video(registry, self.spec, video)
            self.assertIsNone(find_duplicate_owner(registry, self.spec, video))
            other = ProductionSpec(
                slug="other-production",
                title=self.spec.title,
                source=self.spec.source,
                character_image=None,
                scenes=self.spec.scenes,
                language=self.spec.language,
                metadata=self.spec.metadata,
            )
            self.assertEqual(
                find_duplicate_owner(registry, other, video), "audit-test:en"
            )


if __name__ == "__main__":
    unittest.main()
