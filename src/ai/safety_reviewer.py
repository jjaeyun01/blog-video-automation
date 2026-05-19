from __future__ import annotations

from src.models import VideoScript


class SafetyReviewer:
    BLOCKED_PHRASES = (
        "반드시 복용",
        "진단됩니다",
        "확실합니다",
        "병원에 가지 않아도 됩니다",
        "약을 중단하세요",
    )

    def review(self, script: VideoScript) -> list[str]:
        warnings: list[str] = []
        text = " ".join([script.narration, script.outro, script.disclaimer])
        for phrase in self.BLOCKED_PHRASES:
            if phrase in text:
                warnings.append(f"Potentially unsafe medical phrasing: {phrase}")
        if "진료를 대신하지 않습니다" not in text:
            warnings.append("Missing medical disclaimer.")
        return warnings
