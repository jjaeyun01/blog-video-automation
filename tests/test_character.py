from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fevercoach_shorts.models import ProductionSpec, SceneSpec
from fevercoach_shorts.providers.character import CharacterReferenceGenerator


class _ImageModels:
    def __init__(self) -> None:
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        inline_data = SimpleNamespace(data=b"automatic-character")
        return SimpleNamespace(parts=[SimpleNamespace(inline_data=inline_data)])


class CharacterReferenceGeneratorTest(unittest.TestCase):
    def test_generates_and_reuses_an_automatic_character(self) -> None:
        scene = SceneSpec(
            index=1,
            title="Hook",
            mode="i2v",
            timeline_seconds=60,
            generation_seconds=6,
            narration="Consult a doctor.",
            subtitle="Consult a doctor.",
            prompt="The character points once.",
            negative_prompt="text, logo",
            asset_prompt="A clean scene.",
            include_character=True,
        )
        spec = ProductionSpec(
            slug="auto-character",
            title="Automatic character",
            source="article.md",
            character_image=None,
            scenes=[scene],
            language="en",
            metadata={
                "character_concept": {
                    "subject": "thermometer",
                    "source_basis": "The article is about fever measurement.",
                    "visual_identity": "Rounded digital thermometer with a blank screen",
                    "primary_color": "pale teal",
                    "surface_texture": "smooth matte plastic",
                }
            },
        )
        models = _ImageModels()
        generator = CharacterReferenceGenerator(
            "key", "image-model", client=SimpleNamespace(models=models)
        )

        with tempfile.TemporaryDirectory() as directory:
            visual_dir = Path(directory) / "visuals"
            first = generator.generate(spec, visual_dir)
            second = generator.generate(spec, visual_dir)

            expected = (visual_dir / "character" / "reference.png").resolve()
            self.assertEqual(first.character_image, expected)
            self.assertEqual(second.character_image, expected)
            self.assertEqual(expected.read_bytes(), b"automatic-character")
            self.assertEqual(len(models.calls), 1)
            prompt = models.calls[0]["contents"][0]
            self.assertIn("thermometer", prompt)
            self.assertIn("no text", prompt)
            self.assertIn("wide-open shouting mouth", prompt)

    def test_preserves_a_supplied_character_without_api_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            character = root / "supplied.png"
            character.write_bytes(b"supplied")
            spec = ProductionSpec(
                slug="manual",
                title="Manual",
                source="article.md",
                character_image=character,
                scenes=[],
            )
            models = _ImageModels()
            result = CharacterReferenceGenerator(
                "key", "image-model", client=SimpleNamespace(models=models)
            ).generate(spec, root / "visuals")

            self.assertEqual(result.character_image, character)
            self.assertEqual(models.calls, [])


if __name__ == "__main__":
    unittest.main()
