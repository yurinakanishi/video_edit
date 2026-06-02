from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from video_edit_core.paths import OUTPUT_OVERLAYS, ROOT as WORKSPACE_ROOT
from video_edit_core.app_config import load_app_config, nested, selected_subtitle_path


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
SRT = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
OUT_DIR = OUTPUT_OVERLAYS / "glossary_term_overlays"
FONT_PATH = Path(r"C:\Windows\Fonts\YuGothB.ttc")


@dataclass(frozen=True)
class Caption:
    index: int
    start: str
    end: str
    text: str


DEFAULT_GLOSSARY_TERMS: list[dict[str, object]] = []


def configured_terms() -> list[dict[str, object]]:
    terms = nested(APP_CONFIG, "glossary", "terms", default=None)
    if not isinstance(terms, list):
        return []
    normalized = []
    for term in terms:
        if not isinstance(term, dict) or term.get("enabled") is False:
            continue
        label = str(term.get("label") or "").strip()
        description = str(term.get("description") or "").strip()
        raw_patterns = term.get("patterns") or label
        if isinstance(raw_patterns, str):
            patterns = [item.strip() for item in re.split(r"[,、\n]", raw_patterns) if item.strip()]
        elif isinstance(raw_patterns, list):
            patterns = [str(item).strip() for item in raw_patterns if str(item).strip()]
        else:
            patterns = [label] if label else []
        if label and description and patterns:
            normalized.append({"label": label, "description": description, "patterns": tuple(patterns)})
    return normalized


def parse_srt_timestamp(timestamp: str) -> str:
    hours, minutes, seconds = timestamp.replace(",", ".").split(":")
    return f"{int(hours)}:{minutes}:{seconds}"


def parse_srt(path: Path) -> list[Caption]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    captions: list[Caption] = []
    for block in blocks:
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->")]
        captions.append(
            Caption(
                index=int(rows[0]),
                start=parse_srt_timestamp(start_raw),
                end=parse_srt_timestamp(end_raw),
                text="".join(rows[2:]).replace(" ", ""),
            )
        )
    return captions


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def format_timestamp(value: float) -> str:
    minutes, rest = divmod(value, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}:{minutes:02d}:{rest:06.3f}"


def detect_terms(text: str) -> list[dict[str, str]]:
    detected = []
    for term in configured_terms():
        if any(pattern in text for pattern in term["patterns"]):
            detected.append(
                {
                    "label": term["label"],
                    "description": term["description"],
                }
            )
    return detected


def wrap_description(text: str, max_chars: int = 18) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    lines: list[str] = []
    current = ""
    break_chars = "、。，．・"
    for char in text:
        current += char
        if len(current) >= max_chars or char in break_chars:
            lines.append(current.rstrip("、。，．・"))
            current = ""
    if current:
        lines.append(current)
    return lines


def draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    tracking: int = 2,
) -> None:
    x, y = xy
    for index, char in enumerate(text):
        bbox = draw.textbbox((0, 0), char, font=font)
        draw.text((x - bbox[0], y - bbox[1]), char, font=font, fill=fill)
        x += bbox[2] - bbox[0]
        if index < len(text) - 1:
            x += tracking


def tracked_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, tracking: int = 2) -> int:
    width = 0
    for index, char in enumerate(text):
        bbox = draw.textbbox((0, 0), char, font=font)
        width += bbox[2] - bbox[0]
        if index < len(text) - 1:
            width += tracking
    return width


def render_card(terms: list[dict[str, str]]) -> Image.Image:
    title_font = ImageFont.truetype(str(FONT_PATH), 38, index=1)
    body_font = ImageFont.truetype(str(FONT_PATH), 30, index=1)
    label_font = ImageFont.truetype(str(FONT_PATH), 32, index=1)

    rows: list[tuple[str, str, ImageFont.FreeTypeFont]] = [("title", "用語メモ", title_font)]
    for term in terms:
        rows.append(("label", term["label"], label_font))
        for line in wrap_description(term["description"]):
            rows.append(("body", line, body_font))

    probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    max_width = max(tracked_width(draw, text, font) for _, text, font in rows)
    line_heights = []
    for kind, text, font in rows:
        bbox = draw.textbbox((0, 0), text, font=font)
        extra = 10 if kind == "label" else 6
        line_heights.append(bbox[3] - bbox[1] + extra)

    pad_x = 26
    pad_y = 22
    width = min(660, max_width + pad_x * 2)
    height = sum(line_heights) + pad_y * 2 + 8
    canvas = Image.new("RGBA", (width + 8, height + 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((8, 8, width + 8, height + 8), radius=22, fill=(0, 0, 0, 85))
    draw.rounded_rectangle((0, 0, width, height), radius=22, fill=(255, 255, 255, 232), outline=(49, 106, 255, 230), width=4)
    draw.rectangle((0, height - 12, width, height), fill=(49, 106, 255, 230))

    y = pad_y
    for (kind, text, font), line_height in zip(rows, line_heights):
        if kind == "title":
            fill = (49, 106, 255, 255)
        elif kind == "label":
            fill = (216, 0, 0, 255)
        else:
            fill = (20, 24, 32, 255)
        draw_tracked_text(draw, (pad_x, y), text, font, fill)
        y += line_height
    return canvas


def reset_output_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for pattern in ("glossary_*.png", "manifest.json"):
        for path in OUT_DIR.glob(pattern):
            if path.is_file():
                path.unlink()


def main() -> None:
    reset_output_dir()
    manifest = []
    if SRT is None:
        (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    for caption in parse_srt(SRT):
        terms = detect_terms(caption.text)
        if not terms:
            continue
        image = render_card(terms)
        filename = f"glossary_{caption.index:03d}.png"
        image.save(OUT_DIR / filename)
        start = seconds(caption.start)
        end = max(seconds(caption.end), start + 3.4)
        manifest.append(
            {
                "caption_index": caption.index,
                "start": caption.start,
                "end": format_timestamp(end),
                "terms": terms,
                "file": str((OUT_DIR / filename).relative_to(WORK)),
                "width": image.width,
                "height": image.height,
            }
        )
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
