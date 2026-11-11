from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect final videos and their persisted Gemini medical-audit answers."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    settings = Settings.from_env()
    if args.jobs_dir:
        settings = replace(settings, jobs_dir=args.jobs_dir)
    rows: list[dict[str, Any]] = []
    answers: list[dict[str, Any]] = []

    for post in manifest["posts"]:
        for language in manifest.get("languages", ["ko", "en", "es"]):
            video_id = f"{post['key']}.{language}"
            config_path = args.config_dir / f"{post['key']}.production.{language}.json"
            spec = ProductionSpec.load(config_path, check_files=False)
            job_dir = settings.jobs_dir / spec.slug / language
            video_path = job_dir / spec.final_video_filename
            report_path = job_dir / "audit" / "final_report.json"
            snapshot_path = job_dir / "production.snapshot.json"

            report = _read_json(report_path)
            snapshot = _read_json(snapshot_path)
            media = _probe(video_path) if video_path.exists() else {}
            current_config = snapshot == spec.to_dict()
            verdict = str(report.get("overall_verdict", "MISSING")).upper()
            technical_pass = (
                media.get("width") == 1080
                and media.get("height") == 1920
                and media.get("has_audio") is True
                and 59.8 <= float(media.get("duration_seconds", 0)) <= 60.2
            )
            ready = video_path.exists() and current_config and verdict == "PASS" and technical_pass
            rows.append(
                {
                    "video_id": video_id,
                    "post_key": post["key"],
                    "source_url": post["url"],
                    "language": language,
                    "title": spec.title,
                    "slug": spec.slug,
                    "video": str(video_path.resolve()),
                    "config": str(config_path.resolve()),
                    "gemini_report": str(report_path.resolve()),
                    "verdict": verdict,
                    "current_config": current_config,
                    "technical_pass": technical_pass,
                    "ready": ready,
                    "media": media,
                }
            )
            if report:
                answers.append({"video_id": video_id, "answer": report})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    verdicts = Counter(row["verdict"] for row in rows)
    summary = {
        "expected": len(manifest["posts"]) * len(manifest.get("languages", ["ko", "en", "es"])),
        "ready": sum(row["ready"] for row in rows),
        "verdict_counts": dict(verdicts),
        "videos": rows,
    }
    _write_json(args.output_dir / "delivery_manifest.json", summary)
    _write_json(args.output_dir / "gemini_answers.json", answers)
    (args.output_dir / "gemini_answers.md").write_text(
        _answers_markdown(rows, answers), encoding="utf-8"
    )

    print(
        f"READY {summary['ready']}/{summary['expected']} | verdicts={dict(verdicts)} | "
        f"output={args.output_dir}",
        flush=True,
    )
    if summary["ready"] != summary["expected"]:
        raise SystemExit("Batch is not ready; inspect delivery_manifest.json.")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _probe(path: Path) -> dict[str, Any]:
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,width,height", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(probe.stdout)
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    return {
        "duration_seconds": float(data.get("format", {}).get("duration", 0)),
        "width": video.get("width"),
        "height": video.get("height"),
        "has_audio": any(item.get("codec_type") == "audio" for item in streams),
    }


def _answers_markdown(
    rows: list[dict[str, Any]], answers: list[dict[str, Any]]
) -> str:
    by_id = {item["video_id"]: item["answer"] for item in answers}
    lines = [
        "# Gemini 최종 의료·영상 감사 답변",
        "",
        "> 이 결과는 자동 선별 감사이며 게시 전 소아청소년과 전문의의 최종 검수를 대체하지 않습니다.",
        "",
    ]
    for row in rows:
        answer = by_id.get(row["video_id"], {})
        lines.extend(
            [
                f"## {row['video_id']} — {row['verdict']}",
                "",
                str(answer.get("review_summary_ko", "Gemini 최종 답변 없음")),
                "",
            ]
        )
        issues = answer.get("issues", [])
        if not issues:
            lines.append("- 감지된 이슈 없음")
        for issue in issues:
            lines.append(
                f"- {issue.get('severity', 'unknown')} / {issue.get('category', 'unknown')} / "
                f"{issue.get('timestamp', '시간 미상')}: {issue.get('problem_ko', '')}"
            )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
