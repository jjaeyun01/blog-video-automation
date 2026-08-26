from __future__ import annotations

from io import BytesIO
from math import atan2, cos, pi, sin
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import ProductionSpec


def render_caption_images(
    spec: ProductionSpec,
    output_dir: Path,
    width: int = 1080,
    height: int = 1920,
) -> list[Path]:
    return [paths[0] for paths in render_caption_chunk_images(spec, output_dir, width, height)]


def render_caption_chunk_images(
    spec: ProductionSpec,
    output_dir: Path,
    width: int = 1080,
    height: int = 1920,
) -> list[list[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_paths: list[list[Path]] = []
    for scene in spec.scenes:
        chunks = scene.caption_chunks or [scene.narration]
        paths: list[Path] = []
        for chunk_index, chunk in enumerate(chunks, start=1):
            image = _caption_layer(spec, scene.overlays, chunk, width, height)
            path = output_dir / f"scene_{scene.index:02}_chunk_{chunk_index:02}.png"
            encoded = BytesIO()
            image.save(encoded, format="PNG")
            data = encoded.getvalue()
            if not path.exists() or path.read_bytes() != data:
                path.write_bytes(data)
            paths.append(path)
        scene_paths.append(paths)
    return scene_paths


def _caption_layer(
    spec: ProductionSpec,
    overlays: list[dict],
    text: str,
    width: int,
    height: int,
) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _draw_overlays(draw, overlays, width, height, spec.language)
    font, lines = _fit_caption(
        draw, text, spec.language, width - 150, max_lines=2
    )
    line_height = round(font.size * 1.3)
    text_height = line_height * len(lines)
    box_top = height - 175 - text_height
    y = box_top
    for line in lines:
        bounds = draw.textbbox((0, 0), line, font=font, stroke_width=4)
        text_width = bounds[2] - bounds[0]
        draw.text(
            ((width - text_width) / 2, y),
            line,
            font=font,
            fill="white",
            stroke_width=5,
            stroke_fill=(0, 0, 0, 230),
        )
        y += line_height
    return image


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    language: str = "ko",
) -> list[str]:
    return _wrap_words(draw, text, font, max_width)


def _fit_caption(
    draw: ImageDraw.ImageDraw,
    text: str,
    language: str,
    max_width: int,
    max_lines: int,
    max_font_size: int = 64,
    min_font_size: int = 36,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(max_font_size, min_font_size - 1, -2):
        font = _font(size, language)
        lines = _wrap(draw, text, font, max_width, language)
        if len(lines) <= max_lines:
            return font, lines
    font = _font(min_font_size, language)
    return font, _wrap(draw, text, font, max_width, language)


def _wrap_characters(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text.strip():
        candidate = current + character
        bounds = draw.textbbox((0, 0), candidate, font=font, stroke_width=4)
        if current and bounds[2] - bounds[0] > max_width:
            lines.append(current.strip())
            current = character
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())
    return lines or [""]


def _wrap_words(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.strip().split():
        candidate = f"{current} {word}".strip()
        bounds = draw.textbbox((0, 0), candidate, font=font, stroke_width=4)
        if current and bounds[2] - bounds[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _font(size: int, language: str = "ko") -> ImageFont.FreeTypeFont:
    if language in {"es", "en"}:
        candidates = [
            (Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"), 0),
            (Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), 0),
            (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"), 0),
        ]
    else:
        candidates = [
            # Apple SD Gothic Neo ExtraBold face. TTC index 14 is stable on macOS.
            (Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"), 14),
            (Path.home() / "Library/Fonts/NanumSquareEB.otf", 0),
            (Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), 0),
            (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"), 0),
        ]
    for path, index in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size, index=index)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _draw_overlays(
    draw: ImageDraw.ImageDraw,
    overlays: list[dict],
    width: int,
    height: int,
    language: str,
) -> None:
    font = _font(48, language)
    for overlay in overlays:
        kind = overlay.get("type")
        color = str(overlay.get("color", "#E5482F"))
        line_width = max(3, int(overlay.get("line_width", 7)))
        start = _point(overlay.get("from", [0.25, 0.35]), width, height)
        end = _point(overlay.get("to", [0.75, 0.35]), width, height)
        if kind in {"arrow", "dimension", "threshold"}:
            draw.line([start, end], fill=color, width=line_width)
        if kind == "arrow":
            _arrow_head(draw, start, end, color, line_width)
        elif kind == "dimension":
            dx, dy = end[0] - start[0], end[1] - start[1]
            length = max(1.0, (dx * dx + dy * dy) ** 0.5)
            px, py = -dy / length * 18, dx / length * 18
            draw.line([(start[0] - px, start[1] - py), (start[0] + px, start[1] + py)], fill=color, width=line_width)
            draw.line([(end[0] - px, end[1] - py), (end[0] + px, end[1] + py)], fill=color, width=line_width)
        elif kind == "cross":
            center = _point(overlay.get("position", [0.5, 0.4]), width, height)
            size = int(float(overlay.get("size", 0.13)) * width)
            draw.line([(center[0] - size, center[1] - size), (center[0] + size, center[1] + size)], fill=color, width=line_width * 2)
            draw.line([(center[0] + size, center[1] - size), (center[0] - size, center[1] + size)], fill=color, width=line_width * 2)
        text = str(overlay.get("text", "")).strip()
        if text:
            position = _point(
                overlay.get("label_position", overlay.get("position", [0.5, 0.22])),
                width,
                height,
            )
            bounds = draw.textbbox((0, 0), text, font=font, stroke_width=3)
            x = position[0] - (bounds[2] - bounds[0]) / 2
            y = position[1] - (bounds[3] - bounds[1]) / 2
            draw.text(
                (x, y), text, font=font, fill=color,
                stroke_width=3, stroke_fill=(20, 20, 20, 220),
            )


def _point(value: object, width: int, height: int) -> tuple[int, int]:
    try:
        x, y = value  # type: ignore[misc]
        return (
            round(max(0.0, min(1.0, float(x))) * width),
            round(max(0.0, min(1.0, float(y))) * height),
        )
    except (TypeError, ValueError):
        return width // 2, height // 2


def _arrow_head(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str,
    line_width: int,
) -> None:
    angle = atan2(end[1] - start[1], end[0] - start[0])
    size = max(22, line_width * 5)
    points = [
        end,
        (round(end[0] - size * cos(angle - pi / 6)), round(end[1] - size * sin(angle - pi / 6))),
        (round(end[0] - size * cos(angle + pi / 6)), round(end[1] - size * sin(angle + pi / 6))),
    ]
    draw.polygon(points, fill=color)
