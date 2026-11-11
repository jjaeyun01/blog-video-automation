"""Conservatively adjudicate the 39 Gemini audits against their exact MP4 hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


GOOD_LOCAL = (
    "has_audio",
    "captions_equal_expected_narration",
    "all_caption_image_corners_transparent",
    "srt_semantically_expected_by_normalized_text",
    "srt_numbers_match_expected",
)
GOOD_MODEL = (
    "expected_narration_matches_audio",
    "visible_captions_match_audio",
    "speaker_voice_consistent",
)
BAD_MODEL = (
    "korean_hallucination_detected",
    "unexpected_generated_text_detected",
)
SCENE_CHECKS = (
    "speech_complete",
    "caption_covers_speech",
    "numbers_and_units_match",
    "declared_language_only",
    "caption_timing_readable",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decide(entry: dict, audit: dict | None) -> tuple[str, list[str]]:
    if audit is None:
        return "UNVERIFIED", ["Gemini 감사 응답 없음"]
    reasons: list[str] = []
    if audit.get("audit_metadata", {}).get("video_sha256") != entry["sha256"]:
        reasons.append("감사한 영상 해시가 현재 Revision 최종본과 다름")
    if audit.get("overall_verdict") != "PASS":
        reasons.append(f"Gemini 전체 판정: {audit.get('overall_verdict', 'MISSING')}")
    for key in ("medical_accuracy", "source_fidelity", "av_integrity"):
        if audit.get(key) != "PASS":
            reasons.append(f"{key}: {audit.get(key, 'MISSING')}")
    if audit.get("requires_human_medical_review") is not False:
        reasons.append("의료진 추가 검토 필요")
    for key in GOOD_MODEL:
        if audit.get(key) is not True:
            reasons.append(f"{key} 미통과 또는 미확인")
    for key in BAD_MODEL:
        if audit.get(key) is not False:
            reasons.append(f"{key} 감지 또는 미확인")
    local = audit.get("audit_metadata", {}).get("local_check", {})
    for key in GOOD_LOCAL:
        if local.get(key) is not True:
            reasons.append(f"로컬 검사 {key} 미통과")
    checks = audit.get("scene_av_checks", [])
    if [row.get("scene") for row in checks] != list(range(1, 11)):
        reasons.append("장면별 1~10 검사 기록 불완전")
    for row in checks:
        for key in SCENE_CHECKS:
            if row.get(key) is not True:
                reasons.append(f"장면 {row.get('scene')} {key} 미통과")
    if any(value == "FAIL" for key, value in audit.get("calibration_checks", {}).items() if key != "evidence_ko"):
        reasons.append("피드백 회귀 검사 FAIL")
    issues = audit.get("issues", [])
    material_issues = [issue for issue in issues if issue.get("severity") != "low"]
    if material_issues:
        reasons.append(f"Gemini 중간 이상 지적사항 {len(material_issues)}건")
    route_errors = [row for row in audit.get("medication_route_review", []) if row.get("is_error")]
    if route_errors:
        reasons.append(f"투약 경로 오류 {len(route_errors)}건")
    if not reasons:
        return "PASS", []
    severe = any(issue.get("severity") in {"critical", "high"} for issue in issues)
    if audit.get("overall_verdict") == "FAIL" or route_errors or severe:
        return "FAIL", reasons
    return "WARN", reasons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision-dir", type=Path, default=Path("Revision"))
    args = parser.parse_args()
    revision = args.revision_dir
    manifest_path = revision / "revision_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit_dir = revision / "final_audit"
    adjudications_path = audit_dir / "adjudications.json"
    adjudications = (
        json.loads(adjudications_path.read_text(encoding="utf-8"))
        if adjudications_path.exists() else {}
    )
    rows = []
    for entry in manifest["entries"]:
        video_id = f"{entry['slug']}.{entry['language']}"
        video_path = Path(entry["output_video"])
        path = audit_dir / "raw" / f"{video_id}.json"
        audit = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        status, reasons = decide(entry, audit)
        if not video_path.is_file():
            status, reasons = "UNVERIFIED", ["현재 Revision 영상 파일 없음"]
        elif sha256_file(video_path) != entry["sha256"]:
            status, reasons = "UNVERIFIED", ["현재 Revision 영상 해시가 감사 당시와 다름"]
        automatic_status = status
        adjudication = adjudications.get(video_id)
        if adjudication and status != "UNVERIFIED":
            basis = adjudication["basis"]
            if basis == "second_gemini":
                second_path = audit_dir / "adjudication_raw" / f"{video_id}.json"
                second = json.loads(second_path.read_text(encoding="utf-8"))
                if second.get("recommended_status") != adjudication["status"]:
                    raise ValueError(f"Second Gemini result disagrees with adjudication: {video_id}")
            elif basis == "verified_shared_visual":
                evidence = audit_dir / adjudication["evidence_image"]
                if not evidence.is_file():
                    raise FileNotFoundError(evidence)
            else:
                raise ValueError(f"Unknown adjudication basis: {basis}")
            status = adjudication["status"]
            reasons = [adjudication["reason_ko"]]
        entry["review_status"] = status
        entry["gemini_audit"] = str(path.resolve()) if path.exists() else None
        entry["adjudication"] = adjudication
        rows.append({
            "video_id": video_id,
            "status": status,
            "automatic_status": automatic_status,
            "gemini_verdict": audit.get("overall_verdict") if audit else None,
            "medical_accuracy": audit.get("medical_accuracy") if audit else None,
            "source_fidelity": audit.get("source_fidelity") if audit else None,
            "av_integrity": audit.get("av_integrity") if audit else None,
            "issue_count": len(audit.get("issues", [])) if audit else None,
            "reasons": reasons,
            "adjudication": adjudication,
            "video": entry["output_video"],
            "audit": str(path.resolve()) if path.exists() else None,
        })
    counts = dict(Counter(row["status"] for row in rows))
    first_model_counts = dict(Counter(row["gemini_verdict"] for row in rows))
    second_review_count = sum(row["adjudication"] is not None for row in rows)
    result = {"updated_at": datetime.now(timezone.utc).isoformat(), "target_count": len(rows), "counts": counts, "rows": rows, "meaning": "PASS는 Gemini 영상 의학·시청각 검사와 로컬 무결성 검사를 모두 통과한 자동 선별 판정이며 의사 승인은 아님"}
    result["first_gemini_counts"] = first_model_counts
    result["second_review_count"] = second_review_count
    (audit_dir / "final_pass_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Revision 영상 의학 재감사·최종 자동 판정",
        "",
        f"- 총 {len(rows)}편: " + ", ".join(f"{key} {counts.get(key, 0)}" for key in ("PASS", "WARN", "FAIL", "UNVERIFIED")),
        "- 1차 Gemini 원판정: " + ", ".join(f"{key} {first_model_counts.get(key, 0)}" for key in ("PASS", "WARN", "FAIL")) + f"; 이 중 {second_review_count}편은 별도 근거·2차 Gemini 재판정을 반영했습니다.",
        "- PASS는 Gemini 모델 및 로컬 검사의 자동 선별 결과이며 의사의 최종 승인을 대체하지 않습니다.",
        "- WARN·FAIL·UNVERIFIED 영상은 최종 PASS 영상으로 간주하지 않습니다.",
        "",
        "| 영상 | 최종 판정 | Gemini | 이슈 | 이유 |",
        "|---|---|---|---:|---|",
    ]
    for row in rows:
        reason = "; ".join(row["reasons"]).replace("|", "\\|")
        lines.append(f"| {row['video_id']} | {row['status']} | {row['gemini_verdict'] or '-'} | {row['issue_count'] if row['issue_count'] is not None else '-'} | {reason or '-'} |")
    lines.extend(["", "개별 원문 Gemini 답변은 `raw/`에, 전체 답변 모음은 `gemini_answers.md`에 있습니다.", ""])
    (audit_dir / "final_pass_report.md").write_text("\n".join(lines), encoding="utf-8")
    manifest["final_audit_summary"] = {"updated_at": result["updated_at"], "counts": counts, "report": str((audit_dir / "final_pass_report.md").resolve())}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
