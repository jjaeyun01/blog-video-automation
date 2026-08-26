from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from google import genai
from google.genai import types

from ..models import ProductionSpec, SceneSpec


class VeoGenerator:
    """Resumable Veo long-running operation manager."""

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str | None = "veo-3.1-fast-generate-preview",
        poll_interval_seconds: int = 10,
        client=None,
        sleep: Callable[[float], None] = time.sleep,
        max_generation_attempts: int = 5,
    ):
        self.client = client or genai.Client(api_key=api_key)
        self.model = model
        self.fallback_model = fallback_model
        self.poll_interval_seconds = max(5, poll_interval_seconds)
        self.sleep = sleep
        self.max_generation_attempts = max(1, max_generation_attempts)

    def generate(
        self,
        spec: ProductionSpec,
        job_dir: Path,
        status: Callable[[str], None] = print,
    ) -> list[Path]:
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        state_path = job_dir / "operations.json"
        state = _load_state(state_path, self.model)
        if state.get("model") != self.model:
            state = _new_state(self.model)

        # Submit missing scenes first. This lets generation jobs run concurrently.
        for scene in spec.scenes:
            key = str(scene.index)
            output_path = clips_dir / f"scene_{scene.index:02}.mp4"
            fingerprint = _fingerprint(scene, spec, self.model)
            entry = state["scenes"].get(key, {})
            if output_path.exists() and entry.get("fingerprint") == fingerprint:
                entry["status"] = "SUCCEEDED"
                continue
            same_request = entry.get("fingerprint") == fingerprint
            if same_request and entry.get("operation_id") and entry.get("status") != "FAILED":
                continue
            exhausted_primary = (
                same_request
                and entry.get("status") == "FAILED"
                and int(entry.get("generation_attempts", 0)) >= self.max_generation_attempts
                and (entry.get("request_model") or self.model) == self.model
                and self.fallback_model
            )
            request_model = self.fallback_model if exhausted_primary else self.model
            try:
                operation = self._submit(scene, spec, request_model)
            except Exception as error:
                if (
                    self.fallback_model
                    and request_model != self.fallback_model
                    and _is_quota_error(error)
                ):
                    request_model = self.fallback_model
                    operation = self._submit(scene, spec, request_model)
                    status(
                        f"Scene {scene.index}: primary submission quota exhausted; "
                        f"submitted with {request_model}"
                    )
                else:
                    raise
            state["scenes"][key] = {
                "scene": scene.index,
                "fingerprint": fingerprint,
                "operation_id": operation.name,
                "status": "SUBMITTED",
                "output_path": str(output_path.resolve()),
                "updated_at": _now(),
                "poll_errors": 0,
                "generation_attempts": (
                    1
                    if exhausted_primary or not same_request
                    else int(entry.get("generation_attempts", 0)) + 1
                ),
                "request_model": request_model,
            }
            _save_state(state_path, state)
            status(f"Scene {scene.index}: submitted {operation.name}")

        while True:
            for scene in spec.scenes:
                entry = state["scenes"][str(scene.index)]
                if entry["status"] == "SUCCEEDED":
                    continue
                try:
                    if entry["status"] in {"RETRYING", "FALLBACK"}:
                        use_fallback = entry["status"] == "FALLBACK"
                        request_model = self.fallback_model if use_fallback else (
                            entry.get("request_model") or self.model
                        )
                        try:
                            operation = self._submit(scene, spec, request_model)
                        except Exception as error:
                            if (
                                self.fallback_model
                                and request_model != self.fallback_model
                                and _is_quota_error(error)
                            ):
                                request_model = self.fallback_model
                                operation = self._submit(scene, spec, request_model)
                                status(
                                    f"Scene {scene.index}: primary retry quota exhausted; "
                                    f"submitted with {request_model}"
                                )
                            else:
                                raise
                        entry["operation_id"] = operation.name
                        entry["status"] = "SUBMITTED"
                        entry["generation_attempts"] = (
                            1 if use_fallback else int(entry.get("generation_attempts", 1)) + 1
                        )
                        entry["request_model"] = request_model
                        entry["updated_at"] = _now()
                        entry["poll_errors"] = 0
                        _save_state(state_path, state)
                        status(
                            f"Scene {scene.index}: retry {entry['generation_attempts']}/"
                            f"{self.max_generation_attempts} on {request_model} submitted {operation.name}"
                        )
                        continue
                    operation = self.client.operations.get(
                        types.GenerateVideosOperation(name=entry["operation_id"])
                    )
                    entry["poll_errors"] = 0
                    entry.pop("last_error", None)
                    if not operation.done:
                        entry["status"] = "POLLING"
                        entry["updated_at"] = _now()
                        continue
                    if getattr(operation, "error", None):
                        entry["last_error"] = str(operation.error)
                        error_code = _operation_error_code(operation.error)
                        attempts = int(entry.get("generation_attempts", 1))
                        if error_code in _TRANSIENT_OPERATION_CODES and attempts < self.max_generation_attempts:
                            entry["status"] = "RETRYING"
                            entry["updated_at"] = _now()
                            status(
                                f"Scene {scene.index}: temporary Veo error (code {error_code}); "
                                f"retrying after {self.poll_interval_seconds}s"
                            )
                            continue
                        current_model = entry.get("request_model") or self.model
                        if (
                            error_code in _TRANSIENT_OPERATION_CODES
                            and self.fallback_model
                            and current_model != self.fallback_model
                        ):
                            entry["status"] = "FALLBACK"
                            entry["updated_at"] = _now()
                            status(
                                f"Scene {scene.index}: primary model retries exhausted; "
                                f"switching to {self.fallback_model}"
                            )
                            continue
                        entry["status"] = "FAILED"
                        _save_state(state_path, state)
                        raise RuntimeError(f"Scene {scene.index} failed: {operation.error}")
                    generated_videos = getattr(
                        getattr(operation, "response", None), "generated_videos", None
                    )
                    if not generated_videos:
                        attempts = int(entry.get("generation_attempts", 1))
                        entry["last_error"] = "Veo completed without a generated video."
                        if attempts < self.max_generation_attempts:
                            entry["status"] = "RETRYING"
                            entry["updated_at"] = _now()
                            status(
                                f"Scene {scene.index}: Veo returned an empty completed response; "
                                f"retrying after {self.poll_interval_seconds}s"
                            )
                            continue
                        current_model = entry.get("request_model") or self.model
                        if self.fallback_model and current_model != self.fallback_model:
                            entry["status"] = "FALLBACK"
                            entry["updated_at"] = _now()
                            status(
                                f"Scene {scene.index}: empty-response retries exhausted; "
                                f"switching to {self.fallback_model}"
                            )
                            continue
                        entry["status"] = "FAILED"
                        _save_state(state_path, state)
                        raise RuntimeError(
                            f"Scene {scene.index} completed without a generated video."
                        )
                    generated = generated_videos[0]
                    self.client.files.download(file=generated.video)
                    generated.video.save(entry["output_path"])
                    entry["status"] = "SUCCEEDED"
                    entry["updated_at"] = _now()
                    status(f"Scene {scene.index}: saved {entry['output_path']}")
                except RuntimeError:
                    raise
                except Exception as error:
                    entry["poll_errors"] = int(entry.get("poll_errors", 0)) + 1
                    entry["last_error"] = str(error)
                    entry["updated_at"] = _now()
                    if entry["poll_errors"] >= 3:
                        _save_state(state_path, state)
                        raise RuntimeError(
                            f"Scene {scene.index} polling failed three times: {error}"
                        ) from error
            _save_state(state_path, state)
            waiting = sum(
                state["scenes"][str(scene.index)]["status"] != "SUCCEEDED"
                for scene in spec.scenes
            )
            if waiting == 0:
                break
            status(f"Waiting {self.poll_interval_seconds}s for {waiting} operation(s)...")
            self.sleep(self.poll_interval_seconds)

        return [clips_dir / f"scene_{scene.index:02}.mp4" for scene in spec.scenes]

    def _submit(self, scene: SceneSpec, spec: ProductionSpec, model: str | None = None):
        request = {
            "model": model or self.model,
            "prompt": scene.prompt,
            "config": types.GenerateVideosConfig(
                aspect_ratio=spec.aspect_ratio,
                resolution=spec.resolution,
                duration_seconds=scene.generation_seconds,
                number_of_videos=1,
                negative_prompt=scene.negative_prompt,
            ),
        }
        if scene.mode == "i2v":
            request["image"] = types.Image.from_file(location=str(scene.image))
        return self.client.models.generate_videos(**request)


def write_generation_plan(spec: ProductionSpec, model: str, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / "generation_plan.json"
    data = {
        "model": model,
        "aspect_ratio": spec.aspect_ratio,
        "resolution": spec.resolution,
        "duration_seconds": spec.duration_seconds,
        "scenes": [scene.to_dict() for scene in spec.scenes],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _fingerprint(scene: SceneSpec, spec: ProductionSpec, model: str) -> str:
    image = None
    if scene.image:
        image = {
            "path": str(scene.image),
            "sha256": hashlib.sha256(scene.image.read_bytes()).hexdigest(),
        }
    payload = {
        "model": model,
        "aspect_ratio": spec.aspect_ratio,
        "resolution": spec.resolution,
        "mode": scene.mode,
        "prompt": scene.prompt,
        "negative_prompt": scene.negative_prompt,
        "generation_seconds": scene.generation_seconds,
        "image": image,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _new_state(model: str) -> dict:
    return {"model": model, "created_at": _now(), "scenes": {}}


def _load_state(path: Path, model: str) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else _new_state(model)


def _save_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_TRANSIENT_OPERATION_CODES = {4, 8, 10, 13, 14}


def _operation_error_code(error: object) -> int | None:
    if isinstance(error, dict):
        value = error.get("code")
    else:
        value = getattr(error, "code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_quota_error(error: Exception) -> bool:
    value = str(error).lower()
    return "resource_exhausted" in value or "quota" in value or "429" in value
