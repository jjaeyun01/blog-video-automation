from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.providers.tts import (
    FEVERCOACH_TTS_VOICE,
    GeminiTtsProvider,
    build_timeline_audio,
)


class _Provider:
    cache_key = "fake:voice"

    def __init__(self):
        self.calls = 0

    def synthesize(self, scene, output_path):
        self.calls += 1
        output_path.write_bytes(b"audio")


class _RetryTtsModels:
    def __init__(self) -> None:
        self.calls = 0
        self.last_kwargs = None

    def generate_content(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
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
            gemini_api_key="key", gemini_tts_model="tts-model"
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
            self.assertEqual(provider.voice, FEVERCOACH_TTS_VOICE)
            self.assertEqual(models.last_kwargs["config"].temperature, 0.0)
            voice_name = (
                models.last_kwargs["config"]
                .speech_config.voice_config.prebuilt_voice_config.voice_name
            )
            self.assertEqual(voice_name, FEVERCOACH_TTS_VOICE)
            self.assertIn("fixed FeverCoach adult female narrator", models.last_kwargs["contents"])

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

    def test_anomalously_long_tts_is_regenerated_before_failing(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            provider = _Provider()
            probes = 0

            def fake_probe(_path):
                nonlocal probes
                probes += 1
                return 20.0 if probes == 1 else 5.0

            def fake_run(command):
                Path(command[-1]).write_bytes(b"output")

            with (
                patch("fevercoach_shorts.providers.tts._require_ffmpeg"),
                patch("fevercoach_shorts.providers.tts._probe_duration", side_effect=fake_probe),
                patch("fevercoach_shorts.providers.tts._run", side_effect=fake_run),
            ):
                build_timeline_audio(spec, provider, root / "job")

        self.assertEqual(provider.calls, len(spec.scenes) + 1)

    def test_timeline_only_change_reuses_the_same_raw_voice_take(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            provider = _Provider()

            def fake_run(command):
                Path(command[-1]).write_bytes(b"output")

            with (
                patch("fevercoach_shorts.providers.tts._require_ffmpeg"),
                patch("fevercoach_shorts.providers.tts._probe_duration", return_value=5.0),
                patch("fevercoach_shorts.providers.tts._run", side_effect=fake_run),
            ):
                build_timeline_audio(ProductionSpec.load(config), provider, root / "job")
                first_calls = provider.calls
                data["scenes"][0]["timeline_seconds"] += 1
                data["scenes"][1]["timeline_seconds"] -= 1
                config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                build_timeline_audio(ProductionSpec.load(config), provider, root / "job")

        self.assertEqual(first_calls, len(data["scenes"]))
        self.assertEqual(provider.calls, first_calls)


if __name__ == "__main__":
    unittest.main()
