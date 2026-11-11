from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("message,category", [
    ("[Errno 8] nodename nor servname provided", "network"),
    ("Scene 2 narration is 10s but the timeline is 6s", "tts_length"),
    ("Scene 9 reference image has a high medical safety risk", "reference_safety"),
    ("Scene 8 completed without a generated video.", "empty_generation"),
    ("Medical copy review failed: unsafe phrase", "plan_validation"),
    ("429 quota", "api_blocked"),
    ("unknown failure", "manual_review"),
])
def test_failure_classification(worker, message, category):
    assert worker.failure_category(message) == category


def test_analysis_preserves_pass_and_errors(worker, tmp_path):
    state = {"items": {"ok": {"status": "PASS", "language": "ko"},
                       "bad": {"status": "FAILED", "language": "en", "error": "Connection reset by peer"}}}
    worker.write_json(tmp_path / "status.json", state)
    report = worker.analyze_failures(tmp_path)
    assert report["counts"] == {"network": 1}
    assert worker.read_json(tmp_path / "status.json") == state


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return importlib.import_module("run_collected_blog_videos")


def test_manifest_creates_one_video_per_source_language_and_resumes(worker, tmp_path):
    links, batch = tmp_path / "links", tmp_path / "batch"
    for lang, relative, prefix in (("ko", "blog_links.json", "/ko/post/"),
                                   ("en", "en/blog_links.json", "/post/"),
                                   ("es", "es/blog_links.json", "/es/post/")):
        worker.write_json(links / relative, {"status": "ok", "posts": [
            {"url": "https://www.fevercoach.us" + prefix + "a", "last_modified": "2026-10-10"},
            {"url": "https://www.fevercoach.us" + prefix + "a?tracking=x"},
        ]})
    manifest = worker.prepare(links, batch)
    assert manifest["total"] == 3
    assert [t["language"] for t in manifest["tasks"]] == ["ko", "en", "es"]
    assert len({t["key"] for t in manifest["tasks"]}) == 3
    assert worker.prepare(tmp_path / "missing", batch) == manifest


def test_partial_or_wrong_language_input_is_rejected(worker, tmp_path):
    links = tmp_path / "links"
    path = links / "blog_links.json"
    worker.write_json(path, {"status": "partial", "posts": []})
    with pytest.raises(ValueError, match="incomplete"):
        worker.prepare(links, tmp_path / "batch")
    worker.write_json(path, {"status": "ok", "posts": [{"url": "https://www.fevercoach.us/post/en"}]})
    with pytest.raises(ValueError, match="Wrong language"):
        worker.prepare(links, tmp_path / "batch")


def test_delivery_gate_requires_current_pass_and_exact_bytes(worker, tmp_path):
    video = tmp_path / "test.mp4"
    video.write_bytes(b"completed-video")
    report = {"overall_verdict": "PASS", "audit_metadata": {
        "review_guideline_version": worker.REVIEW_GUIDELINE_VERSION,
        "model": "audit-model", "video_sha256": worker.sha256(video),
    }}
    assert worker.current_pass(video, report, "audit-model")
    assert not worker.current_pass(video, {**report, "overall_verdict": "WARN"}, "audit-model")
    assert not worker.current_pass(video, report, "old-model")
    video.write_bytes(b"changed-video")
    assert not worker.current_pass(video, report, "audit-model")


def test_organize_keeps_video_and_preserves_records(worker, tmp_path):
    folder = tmp_path / "completed" / "ko"
    folder.mkdir(parents=True)
    video = folder / "title_KO.mp4"
    video.write_bytes(b"video")
    report = video.with_suffix(".audit.json")
    report.write_text('{"overall_verdict":"PASS"}')
    assert worker.organize_completed(tmp_path) == 1
    assert video.read_bytes() == b"video"
    relocated = worker.record_path(tmp_path, video, ".audit.json")
    assert worker.read_json(relocated)["overall_verdict"] == "PASS"
    assert list(folder.iterdir()) == [video]
    assert worker.organize_completed(tmp_path) == 0


def test_organize_refuses_overwriting_records(worker, tmp_path):
    source = tmp_path / "completed" / "en" / "title.audit.json"
    worker.write_json(source, {"old": True})
    target = tmp_path / "delivery_records" / "en" / source.name
    worker.write_json(target, {"new": True})
    with pytest.raises(ValueError, match="refusing to overwrite"):
        worker.organize_completed(tmp_path)
    assert source.exists()


def test_api_blocker_stops_without_attempting_thousands_of_failing_jobs(worker, monkeypatch, tmp_path):
    from dataclasses import replace
    settings = replace(worker.Settings.from_env(), gemini_api_key="test-key")
    monkeypatch.setattr(worker.Settings, "from_env", lambda: settings)
    calls = []

    class Planner:
        def __init__(self, _):
            pass

        def create_multilingual(self, article, character, base, languages, **kwargs):
            calls.append(languages)
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    monkeypatch.setattr(worker, "ScenePlanner", Planner)
    monkeypatch.setattr(worker, "ShortsPipeline", lambda _: object())
    monkeypatch.setattr(worker, "load_article", lambda url: SimpleNamespace(source=url, title="Topic", text="Source"))
    tasks = [{"key": "a", "language": "en", "url": "https://www.fevercoach.us/post/a"},
             {"key": "b", "language": "es", "url": "https://www.fevercoach.us/es/post/b"}]
    worker.write_json(tmp_path / "manifest.json", {"total": 2, "tasks": tasks})
    assert worker.run(tmp_path, min_free_gb=1, max_items=None, retry_failed=False) == 2
    state = worker.read_json(tmp_path / "status.json")
    assert state["status"] == "BLOCKED_API"
    assert calls == [("en",)]


def test_disk_reserve_stops_before_any_article_request(worker, monkeypatch, tmp_path):
    from dataclasses import replace
    settings = replace(worker.Settings.from_env(), gemini_api_key="test-key")
    monkeypatch.setattr(worker.Settings, "from_env", lambda: settings)
    monkeypatch.setattr(worker, "ScenePlanner", lambda _: object())
    monkeypatch.setattr(worker, "ShortsPipeline", lambda _: object())
    monkeypatch.setattr(worker.shutil, "disk_usage", lambda _: SimpleNamespace(free=100))
    worker.write_json(tmp_path / "manifest.json", {"total": 1, "tasks": [
        {"key": "a", "language": "ko", "url": "https://www.fevercoach.us/ko/post/a"}]})
    assert worker.run(tmp_path, min_free_gb=1, max_items=None, retry_failed=False) == 2
    assert worker.read_json(tmp_path / "status.json")["status"] == "BLOCKED_DISK"


def test_retry_network_preflight_leaves_failed_items_untouched(worker, monkeypatch, tmp_path):
    from dataclasses import replace
    settings = replace(worker.Settings.from_env(), gemini_api_key="test-key")
    monkeypatch.setattr(worker.Settings, "from_env", lambda: settings)
    monkeypatch.setattr(worker, "ScenePlanner", lambda _: object())
    monkeypatch.setattr(worker, "ShortsPipeline", lambda _: object())
    def unavailable():
        raise OSError("DNS unavailable")
    monkeypatch.setattr(worker, "check_network", unavailable)
    task = {"key": "bad", "language": "en", "url": "https://www.fevercoach.us/post/a"}
    original = {"status": "FAILED", "language": "en", "error": "Connection reset by peer"}
    worker.write_json(tmp_path / "manifest.json", {"total": 1, "tasks": [task]})
    worker.write_json(tmp_path / "status.json", {"items": {"bad": original}})
    assert worker.run(tmp_path, min_free_gb=1, max_items=None, retry_failed=True) == 2
    state = worker.read_json(tmp_path / "status.json")
    assert state["status"] == "BLOCKED_NETWORK"
    assert state["items"]["bad"] == original


def test_delivery_names_handle_unicode_and_filesystem_limits(worker):
    name = worker.delivery_name("아이/발열:" * 100, "collected-ko-123456789abcdef0", "ko")
    assert len(name.encode()) < 200 and "/" not in name and ":" not in name
    assert name.endswith("_12345678_KO.mp4")
