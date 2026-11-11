from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

from fevercoach_shorts.article import Article
from fevercoach_shorts.planner import _planning_prompt, _multilingual_planning_prompt
from fevercoach_shorts.providers.video_audit import AUDIT_SCHEMA, _audit_prompt
from fevercoach_shorts.review_rules import (
    ADJUDICATION_CHECK_NAMES, REVIEW_GUIDELINE_VERSION, SEPTEMBER_13_REVIEW_RULES,
    WEEK8_REVIEW_RULES,
    JAEYOON_FAIL_ONLY_RULES, JAEYOON_VISUAL_SAFETY_RULES,
)


def load_scripts(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return (
        importlib.import_module("audit_blog_videos_with_gemini"),
        importlib.import_module("audit_all_final_tts_captions_with_gemini"),
        importlib.import_module("repair_failed_video_audits"),
    )


def example_spec():
    scenes = [SimpleNamespace(
        index=i, title="Review", timeline_seconds=duration,
        narration="Do not routinely alternate medicines every 2 hours.",
        caption_chunks=["Do not routinely alternate medicines every 2 hours."],
        medical_claim="Warning against routine alternation", prompt="Child resting",
        overlays=[],
    ) for i, duration in ((1, 8), (2, 4))]
    return SimpleNamespace(scenes=scenes, language="en", source="source",
                           metadata={"distribution_country": "unknown"})


def test_new_adjudication_reaches_both_auditors_and_repair(monkeypatch):
    batch, _, repair = load_scripts(monkeypatch)
    spec = example_spec()
    prompts = [
        batch.build_prompt("test.en", "source", spec, {}),
        _audit_prompt(spec, "source", .75),
        repair.repair_prompt({"language": "en"}, [], []),
    ]
    for prompt in prompts:
        assert SEPTEMBER_13_REVIEW_RULES in prompt
        assert WEEK8_REVIEW_RULES in prompt
        assert JAEYOON_FAIL_ONLY_RULES in prompt
        assert "warning, not a dosing recommendation" in prompt
        assert "An early or final emergency warning does not cancel" in prompt
        assert "never require\n    39°C" in prompt
    for schema in (batch.AUDIT_SCHEMA, AUDIT_SCHEMA):
        checks = schema["properties"]["calibration_checks"]
        assert set(ADJUDICATION_CHECK_NAMES) <= set(checks["required"])
        assert len(checks["required"]) == len(set(checks["required"]))


def test_planning_uses_same_medical_rules():
    article = Article("Title", "Source content", "source.md")
    assert SEPTEMBER_13_REVIEW_RULES in _planning_prompt(article)
    assert SEPTEMBER_13_REVIEW_RULES in _multilingual_planning_prompt(article, ("ko", "en", "es"))
    assert WEEK8_REVIEW_RULES in _planning_prompt(article)
    assert WEEK8_REVIEW_RULES in _multilingual_planning_prompt(article, ("ko", "en", "es"))
    assert JAEYOON_FAIL_ONLY_RULES in _planning_prompt(article)
    assert JAEYOON_FAIL_ONLY_RULES in _multilingual_planning_prompt(article, ("ko", "en", "es"))


def test_jaeyoon_visual_rules_reach_assets_and_actual_video_prompt():
    from fevercoach_shorts.models import SceneSpec
    from fevercoach_shorts.providers.assets import _asset_prompt
    from fevercoach_shorts.providers.prompt_refiner import (
        _refinement_request, _compose_refined_prompt, _enforce_video_contract,
    )
    scene = SceneSpec(
        index=1, title="Breathing", prompt="Caregiver seeks care", mode="i2v",
        timeline_seconds=6, generation_seconds=6, narration="Seek medical care.",
        subtitle="Seek medical care.", negative_prompt="text",
    )
    for prompt in (
        _asset_prompt(scene.prompt), _refinement_request(scene, 1),
        _compose_refined_prompt({}, scene), _enforce_video_contract(scene.prompt, scene),
    ):
        assert JAEYOON_VISUAL_SAFETY_RULES in prompt


def test_jaeyoon_rules_preserve_scope_and_false_failure_guards():
    assert "Other creators, P rows and unrated rows did not" in JAEYOON_FAIL_ONLY_RULES
    assert "Do not state that fever naturally cycles every 4-6 hours" in JAEYOON_FAIL_ONLY_RULES
    assert "never remove young-infant age exceptions" in JAEYOON_FAIL_ONLY_RULES
    assert "do not establish overdose or aspiration" in JAEYOON_FAIL_ONLY_RULES
    assert "only from supplied/computed hashes" in JAEYOON_FAIL_ONLY_RULES


def test_audit_timestamps_follow_rebalanced_scene_durations(monkeypatch):
    batch, _, _ = load_scripts(monkeypatch)
    prompt = batch.build_prompt("test.en", "source", example_spec(), {})
    data = prompt.split("EXPECTED PRODUCTION SPECIFICATION:\n", 1)[1].split(
        "\n\nDETERMINISTIC LOCAL MEDIA CHECKS:", 1)[0]
    scenes = json.loads(data)
    assert scenes[0]["time_seconds"] == [0, 8]
    assert scenes[1]["time_seconds"] == [8, 12]


def test_warning_is_only_a_focus_hint_not_local_fail(monkeypatch):
    batch, _, _ = load_scripts(monkeypatch)
    focus = batch.reviewer_feedback_focus(example_spec())
    assert "TWO_HOUR_ALTERNATING_MEDICINE" in focus[0]["checks"]
    assert "verdict" not in focus[0]
    assert "recommendation_vs_warning" in batch.AUDIT_SCHEMA["properties"]["calibration_checks"]["required"]


def test_cache_invalidates_old_rubric_video_snapshot_or_model(monkeypatch, tmp_path):
    _, runner, _ = load_scripts(monkeypatch)
    video, snapshot = tmp_path / "final.mp4", tmp_path / "snapshot.json"
    video.write_bytes(b"original-video")
    snapshot.write_text('{}')
    target = {"video": video, "snapshot": snapshot}
    metadata = {
        "review_guideline_version": REVIEW_GUIDELINE_VERSION, "model": "test-model",
        "video_sha256": runner.sha256(video), "snapshot_sha256": runner.sha256(snapshot),
    }
    result = {"overall_verdict": "PASS", "audit_metadata": metadata}
    assert runner.cached_audit_is_current(result, target, "test-model")
    assert not runner.cached_audit_is_current(result, target, "another-model")
    old = {"audit_metadata": {**metadata, "review_guideline_version": "old"}}
    assert not runner.cached_audit_is_current(old, target, "test-model")
    video.write_bytes(b"repaired-video")
    assert not runner.cached_audit_is_current(result, target, "test-model")
    video.write_bytes(b"original-video")
    snapshot.write_text('{"changed": true}')
    assert not runner.cached_audit_is_current(result, target, "test-model")
