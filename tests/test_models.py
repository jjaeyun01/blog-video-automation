from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec


class ProductionSpecTest(unittest.TestCase):
    def test_caption_chunks_fall_back_when_they_do_not_match_tts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            character = root / "character.png"
            character.write_bytes(b"image")
            data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
            data["character_image"] = str(character)
            data["scenes"][0]["narration"] = "열이 계속되면 진료를 받으세요."
            data["scenes"][0]["caption_chunks"] = ["열이 내리면", "약을 중단하세요."]
            path = root / "production.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            spec = ProductionSpec.load(path)

            self.assertEqual(
                " ".join(spec.scenes[0].caption_chunks), spec.scenes[0].narration
            )

    def test_caption_chunks_are_merged_to_three_without_changing_tts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            character = root / "character.png"
            character.write_bytes(b"image")
            data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
            data["character_image"] = str(character)
            narration = "one two three four five"
            data["scenes"][0]["narration"] = narration
            data["scenes"][0]["caption_chunks"] = narration.split()
            path = root / "production.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            spec = ProductionSpec.load(path)

            chunks = spec.scenes[0].caption_chunks
            self.assertLessEqual(len(chunks), 3)
            self.assertEqual(" ".join(chunks), narration)

    def test_loads_six_scene_sixty_second_spec_and_resolves_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "character.png"
            image.write_bytes(b"image")
            data = {
                "slug": "week-1",
                "title": "Weekly",
                "source": "article.md",
                "character_image": "character.png",
                "scenes": [],
            }
            durations = [8, 10, 10, 12, 12, 8]
            modes = ["i2v", "i2v", "t2v", "t2v", "i2v", "i2v"]
            for index, (duration, mode) in enumerate(zip(durations, modes), start=1):
                data["scenes"].append(
                    {
                        "index": index,
                        "title": f"Scene {index}",
                        "mode": mode,
                        "timeline_seconds": duration,
                        "generation_seconds": 8,
                        "narration": "나레이션",
                        "subtitle": "자막",
                        "prompt": "Detailed motion prompt",
                        "negative_prompt": "text, logo",
                    }
                )
            path = root / "production.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            spec = ProductionSpec.load(path)

            self.assertEqual(spec.duration_seconds, 60)
            self.assertEqual(spec.aspect_ratio, "9:16")
            self.assertEqual(spec.scenes[0].image, image.resolve())
            self.assertIsNone(spec.scenes[2].image)
            self.assertEqual(spec.scenes[0].subtitle, spec.scenes[0].narration)

    def test_legacy_summary_subtitle_is_normalized_to_tts_narration(self) -> None:
        example = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            example["character_image"] = "character.png"
            example["scenes"][0]["subtitle"] = "Short summary"
            path = root / "production.json"
            path.write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(path)
            self.assertEqual(spec.scenes[0].subtitle, spec.scenes[0].narration)

    def test_rejects_non_sixty_second_timeline(self) -> None:
        example = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        example["scenes"][0]["timeline_seconds"] = 7
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            example["character_image"] = "character.png"
            path = root / "invalid.json"
            path.write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "60 seconds"):
                ProductionSpec.load(path)


if __name__ == "__main__":
    unittest.main()
