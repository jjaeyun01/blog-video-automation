from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fevercoach_shorts.article import Article
from fevercoach_shorts.planner import ScenePlanner, _normalize_overlay, _text_free_visual_prompt
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
            "medical_facts": [{"claim": "Supported claim", "numeric_values": []}],
            "scenes": [
                {
                    "mode": "i2v",
                    "timeline_seconds": 6,
                    "generation_seconds": 6,
                    "visual_type": "mechanism",
                    "medical_claim": f"Claim {index}",
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
            character = root / "character.png"
            character.write_bytes(b"image")
            results = planner.create_multilingual(
                Article("Article", "Content", "article.md"),
                character,
                root / "weekly.production.json",
            )

            self.assertEqual(set(results), {"ko", "es", "en"})
            prompts = []
            for language, (path, spec) in results.items():
                self.assertEqual(path.name, f"weekly.production.{language}.json")
                self.assertEqual(spec.language, language)
                self.assertTrue(spec.metadata["multilingual"])
                self.assertEqual(len(spec.scenes), 10)
                self.assertEqual(spec.scenes[0].overlays[0]["text"], f"Value {language}")
                prompts.append([scene.prompt for scene in spec.scenes])
            self.assertEqual(prompts[0], prompts[1])
            self.assertEqual(prompts[1], prompts[2])

    def test_tts_instructions_are_localized(self) -> None:
        self.assertIn("한국어", _tts_direction("ko"))
        self.assertIn("español", _tts_direction("es"))
        self.assertIn("US English", _tts_direction("en"))

    def test_generated_text_requests_are_removed_and_threshold_is_horizontal(self) -> None:
        prompt = _text_free_visual_prompt("A thermometer displaying '40.0°C'.")
        self.assertNotIn("40.0°C", prompt)
        self.assertIn("blank, unlit display", prompt)
        overlay = _normalize_overlay(
            {"type": "threshold", "from": [0.5, 0.75], "to": [0.5, 0.9]}
        )
        self.assertEqual(overlay["from"][1], overlay["to"][1])
        self.assertLessEqual(overlay["from"][1], 0.68)


if __name__ == "__main__":
    unittest.main()
