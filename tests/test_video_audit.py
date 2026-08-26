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
    def test_prompt_distinguishes_oral_syringe_from_injection(self) -> None:
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

        self.assertIn("needleless oral dosing syringe", prompt)
        self.assertIn("must not be called an injection", prompt)

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
