from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fevercoach_shorts.models import ProductionSpec
from fevercoach_shorts.captions import _caption_layer, _fit_caption, _font, _wrap
from fevercoach_shorts.renderer import _caption_timings
from fevercoach_shorts.subtitles import write_srt
from PIL import Image, ImageDraw


class SubtitleTest(unittest.TestCase):
    def test_caption_layer_has_no_background_panel(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            path = root / "production.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(path)
            layer = _caption_layer(spec, [], "배경 없는 자막", 1080, 1920)

        self.assertEqual(layer.getpixel((20, 1800))[3], 0)
        self.assertGreater(max(pixel[3] for pixel in layer.getdata()), 0)

    def test_caption_timing_tracks_spoken_text_length(self) -> None:
        timings = _caption_timings(["짧게", "조금 더 긴 문장입니다"], 6)

        self.assertEqual(timings[0][0], 0)
        self.assertEqual(timings[-1][1], 6)
        self.assertLess(timings[0][1] - timings[0][0], timings[1][1] - timings[1][0])

    def test_latin_subtitles_wrap_at_word_boundaries_and_render_accents(self) -> None:
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 400)))
        font = _font(64, "es")
        lines = _wrap(
            draw,
            "Hidratación, antifebriles y descanso.",
            font,
            800,
            "es",
        )
        self.assertEqual(" ".join(lines), "Hidratación, antifebriles y descanso.")
        self.assertNotIn("\ufffd", "".join(lines))

    def test_long_caption_is_fitted_without_truncating_tts_text(self) -> None:
        text = (
            "Si la fiebre de 40°C o más persiste después de 3 días de antibióticos, "
            "podría requerir una reevaluación."
        )
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 400)))
        font, lines = _fit_caption(draw, text, "es", 930, max_lines=3)
        self.assertLessEqual(len(lines), 3)
        self.assertEqual(" ".join(lines), text)
        self.assertGreaterEqual(font.size, 36)

    def test_srt_ends_at_one_minute(self) -> None:
        data = json.loads(Path("examples/oc43.production.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "character.png").write_bytes(b"image")
            data["character_image"] = "character.png"
            config = root / "production.json"
            config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            spec = ProductionSpec.load(config)
            output = write_srt(spec, root / "subtitles.srt")
            text = output.read_text(encoding="utf-8")

        self.assertIn("00:00:52,000 --> 00:01:00,000", text)


if __name__ == "__main__":
    unittest.main()
