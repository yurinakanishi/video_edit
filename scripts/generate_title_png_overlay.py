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

from video_edit_app_config import hex_rgba, int_value, load_app_config, nested, opacity_alpha


WORK = WORKSPACE_ROOT
OUTPUT = OUTPUT_OVERLAYS / "ai_engineer_now_title.png"
FONT_PATH = Path(r"C:\Windows\Fonts\YuGothB.ttc")

TEXT = "AIエンジニアの今"
PURPLE = (170, 28, 214, 255)
WHITE = (255, 255, 255, 250)
LIGHT_PURPLE = (245, 224, 255, 250)
TRACKING = 4
TITLE_SCALE = 1.2
APP_CONFIG = load_app_config()


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


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    font_size = round(int_value(APP_CONFIG, "style", "titleSize", default=64) * TITLE_SCALE)
    text = TEXT
    accent = hex_rgba(nested(APP_CONFIG, "style", "highlightColor"), default=PURPLE)
    alpha = opacity_alpha(nested(APP_CONFIG, "style", "boxOpacity"), 250)
    white = (255, 255, 255, max(alpha, 180))
    light_accent = (*accent[:3], max(70, min(180, round(alpha * 0.55))))
    font = ImageFont.truetype(str(FONT_PATH), font_size, index=1)
    stroke = 1
    pad_x = round(20 * TITLE_SCALE)
    pad_y = round(9 * TITLE_SCALE)
    stripe = round(8 * TITLE_SCALE)

    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    text_w = tracked_text_width(draw, text, font, stroke)
    text_h = bbox[3] - bbox[1]

    box_w = text_w + pad_x * 2
    box_h = text_h + pad_y * 2
    canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, box_w, box_h), fill=white)
    draw.rectangle((0, box_h - stripe, box_w, box_h), fill=light_accent)
    draw.rectangle((0, box_h - 2, box_w, box_h), fill=accent)
    draw_tracked_text(
        draw,
        (pad_x - bbox[0], pad_y - bbox[1]),
        text,
        font=font,
        fill=accent,
        stroke_width=stroke,
        stroke_fill=accent,
    )
    canvas.save(OUTPUT)


if __name__ == "__main__":
    main()
