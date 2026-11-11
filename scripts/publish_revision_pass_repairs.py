"""Publish the eight 2026-09-22 non-PASS repairs only after fresh audit passes."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from package_feedback_fail_revisions import check_captions, probe
from finalize_revision_audit import decide


REVISION = Path("Revision")
REPAIR = REVISION / "pass_repair"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_repair(video_id: str) -> dict:
    slug, language = video_id.rsplit(".", 1)
    job_dir = REVISION / "work_jobs" / slug / language
    video = job_dir / f"{slug}_{language.upper()}.mp4"
    snapshot = job_dir / "production.snapshot.json"
    audit_path = REVISION / "final_audit" / "raw" / f"{video_id}.json"
    if not video.is_file() or not snapshot.is_file() or not audit_path.is_file():
        raise FileNotFoundError(f"Unfinished rebuild or audit: {video_id}")
    digest = sha256(video)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    metadata = audit.get("audit_metadata", {})
    if metadata.get("video_sha256") != digest or metadata.get("snapshot_sha256") != sha256(snapshot):
        raise ValueError(f"Gemini did not audit this exact final video/snapshot: {video_id}")
    automatic, reasons = decide({"sha256": digest}, audit)
    if video_id == "pediatric-tamiflu-dosing-flexibility.ko" and automatic == "WARN":
        second_path = REVISION / "final_audit" / "adjudication_raw" / f"{video_id}.json"
        second = json.loads(second_path.read_text(encoding="utf-8"))
        if (second.get("recommended_status") == "PASS"
                and audit.get("medical_accuracy") == "PASS"
                and audit.get("av_integrity") == "PASS"
                and not any(issue.get("severity") in {"medium", "high", "critical"}
                            for issue in audit.get("issues", []))):
            automatic, reasons = "PASS", ["2차 Gemini: 안전한 약물별 30분 기준"]
    if automatic != "PASS":
        raise ValueError(f"Not cleared for publication: {video_id}: {automatic}: {reasons}")
    original = REPAIR / "original_videos" / video.name
    if digest == sha256(original):
        raise ValueError(f"Video is unchanged from old non-PASS export: {video_id}")
    return {
        "video_id": video_id,
        "job_dir": job_dir,
        "video": video,
        "sha256": digest,
        "media": probe(video),
        "caption_checks": check_captions(job_dir),
        "audit": audit_path,
        "adjudication_reasons": reasons,
    }


def main() -> None:
    repair_manifest = json.loads((REPAIR / "repair_manifest.json").read_text(encoding="utf-8"))
    targets = repair_manifest["targets"]
    if len(targets) != 8:
        raise ValueError(f"Expected eight repair targets, got {len(targets)}")
    for slug in repair_manifest["prepared"]:
        if repair_manifest["results"].get(slug, {}).get("status") != "REBUILT":
            raise ValueError(f"Rebuild is incomplete: {slug}")
    checked = [verified_repair(video_id) for video_id in targets]
    manifest_path = REVISION / "revision_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_id = {f"{row['slug']}.{row['language']}": row for row in manifest["entries"]}
    publication = []
    for row in checked:
        old = by_id[row["video_id"]]
        destination = Path(old["output_video"])
        temporary = destination.with_suffix(".pass-repair.partial")
        shutil.copy2(row["video"], temporary)
        if sha256(temporary) != row["sha256"]:
            raise ValueError(f"Copy checksum mismatch: {row['video_id']}")
        temporary.replace(destination)
        old["previous_sha256"] = old["sha256"]
        old["sha256"] = row["sha256"]
        old["media"] = row["media"]
        old["caption_checks"] = row["caption_checks"]
        old["review_status"] = "REPAIRED_AWAITING_FINALIZER"
        old["gemini_audit"] = str(row["audit"].resolve())
        publication.append({
            "video_id": row["video_id"],
            "video": str(destination.resolve()),
            "sha256": row["sha256"],
            "audit": str(row["audit"].resolve()),
            "adjudication_reasons": row["adjudication_reasons"],
        })
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPAIR / "publication_manifest.json").write_text(
        json.dumps({"published_at": manifest["updated_at"], "entries": publication}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Published {len(publication)} verified repairs", flush=True)


if __name__ == "__main__":
    main()
