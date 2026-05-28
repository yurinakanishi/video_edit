from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from project_paths import OUTPUT_OVERLAYS
from video_edit_app_config import hex_rgba, load_app_config, nested, opacity_alpha


WIDTH = 1920
HEIGHT = 1080
FONT_BOLD = Path(r"C:\Windows\Fonts\YuGothB.ttc")
FONT_REGULAR = Path(r"C:\Windows\Fonts\YuGothM.ttc")
DEFAULT_OUTPUT = OUTPUT_OVERLAYS / "omission_card.png"
DEFAULT_TITLE = "質問を要約"
DEFAULT_SUBTITLE = "ここでは聞き手の質問を短くまとめています"


def text_value(config: dict[str, Any], *keys: str, default: str = "") -> str:
    value = nested(config, *keys, default=default)
    return str(value) if value is not None else default


def font(path: Path, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    if path.exists():
        return ImageFont.truetype(str(path), size, index=index)
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def wrapped_lines(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    rows: list[str] = []
    for raw_line in text.splitlines() or [text]:
        line = raw_line.strip()
        if not line:
            continue
        current = ""
        for char in line:
            probe = current + char
            bbox = draw.textbbox((0, 0), probe, font=font_obj)
            if current and bbox[2] - bbox[0] > max_width:
                rows.append(current)
                current = char
            else:
                current = probe
        if current:
            rows.append(current)
    return rows or [""]


def main() -> None:
    config = load_app_config()
    parser = argparse.ArgumentParser(description="Generate a generic omission summary card for app renders.")
    parser.add_argument("--output", type=Path, default=Path(text_value(config, "omissionCard", "outputPath", default=str(DEFAULT_OUTPUT))))
    parser.add_argument("--title", default=text_value(config, "omissionCard", "title", default=DEFAULT_TITLE))
    parser.add_argument("--subtitle", default=text_value(config, "omissionCard", "subtitle", default=DEFAULT_SUBTITLE))
    args = parser.parse_args()

    title = args.title.strip() or DEFAULT_TITLE
    subtitle = args.subtitle.strip() or DEFAULT_SUBTITLE
    accent = hex_rgba(nested(config, "style", "highlightColor"), default=(174, 72, 224, 255))
    box_alpha = opacity_alpha(nested(config, "omissionCard", "boxOpacity", default=86), 220)
    bg_alpha = opacity_alpha(nested(config, "omissionCard", "backgroundOpacity", default=82), 210)

    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (20, 22, 24, bg_alpha))
    draw = ImageDraw.Draw(canvas)
    title_font = font(FONT_BOLD, 86, index=1)
    subtitle_font = font(FONT_REGULAR, 46)
    tag_font = font(FONT_BOLD, 34, index=1)

    panel_w = 1420
    panel_h = 430
    panel_x = (WIDTH - panel_w) // 2
    panel_y = (HEIGHT - panel_h) // 2
    draw.rounded_rectangle(
        (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
        radius=28,
        fill=(255, 255, 255, box_alpha),
        outline=(accent[0], accent[1], accent[2], 230),
        width=5,
    )
    draw.rectangle((panel_x, panel_y, panel_x + 18, panel_y + panel_h), fill=accent)

    tag = text_value(config, "omissionCard", "label", default="SUMMARY")
    draw.text((panel_x + 70, panel_y + 52), tag, font=tag_font, fill=(accent[0], accent[1], accent[2], 255))

    title_lines = wrapped_lines(draw, title, title_font, panel_w - 170)[:2]
    subtitle_lines = wrapped_lines(draw, subtitle, subtitle_font, panel_w - 170)[:3]

    y = panel_y + 112
    for line in title_lines:
        draw.text((panel_x + 70, y), line, font=title_font, fill=(31, 31, 34, 255))
        y += 104
    y += 16
    for line in subtitle_lines:
        draw.text((panel_x + 74, y), line, font=subtitle_font, fill=(72, 69, 75, 245))
        y += 62

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)
    report = {"output": str(args.output), "title": title, "subtitle": subtitle}
    args.output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
