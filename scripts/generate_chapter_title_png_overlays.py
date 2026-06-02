from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from video_edit_core.paths import OUTPUT_OVERLAYS, ROOT as WORKSPACE_ROOT, resolve_project_path
from video_edit_core.app_config import hex_rgba, int_value, load_app_config, nested, opacity_alpha


WORK = WORKSPACE_ROOT
OUTPUT_DIR = OUTPUT_OVERLAYS / "chapter_title_png_overlays"
MANIFEST = OUTPUT_DIR / "manifest.json"
FONT_PATH = Path(r"C:\Windows\Fonts\YuGothB.ttc")
PURPLE = (170, 28, 214, 255)
TRACKING = 4
TITLE_SCALE = 1.2
APP_CONFIG = load_app_config()


def parse_time(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return 0.0
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return max(0.0, float(parts[0]))
        if len(parts) == 2:
            return max(0.0, int(parts[0]) * 60 + float(parts[1]))
        if len(parts) == 3:
            return max(0.0, int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2]))
    except ValueError:
        return 0.0
    return 0.0


def format_time(total_seconds: float) -> str:
    total_seconds = max(0.0, float(total_seconds))
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds - hours * 3600 - minutes * 60
    return f"{hours}:{minutes:02d}:{seconds:06.3f}"


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


def chapter_rows() -> list[dict[str, Any]]:
    rows = nested(APP_CONFIG, "style", "chapterTitles", default=None)
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    path_text = str(nested(APP_CONFIG, "style", "chapterTitlesPath", default="") or "").strip()
    if not path_text:
        return []
    path = resolve_project_path(path_text)
    if not path.exists():
        path = Path(path_text)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("chapters") or payload.get("items") or []
    return [row for row in payload if isinstance(row, dict)]


def render_title_png(text: str, destination: Path) -> None:
    font_size = round(int_value(APP_CONFIG, "style", "titleSize", default=64) * TITLE_SCALE)
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
    canvas.save(destination)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    chapters = chapter_rows()
    manifest: list[dict[str, Any]] = []
    for index, row in enumerate(chapters, start=1):
        title = " ".join(str(row.get("title") or row.get("text") or "").split())
        if not title:
            continue
        start = parse_time(row.get("start", 0.0))
        end = parse_time(row.get("end", start + 300.0))
        if end <= start + 0.1:
            continue
        png = OUTPUT_DIR / f"chapter_{index:03d}.png"
        render_title_png(title, png)
        manifest.append(
            {
                "start": format_time(start),
                "end": format_time(end),
                "text": title,
                "file": str(png.relative_to(WORK)).replace("\\", "/"),
            }
        )
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST), "items": len(manifest)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
