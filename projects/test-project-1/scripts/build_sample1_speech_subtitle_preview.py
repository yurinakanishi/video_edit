from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE_VIDEO = PROJECT_ROOT / "source" / "video" / "Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4"
TRANSCRIPT_DIR = PROJECT_ROOT / "output" / "transcripts" / "manifest_sources"
PRIMARY_SRT = TRANSCRIPT_DIR / "primary.srt"
CORRECTED_SRT = TRANSCRIPT_DIR / "primary_corrected.srt"
CORRECTED_TXT = TRANSCRIPT_DIR / "primary_corrected.txt"
REFERENCE_ANALYSIS = REPO_ROOT / "reference-assets" / "library" / "collections" / "layer-x" / "video" / "sample-1" / "analysis.json"
MEDIA_MANIFEST = PROJECT_ROOT / "output" / "reports" / "media_manifest.json"

OUTPUT_SUBTITLES = PROJECT_ROOT / "output" / "subtitles"
OUTPUT_TIMELINES = PROJECT_ROOT / "output" / "timelines"
OUTPUT_REPORTS = PROJECT_ROOT / "output" / "reports"
OUTPUT_IMAGES = PROJECT_ROOT / "output" / "images"
OUTPUT_VIDEOS = PROJECT_ROOT / "output" / "videos"
OUTPUT_OVERLAYS = PROJECT_ROOT / "output" / "overlays" / "sample1_speech_subtitles"

STYLE_PROFILE = OUTPUT_SUBTITLES / "sample1_speech_subtitle_style_profile.json"
PATTERN_LIBRARY = OUTPUT_SUBTITLES / "sample1_speech_subtitle_pattern_library.json"
OVERLAY_MANIFEST = OUTPUT_SUBTITLES / "sample1_speech_subtitle_overlays.json"
OVERLAY_VIDEO = OUTPUT_SUBTITLES / "sample1_speech_subtitle_overlay.mov"
TIMELINE_PATH = OUTPUT_TIMELINES / "sample1_speech_subtitle_preview.timeline.json"
REPORT_PATH = OUTPUT_REPORTS / "sample1_speech_subtitle_preview_report.json"
PREVIEW_VIDEO = OUTPUT_VIDEOS / "preview_sample1_speech_subtitles.mp4"
PREVIEW_STILL = OUTPUT_IMAGES / "preview_sample1_speech_subtitles_t0005.jpg"

FONT_PATH = Path(r"C:\Windows\Fonts\YuGothB.ttc")
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
PREVIEW_WIDTH = 1280
PREVIEW_HEIGHT = 720
FPS = "24000/1001"
FPS_NUM = 24000
FPS_DEN = 1001
FPS_FLOAT = FPS_NUM / FPS_DEN
PURPLE_DARK = "#4D15D7"
PURPLE_MID = "#5A2DEF"
PURPLE_LIGHT = "#7863F3"
WHITE = "#FFFFFF"
WHITE_WARM = "#F7F5FA"
TEXT_PURPLE = "#572AF0"
TEXT_PURPLE_DARK = "#511DE3"
TEXT_PURPLE_MID = "#6442F2"
TEXT_PURPLE_LIGHT = "#755FF4"
MAX_CHARS_PER_CHUNK = 40


class Caption(dict):
    @property
    def index(self) -> int:
        return int(self["index"])

    @property
    def start(self) -> float:
        return float(self["start"])

    @property
    def end(self) -> float:
        return float(self["end"])

    @property
    def text(self) -> str:
        return str(self["text"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_srt_time(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid SRT timestamp: {value}")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def format_srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def parse_srt(path: Path) -> list[Caption]:
    raw = path.read_text(encoding="utf-8-sig").strip()
    if not raw:
        return []
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", raw):
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
        captions.append(
            Caption(
                index=int(rows[0]),
                start=parse_srt_time(start_raw),
                end=parse_srt_time(end_raw),
                text=normalize_text(" ".join(rows[2:])),
            )
        )
    return captions


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        "a high-opening experience.": "an eye-opening experience.",
        "A high-opening experience.": "An eye-opening experience.",
    }
    return replacements.get(text, text)


def write_srt(path: Path, captions: list[Caption]) -> None:
    rows: list[str] = []
    for index, caption in enumerate(captions, start=1):
        rows.extend(
            [
                str(index),
                f"{format_srt_time(caption.start)} --> {format_srt_time(caption.end)}",
                caption.text,
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows), encoding="utf-8")


def write_transcript_text(path: Path, captions: list[Caption]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(" ".join(caption.text for caption in captions).strip() + "\n", encoding="utf-8")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def rgb_to_hex(value: tuple[int, int, int]) -> str:
    return f"#{value[0]:02X}{value[1]:02X}{value[2]:02X}"


def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def gradient_image(size: tuple[int, int], stops: list[str]) -> Image.Image:
    width, height = size
    colors = [hex_to_rgb(stop) for stop in stops]
    gradient = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    pixels = gradient.load()
    for x in range(width):
        t = 0.0 if width <= 1 else x / (width - 1)
        segment = min(len(colors) - 2, int(t * (len(colors) - 1)))
        local_start = segment / (len(colors) - 1)
        local_end = (segment + 1) / (len(colors) - 1)
        local_t = 0.0 if local_end == local_start else (t - local_start) / (local_end - local_start)
        c0 = colors[segment]
        c1 = colors[segment + 1]
        color = tuple(lerp(c0[i], c1[i], local_t) for i in range(3)) + (255,)
        for y in range(height):
            pixels[x, y] = color
    return gradient


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def paste_gradient_box(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    colors: list[str],
    radius: int,
    shadow: dict[str, Any],
) -> None:
    x0, y0, x1, y1 = box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    mask = rounded_mask((width, height), radius)
    if shadow.get("enabled"):
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_rect = Image.new("RGBA", (width, height), (0, 0, 0, int(255 * float(shadow.get("opacity", 0.2)))))
        shadow_layer.paste(shadow_rect, (x0, y0 + int(shadow.get("offsetY", 4))), mask)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(int(shadow.get("blur", 8))))
        canvas.alpha_composite(shadow_layer)
    rect = gradient_image((width, height), colors)
    canvas.paste(rect, (x0, y0), mask)


def draw_gradient_text(
    layer: Image.Image,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str | list[str],
) -> None:
    if isinstance(fill, str):
        ImageDraw.Draw(layer).text(position, text, font=font, fill=fill)
        return

    text_mask = Image.new("L", layer.size, 0)
    mask_draw = ImageDraw.Draw(text_mask)
    mask_draw.text(position, text, font=font, fill=255)
    bounds = text_mask.getbbox()
    if bounds is None:
        return
    x0, y0, x1, y1 = bounds
    text_gradient = gradient_image((x1 - x0, y1 - y0), fill)
    layer.paste(text_gradient, (x0, y0), text_mask.crop(bounds))


def text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = text_bbox(draw, text, font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def split_words(text: str, limit: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > limit:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def split_caption_to_chunks(caption: Caption) -> list[Caption]:
    chunks = split_words(caption.text, MAX_CHARS_PER_CHUNK)
    if len(chunks) <= 1:
        return [caption]
    weights = [max(1, len(chunk)) for chunk in chunks]
    total = sum(weights)
    duration = max(0.1, caption.end - caption.start)
    output: list[Caption] = []
    cursor = caption.start
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        end = caption.end if index == len(chunks) - 1 else min(caption.end, cursor + duration * weight / total)
        output.append(Caption(index=caption.index, start=cursor, end=end, text=chunk))
        cursor = end
    return output


def ease_out_cubic(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1.0 - (1.0 - value) ** 3


def analyze_subtitle_animation(data: dict[str, Any]) -> dict[str, Any]:
    states: list[dict[str, Any]] = []
    for frame in data.get("frames", []):
        if not isinstance(frame, dict):
            continue
        subtitles = [
            item
            for item in frame.get("textOverlays", [])
            if isinstance(item, dict)
            and item.get("role") == "subtitle"
            and isinstance(item.get("bbox", {}).get("norm"), list)
            and float(item["bbox"]["norm"][1]) >= 0.55
        ]
        if not subtitles:
            states.append({"time": float(frame.get("timeSeconds", 0.0)), "subtitles": []})
            continue
        states.append(
            {
                "time": float(frame.get("timeSeconds", 0.0)),
                "subtitles": [
                    {
                        "text": str(item.get("text") or ""),
                        "x": float(item["bbox"]["norm"][0]),
                        "y": float(item["bbox"]["norm"][1]),
                        "w": float(item["bbox"]["norm"][2]),
                        "h": float(item["bbox"]["norm"][3]),
                    }
                    for item in subtitles
                ],
            }
        )

    observations: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for state in states:
        current_subs = state["subtitles"]
        if previous is None:
            previous = state
            continue
        previous_subs = previous["subtitles"]
        for current in current_subs:
            best_previous = None
            for candidate in previous_subs:
                if current["text"].startswith(candidate["text"]) or candidate["text"].startswith(current["text"]):
                    best_previous = candidate
                    break
            if best_previous and current["w"] > best_previous["w"] * 1.25:
                observations.append(
                    {
                        "timeFrom": previous["time"],
                        "timeTo": state["time"],
                        "textFrom": best_previous["text"],
                        "textTo": current["text"],
                        "widthNormFrom": round(best_previous["w"], 6),
                        "widthNormTo": round(current["w"], 6),
                        "widthGrowthRatio": round(current["w"] / max(0.001, best_previous["w"]), 3),
                        "interpretation": "same subtitle expands horizontally while text is revealed",
                    }
                )
        if not previous_subs and current_subs:
            observations.append(
                {
                    "timeFrom": previous["time"],
                    "timeTo": state["time"],
                    "textTo": " | ".join(item["text"] for item in current_subs),
                    "interpretation": "subtitle group appears after empty state",
                }
            )
        if len(current_subs) > len(previous_subs) and previous_subs:
            observations.append(
                {
                    "timeFrom": previous["time"],
                    "timeTo": state["time"],
                    "lineCountFrom": len(previous_subs),
                    "lineCountTo": len(current_subs),
                    "interpretation": "second subtitle line is staggered after first line",
                }
            )
        previous = state

    growth_durations = [float(item["timeTo"]) - float(item["timeFrom"]) for item in observations if item.get("widthGrowthRatio")]
    stagger_durations = [
        float(item["timeTo"]) - float(item["timeFrom"])
        for item in observations
        if str(item.get("interpretation", "")).startswith("second subtitle line")
    ]
    return {
        "analysisSource": "reference analysis subtitle OCR time series",
        "samplingNote": "Reference analysis samples are sparse, so exact easing is inferred from observed partial-width subtitle states.",
        "observations": observations[:12],
        "in": {
            "type": "horizontal-reveal",
            "direction": "left-to-right",
            "durationSeconds": round(median_or_default(growth_durations, 0.46), 3),
            "easing": "easeOutCubic",
            "initialVisibleWidthRatio": 0.08,
            "initialOpacity": 0.0,
            "opacityDurationSeconds": 0.12,
        },
        "secondaryLine": {
            "staggerSeconds": round(min(0.18, median_or_default(stagger_durations, 0.12) * 0.35), 3),
            "inheritsReveal": True,
        },
        "out": {
            "type": "quick-fade",
            "durationSeconds": 0.1,
        },
    }


def best_two_line_split(text: str) -> list[str]:
    words = text.split()
    if len(words) < 3:
        return [text]
    best: tuple[float, list[str]] | None = None
    for index in range(1, len(words)):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        score = abs(len(left) - len(right))
        if left.endswith(("of", "to", "and", "the", "a")):
            score += 8
        if right.startswith(("of", "to", "and", "the", "a")):
            score += 5
        if best is None or score < best[0]:
            best = (score, [left, right])
    return best[1] if best else [text]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def fit_font_size(lines: list[str], style: dict[str, Any], draw: ImageDraw.ImageDraw) -> int:
    base_size = int(style["text"]["fontSizePx"])
    min_size = int(style["text"]["minFontSizePx"])
    padding_x = int(style["background"]["paddingX"])
    max_widths = [int(row["maxWidthPx"]) for row in style["placement"]["rows"]]
    for size in range(base_size, min_size - 1, -2):
        font = load_font(size)
        fits = True
        for index, line in enumerate(lines):
            width, _ = text_size(draw, line, font)
            max_width = max_widths[min(index, len(max_widths) - 1)]
            if width + padding_x * 2 > max_width:
                fits = False
                break
        if fits:
            return size
    return min_size


def fit_lines(text: str, style: dict[str, Any], draw: ImageDraw.ImageDraw) -> tuple[list[str], int]:
    single = [text]
    size = fit_font_size(single, style, draw)
    font = load_font(size)
    width, _ = text_size(draw, text, font)
    if width + int(style["background"]["paddingX"]) * 2 <= int(style["placement"]["rows"][0]["maxWidthPx"]):
        return single, size
    lines = best_two_line_split(text)
    return lines, fit_font_size(lines, style, draw)


def subtitle_items_from_analysis(data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for frame in data.get("frames", []):
        if not isinstance(frame, dict):
            continue
        for item in frame.get("textOverlays", []):
            if isinstance(item, dict) and item.get("role") == "subtitle":
                bbox = item.get("bbox", {}).get("norm")
                if isinstance(bbox, list) and len(bbox) == 4 and float(bbox[1]) >= 0.55:
                    items.append(item)
    return items


def median_or_default(values: list[float], default: float) -> float:
    return float(median(values)) if values else default


def median_rgb_or_default(values: list[tuple[int, int, int]], default: tuple[int, int, int]) -> tuple[int, int, int]:
    if not values:
        return default
    return tuple(round(median([value[index] for value in values])) for index in range(3))


def reference_sample_path(time_seconds: float) -> Path | None:
    samples_dir = REFERENCE_ANALYSIS.parent / "samples"
    patterns = [
        f"*t{time_seconds:08.3f}.jpg",
        f"*t{time_seconds:07.3f}.jpg",
        f"*t{time_seconds:04.3f}.jpg",
    ]
    for pattern in patterns:
        matches = sorted(samples_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def classify_anchor(x_norm: float, w_norm: float) -> str:
    center = x_norm + w_norm / 2
    if center <= 0.45:
        return "left"
    if center >= 0.55:
        return "right"
    return "center"


def width_bucket(w_norm: float) -> str:
    if w_norm >= 0.74:
        return "wide"
    if w_norm >= 0.48:
        return "medium"
    return "narrow"


def sample_color_thirds(
    image: Image.Image,
    box: tuple[int, int, int, int],
    predicate: Any,
    default: tuple[int, int, int],
) -> list[str]:
    crop = image.crop(box)
    width, height = crop.size
    thirds: list[list[tuple[int, int, int]]] = [[], [], []]
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            pixel = crop.getpixel((x, y))
            if predicate(pixel):
                thirds[min(2, int(x / max(1, width) * 3))].append(pixel)
    return [rgb_to_hex(median_rgb_or_default(values, default)) for values in thirds]


def is_purple_pixel(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    return b >= 145 and r <= 175 and g <= 165 and b - r >= 25 and b - g >= 45


def is_white_pixel(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    return r >= 220 and g >= 220 and b >= 220


def is_purple_background_pixel(pixel: tuple[int, int, int]) -> bool:
    r, g, b = pixel
    return b >= 150 and r <= 145 and g <= 135 and b - g >= 45


def normalize_purple_text_gradient(stops: list[str]) -> list[str]:
    if len(stops) < 3:
        return [TEXT_PURPLE_DARK, TEXT_PURPLE_MID, TEXT_PURPLE_LIGHT]
    parsed = [hex_to_rgb(stop) for stop in stops[:3]]
    if all(b >= 200 and b - r >= 20 and b - g >= 45 for r, g, b in parsed):
        return stops[:3]
    return [TEXT_PURPLE_DARK, TEXT_PURPLE_MID, TEXT_PURPLE_LIGHT]


def analyze_line_from_frame(
    image: Image.Image,
    item: dict[str, Any],
    ref_w: int,
    ref_h: int,
) -> dict[str, Any] | None:
    bbox = item.get("bbox", {})
    norm = bbox.get("norm")
    xyxy = bbox.get("xyxyPixel")
    if not isinstance(norm, list) or len(norm) != 4 or not isinstance(xyxy, list) or len(xyxy) != 4:
        return None

    x0, y0, x1, y1 = [max(0, round(float(value))) for value in xyxy]
    x1 = min(ref_w, x1)
    y1 = min(ref_h, y1)
    if x1 <= x0 or y1 <= y0:
        return None

    crop = image.crop((x0, y0, x1, y1))
    width, height = crop.size
    purple_count = 0
    white_count = 0
    sample_count = 0
    for y in range(0, height, 3):
        for x in range(0, width, 3):
            pixel = crop.getpixel((x, y))
            sample_count += 1
            if is_purple_background_pixel(pixel):
                purple_count += 1
            if is_white_pixel(pixel):
                white_count += 1

    background_kind = "purple" if purple_count >= white_count * 0.65 else "white"
    if background_kind == "purple":
        bg_default = hex_to_rgb(PURPLE_MID)
        bg_gradient = sample_color_thirds(image, (x0, y0, x1, y1), is_purple_background_pixel, bg_default)
        text_fill: str | list[str] = WHITE
        text_kind = "white"
    else:
        bg_gradient = sample_color_thirds(image, (x0, y0, x1, y1), is_white_pixel, hex_to_rgb(WHITE))
        purple_text = sample_color_thirds(image, (x0, y0, x1, y1), is_purple_pixel, hex_to_rgb(TEXT_PURPLE))
        text_fill = normalize_purple_text_gradient(purple_text)
        text_kind = "purple-gradient"

    x_norm, y_norm, w_norm, h_norm = [float(value) for value in norm]
    return {
        "text": str(item.get("text") or ""),
        "xNorm": round(x_norm, 6),
        "yNorm": round(y_norm, 6),
        "wNorm": round(w_norm, 6),
        "hNorm": round(h_norm, 6),
        "centerXNorm": round(x_norm + w_norm / 2, 6),
        "rightNorm": round(x_norm + w_norm, 6),
        "rowBand": "upper-speech" if y_norm < 0.72 else "lower-speech",
        "anchor": classify_anchor(x_norm, w_norm),
        "widthBucket": width_bucket(w_norm),
        "backgroundKind": background_kind,
        "backgroundGradient": bg_gradient,
        "textKind": text_kind,
        "textFill": text_fill,
        "fontSizePxEstimate": item.get("fontSizePxEstimate"),
        "sampledPixelCounts": {
            "total": sample_count,
            "purple": purple_count,
            "white": white_count,
        },
    }


def pattern_signature(lines: list[dict[str, Any]]) -> str:
    parts = [f"lines={len(lines)}"]
    for line in lines:
        parts.append(
            "|".join(
                [
                    str(line["rowBand"]),
                    str(line["anchor"]),
                    str(line["widthBucket"]),
                    str(line["backgroundKind"]),
                    str(line["textKind"]),
                ]
            )
        )
    return ";".join(parts)


def build_reference_pattern_library(data: dict[str, Any]) -> dict[str, Any]:
    asset = data.get("asset", {})
    ref_w = int(asset.get("width") or 1834)
    ref_h = int(asset.get("height") or 1030)
    analyzed_frames: list[dict[str, Any]] = []
    clusters: dict[str, dict[str, Any]] = {}

    for frame in data.get("frames", []):
        time_seconds = float(frame.get("timeSeconds", 0.0))
        if abs(time_seconds - round(time_seconds)) > 0.001:
            continue
        sample_path = reference_sample_path(time_seconds)
        if sample_path is None:
            continue
        image = Image.open(sample_path).convert("RGB")
        lines: list[dict[str, Any]] = []
        for item in frame.get("textOverlays", []):
            if not isinstance(item, dict) or item.get("role") != "subtitle":
                continue
            bbox = item.get("bbox", {}).get("norm")
            if not isinstance(bbox, list) or len(bbox) != 4 or float(bbox[1]) < 0.55:
                continue
            line = analyze_line_from_frame(image, item, ref_w, ref_h)
            if line:
                lines.append(line)
        lines.sort(key=lambda line: (float(line["yNorm"]), float(line["xNorm"])))
        if not lines:
            continue
        signature = pattern_signature(lines)
        frame_entry = {
            "timeSeconds": round(time_seconds, 3),
            "samplePath": str(sample_path),
            "signature": signature,
            "lineCount": len(lines),
            "lines": lines,
        }
        analyzed_frames.append(frame_entry)
        cluster = clusters.setdefault(
            signature,
            {
                "signature": signature,
                "occurrences": [],
                "lineCount": len(lines),
                "lines": lines,
            },
        )
        cluster["occurrences"].append(round(time_seconds, 3))

    patterns: list[dict[str, Any]] = []
    for index, cluster in enumerate(sorted(clusters.values(), key=lambda item: (-len(item["occurrences"]), item["signature"])), start=1):
        cluster["id"] = f"sample1_pattern_{index:02d}"
        cluster["occurrenceCount"] = len(cluster["occurrences"])
        patterns.append(cluster)

    return {
        "schemaVersion": "speech-subtitle-pattern-library/v1",
        "createdAt": now_iso(),
        "sourceReference": {
            "assetId": asset.get("assetId", "sample-1"),
            "analysisPath": str(REFERENCE_ANALYSIS),
            "sampleDirectory": str(REFERENCE_ANALYSIS.parent / "samples"),
            "sampleIntervalSeconds": 1,
            "targetRole": "subtitle",
            "ignoredRoles": ["logo_text", "title", "small_text"],
        },
        "referenceCanvas": {"width": ref_w, "height": ref_h},
        "frameCount": len(analyzed_frames),
        "patternCount": len(patterns),
        "patterns": patterns,
        "frames": analyzed_frames,
        "classificationRules": {
            "anchor": "left if centerX <= 0.45, right if centerX >= 0.55, otherwise center",
            "backgroundKind": "purple when sampled purple background pixels dominate sampled white pixels; otherwise white",
            "signature": "line count plus each line row band, anchor, width bucket, background kind, and text kind",
        },
    }


def style_profile_from_reference(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    asset = data.get("asset", {})
    ref_w = int(asset.get("width") or 1834)
    ref_h = int(asset.get("height") or 1030)
    subtitle_items = subtitle_items_from_analysis(data)
    row1 = [item for item in subtitle_items if float(item["bbox"]["norm"][1]) < 0.72]
    row2 = [item for item in subtitle_items if float(item["bbox"]["norm"][1]) >= 0.72]
    all_rows = row1 + row2

    def norm_values(items: list[dict[str, Any]], index: int, default: float) -> float:
        return median_or_default([float(item["bbox"]["norm"][index]) for item in items], default)

    font_norm = median_or_default([float(item.get("fontSizePxEstimate")) / ref_h for item in all_rows if item.get("fontSizePxEstimate")], 0.155)
    row_height_norm = norm_values(all_rows, 3, 0.155)
    pattern_library = build_reference_pattern_library(data)
    profile = {
        "schemaVersion": "speech-subtitle-style/v1",
        "createdAt": now_iso(),
        "sourceReference": {
            "assetId": asset.get("assetId", "sample-1"),
            "analysisPath": str(path),
            "targetRole": "subtitle",
            "ignoredRoles": ["logo_text", "title", "small_text"],
        },
        "referenceCanvas": {"width": ref_w, "height": ref_h, "aspectRatio": asset.get("width", ref_w) / asset.get("height", ref_h)},
        "renderCanvas": {"width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT, "profile": "preview"},
        "measurements": {
            "subtitleBoxCount": len(subtitle_items),
            "row1BoxCount": len(row1),
            "row2BoxCount": len(row2),
            "fontSizeNormMedian": round(font_norm, 6),
            "rowHeightNormMedian": round(row_height_norm, 6),
            "row1NormMedian": {
                "x": round(norm_values(row1, 0, 0.06), 6),
                "y": round(norm_values(row1, 1, 0.604), 6),
                "w": round(norm_values(row1, 2, 0.74), 6),
                "h": round(norm_values(row1, 3, 0.158), 6),
            },
            "row2NormMedian": {
                "x": round(norm_values(row2, 0, 0.377), 6),
                "y": round(norm_values(row2, 1, 0.793), 6),
                "w": round(norm_values(row2, 2, 0.56), 6),
                "h": round(norm_values(row2, 3, 0.153), 6),
            },
        },
        "speechSubtitle": {
            "placement": {
                "anchor": "lower-middle",
                "rows": [
                    {
                        "name": "primary",
                        "centerXNorm": 0.5,
                        "yNorm": round(norm_values(row1, 1, 0.604), 6),
                        "heightNorm": round(row_height_norm, 6),
                        "maxWidthNorm": 0.9,
                    },
                    {
                        "name": "secondary",
                        "centerXNorm": 0.5,
                        "yNorm": round(norm_values(row2, 1, 0.793), 6),
                        "heightNorm": round(row_height_norm, 6),
                        "maxWidthNorm": 0.74,
                    },
                ],
            },
            "text": {
                "fontFamily": "Yu Gothic Bold",
                "fontPath": str(FONT_PATH),
                "fontSizeNorm": round(font_norm, 6),
                "fontSizePx": max(88, round(font_norm * PREVIEW_HEIGHT * 0.9)),
                "minFontSizePx": 74,
                "weight": 800,
                "line1Fill": WHITE,
                "line2Fill": TEXT_PURPLE,
                "line2FillGradient": {
                    "direction": "left-to-right",
                    "stops": [TEXT_PURPLE_DARK, TEXT_PURPLE_MID, TEXT_PURPLE_LIGHT],
                    "referenceSamples": [
                        {
                            "timeSeconds": 0.0,
                            "text": "FDEの正体とは?",
                            "bboxPixel": [691, 817, 1721, 975],
                            "leftMedianRgb": [81, 29, 227],
                            "middleMedianRgb": [100, 65, 241],
                            "rightMedianRgb": [118, 95, 244],
                        },
                        {
                            "timeSeconds": 1.0,
                            "text": "FDEの正体とは?",
                            "bboxPixel": [693, 817, 1721, 975],
                            "leftMedianRgb": [82, 29, 226],
                            "middleMedianRgb": [100, 65, 242],
                            "rightMedianRgb": [117, 95, 244],
                        },
                    ],
                    "analysisNote": "Purple text pixels on the white subtitle box are darker on the left and become slightly lighter/whiter toward the right.",
                },
            },
            "background": {
                "shape": "rounded-rectangle",
                "radiusNorm": 0.008,
                "paddingXNorm": 0.027,
                "paddingYNorm": 0.016,
                "line1Gradient": [PURPLE_DARK, PURPLE_MID, PURPLE_LIGHT],
                "line2Gradient": [WHITE, WHITE_WARM],
                "shadow": {"enabled": True, "color": "#000000", "opacity": 0.2, "blurNorm": 0.008, "offsetYNorm": 0.004},
            },
            "compositionRules": {
                "maxLines": 2,
                "singleLineUsesPrimaryPurpleBox": False,
                "twoLineUsesPurpleThenWhite": False,
                "topLogoAndTitleIgnored": True,
                "renderUsesExtractedReferencePatterns": True,
            },
            "referencePatterns": pattern_library,
            "animation": analyze_subtitle_animation(data),
        },
    }
    materialize_style_pixels(profile)
    return profile


def materialize_style_pixels(profile: dict[str, Any]) -> None:
    subtitle = profile["speechSubtitle"]
    placement = subtitle["placement"]
    for row in placement["rows"]:
        row["yPx"] = round(float(row["yNorm"]) * PREVIEW_HEIGHT)
        row["heightPx"] = round(float(row["heightNorm"]) * PREVIEW_HEIGHT)
        row["maxWidthPx"] = round(float(row["maxWidthNorm"]) * PREVIEW_WIDTH)
        row["centerXPx"] = round(float(row["centerXNorm"]) * PREVIEW_WIDTH)
    bg = subtitle["background"]
    bg["radiusPx"] = round(float(bg["radiusNorm"]) * PREVIEW_HEIGHT)
    bg["paddingX"] = round(float(bg["paddingXNorm"]) * PREVIEW_WIDTH)
    bg["paddingY"] = round(float(bg["paddingYNorm"]) * PREVIEW_HEIGHT)
    shadow = bg["shadow"]
    shadow["blur"] = round(float(shadow["blurNorm"]) * PREVIEW_HEIGHT)
    shadow["offsetY"] = round(float(shadow["offsetYNorm"]) * PREVIEW_HEIGHT)


def line_animation_progress(caption: Caption, style: dict[str, Any], time_seconds: float | None, line_index: int) -> tuple[float, float]:
    if time_seconds is None:
        return 1.0, 1.0
    animation = style["animation"]
    start_delay = 0.0
    if line_index > 0:
        start_delay = float(animation["secondaryLine"]["staggerSeconds"])
    start = caption.start + start_delay
    reveal_duration = max(0.01, float(animation["in"]["durationSeconds"]))
    opacity_duration = max(0.01, float(animation["in"]["opacityDurationSeconds"]))
    out_duration = max(0.01, float(animation["out"]["durationSeconds"]))
    reveal = ease_out_cubic((time_seconds - start) / reveal_duration)
    opacity = min(1.0, max(0.0, (time_seconds - start) / opacity_duration))
    if caption.end - out_duration <= time_seconds <= caption.end:
        opacity *= max(0.0, (caption.end - time_seconds) / out_duration)
    if time_seconds < start or time_seconds > caption.end:
        return 0.0, 0.0
    visible_start = float(animation["in"]["initialVisibleWidthRatio"])
    visible_ratio = visible_start + (1.0 - visible_start) * reveal
    return max(0.0, min(1.0, visible_ratio)), max(0.0, min(1.0, opacity))


def apply_opacity(layer: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return layer
    next_layer = layer.copy()
    alpha = next_layer.getchannel("A").point(lambda value: round(value * opacity))
    next_layer.putalpha(alpha)
    return next_layer


def choose_reference_pattern(caption: Caption, style: dict[str, Any], line_count: int) -> dict[str, Any] | None:
    patterns = style.get("referencePatterns", {}).get("patterns", [])
    if not patterns:
        return None
    eligible = [pattern for pattern in patterns if int(pattern.get("lineCount", 0)) == line_count]
    if not eligible:
        eligible = [pattern for pattern in patterns if int(pattern.get("lineCount", 0)) >= line_count]
    if not eligible:
        eligible = patterns
    key = f"{caption.index}|{caption.start:.3f}|{caption.end:.3f}|{caption.text}|{line_count}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return eligible[int(digest[:12], 16) % len(eligible)]


def resolve_line_layout(
    pattern: dict[str, Any] | None,
    index: int,
    row: dict[str, Any],
    box_w: int,
    box_h: int,
) -> tuple[int, int, int, int, list[str], str | list[str], str, str]:
    if not pattern or not pattern.get("lines"):
        center_x = int(row["centerXPx"])
        x0 = max(0, center_x - box_w // 2)
        x1 = min(PREVIEW_WIDTH, x0 + box_w)
        x0 = x1 - box_w
        y0 = int(row["yPx"])
        y1 = min(PREVIEW_HEIGHT - 6, y0 + box_h)
        colors = [PURPLE_DARK, PURPLE_MID, PURPLE_LIGHT] if index == 0 else [WHITE, WHITE_WARM]
        fill: str | list[str] = WHITE if index == 0 else [TEXT_PURPLE_DARK, TEXT_PURPLE_MID, TEXT_PURPLE_LIGHT]
        return x0, y0, x1, y1, colors, fill, "fallback", "center"

    pattern_lines = pattern["lines"]
    line = pattern_lines[min(index, len(pattern_lines) - 1)]
    anchor = str(line.get("anchor", "center"))
    observed_x0 = round(float(line.get("xNorm", 0.1)) * PREVIEW_WIDTH)
    observed_right = round(float(line.get("rightNorm", 0.9)) * PREVIEW_WIDTH)
    observed_center = round(float(line.get("centerXNorm", 0.5)) * PREVIEW_WIDTH)
    y0 = round(float(line.get("yNorm", float(row["yNorm"]))) * PREVIEW_HEIGHT)
    if anchor == "left":
        x0 = observed_x0
    elif anchor == "right":
        x0 = observed_right - box_w
    else:
        x0 = observed_center - box_w // 2
    x0 = max(8, min(PREVIEW_WIDTH - box_w - 8, x0))
    x1 = x0 + box_w
    y1 = min(PREVIEW_HEIGHT - 6, y0 + box_h)
    colors = line.get("backgroundGradient")
    if not isinstance(colors, list) or not colors:
        colors = [PURPLE_DARK, PURPLE_MID, PURPLE_LIGHT] if line.get("backgroundKind") == "purple" else [WHITE, WHITE_WARM]
    fill_value = line.get("textFill")
    if line.get("textKind") == "purple-gradient":
        fill = fill_value if isinstance(fill_value, list) and fill_value else [TEXT_PURPLE_DARK, TEXT_PURPLE_MID, TEXT_PURPLE_LIGHT]
    else:
        fill = WHITE
    return x0, y0, x1, y1, colors, fill, str(pattern.get("id", "")), anchor


def draw_caption_on_canvas(
    canvas: Image.Image,
    caption: Caption,
    profile: dict[str, Any],
    *,
    time_seconds: float | None = None,
) -> list[dict[str, Any]]:
    style = profile["speechSubtitle"]
    draw = ImageDraw.Draw(canvas)
    lines, font_size = fit_lines(caption.text, style, draw)
    pattern = choose_reference_pattern(caption, style, len(lines))
    font = load_font(font_size)
    padding_x = int(style["background"]["paddingX"])
    padding_y = int(style["background"]["paddingY"])
    radius = int(style["background"]["radiusPx"])
    shadow = style["background"]["shadow"]
    rendered_lines: list[dict[str, Any]] = []
    for index, line in enumerate(lines[:2]):
        visible_ratio, opacity = line_animation_progress(caption, style, time_seconds, index)
        if visible_ratio <= 0.001 or opacity <= 0.001:
            continue
        row = style["placement"]["rows"][min(index, 1)]
        text_w, text_h = text_size(draw, line, font)
        box_w = min(PREVIEW_WIDTH - 16, max(text_w + padding_x * 2, round(float(row["heightPx"]) * 2.1)))
        box_h = max(int(row["heightPx"]), text_h + padding_y * 2)
        x0, y0, x1, y1, colors, fill, pattern_id, anchor = resolve_line_layout(pattern, index, row, box_w, box_h)
        line_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        paste_gradient_box(line_layer, (x0, y0, x1, y1), colors, radius, shadow)
        bbox = text_bbox(draw, line, font)
        tx = x0 + (box_w - text_w) // 2 - bbox[0]
        ty = y0 + (box_h - text_h) // 2 - bbox[1]
        draw_gradient_text(line_layer, (tx, ty), line, font, fill)
        reveal_width = max(1, min(PREVIEW_WIDTH - x0, round((x1 - x0) * visible_ratio)))
        reveal_mask = Image.new("L", canvas.size, 0)
        reveal_draw = ImageDraw.Draw(reveal_mask)
        reveal_draw.rectangle((x0, max(0, y0 - 24), x0 + reveal_width, min(PREVIEW_HEIGHT, y1 + 24)), fill=255)
        line_alpha = line_layer.getchannel("A")
        line_alpha = Image.composite(line_alpha, Image.new("L", canvas.size, 0), reveal_mask)
        line_layer.putalpha(line_alpha)
        canvas.alpha_composite(apply_opacity(line_layer, opacity))
        style_label = "whiteBoxPurpleGradientText" if isinstance(fill, list) else "purpleBoxWhiteText"
        rendered_lines.append(
            {
                "text": line,
                "style": style_label,
                "boxPx": [x0, y0, x1, y1],
                "fontSizePx": font_size,
                "textFill": fill,
                "textFillMode": "solid" if isinstance(fill, str) else "left-to-right-gradient",
                "backgroundGradient": colors,
                "referencePatternId": pattern_id,
                "referenceAnchor": anchor,
                "animation": {
                    "visibleWidthRatio": round(visible_ratio, 4),
                    "opacity": round(opacity, 4),
                },
            }
        )
    return rendered_lines


def render_overlay_png(caption: Caption, profile: dict[str, Any], output: Path) -> dict[str, Any]:
    canvas = Image.new("RGBA", (PREVIEW_WIDTH, PREVIEW_HEIGHT), (0, 0, 0, 0))
    rendered_lines = draw_caption_on_canvas(canvas, caption, profile, time_seconds=None)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    return {
        "file": str(output),
        "start": round(caption.start, 6),
        "end": round(caption.end, 6),
        "text": caption.text,
        "lines": rendered_lines,
    }


def build_overlay_manifest(captions: list[Caption], profile: dict[str, Any]) -> dict[str, Any]:
    if OUTPUT_OVERLAYS.exists():
        shutil.rmtree(OUTPUT_OVERLAYS)
    OUTPUT_OVERLAYS.mkdir(parents=True, exist_ok=True)
    overlays: list[dict[str, Any]] = []
    count = 1
    for caption in captions:
        for chunk in split_caption_to_chunks(caption):
            path = OUTPUT_OVERLAYS / f"speech_subtitle_{count:04d}.png"
            overlays.append(render_overlay_png(chunk, profile, path))
            count += 1
    payload = {
        "schemaVersion": "speech-subtitle-overlays/v1",
        "createdAt": now_iso(),
        "styleProfile": str(STYLE_PROFILE),
        "patternLibrary": str(PATTERN_LIBRARY),
        "animatedOverlayVideo": str(OVERLAY_VIDEO),
        "canvas": {"width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT},
        "animation": profile["speechSubtitle"]["animation"],
        "overlays": overlays,
    }
    OVERLAY_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OVERLAY_MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def video_duration(path: Path, ffprobe: str) -> float:
    command = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    return float(subprocess.check_output(command, cwd=REPO_ROOT, text=True).strip())


def render_animated_overlay_video(ffmpeg: str, captions: list[Caption], profile: dict[str, Any], duration: float) -> None:
    OVERLAY_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    total_frames = math.ceil(duration * FPS_FLOAT)
    chunks: list[Caption] = []
    for caption in captions:
        chunks.extend(split_caption_to_chunks(caption))
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{PREVIEW_WIDTH}x{PREVIEW_HEIGHT}",
        "-r",
        FPS,
        "-i",
        "-",
        "-an",
        "-c:v",
        "qtrle",
        str(OVERLAY_VIDEO),
    ]
    process = subprocess.Popen(command, cwd=REPO_ROOT, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(total_frames):
            time_seconds = frame_index / FPS_FLOAT
            canvas = Image.new("RGBA", (PREVIEW_WIDTH, PREVIEW_HEIGHT), (0, 0, 0, 0))
            for chunk in chunks:
                animation = profile["speechSubtitle"]["animation"]
                earliest = chunk.start
                latest = chunk.end
                if earliest <= time_seconds <= latest + float(animation["out"]["durationSeconds"]):
                    draw_caption_on_canvas(canvas, chunk, profile, time_seconds=time_seconds)
            process.stdin.write(canvas.tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise subprocess.CalledProcessError(process.returncode, command)


def render_preview(ffmpeg: str, overlay_video: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = f"[0:v]scale={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:flags=bicubic[base];[base][1:v]overlay=0:0:format=auto[v]"
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(SOURCE_VIDEO),
        "-i",
        str(overlay_video),
        "-filter_complex",
        filters,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def extract_still(ffmpeg: str, video: Path, output: Path, at: str = "5") -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-y", "-ss", at, "-i", str(video), "-frames:v", "1", "-update", "1", str(output)]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def write_timeline(duration: float) -> None:
    timeline = {
        "schemaVersion": "video-edit-timeline/v1",
        "id": "timeline_test-project-1_sample1_speech_subtitle_preview",
        "createdAt": now_iso(),
        "project": {
            "id": "test-project-1",
            "name": "Test Project 1",
            "root": str(PROJECT_ROOT),
            "sourceRoot": str(PROJECT_ROOT / "source"),
            "outputRoot": str(PROJECT_ROOT / "output"),
        },
        "timebase": {"unit": "seconds", "fps": FPS},
        "duration": round(duration, 6),
        "sources": [
            {"id": "src_master", "kind": "video", "role": "master", "path": str(SOURCE_VIDEO), "duration": round(duration, 6), "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT, "fps": FPS, "codec": "h264"},
            {"id": "src_corrected_srt", "kind": "subtitle", "role": "subtitle", "path": str(CORRECTED_SRT)},
            {"id": "src_style_profile", "kind": "data", "role": "speech-subtitle-style-profile", "path": str(STYLE_PROFILE)},
            {"id": "src_pattern_library", "kind": "data", "role": "speech-subtitle-pattern-library", "path": str(PATTERN_LIBRARY)},
            {"id": "src_overlay_manifest", "kind": "data", "role": "speech-subtitle-overlay-manifest", "path": str(OVERLAY_MANIFEST)},
            {"id": "src_animated_overlay", "kind": "video", "role": "speech-subtitle-animated-overlay", "path": str(OVERLAY_VIDEO), "duration": round(duration, 6), "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT, "fps": FPS, "codec": "qtrle"},
        ],
        "tracks": [
            {"id": "video.main", "kind": "video", "label": "Main video", "allowOverlap": False},
            {"id": "audio.main", "kind": "audio", "label": "Source audio", "allowOverlap": False},
            {"id": "subtitle.main", "kind": "subtitle", "label": "Sample-1 speech subtitle overlays", "allowOverlap": True},
        ],
        "clips": [
            {"id": "clip_video_master", "trackId": "video.main", "kind": "video", "sourceId": "src_master", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "sourceIn": 0.0, "sourceOut": round(duration, 6), "fit": {"mode": "contain", "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT}},
            {"id": "clip_audio_master", "trackId": "audio.main", "kind": "audio", "sourceId": "src_master", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "sourceIn": 0.0, "sourceOut": round(duration, 6)},
            {"id": "clip_subtitle_overlay", "trackId": "subtitle.main", "kind": "generated", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "style": {"renderMethod": "animated-alpha-overlay-video", "styleProfile": str(STYLE_PROFILE), "patternLibrary": str(PATTERN_LIBRARY), "overlayManifest": str(OVERLAY_MANIFEST), "overlayVideo": str(OVERLAY_VIDEO)}},
        ],
        "transitions": [],
        "render": {
            "targets": [{"id": "preview", "path": str(PREVIEW_VIDEO), "format": "mp4", "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT, "fps": FPS, "profile": "preview", "videoCodec": "libx264", "audioCodec": "aac"}],
            "preview": {"enabled": True, "rangeStart": 0.0, "rangeEnd": round(duration, 6), "proxy": True},
        },
        "analysis": {
            "mediaManifestPath": str(MEDIA_MANIFEST),
            "reports": [
                {"kind": "media-manifest", "path": str(MEDIA_MANIFEST), "exists": MEDIA_MANIFEST.exists()},
                {"kind": "reference-analysis", "path": str(REFERENCE_ANALYSIS), "exists": REFERENCE_ANALYSIS.exists()},
                {"kind": "speech-subtitle-style-profile", "path": str(STYLE_PROFILE), "exists": STYLE_PROFILE.exists()},
                {"kind": "speech-subtitle-pattern-library", "path": str(PATTERN_LIBRARY), "exists": PATTERN_LIBRARY.exists()},
                {"kind": "speech-subtitle-overlay-manifest", "path": str(OVERLAY_MANIFEST), "exists": OVERLAY_MANIFEST.exists()},
                {"kind": "speech-subtitle-animated-overlay-video", "path": str(OVERLAY_VIDEO), "exists": OVERLAY_VIDEO.exists()},
            ],
        },
        "audit": {
            "createdBy": "projects/test-project-1/scripts/build_sample1_speech_subtitle_preview.py",
            "inputs": [
                {"kind": "primary-srt", "path": str(PRIMARY_SRT), "exists": PRIMARY_SRT.exists()},
                {"kind": "reference-analysis", "path": str(REFERENCE_ANALYSIS), "exists": REFERENCE_ANALYSIS.exists()},
            ],
        },
    }
    TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TIMELINE_PATH.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sample-1 speech-subtitle style JSON and preview overlays.")
    parser.add_argument("--ffmpeg", default=r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
    parser.add_argument("--ffprobe", default=r"C:\ProgramData\chocolatey\bin\ffprobe.exe")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    if not PRIMARY_SRT.exists():
        raise SystemExit(f"Transcript SRT is missing: {PRIMARY_SRT}")
    if not REFERENCE_ANALYSIS.exists():
        raise SystemExit(f"Reference analysis is missing: {REFERENCE_ANALYSIS}")

    duration = video_duration(SOURCE_VIDEO, args.ffprobe)
    captions = [Caption(index=item.index, start=item.start, end=item.end, text=normalize_text(item.text)) for item in parse_srt(PRIMARY_SRT)]
    write_srt(CORRECTED_SRT, captions)
    write_transcript_text(CORRECTED_TXT, captions)

    profile = style_profile_from_reference(REFERENCE_ANALYSIS)
    STYLE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    STYLE_PROFILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    PATTERN_LIBRARY.write_text(json.dumps(profile["speechSubtitle"]["referencePatterns"], ensure_ascii=False, indent=2), encoding="utf-8")
    overlay_manifest = build_overlay_manifest(captions, profile)
    write_timeline(duration)

    if not args.skip_render:
        render_animated_overlay_video(args.ffmpeg, captions, profile, duration)
        render_preview(args.ffmpeg, OVERLAY_VIDEO, PREVIEW_VIDEO)
        extract_still(args.ffmpeg, PREVIEW_VIDEO, PREVIEW_STILL, "5")
        extract_still(args.ffmpeg, PREVIEW_VIDEO, OUTPUT_IMAGES / "preview_sample1_speech_subtitles_t0032.jpg", "32")

    report = {
        "createdAt": now_iso(),
        "sourceVideo": str(SOURCE_VIDEO),
        "referenceAnalysis": str(REFERENCE_ANALYSIS),
        "styleProfile": str(STYLE_PROFILE),
        "patternLibrary": str(PATTERN_LIBRARY),
        "overlayManifest": str(OVERLAY_MANIFEST),
        "animatedOverlayVideo": str(OVERLAY_VIDEO) if OVERLAY_VIDEO.exists() else "",
        "correctedSrt": str(CORRECTED_SRT),
        "correctedTranscriptText": str(CORRECTED_TXT),
        "timeline": str(TIMELINE_PATH),
        "previewVideo": str(PREVIEW_VIDEO) if PREVIEW_VIDEO.exists() else "",
        "previewStill": str(PREVIEW_STILL) if PREVIEW_STILL.exists() else "",
        "captionCount": len(captions),
        "overlayCount": len(overlay_manifest["overlays"]),
        "referencePatternCount": profile["speechSubtitle"]["referencePatterns"]["patternCount"],
        "referencePatternFrameCount": profile["speechSubtitle"]["referencePatterns"]["frameCount"],
        "duration": round(duration, 6),
        "notes": [
            "Preview render only; production render should wait for user approval.",
            "Only sample-1 role=subtitle lower speech captions are profiled; top logo/title text is intentionally ignored.",
            "All whole-second sample-1 reference frames are classified into subtitle layout/background/anchor patterns.",
            "Preview subtitles choose a deterministic random extracted reference pattern per caption chunk.",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
