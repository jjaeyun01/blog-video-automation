from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.safety import validate_medical_copy


class SafetyTest(unittest.TestCase):
    def test_example_passes(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            path = root / "production.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            validate_medical_copy(ProductionSpec.load(path))

    def test_blocks_instruction_to_stop_medicine(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        data["scenes"][2]["narration"] = "항생제를 끊으세요."
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            path = root / "production.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "항생제를 끊으세요"):
                validate_medical_copy(ProductionSpec.load(path))

    def test_accepts_pediatric_clinic_visit_as_consultation(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        data["scenes"][-1]["narration"] = "증상이 지속되면 소아청소년과에 방문하세요."
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            path = root / "production.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            validate_medical_copy(ProductionSpec.load(path))


if __name__ == "__main__":
    unittest.main()
