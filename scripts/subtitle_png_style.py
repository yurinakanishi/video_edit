from __future__ import annotations

from pathlib import Path

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_OVERLAYS,
    OUTPUT_REPORTS,
    OUTPUT_TRANSCRIPTS,
    OUTPUT_VIDEOS,
    ROOT as WORKSPACE_ROOT,
    SCRIPTS,
    SOURCE_AUDIO,
    SOURCE_IMAGES,
    SOURCE_SUBTITLES,
    SOURCE_VIDEO,
    multicam_source_root,
    resolve_project_path,
)

from PIL import Image, ImageDraw, ImageFont


FONT_PATH = Path(r"C:\Windows\Fonts\YuGothB.ttc")
RED = (216, 0, 0, 255)
WHITE = (255, 255, 255, 255)
LIGHT_PURPLE = (174, 72, 224, 185)
BLACK = (0, 0, 0, 175)
TRACKING = 4


def tracked_text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, stroke: int) -> int:
    width = 0
    for index, char in enumerate(text):
        bbox = draw.textbbox((0, 0), char, font=font, stroke_width=stroke)
        width += bbox[2] - bbox[0]
        if index < len(text) - 1:
            width += TRACKING
    return width


def draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
) -> None:
    x, y = position
    for index, char in enumerate(text):
        bbox = draw.textbbox((0, 0), char, font=font, stroke_width=stroke_width)
        draw.text(
            (x - bbox[0], y),
            char,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        x += bbox[2] - bbox[0]
        if index < len(text) - 1:
            x += TRACKING


def render_caption(
    lines: tuple[str, ...],
    font_size: int,
    *,
    stroke: int = 2,
    pad_x: int = 18,
    pad_y: int = 8,
    shadow: int = 12,
    line_gap: int = 0,
    box_fill: tuple[int, int, int, int] = WHITE,
    text_fill: tuple[int, int, int, int] = RED,
    shadow_fill: tuple[int, int, int, int] = RED,
) -> Image.Image:
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    metrics: list[tuple[str, tuple[int, int, int, int], int, int]] = []
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        width = tracked_text_width(draw, line, font, stroke) if len(line) > 1 else bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        metrics.append((line, bbox, width, height))

    max_width = max(width for _, _, width, _ in metrics)
    total_height = sum(height + pad_y * 2 for _, _, _, height in metrics) + line_gap * (len(lines) - 1)
    canvas = Image.new("RGBA", (max_width + pad_x * 2 + shadow, total_height + shadow), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    y = 0
    for line, bbox, width, height in metrics:
        box_w = width + pad_x * 2
        box_h = height + pad_y * 2
        x = round((canvas.width - shadow - box_w) / 2)
        shadow_box = (x + shadow, y + shadow, x + shadow + box_w, y + shadow + box_h)
        box = (x, y, x + box_w, y + box_h)
        draw.rectangle(shadow_box, fill=shadow_fill)
        draw.rectangle(box, fill=box_fill)
        draw_tracked_text(
            draw,
            (x + pad_x - bbox[0], y + pad_y - bbox[1]),
            line,
            font=font,
            fill=text_fill,
            stroke_width=stroke,
            stroke_fill=text_fill,
        )
        y += box_h + line_gap

    return canvas


def render_simple_caption(
    lines: tuple[str, ...],
    font_size: int,
    *,
    stroke: int = 2,
    pad_x: int = 18,
    pad_y: int = 10,
    line_gap: int = 4,
    box_fill: tuple[int, int, int, int] = LIGHT_PURPLE,
) -> Image.Image:
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    metrics: list[tuple[str, tuple[int, int, int, int], int, int]] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        width = tracked_text_width(draw, line, font, stroke) if len(line) > 1 else bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        metrics.append((line, bbox, width, height))

    max_width = max(width for _, _, width, _ in metrics)
    total_height = sum(height + pad_y * 2 for _, _, _, height in metrics) + line_gap * (len(lines) - 1)
    canvas = Image.new("RGBA", (max_width + pad_x * 2, total_height + pad_y * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    y = pad_y
    for line, bbox, width, height in metrics:
        box_w = width + pad_x * 2
        box_h = height + pad_y * 2
        x = round((canvas.width - box_w) / 2)
        draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=10, fill=box_fill)
        draw_tracked_text(
            draw,
            (x + pad_x - bbox[0], y + pad_y - bbox[1]),
            line,
            font=font,
            fill=WHITE,
            stroke_width=stroke,
            stroke_fill=WHITE,
        )
        y += box_h + line_gap

    return canvas
