from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image, ImageDraw

from fevercoach_shorts.settings import Settings


SHEET_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["slug", "verdict", "syringe_visible", "syringe_near_mouth", "issues", "summary_ko"],
    "properties": {
        "slug": {"type": "string"},
        "verdict": {"type": "string", "enum": ["PASS", "REVIEW", "FAIL"]},
        "syringe_visible": {"type": "boolean"},
        "syringe_near_mouth": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scene", "sample", "evidence_ko", "confidence"],
                "properties": {
                    "scene": {"type": "integer", "minimum": 1, "maximum": 10},
                    "sample": {"type": "integer", "minimum": 1, "maximum": 4},
                    "evidence_ko": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "summary_ko": {"type": "string"},
    },
}

VIDEO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["slug", "verdict", "syringe_visible", "syringe_near_mouth", "issues", "summary_ko"],
    "properties": {
        "slug": {"type": "string"},
        "verdict": {"type": "string", "enum": ["PASS", "REVIEW", "FAIL"]},
        "syringe_visible": {"type": "boolean"},
        "syringe_near_mouth": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scene", "timestamp", "evidence_ko", "confidence"],
                "properties": {
                    "scene": {"type": "integer", "minimum": 1, "maximum": 10},
                    "timestamp": {"type": "string"},
                    "evidence_ko": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "summary_ko": {"type": "string"},
    },
}

ROUTE_TERMS = re.compile(r"syringe|oral\s+syringe|주사기|투약기|jeringa", re.IGNORECASE)
_print_lock = threading.Lock()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect every shared FeverCoach Veo scene for a syringe in/near a mouth, "
            "then use full-video Gemini review for every candidate."
        )
    )
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/oral_syringe_visual_audit")
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--slugs", nargs="+", help="Optional topic ids to audit instead of every completed topic."
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sheet-only", action="store_true")
    parser.add_argument(
        "--full-video-all",
        action="store_true",
        help="Cross-check every selected topic as a complete video, even when its sheet passes.",
    )
    parser.add_argument("--keep-uploaded-files", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is required.")
    model = args.model or settings.gemini_audit_model
    output = args.output_dir
    for name in ("contact_sheets", "sheet_answers", "video_answers"):
        (output / name).mkdir(parents=True, exist_ok=True)

    topics = discover_topics(args.jobs_dir)
    if args.slugs:
        wanted = set(args.slugs)
        topics = [topic for topic in topics if topic[0] in wanted]
        missing = sorted(wanted - {topic[0] for topic in topics})
        if missing:
            raise SystemExit(f"Unknown or incomplete topic(s): {', '.join(missing)}")
    if not topics:
        raise SystemExit(f"No complete visual sets found under {args.jobs_dir}")
    print(f"Found {len(topics)} complete visual sets ({len(topics) * 10} scenes).", flush=True)

    sheet_results = run_parallel(
        topics,
        args.workers,
        lambda item: audit_contact_sheet(
            item, output, model, settings.gemini_api_key or "", args.force
        ),
        "SHEET",
    )
    write_progress(output, topics, sheet_results, [], model)

    video_topics = []
    if not args.sheet_only:
        for topic in topics:
            sheet = sheet_results.get(topic[0], {})
            if (
                args.full_video_all
                or prompt_mentions_syringe(topic[1])
                or sheet.get("verdict") != "PASS"
            ):
                video_topics.append(topic)
        print(
            f"Full-video cross-check queued for {len(video_topics)} candidate topic(s).",
            flush=True,
        )

    video_results = run_parallel(
        video_topics,
        min(args.workers, 3),
        lambda item: audit_full_video(
            item,
            output,
            model,
            settings.gemini_api_key or "",
            args.force,
            args.keep_uploaded_files,
        ),
        "VIDEO",
    )
    write_progress(output, topics, sheet_results, video_results, model)


def discover_topics(jobs_dir: Path) -> list[tuple[str, Path]]:
    topics: list[tuple[str, Path]] = []
    for clips_dir in sorted(jobs_dir.glob("*/visuals/clips")):
        clips = sorted(clips_dir.glob("scene_*.mp4"))
        if len(clips) == 10:
            topics.append((clips_dir.parents[1].name, clips_dir.parents[1]))
    return topics


def run_parallel(
    items: list[tuple[str, Path]],
    workers: int,
    work: Any,
    label: str,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not items:
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(work, item): item[0] for item in items}
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            slug = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {"slug": slug, "verdict": "ERROR", "error": str(error)}
            results[slug] = result
            with _print_lock:
                print(
                    f"{label} {index}/{len(items)} {slug}: {result.get('verdict')}",
                    flush=True,
                )
    return results


def audit_contact_sheet(
    topic: tuple[str, Path],
    output: Path,
    model: str,
    api_key: str,
    force: bool,
) -> dict[str, Any]:
    slug, job_dir = topic
    answer_path = output / "sheet_answers" / f"{slug}.json"
    if answer_path.exists() and not force:
        return json.loads(answer_path.read_text(encoding="utf-8"))
    sheet_path = output / "contact_sheets" / f"{slug}.jpg"
    if force or not sheet_path.exists():
        create_contact_sheet(job_dir / "visuals" / "clips", sheet_path)

    prompt = f"""You are visually auditing a pediatric health video contact sheet.
The sheet contains ten labeled scenes in order. Each scene has four chronological samples.
Topic id: {slug}

FeverCoach has a zero-tolerance publishing rule: ANY syringe, needleless oral dosing syringe,
medicine plunger, or syringe-shaped applicator inserted into, touching, pointed at, or immediately
beside a person's mouth is an automatic FAIL. A dosing cup, ordinary drinking cup, spoon, tablet,
inhaler, nasal spray, and thermometer are not syringes. An injection into skin/arm or an IV line is
not this specific error. Inspect all 40 samples carefully. Do not infer an object that is not visible.
Use REVIEW when an object near a mouth could plausibly be a syringe but the image is inconclusive.
Return only JSON. The scene/sample number must match the labels and left-to-right sample order.
"""
    client = genai.Client(api_key=api_key)
    image_part = types.Part.from_bytes(data=sheet_path.read_bytes(), mime_type="image/jpeg")
    result = generate_json(client, model, [image_part, prompt], SHEET_SCHEMA)
    result["slug"] = slug
    result["metadata"] = {
        "model": model,
        "contact_sheet": str(sheet_path.resolve()),
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }
    answer_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def audit_full_video(
    topic: tuple[str, Path],
    output: Path,
    model: str,
    api_key: str,
    force: bool,
    keep_uploaded: bool,
) -> dict[str, Any]:
    slug, job_dir = topic
    answer_path = output / "video_answers" / f"{slug}.json"
    if answer_path.exists() and not force:
        return json.loads(answer_path.read_text(encoding="utf-8"))
    video = representative_video(job_dir, slug)
    client = genai.Client(api_key=api_key)
    uploaded = None
    try:
        uploaded = upload_and_wait(client, video)
        prompt = f"""Watch this entire pediatric health video from first to last frame.
Topic id: {slug}. Ten scenes occupy approximately six seconds each.

This is a focused visual route audit. ANY syringe, needleless oral dosing syringe, medicine plunger,
or syringe-shaped applicator inserted into, touching, pointed at, or immediately beside a person's
mouth is an automatic FAIL, even if it is commonly sold for oral dosing. A dosing cup, ordinary cup,
spoon, tablet, inhaler, nasal spray, thermometer, injection into skin, and IV line are not this
specific error. Check motion between frames, not merely static keyframes. Report exact evidence and
timestamp. Do not infer a syringe when the object is not visible. Use REVIEW only for genuine visual
ambiguity. Return only JSON.
"""
        result = generate_json(client, model, [uploaded, prompt], VIDEO_SCHEMA)
        result["slug"] = slug
        result["metadata"] = {
            "model": model,
            "video": str(video.resolve()),
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }
        answer_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result
    finally:
        if uploaded is not None and not keep_uploaded:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass


def create_contact_sheet(clips_dir: Path, output: Path) -> None:
    tile_width, frame_height, label_height = 432, 384, 34
    tiles: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="fevercoach-syringe-") as temp_name:
        temp = Path(temp_name)
        for scene, clip in enumerate(sorted(clips_dir.glob("scene_*.mp4")), start=1):
            pattern = temp / f"scene_{scene:02d}_%02d.jpg"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(clip),
                    "-vf", "fps=2/3,scale=216:384:force_original_aspect_ratio=decrease,"
                    "pad=216:384:(ow-iw)/2:(oh-ih)/2:black",
                    "-frames:v", "4", str(pattern),
                ],
                check=True,
            )
            frames = sorted(temp.glob(f"scene_{scene:02d}_*.jpg"))
            if len(frames) != 4:
                raise RuntimeError(f"Expected 4 samples from {clip}, found {len(frames)}")
            tile = Image.new("RGB", (tile_width, label_height + frame_height * 2), "white")
            draw = ImageDraw.Draw(tile)
            draw.text((8, 8), f"SCENE {scene:02d}   samples 1-4", fill="black")
            for sample, frame in enumerate(frames):
                with Image.open(frame).convert("RGB") as image:
                    x = (sample % 2) * 216
                    y = label_height + (sample // 2) * frame_height
                    tile.paste(image, (x, y))
            tiles.append(tile)
    sheet = Image.new("RGB", (tile_width * 5, (label_height + frame_height * 2) * 2), "white")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % 5) * tile_width, (index // 5) * tile.height))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "JPEG", quality=88, optimize=True)


def prompt_mentions_syringe(job_dir: Path) -> bool:
    paths = sorted(job_dir.glob("*/production.snapshot.json"))
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for scene in data.get("scenes", []):
            positive = " ".join(
                str(scene.get(key, ""))
                for key in ("prompt", "asset_prompt", "medical_claim", "narration")
            )
            if ROUTE_TERMS.search(positive):
                return True
    return False


def representative_video(job_dir: Path, slug: str) -> Path:
    preferred = [
        job_dir / "ko" / f"{slug}_KO.mp4",
        job_dir / "en" / f"{slug}_EN.mp4",
        job_dir / "es" / f"{slug}_ES.mp4",
    ]
    for path in preferred:
        if path.exists():
            return path
    for language in ("ko", "en", "es"):
        videos = sorted((job_dir / language).glob("*.mp4"))
        if videos:
            return videos[0]
    raise FileNotFoundError(f"No representative final video for {slug}")


def upload_and_wait(client: genai.Client, path: Path) -> Any:
    uploaded = client.files.upload(
        file=path, config=types.UploadFileConfig(mime_type="video/mp4")
    )
    while str(getattr(uploaded, "state", "")) in {"FileState.PROCESSING", "PROCESSING"}:
        time.sleep(4)
        uploaded = client.files.get(name=uploaded.name)
    if str(getattr(uploaded, "state", "")) in {"FileState.FAILED", "FAILED"}:
        raise RuntimeError(f"Gemini file processing failed for {path}")
    return uploaded


def generate_json(
    client: genai.Client,
    model: str,
    contents: list[Any],
    schema: dict[str, Any],
    attempts: int = 4,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    temperature=0,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned an empty response")
            return json.loads(response.text)
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Gemini audit failed after {attempts} attempts: {last_error}")


def write_progress(
    output: Path,
    topics: list[tuple[str, Path]],
    sheet_results: dict[str, dict[str, Any]],
    video_results: dict[str, dict[str, Any]] | list[Any],
    model: str,
) -> None:
    if isinstance(video_results, list):
        video_results = {}
    rows = []
    for slug, _ in topics:
        sheet = sheet_results.get(slug, {})
        video = video_results.get(slug, {})
        final = video if video else sheet
        rows.append(
            {
                "slug": slug,
                "sheet_verdict": sheet.get("verdict", "NOT_RUN"),
                "video_verdict": video.get("verdict", "NOT_RUN"),
                "final_verdict": final.get("verdict", "NOT_RUN"),
                "issues": final.get("issues", []),
                "summary_ko": final.get("summary_ko", ""),
            }
        )
    summary = {
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic_count": len(topics),
        "scene_count": len(topics) * 10,
        "counts": dict(Counter(row["final_verdict"] for row in rows)),
        "results": rows,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 입 주변 주사기 전수검사 — Gemini 답변",
        "",
        f"- 모델: `{model}`",
        f"- 주제: {len(topics)}개",
        f"- 실제 Veo 장면: {len(topics) * 10}개",
        f"- 집계: {json.dumps(summary['counts'], ensure_ascii=False)}",
        "",
        "| 주제 | 접촉시트 | 완성 영상 교차검증 | 최종 | Gemini 요약 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        text = str(row["summary_ko"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {row['slug']} | {row['sheet_verdict']} | {row['video_verdict']} | "
            f"{row['final_verdict']} | {text} |"
        )
        for issue in row["issues"]:
            lines.append(
                f"| ↳ scene {issue.get('scene', '?')} |  | {issue.get('timestamp', '')} |  | "
                f"{str(issue.get('evidence_ko', '')).replace('|', chr(92) + '|')} |"
            )
    (output / "gemini_answers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
