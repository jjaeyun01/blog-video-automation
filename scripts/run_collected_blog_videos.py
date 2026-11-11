"""Resume source-language Shorts production from the collected KO/EN/ES URL lists."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import traceback
import urllib.request
import urllib.error

from fevercoach_shorts.article import load_article
from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.pipeline import ShortsPipeline
from fevercoach_shorts.planner import ScenePlanner
from fevercoach_shorts.review_rules import REVIEW_GUIDELINE_VERSION
from fevercoach_shorts.settings import Settings

from crawl_fevercoach_blog import post_url


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(links_dir: Path, batch_dir: Path) -> dict:
    manifest_path = batch_dir / "manifest.json"
    if manifest_path.exists():
        return read_json(manifest_path)
    lists = {}
    inputs = {}
    for language, relative in (("ko", "blog_links.json"), ("en", "en/blog_links.json"), ("es", "es/blog_links.json")):
        path = links_dir / relative
        source = read_json(path)
        if source.get("status") != "ok":
            raise ValueError(f"Link collection is incomplete: {path}")
        unique = {}
        for row in source["posts"]:
            url = post_url(row["url"], language=language)
            if not url:
                raise ValueError(f"Wrong language URL in {path}: {row['url']}")
            key = f"collected-{language}-{hashlib.sha256(url.encode()).hexdigest()[:16]}"
            unique[url] = {"key": key, "url": url, "language": language,
                           "last_modified": row.get("last_modified"), "listed_title": row.get("title")}
        lists[language] = sorted(unique.values(), key=lambda r: (r["last_modified"] or "", r["url"]), reverse=True)
        inputs[language] = {"path": str(path.resolve()), "sha256": sha256(path), "count": len(unique)}
    # Each URL creates exactly one video in its own language. Round-robin exposes
    # problems in all three language paths early, rather than after 1,000 builds.
    tasks = []
    for index in range(max(map(len, lists.values()))):
        for language in ("ko", "en", "es"):
            if index < len(lists[language]):
                tasks.append(lists[language][index])
    manifest = {"created_at": now(), "review_guideline_version": REVIEW_GUIDELINE_VERSION,
                "inputs": inputs, "total": len(tasks), "tasks": tasks,
                "policy": "One source-language video per collected URL; latest-modified first within each language."}
    write_json(manifest_path, manifest)
    return manifest


def current_pass(video: Path, report: dict, model: str) -> bool:
    metadata = report.get("audit_metadata", {})
    return (video.is_file() and report.get("overall_verdict") == "PASS"
            and metadata.get("review_guideline_version") == REVIEW_GUIDELINE_VERSION
            and metadata.get("model") == model
            and metadata.get("video_sha256") == sha256(video))


def delivery_name(title: str, key: str, language: str) -> str:
    title = re.sub(r"[\x00-\x1f/\\:*?\"<>|]", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .") or key
    # Stay below filesystem byte limits even for long Korean titles.
    title = title.encode("utf-8")[:160].decode("utf-8", errors="ignore").rstrip(" .")
    return f"{title}_{key.rsplit('-', 1)[-1][:8]}_{language.upper()}.mp4"


def record_path(batch_dir: Path, video: Path, suffix: str) -> Path:
    return (batch_dir / "delivery_records" / video.relative_to(batch_dir / "completed")).with_suffix(suffix)


def organize_completed(batch_dir: Path) -> int:
    """Move non-video files without overwriting existing records or touching videos."""
    moved = 0
    for source in sorted((batch_dir / "completed").rglob("*")):
        if not source.is_file() or source.suffix.lower() == ".mp4":
            continue
        destination = batch_dir / "delivery_records" / source.relative_to(batch_dir / "completed")
        if destination.exists():
            raise ValueError(f"Record already exists; refusing to overwrite: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        moved += 1
    return moved


def package(batch_dir: Path, task: dict, config: Path, video: Path, settings: Settings) -> dict:
    report_path = video.parent / "audit" / "final_report.json"
    report = read_json(report_path)
    if not current_pass(video, report, settings.gemini_audit_model):
        raise ValueError(f"Final video lacks a current, hash-matched PASS: {report_path}")
    spec = ProductionSpec.load(config, check_files=False)
    destination = batch_dir / "completed" / task["language"] / delivery_name(spec.title, task["key"], task["language"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256(destination) != sha256(video):
            raise ValueError(f"Different completed file already exists: {destination}")
    else:
        # Same-volume hardlink avoids keeping two large copies of every final.
        try:
            os.link(video, destination)
        except OSError:
            shutil.copy2(video, destination)
    delivery = {"source_url": task["url"], "language": task["language"], "title": spec.title,
                "file": str(destination.resolve()), "sha256": sha256(destination),
                "verdict": "PASS", "review_guideline_version": REVIEW_GUIDELINE_VERSION,
                "config": str(config.resolve()), "job_video": str(video.resolve()), "completed_at": now()}
    write_json(record_path(batch_dir, destination, ".audit.json"), report)
    write_json(record_path(batch_dir, destination, ".delivery.json"), delivery)
    return delivery


def api_blocker(error: Exception) -> bool:
    message = str(error).lower()
    return any(term in message for term in (
        "api_key_invalid", "api key not valid", "permission_denied", "unauthenticated",
        "resource_exhausted", "quota", "429", "billing", "insufficient credits",
        "model is not found", "not found for api version",
    ))


def failure_category(message: str) -> str:
    text = message.lower()
    if api_blocker(RuntimeError(message)):
        return "api_blocked"
    if any(term in text for term in ("nodename", "connection", "timed out", "broken pipe", "connecterror", "name resolution")):
        return "network"
    if "narration is" in text and "timeline" in text:
        return "tts_length"
    if "reference image" in text:
        return "reference_safety"
    if "without a generated video" in text or "returned no asset" in text:
        return "empty_generation"
    if any(term in text for term in ("invalid production spec", "medical copy review failed")):
        return "plan_validation"
    return "manual_review"


def analyze_failures(batch_dir: Path) -> dict:
    state = read_json(batch_dir / "status.json")
    items = [{"key": key, "language": item["language"],
              "category": failure_category(item.get("error", "")),
              "error": item.get("error", ""), "retry_attempts": item.get("retry_attempts", 0)}
             for key, item in state["items"].items() if item["status"] in {"FAILED", "NEEDS_REVIEW", "BLOCKED_API"}]
    report = {"created_at": now(), "counts": dict(Counter(item["category"] for item in items)), "items": items}
    write_json(batch_dir / "failure_analysis.json", report)
    return report


def check_network() -> None:
    # An HTTP error still proves DNS/TLS/connectivity; no generation or API key is used.
    try:
        with urllib.request.urlopen("https://generativelanguage.googleapis.com/", timeout=20):
            pass
    except urllib.error.HTTPError:
        pass


def run(batch_dir: Path, *, min_free_gb: float, max_items: int | None, retry_failed: bool) -> int:
    manifest = read_json(batch_dir / "manifest.json")
    status_path = batch_dir / "status.json"
    state = read_json(status_path) if status_path.exists() else {"items": {}, "created_at": now()}
    # The exclusive worker lock proves old in-flight stages are interrupted work.
    for item in state["items"].values():
        if item.get("status") in {"PLANNING", "BUILDING"}:
            item["status"] = "PENDING"
    settings = replace(Settings.from_env(), jobs_dir=(batch_dir / "jobs").resolve())
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is required")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("ffmpeg and ffprobe are required")
    planner, pipeline = ScenePlanner(settings), ShortsPipeline(settings)
    state.update(worker_pid=os.getpid(), review_guideline_version=REVIEW_GUIDELINE_VERSION)

    def persist(status: str, active: str | None = None) -> None:
        counts = Counter(item.get("status", "PENDING") for item in state["items"].values())
        counts["PENDING"] += manifest["total"] - len(state["items"])
        state.update(status=status, active_key=active, updated_at=now(), counts=dict(counts), total=manifest["total"])
        write_json(status_path, state)

    persist("RUNNING")
    processed = 0
    consecutive_network_failures = 0
    if retry_failed:
        report = analyze_failures(batch_dir)
        print(f"FAILURE ANALYSIS: {report['counts']}", flush=True)
        try:
            check_network()
        except (OSError, urllib.error.URLError) as error:
            state["blocker"] = f"Network preflight failed: {error}"
            persist("BLOCKED_NETWORK")
            return 2
    for task in manifest["tasks"]:
        key, language = task["key"], task["language"]
        item = state["items"].setdefault(key, {"language": language, "url": task["url"], "status": "PENDING"})
        if item["status"] == "PASS":
            try:
                delivery = item["delivery"]
                video = Path(delivery["file"])
                audit_path = record_path(batch_dir, video, ".audit.json")
                if not audit_path.exists():
                    audit_path = video.with_suffix(".audit.json")  # Legacy layout.
                if not video.exists():
                    archived = batch_dir / "previous_completed" / video.relative_to(batch_dir / "completed")
                    if archived.is_file():
                        video = archived
                if current_pass(video, read_json(audit_path), settings.gemini_audit_model):
                    continue
            except (OSError, KeyError, ValueError):
                pass
            item["status"] = "PENDING"
        if item["status"] in {"FAILED", "NEEDS_REVIEW"} and not retry_failed:
            continue
        retry_category = None
        if retry_failed and item["status"] in {"FAILED", "NEEDS_REVIEW", "BLOCKED_API"}:
            retry_category = failure_category(item.get("error", ""))
            if retry_category in {"manual_review", "api_blocked"} or item.get("retry_attempts", 0) >= 3:
                item["retry_hold"] = retry_category if retry_category in {"manual_review", "api_blocked"} else "attempt_limit"
                continue
        if max_items is not None and processed >= max_items:
            persist("STOPPED_AT_ITEM_LIMIT")
            return 0
        free_gb = shutil.disk_usage(batch_dir).free / 1e9
        if free_gb < min_free_gb:
            state["blocker"] = f"Free disk {free_gb:.1f} GB below reserve {min_free_gb:.1f} GB"
            persist("BLOCKED_DISK")
            print(state["blocker"], flush=True)
            return 2
        config = batch_dir / "configs" / f"{key}.production.{language}.json"
        try:
            if retry_category:
                history = item.setdefault("retry_history", [])
                history.append({"at": now(), "category": retry_category, "previous_error": item.get("error", "")})
                item["retry_attempts"] = item.get("retry_attempts", 0) + 1
                persist("RUNNING", key)
            plan_current = False
            feedback = None
            if config.exists():
                try:
                    existing = ProductionSpec.load(config, check_files=False)
                    plan_current = (existing.source == task["url"] and existing.language == language
                                    and existing.slug == key
                                    and existing.metadata.get("batch_review_guideline_version") == REVIEW_GUIDELINE_VERSION)
                except (OSError, KeyError, ValueError) as error:
                    feedback = str(error)  # Repair invalid interrupted plans before building.
            if retry_category in {"tts_length", "reference_safety", "plan_validation"}:
                plan_current = False
                feedback = ("Previous completed attempt failed: " + item.get("error", "") +
                            "\nCorrect this cause without inventing medical facts or removing safety qualifiers. "
                            "Keep captions identical to narration. Fit each scene's actual speech budget. "
                            "Use blank displays and medically safe, source-supported visuals.")
                if config.exists():
                    backup = batch_dir / "retry_backups" / key / f"attempt_{item['retry_attempts']}.json"
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(config, backup)
            if not plan_current:
                item.update(status="PLANNING", started_at=now())
                persist("RUNNING", key)
                print(f"PLANNING [{language}] {task['url']}", flush=True)
                article = load_article(url=task["url"])
                source_dir = batch_dir / "sources"
                source_dir.mkdir(parents=True, exist_ok=True)
                write_json(source_dir / f"{key}.json", {"url": article.source, "title": article.title,
                           "text": article.text, "fetched_at": now()})
                base = batch_dir / "configs" / f"{key}.production.json"
                for attempt in range(1, 4):
                    try:
                        results = planner.create_multilingual(
                            article, None, base, (language,), validation_feedback=feedback
                        )
                        break
                    except ValueError as error:
                        if attempt == 3:
                            raise
                        feedback = str(error)
                        print(f"REPLAN [{language}] {key}: {feedback}", flush=True)
                generated, spec = results[language]
                spec = replace(spec, slug=key, metadata={**spec.metadata,
                    "batch_review_guideline_version": REVIEW_GUIDELINE_VERSION,
                    "batch_source_sha256": hashlib.sha256(article.text.encode()).hexdigest()})
                spec.save(generated)
            item.update(status="BUILDING", config=str(config.resolve()))
            persist("RUNNING", key)
            print(f"BUILDING [{language}] {key}", flush=True)
            spec = ProductionSpec.load(config, check_files=False)
            video = settings.jobs_dir / key / language / spec.final_video_filename
            report_path = video.parent / "audit" / "final_report.json"
            reusable = False
            if report_path.exists():
                reusable = current_pass(video, read_json(report_path), settings.gemini_audit_model)
            if not reusable:
                video = pipeline.build(config, tts_provider="gemini")
            item.update(status="PASS", delivery=package(batch_dir, task, config, video, settings), finished_at=now())
            consecutive_network_failures = 0
            print(f"PASS [{language}] {item['delivery']['file']}", flush=True)
        except Exception as error:
            message = str(error).replace(settings.gemini_api_key, "[REDACTED]")
            item.update(status="FAILED", error=message, finished_at=now())
            item["failure_category"] = failure_category(message)
            consecutive_network_failures = consecutive_network_failures + 1 if item["failure_category"] == "network" else 0
            print(f"FAILED [{language}] {key}: {message}", flush=True)
            log = batch_dir / "errors" / f"{key}.txt"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc().replace(settings.gemini_api_key, "[REDACTED]"), encoding="utf-8")
            if consecutive_network_failures >= 3:
                state["blocker"] = "Three consecutive network failures; stopped to prevent mass failures."
                persist("BLOCKED_NETWORK", key)
                return 2
            if api_blocker(error):
                item["status"] = "BLOCKED_API"
                state["blocker"] = message
                persist("BLOCKED_API", key)
                return 2
        processed += 1
        persist("RUNNING")
    failures = [item for item in state["items"].values() if item["status"] != "PASS"]
    persist("NEEDS_ATTENTION" if failures else "COMPLETE")
    return 2 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "status", "organize", "analyze"])
    parser.add_argument("--links-dir", type=Path, default=Path("outputs/blog_links_2026-10-10"))
    parser.add_argument("--batch-dir", type=Path, default=Path("outputs/collected_blog_videos_2026-10-10"))
    parser.add_argument("--min-free-gb", type=float, default=8)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    if args.min_free_gb < 1 or (args.max_items is not None and args.max_items < 1):
        parser.error("--min-free-gb must be >=1; --max-items must be positive")
    args.batch_dir = args.batch_dir.resolve()
    args.batch_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "status":
        path = args.batch_dir / "status.json"
        if not path.exists():
            print("No worker status yet")
            return 0
        state = read_json(path)
        print(json.dumps({k: v for k, v in state.items() if k != "items"}, ensure_ascii=False, indent=2))
        return 0
    with (args.batch_dir / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("A worker is already active for this batch")
        if args.command == "analyze":
            print(json.dumps(analyze_failures(args.batch_dir)["counts"], ensure_ascii=False, indent=2))
            return 0
        if args.command == "organize":
            print(json.dumps({"moved_records": organize_completed(args.batch_dir)}))
            return 0
        organize_completed(args.batch_dir)
        if args.command == "prepare":
            manifest = prepare(args.links_dir.resolve(), args.batch_dir)
            print(json.dumps({"total": manifest["total"], "languages": {k: v["count"] for k, v in manifest["inputs"].items()},
                              "manifest": str(args.batch_dir / "manifest.json")}, indent=2))
            return 0
        return run(args.batch_dir, min_free_gb=args.min_free_gb, max_items=args.max_items,
                   retry_failed=args.retry_failed)


if __name__ == "__main__":
    raise SystemExit(main())
