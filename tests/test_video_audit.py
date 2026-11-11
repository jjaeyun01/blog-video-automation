from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path("scripts/audit_blog_videos_with_gemini.py")
SPEC = importlib.util.spec_from_file_location("video_audit", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class VideoAuditTest(unittest.TestCase):
    def test_prompt_marks_oral_syringe_as_automatic_fail(self) -> None:
        class Scene:
            index = 1
            narration = "경구약을 복용하세요."
            caption_chunks = [narration]
            medical_claim = "oral medicine"
            prompt = "needleless oral dosing syringe"
            overlays = []

        class Spec:
            language = "ko"
            scenes = [Scene()]

        prompt = audit.build_prompt("test.ko", "source", Spec(), {})

        self.assertIn("Any syringe in or near a mouth is an automatic FAIL", prompt)
        self.assertIn("purpose-made dosing cup", prompt)

    def test_prompt_contains_submission_feedback_regressions(self) -> None:
        class Scene:
            index = 1
            narration = "Alternate medicines every 2 hours."
            caption_chunks = [narration]
            medical_claim = "high fever"
            prompt = "child resting"
            overlays = []

        class Spec:
            language = "en"
            scenes = [Scene()]

        prompt = audit.build_prompt("test.en", "source", Spec(), {})

        self.assertIn("INCOMPLETE_SPEECH", prompt)
        self.assertIn("CAPTION_OMISSION", prompt)
        self.assertIn("MEDICATION_TIMING_RISK", prompt)
        self.assertIn("normal recovery", prompt)
        self.assertIn("calibration_checks", prompt)
        self.assertIn("exactly ten scene_av_checks", prompt)
        self.assertIn("cut-off final syllable", prompt)

    def test_feedback_focus_detects_reviewer_risk_topics(self) -> None:
        class Scene:
            index = 1
            title = "고열"
            narration = "40도 고열에 해열제를 2시간마다 교차 복용합니다."
            medical_claim = "40°C fever"
            caption_chunks = [narration]

        class Spec:
            scenes = [Scene()]

        focus = audit.reviewer_feedback_focus(Spec())

        self.assertEqual(focus[0]["scene"], 1)
        self.assertIn("TWO_HOUR_ALTERNATING_MEDICINE", focus[0]["checks"])
        self.assertIn("VERY_HIGH_FEVER_40C", focus[0]["checks"])

    def test_schema_requires_ten_scene_av_checks(self) -> None:
        scene_checks = audit.AUDIT_SCHEMA["properties"]["scene_av_checks"]

        self.assertIn("scene_av_checks", audit.AUDIT_SCHEMA["required"])
        # Gemini's serving schema cannot efficiently compile a deeply nested array
        # with a fixed length. The exhaustive runner validates scenes 1..10 after response.
        self.assertNotIn("minItems", scene_checks)
        self.assertNotIn("maxItems", scene_checks)
        required = scene_checks["items"]["required"]
        self.assertIn("spoken_transcript", required)
        self.assertIn("visible_caption_transcript", required)
        self.assertIn("caption_timing_readable", required)

    def test_scene_log_requires_each_scene_once_in_order(self) -> None:
        valid = {"scene_av_checks": [{"scene": value} for value in range(1, 11)]}
        audit.validate_scene_av_checks(valid)

        duplicate = {"scene_av_checks": [{"scene": 1} for _ in range(10)]}
        with self.assertRaisesRegex(RuntimeError, "expected 1..10 exactly once"):
            audit.validate_scene_av_checks(duplicate)

    def test_aggregate_keeps_each_gemini_answer(self) -> None:
        results = [
            {
                "video_id": "article.ko",
                "overall_verdict": "WARN",
                "review_summary_ko": "검토 요약",
                "issues": [
                    {
                        "severity": "medium",
                        "category": "MEDICATION_ROUTE_ERROR",
                        "timestamp": "00:12",
                        "problem_ko": "경로 오류",
                        "recommended_fix_ko": "수정",
                    }
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            audit.write_aggregate(output, results, [], "test-model")
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            answers = (output / "gemini_answers.md").read_text(encoding="utf-8")

        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["issue_severity_counts"]["medium"], 1)
        self.assertIn("article.ko", answers)
        self.assertIn("경로 오류", answers)


if __name__ == "__main__":
    unittest.main()
