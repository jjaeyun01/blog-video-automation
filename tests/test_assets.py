from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fevercoach_shorts.models import ProductionSpec, SceneSpec
from fevercoach_shorts.providers.assets import SceneAssetGenerator


class _ImageModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        inline_data = SimpleNamespace(data=b"generated-png")
        return SimpleNamespace(parts=[SimpleNamespace(inline_data=inline_data)])


class SceneAssetGeneratorTest(unittest.TestCase):
    def test_generates_and_reuses_a_shared_scene_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            character = root / "character.png"
            character.write_bytes(b"character")
            scene = SceneSpec(
                index=1,
                title="Scene",
                mode="i2v",
                timeline_seconds=60,
                generation_seconds=6,
                narration="Consult a pediatrician.",
                subtitle="Consult a pediatrician.",
                prompt="One bounded motion.",
                negative_prompt="text, logo",
                asset_prompt="Clean cutaway throat anatomy.",
            )
            spec = ProductionSpec(
                slug="test", title="Test", source="source", character_image=character,
                scenes=[scene], language="en"
            )
            models = _ImageModels()
            client = SimpleNamespace(models=models)
            generator = SceneAssetGenerator("key", "image-model", client=client)

            first = generator.generate(spec, root / "visuals")
            second = generator.generate(spec, root / "visuals")

            self.assertEqual(models.calls, 1)
            self.assertEqual(first.scenes[0].image, second.scenes[0].image)
            self.assertEqual(first.scenes[0].image.read_bytes(), b"generated-png")


if __name__ == "__main__":
    unittest.main()
