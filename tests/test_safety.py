from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.safety import _clear_unsafe_instruction_errors, validate_medical_copy


class SafetyTest(unittest.TestCase):
    def test_week8_clear_unsafe_instructions_are_blocked_before_generation(self) -> None:
        cases = (
            ("어른보다 한 겹 적게 입혀주세요.", "", "one layer less"),
            ("수유 거부가 12시간 이상 지속되면 병원에 가세요.", "", "12 hours"),
            ("분유를 평소의 2/3로 줄이세요.", "", "per-feed amount"),
            ("가루 해열제는 1~2시간 내 먹이고 냉장 보관하세요.", "", "premix"),
            ("약을 먹고 1시간 이내 토하면 다시 먹이세요.", "", "within one hour"),
            ("", "Nasal rinse bottle for child lying flat with head tilted back", "nasal irrigation"),
        )
        for narration, visual, expected in cases:
            with self.subTest(narration=narration, visual=visual):
                self.assertIn(expected, " ".join(
                    _clear_unsafe_instruction_errors(narration, visual, "")
                ))

    def test_week8_guard_preserves_qualified_and_warning_examples(self) -> None:
        safe_cases = (
            "분유는 제품 표시대로 타고 1회 먹이는 양을 줄여 자주 먹이세요.",
            "2시간 간격의 해열제 교차복용을 권하지 않습니다.",
            "수유 거부 시 12시간을 기다리지 말고 더 일찍 진료받으세요.",
        )
        for narration in safe_cases:
            with self.subTest(narration=narration):
                self.assertEqual(_clear_unsafe_instruction_errors(narration, "", ""), [])

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
