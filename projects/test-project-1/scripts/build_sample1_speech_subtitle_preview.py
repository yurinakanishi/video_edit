from __future__ import annotations

import argparse
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
OVERLAY_MANIFEST = OUTPUT_SUBTITLES / "sample1_speech_subtitle_overlays.json"
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
PURPLE_DARK = "#4D15D7"
PURPLE_MID = "#5A2DEF"
PURPLE_LIGHT = "#7863F3"
WHITE = "#FFFFFF"
WHITE_WARM = "#F7F5FA"
TEXT_PURPLE = "#572AF0"
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
                "singleLineUsesPrimaryPurpleBox": True,
                "twoLineUsesPurpleThenWhite": True,
                "topLogoAndTitleIgnored": True,
            },
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


def render_overlay_png(caption: Caption, profile: dict[str, Any], output: Path) -> dict[str, Any]:
    style = profile["speechSubtitle"]
    canvas = Image.new("RGBA", (PREVIEW_WIDTH, PREVIEW_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    lines, font_size = fit_lines(caption.text, style, draw)
    font = load_font(font_size)
    padding_x = int(style["background"]["paddingX"])
    padding_y = int(style["background"]["paddingY"])
    radius = int(style["background"]["radiusPx"])
    shadow = style["background"]["shadow"]
    rendered_lines: list[dict[str, Any]] = []
    for index, line in enumerate(lines[:2]):
        row = style["placement"]["rows"][min(index, 1)]
        text_w, text_h = text_size(draw, line, font)
        box_w = min(int(row["maxWidthPx"]), text_w + padding_x * 2)
        box_h = max(int(row["heightPx"]), text_h + padding_y * 2)
        center_x = int(row["centerXPx"])
        x0 = max(0, center_x - box_w // 2)
        x1 = min(PREVIEW_WIDTH, x0 + box_w)
        x0 = x1 - box_w
        y0 = int(row["yPx"])
        y1 = min(PREVIEW_HEIGHT - 6, y0 + box_h)
        colors = style["background"]["line1Gradient"] if index == 0 else style["background"]["line2Gradient"]
        fill = style["text"]["line1Fill"] if index == 0 else style["text"]["line2Fill"]
        paste_gradient_box(canvas, (x0, y0, x1, y1), colors, radius, shadow)
        bbox = text_bbox(draw, line, font)
        tx = x0 + (box_w - text_w) // 2 - bbox[0]
        ty = y0 + (box_h - text_h) // 2 - bbox[1] - round(box_h * 0.03)
        draw.text((tx, ty), line, font=font, fill=fill)
        rendered_lines.append(
            {
                "text": line,
                "style": "purpleBoxWhiteText" if index == 0 else "whiteBoxPurpleText",
                "boxPx": [x0, y0, x1, y1],
                "fontSizePx": font_size,
                "textFill": fill,
                "backgroundGradient": colors,
            }
        )
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
        "canvas": {"width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT},
        "overlays": overlays,
    }
    OVERLAY_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    OVERLAY_MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def video_duration(path: Path, ffprobe: str) -> float:
    command = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    return float(subprocess.check_output(command, cwd=REPO_ROOT, text=True).strip())


def render_preview(ffmpeg: str, overlays: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, "-hide_banner", "-y", "-i", str(SOURCE_VIDEO)]
    for item in overlays:
        command.extend(["-i", str(item["file"])])
    filters = [f"[0:v]scale={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:flags=bicubic[v0]"]
    previous = "v0"
    for index, item in enumerate(overlays, start=1):
        current = f"v{index}"
        start = float(item["start"])
        end = float(item["end"])
        filters.append(f"[{previous}][{index}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{current}]")
        previous = current
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{previous}]",
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
    )
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
            {"id": "src_overlay_manifest", "kind": "data", "role": "speech-subtitle-overlay-manifest", "path": str(OVERLAY_MANIFEST)},
        ],
        "tracks": [
            {"id": "video.main", "kind": "video", "label": "Main video", "allowOverlap": False},
            {"id": "audio.main", "kind": "audio", "label": "Source audio", "allowOverlap": False},
            {"id": "subtitle.main", "kind": "subtitle", "label": "Sample-1 speech subtitle overlays", "allowOverlap": True},
        ],
        "clips": [
            {"id": "clip_video_master", "trackId": "video.main", "kind": "video", "sourceId": "src_master", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "sourceIn": 0.0, "sourceOut": round(duration, 6), "fit": {"mode": "contain", "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT}},
            {"id": "clip_audio_master", "trackId": "audio.main", "kind": "audio", "sourceId": "src_master", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "sourceIn": 0.0, "sourceOut": round(duration, 6)},
            {"id": "clip_subtitle_overlay", "trackId": "subtitle.main", "kind": "generated", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "style": {"renderMethod": "png-overlay-gradient-boxes", "styleProfile": str(STYLE_PROFILE), "overlayManifest": str(OVERLAY_MANIFEST)}},
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
                {"kind": "speech-subtitle-overlay-manifest", "path": str(OVERLAY_MANIFEST), "exists": OVERLAY_MANIFEST.exists()},
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
    overlay_manifest = build_overlay_manifest(captions, profile)
    write_timeline(duration)

    if not args.skip_render:
        render_preview(args.ffmpeg, overlay_manifest["overlays"], PREVIEW_VIDEO)
        extract_still(args.ffmpeg, PREVIEW_VIDEO, PREVIEW_STILL, "5")
        extract_still(args.ffmpeg, PREVIEW_VIDEO, OUTPUT_IMAGES / "preview_sample1_speech_subtitles_t0032.jpg", "32")

    report = {
        "createdAt": now_iso(),
        "sourceVideo": str(SOURCE_VIDEO),
        "referenceAnalysis": str(REFERENCE_ANALYSIS),
        "styleProfile": str(STYLE_PROFILE),
        "overlayManifest": str(OVERLAY_MANIFEST),
        "correctedSrt": str(CORRECTED_SRT),
        "correctedTranscriptText": str(CORRECTED_TXT),
        "timeline": str(TIMELINE_PATH),
        "previewVideo": str(PREVIEW_VIDEO) if PREVIEW_VIDEO.exists() else "",
        "previewStill": str(PREVIEW_STILL) if PREVIEW_STILL.exists() else "",
        "captionCount": len(captions),
        "overlayCount": len(overlay_manifest["overlays"]),
        "duration": round(duration, 6),
        "notes": [
            "Preview render only; production render should wait for user approval.",
            "Only sample-1 role=subtitle lower speech captions are profiled; top logo/title text is intentionally ignored.",
            "Gradient subtitle boxes are rendered as transparent PNG overlays, not ASS subtitle backgrounds.",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
