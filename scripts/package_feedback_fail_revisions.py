"""Publish only successfully rebuilt human-FAIL videos into Revision/videos."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration", 0))
    if not video or not audio or not 55 <= duration <= 65:
        raise ValueError(f"Invalid final video/audio/duration: {path} ({duration:.1f}s)")
    width = int(video.get("width", 0))
    height = int(video.get("height", 0))
    if (width, height) not in {(720, 1280), (1080, 1920)}:
        raise ValueError(f"Invalid vertical dimensions: {path}")
    return {"duration_seconds": round(duration, 3), "video_codec": video.get("codec_name"), "audio_codec": audio.get("codec_name"), "width": width, "height": height}


def check_captions(job_dir: Path) -> dict:
    snapshot = json.loads((job_dir / "production.snapshot.json").read_text(encoding="utf-8"))
    scenes = snapshot.get("scenes", [])
    if len(scenes) != 10:
        raise ValueError(f"Expected 10 narration scenes: {job_dir}")
    for scene in scenes:
        narration = " ".join(scene["narration"].split())
        subtitle = " ".join(scene["subtitle"].split())
        chunks = " ".join(" ".join(scene.get("caption_chunks", [])).split())
        if narration != subtitle or narration != chunks:
            raise ValueError(f"Caption does not match narration in scene {scene['index']}: {job_dir}")
    captions = sorted((job_dir / "caption_images").glob("*.png"))
    if not captions:
        raise ValueError(f"No caption PNGs: {job_dir}")
    for path in captions:
        with Image.open(path).convert("RGBA") as frame:
            if any(frame.getpixel(point)[3] != 0 for point in ((0, 0), (frame.width - 1, 0), (0, frame.height - 1), (frame.width - 1, frame.height - 1))):
                raise ValueError(f"Caption PNG is not transparent at corners: {path}")
    return {"scene_count": len(scenes), "caption_images_checked": len(captions), "captions_match_narration": True, "transparent_caption_corners": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision-dir", type=Path, default=Path("Revision"))
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"))
    args = parser.parse_args()
    revision = args.revision_dir
    source = json.loads((revision / "feedback_fail_manifest.json").read_text(encoding="utf-8"))
    repairs = json.loads((revision / "repair_work" / "repair_manifest.json").read_text(encoding="utf-8"))
    output_dir = revision / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for target in source["targets"]:
        slug = target["slug"]
        language = target["language"]
        original = args.jobs_dir / slug / language / f"{slug}_{language.upper()}.mp4"
        rebuilt = revision / "work_jobs" / slug / language / original.name
        output = output_dir / original.name
        topic = repairs.get("results", {}).get(slug, {})
        entry = {"slug": slug, "language": language, "feedback": target["feedback"], "source_video": str(original.resolve()), "status": "PENDING"}
        try:
            if topic.get("status") != "REBUILT" or language not in topic.get("outputs", {}):
                raise RuntimeError(f"Topic build not complete: {topic.get('error', 'pending')}")
            if not rebuilt.is_file():
                raise FileNotFoundError(rebuilt)
            original_sha = sha256(original)
            rebuilt_sha = sha256(rebuilt)
            if original_sha == rebuilt_sha:
                raise RuntimeError("Rebuilt MP4 is byte-identical to the FAIL original")
            media = probe(rebuilt)
            caption_checks = check_captions(rebuilt.parent)
            if not output.exists() or sha256(output) != rebuilt_sha:
                temporary = output.with_suffix(".partial")
                shutil.copy2(rebuilt, temporary)
                temporary.replace(output)
            entry.update({"status": "REVISED", "output_video": str(output.resolve()), "sha256": rebuilt_sha, "original_sha256": original_sha, "media": media, "caption_checks": caption_checks, "review_status": "GEMINI_REAUDIT_PENDING"})
        except Exception as error:
            entry.update({"status": "ERROR", "error": str(error)})
        entries.append(entry)
        print(f"{entry['status']} {slug}.{language}", flush=True)
    manifest = {"updated_at": datetime.now(timezone.utc).isoformat(), "target_count": len(entries), "revised_count": sum(e["status"] == "REVISED" for e in entries), "entries": entries}
    (revision / "revision_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if manifest["revised_count"] != manifest["target_count"]:
        raise SystemExit(f"Packaged {manifest['revised_count']}/{manifest['target_count']} revised videos")


if __name__ == "__main__":
    main()
