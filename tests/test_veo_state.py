from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.providers.veo import VeoGenerator


class _SavedVideo:
    def __init__(self):
        self.uri = "fake://video"

    def save(self, path: str) -> None:
        Path(path).write_bytes(b"mp4")


class _Models:
    def __init__(self):
        self.submitted = []

    def generate_videos(self, **request):
        self.submitted.append(request)
        return SimpleNamespace(name=f"operations/{len(self.submitted)}")


class _PrimaryQuotaModels(_Models):
    def generate_videos(self, **request):
        if request["model"] == "veo-primary":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        return super().generate_videos(**request)


class _Operations:
    def get(self, operation):
        video = _SavedVideo()
        response = SimpleNamespace(generated_videos=[SimpleNamespace(video=video)])
        return SimpleNamespace(done=True, error=None, response=response)


class _TransientOperations:
    def __init__(self):
        self.failed_once = False

    def get(self, operation):
        if operation.name == "operations/5" and not self.failed_once:
            self.failed_once = True
            return SimpleNamespace(
                done=True,
                error={"code": 14, "message": "high demand"},
                response=None,
            )
        video = _SavedVideo()
        response = SimpleNamespace(generated_videos=[SimpleNamespace(video=video)])
        return SimpleNamespace(done=True, error=None, response=response)


class _EmptyCompletedOperations:
    def __init__(self):
        self.returned_empty = False

    def get(self, operation):
        if operation.name == "operations/1" and not self.returned_empty:
            self.returned_empty = True
            return SimpleNamespace(done=True, error=None, response=None)
        video = _SavedVideo()
        response = SimpleNamespace(generated_videos=[SimpleNamespace(video=video)])
        return SimpleNamespace(done=True, error=None, response=response)


class _Files:
    def download(self, file):
        return b"mp4"


class _Client:
    def __init__(self, operations=None, models=None):
        self.models = models or _Models()
        self.operations = operations or _Operations()
        self.files = _Files()


class VeoStateTest(unittest.TestCase):
    def test_uses_fast_model_when_primary_submission_quota_is_exhausted(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            models = _PrimaryQuotaModels()
            client = _Client(models=models)
            generator = VeoGenerator(
                "key", "veo-primary", fallback_model="veo-fast", client=client,
                sleep=lambda _: None
            )

            generator.generate(spec, root / "job", status=lambda _: None)
            state = json.loads((root / "job" / "operations.json").read_text(encoding="utf-8"))

        self.assertTrue(all(call["model"] == "veo-fast" for call in models.submitted))
        self.assertTrue(
            all(scene["request_model"] == "veo-fast" for scene in state["scenes"].values())
        )

    def test_retries_completed_operation_with_no_generated_video(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            client = _Client(operations=_EmptyCompletedOperations())
            messages = []
            generator = VeoGenerator(
                "key", "veo-test", poll_interval_seconds=5, client=client, sleep=lambda _: None
            )

            generator.generate(spec, root / "job", status=messages.append)
            state = json.loads((root / "job" / "operations.json").read_text(encoding="utf-8"))

        self.assertEqual(len(client.models.submitted), 7)
        self.assertEqual(state["scenes"]["1"]["generation_attempts"], 2)
        self.assertEqual(state["scenes"]["1"]["status"], "SUCCEEDED")
        self.assertTrue(any("empty completed response" in message for message in messages))

    def test_persists_operations_and_reuses_completed_clips(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "character.png"
            image.write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            client = _Client()
            generator = VeoGenerator(
                "key", "veo-test", poll_interval_seconds=5, client=client, sleep=lambda _: None
            )

            first = generator.generate(spec, root / "job", status=lambda _: None)
            second = generator.generate(spec, root / "job", status=lambda _: None)
            state = json.loads((root / "job" / "operations.json").read_text(encoding="utf-8"))

        self.assertEqual(len(first), 6)
        self.assertEqual(first, second)
        self.assertEqual(len(client.models.submitted), 6)
        self.assertTrue(all(item["status"] == "SUCCEEDED" for item in state["scenes"].values()))

    def test_retries_temporary_high_demand_operation(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            client = _Client(operations=_TransientOperations())
            messages = []
            generator = VeoGenerator(
                "key", "veo-test", poll_interval_seconds=5, client=client, sleep=lambda _: None
            )

            generator.generate(spec, root / "job", status=messages.append)
            state = json.loads((root / "job" / "operations.json").read_text(encoding="utf-8"))

        self.assertEqual(len(client.models.submitted), 7)
        self.assertEqual(state["scenes"]["5"]["generation_attempts"], 2)
        self.assertEqual(state["scenes"]["5"]["status"], "SUCCEEDED")
        self.assertTrue(any("temporary Veo error" in message for message in messages))

    def test_falls_back_to_fast_model_after_primary_limit(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            client = _Client(operations=_TransientOperations())
            generator = VeoGenerator(
                "key",
                "veo-primary",
                fallback_model="veo-fast",
                poll_interval_seconds=5,
                client=client,
                sleep=lambda _: None,
                max_generation_attempts=1,
            )

            generator.generate(spec, root / "job", status=lambda _: None)
            state = json.loads((root / "job" / "operations.json").read_text(encoding="utf-8"))

        self.assertEqual(client.models.submitted[-1]["model"], "veo-fast")
        self.assertEqual(state["scenes"]["5"]["request_model"], "veo-fast")
        self.assertEqual(state["scenes"]["5"]["status"], "SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
