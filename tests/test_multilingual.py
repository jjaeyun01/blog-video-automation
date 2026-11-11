from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fevercoach_shorts.article import Article
from fevercoach_shorts.planner import (
    ScenePlanner,
    _normalize_overlay,
    _sanitize_shot_design,
    _text_free_visual_prompt,
)
from fevercoach_shorts.providers.tts import _tts_direction


class _Models:
    def __init__(self, response: dict):
        self.response = response

    def generate_content(self, **_kwargs):
        return SimpleNamespace(text=json.dumps(self.response, ensure_ascii=False))


class MultilingualPlanningTest(unittest.TestCase):
    def test_creates_three_localizations_with_shared_visual_prompts(self) -> None:
        response = {
            "slug": "shared-short",
            "character_concept": {
                "subject": "bronchial airway",
                "source_basis": "The article explains airway irritation.",
                "visual_identity": "A soft branching airway tube",
                "primary_color": "coral pink",
                "surface_texture": "soft organic tissue",
            },
            "medical_facts": [{"claim": "Supported claim", "numeric_values": []}],
            "scenes": [
                {
                    "mode": "i2v",
                    "timeline_seconds": 6,
                    "generation_seconds": 6,
                    "visual_type": "mechanism",
                    "narrative_role": "mechanism",
                    "medical_claim": f"Claim {index}",
                    "include_character": index <= 3,
                    "shot_design": {
                        "camera_profile": (
                            "macro_dive" if index % 2 else "lateral_reveal"
                        ),
                        "beat_one": "Move through foreground particles.",
                        "beat_two": "Push toward the airway wall.",
                        "payoff_frame": "Hold on the airway response.",
                        "depth_layers": "particles, airway wall, distant passage",
                        "overlay_safe_zone": "upper-right quadrant",
                        "sound_cues": ["soft airflow"],
                        "transition_out": "follow the airflow",
                    },
                    "asset_prompt": f"Text-free asset {index}",
                    "prompt": f"Shared visual prompt {index}",
                    "negative_prompt": "text, subtitles, logo, watermark, deformation, extra limbs",
                    "overlays": [
                        {"type": "label", "position": [0.5, 0.25], "text_key": "value"}
                    ],
                }
                for index in range(1, 11)
            ],
            "localizations": {},
        }
        endings = {
            "ko": "증상이 지속되면 소아과 전문의와 상담하세요.",
            "es": "Si continúa, consulte a su pediatra.",
            "en": "If it continues, seek immediate medical attention.",
        }
        for language in ("ko", "es", "en"):
            response["localizations"][language] = {
                "title": f"Title {language}",
                "disclaimer": f"Disclaimer {language}",
                "scenes": [
                    {
                        "title": f"Scene {index} {language}",
                        "narration": endings[language] if index == 10 else f"Narration {index} {language}",
                        "subtitle": f"Subtitle {index} {language}",
                        "caption_chunks": [
                            endings[language] if index == 10 else f"Narration {index} {language}"
                        ],
                        "overlay_labels": {"value": f"Value {language}"},
                    }
                    for index in range(1, 11)
                ],
            }

        planner = ScenePlanner.__new__(ScenePlanner)
        planner.settings = SimpleNamespace(gemini_text_model="test-model")
        planner.client = SimpleNamespace(models=_Models(response))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = planner.create_multilingual(
                Article("Article", "Content", "article.md"),
                None,
                root / "weekly.production.json",
            )

            self.assertEqual(set(results), {"ko", "es", "en"})
            prompts = []
            for language, (path, spec) in results.items():
                self.assertEqual(path.name, f"weekly.production.{language}.json")
                self.assertEqual(spec.language, language)
                self.assertTrue(spec.metadata["multilingual"])
                self.assertEqual(spec.metadata["character_mode"], "automatic")
                self.assertEqual(
                    spec.metadata["character_concept"]["subject"], "bronchial airway"
                )
                self.assertIsNone(spec.character_image)
                self.assertEqual(len(spec.scenes), 10)
                self.assertEqual(spec.scenes[0].overlays[0]["text"], f"Value {language}")
                self.assertEqual(spec.scenes[0].narrative_role, "mechanism")
                self.assertEqual(
                    spec.scenes[0].shot_design["camera_profile"], "macro_dive"
                )
                prompts.append([scene.prompt for scene in spec.scenes])
            self.assertEqual(prompts[0], prompts[1])
            self.assertEqual(prompts[1], prompts[2])

    def test_tts_instructions_are_localized(self) -> None:
        self.assertIn("한국어", _tts_direction("ko"))
        self.assertIn("Latin American Spanish", _tts_direction("es"))
        self.assertIn("US English", _tts_direction("en"))

    def test_generated_text_requests_are_removed_and_threshold_is_text_only(self) -> None:
        prompt = _text_free_visual_prompt(
            "A calendar with '3 days' highlighted beside a bottle dispensing exactly "
            "2-3 drops and a thermometer displaying '40.0°C'."
        )
        self.assertNotIn("40.0°C", prompt)
        self.assertNotIn("3 days", prompt)
        self.assertNotIn("2-3 drops", prompt)
        self.assertIn("a few uncounted clear drops", prompt)
        self.assertIn("blank", prompt)
        shot_design = _sanitize_shot_design(
            {
                "camera_profile": "top_down_drop",
                "beat_one": "0.0-1.5 second establishing shot.",
                "beat_two": "Show exactly 2-3 drops and '3 days' on a calendar.",
            }
        )
        self.assertIn("0.0-1.5 second", shot_design["beat_one"])
        self.assertNotIn("2-3 drops", shot_design["beat_two"])
        self.assertNotIn("3 days", shot_design["beat_two"])
        overlay = _normalize_overlay(
            {"type": "threshold", "from": [0.5, 0.75], "to": [0.5, 0.9]}
        )
        self.assertEqual(overlay["type"], "label")
        self.assertLessEqual(overlay["from"][1], 0.68)
        self.assertLessEqual(overlay["to"][1], 0.68)
        self.assertEqual(_normalize_overlay({"type": "cross"})["type"], "label")


if __name__ == "__main__":
    unittest.main()
