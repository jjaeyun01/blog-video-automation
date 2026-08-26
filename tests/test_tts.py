from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.providers.tts import GeminiTtsProvider, build_timeline_audio


class _Provider:
    cache_key = "fake:voice"

    def synthesize(self, scene, output_path):
        output_path.write_bytes(b"audio")


class _RetryTtsModels:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(candidates=[SimpleNamespace(content=None)])
        inline_data = SimpleNamespace(data=b"ID3audio", mime_type="audio/mpeg")
        part = SimpleNamespace(inline_data=inline_data)
        return SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))]
        )


class TtsTimelineTest(unittest.TestCase):
    def test_gemini_tts_retries_an_empty_audio_response(self) -> None:
        settings = SimpleNamespace(
            gemini_api_key="key", gemini_tts_model="tts-model", gemini_tts_voice="Kore"
        )
        models = _RetryTtsModels()
        provider = GeminiTtsProvider(
            settings,
            "en",
            client=SimpleNamespace(models=models),
            sleep=lambda _: None,
        )
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            scene = ProductionSpec.load(config).scenes[0]
            output = root / "scene.mp3"

            provider.synthesize(scene, output)

            self.assertEqual(models.calls, 2)
            self.assertEqual(output.read_bytes(), b"ID3audio")

    def test_slightly_long_audio_is_sped_up_instead_of_failing(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            commands = []

            def fake_run(command):
                commands.append(command)
                Path(command[-1]).write_bytes(b"output")

            with (
                patch("fevercoach_shorts.providers.tts._require_ffmpeg"),
                patch("fevercoach_shorts.providers.tts._probe_duration", return_value=10.7),
                patch("fevercoach_shorts.providers.tts._run", side_effect=fake_run),
            ):
                build_timeline_audio(spec, _Provider(), root / "job")

        filters = [command[command.index("-af") + 1] for command in commands if "-af" in command]
        self.assertTrue(any(value.startswith("atempo=") for value in filters))


if __name__ == "__main__":
    unittest.main()
