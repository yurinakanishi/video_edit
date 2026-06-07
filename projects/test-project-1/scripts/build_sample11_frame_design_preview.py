from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
REFERENCE_ROOT = REPO_ROOT / "reference-assets"
REFERENCE_ASSET_DIR = REFERENCE_ROOT / "library" / "collections" / "layer-x" / "images" / "sample-11"
REFERENCE_IMAGE = REFERENCE_ASSET_DIR / "sample-11.png"
REFERENCE_ANALYSIS = REFERENCE_ASSET_DIR / "analysis.json"
REFERENCE_SAMPLE = REFERENCE_ASSET_DIR / "samples" / "frame_0000.jpg"
REFERENCE_DEBUG = REFERENCE_ASSET_DIR / "debug-overlays" / "frame_0000_debug.jpg"

PROJECT_REFERENCE_IMAGE = PROJECT_ROOT / "source" / "reference" / "sample-11-reference.png"
PROJECT_LOGO = PROJECT_ROOT / "source" / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"
SOURCE_VIDEO = PROJECT_ROOT / "source" / "video" / "Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4"
SUBTITLE_OVERLAY = PROJECT_ROOT / "output" / "subtitles" / "sample1_speech_subtitle_overlay.mov"

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_OVERLAYS = OUTPUT_DIR / "overlays" / "sample11_frame_design"
OUTPUT_REPORTS = OUTPUT_DIR / "reports"
OUTPUT_TIMELINES = OUTPUT_DIR / "timelines"
OUTPUT_IMAGES = OUTPUT_DIR / "images"
OUTPUT_VIDEOS = OUTPUT_DIR / "videos"
DESIGN_PROFILE = OUTPUT_DIR / "subtitles" / "sample11_frame_design_profile.json"
FRAME_OVERLAY = OUTPUT_OVERLAYS / "sample11_frame_overlay.png"
PREVIEW_VIDEO = OUTPUT_VIDEOS / "preview_sample11_frame_design.mp4"
PREVIEW_STILL = OUTPUT_IMAGES / "preview_sample11_frame_design_t0005.jpg"
TIMELINE_PATH = OUTPUT_TIMELINES / "sample11_frame_design_preview.timeline.json"
REPORT_PATH = OUTPUT_REPORTS / "sample11_frame_design_preview_report.json"

REFERENCE_MANIFEST = REFERENCE_ROOT / "output" / "reports" / "reference_assets_manifest.json"
MEDIA_MANIFEST = REFERENCE_ROOT / "output" / "reports" / "media_manifest.json"

PREVIEW_WIDTH = 1280
PREVIEW_HEIGHT = 720
FPS = "24000/1001"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def hex_color(rgb: tuple[int, int, int] | list[int] | np.ndarray) -> str:
    values = [round(clamp(float(v), 0, 255)) for v in list(rgb)[:3]]
    return f"#{values[0]:02X}{values[1]:02X}{values[2]:02X}"


def rgb_from_hex(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def bbox_payload(x0: int, y0: int, x1: int, y1: int, width: int, height: int) -> dict[str, Any]:
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height, y0))
    y1 = max(0, min(height, y1))
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    return {
        "pixel": [left, top, right - left, bottom - top],
        "xyxyPixel": [left, top, right, bottom],
        "norm": [
            round(left / width, 6),
            round(top / height, 6),
            round((right - left) / width, 6),
            round((bottom - top) / height, 6),
        ],
    }


def dominant_colors(rgb: np.ndarray, count: int = 5) -> list[dict[str, Any]]:
    if rgb.size == 0:
        return []
    small = cv2.resize(rgb, (min(180, rgb.shape[1]), max(1, round(rgb.shape[0] * min(180, rgb.shape[1]) / max(rgb.shape[1], 1)))))
    pixels = small.reshape((-1, 3)).astype(np.float32)
    if len(pixels) < count:
        return []
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 0.3)
    _, labels, centers = cv2.kmeans(pixels, count, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    unique, counts = np.unique(labels, return_counts=True)
    order = np.argsort(-counts)
    total = max(1, len(labels))
    return [{"hex": hex_color(centers[int(unique[i])]), "ratio": round(float(counts[i]) / total, 4)} for i in order]


def visual_style(rgb: np.ndarray) -> dict[str, Any]:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return {
        "brightness": round(float(np.mean(gray)) / 255.0, 4),
        "contrast": round(float(np.std(gray)) / 255.0, 4),
        "saturation": round(float(np.mean(hsv[:, :, 1])) / 255.0, 4),
        "dominantColors": dominant_colors(rgb, 5),
    }


def is_purple_blue(pixel: np.ndarray) -> np.ndarray:
    r = pixel[..., 0].astype(np.int16)
    g = pixel[..., 1].astype(np.int16)
    b = pixel[..., 2].astype(np.int16)
    return (b > 135) & (r > 45) & (g < 140) & (b - g > 35)


def is_white(pixel: np.ndarray) -> np.ndarray:
    return (pixel[..., 0] > 235) & (pixel[..., 1] > 235) & (pixel[..., 2] > 235)


def median_hex(rgb: np.ndarray, default: str = "#5A2DEF") -> str:
    if rgb.size == 0:
        return default
    return hex_color(np.median(rgb.reshape((-1, 3)), axis=0))


def gradient_stops_for_region(rgb: np.ndarray, mask: np.ndarray, default: list[str]) -> list[str]:
    height, width = mask.shape
    stops: list[str] = []
    for left, right in [(0, width // 3), (width // 3, 2 * width // 3), (2 * width // 3, width)]:
        section_mask = mask[:, left:right]
        section_rgb = rgb[:, left:right]
        stops.append(median_hex(section_rgb[section_mask], default[min(len(stops), len(default) - 1)]))
    return stops


def detect_band_bounds(rgb: np.ndarray) -> tuple[int, int]:
    height, width, _ = rgb.shape
    white = is_white(rgb)
    purple = is_purple_blue(rgb)
    band_like = white | purple
    row_ratios = band_like.mean(axis=1)
    top_candidates = np.where(row_ratios[: height // 3] > 0.82)[0]
    top_height = int(top_candidates[-1] + 1) if len(top_candidates) else round(height * 0.142)

    purple_row_ratios = purple.mean(axis=1)
    bottom_start = height
    for y in range(height - 1, height // 2, -1):
        if purple_row_ratios[y] > 0.72:
            bottom_start = y
        elif bottom_start < height:
            break
    if bottom_start == height:
        bottom_start = round(height * 0.972)
    return top_height, bottom_start


def connected_boxes(mask: np.ndarray, min_area: int) -> list[dict[str, int]]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    boxes: list[dict[str, int]] = []
    for index in range(1, count):
        x, y, w, h, area = [int(v) for v in stats[index]]
        if area >= min_area:
            boxes.append({"x": x, "y": y, "w": w, "h": h, "area": area})
    return sorted(boxes, key=lambda item: item["area"], reverse=True)


def detect_faces(rgb: np.ndarray, top_height: int, bottom_start: int) -> list[dict[str, Any]]:
    gray = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)
    detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    raw_faces = detector.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=4, minSize=(60, 60))
    faces: list[dict[str, Any]] = []
    height, width, _ = rgb.shape
    for x, y, w, h in raw_faces:
        if y < top_height or y + h > bottom_start:
            continue
        if h < 120:
            continue
        faces.append(
            {
                "bbox": bbox_payload(int(x), int(y), int(x + w), int(y + h), width, height),
                "confidence": 0.55,
                "source": "opencv-haar-filtered",
            }
        )
    return sorted(faces, key=lambda item: item["bbox"]["xyxyPixel"][0])[:4]


def detect_logo_panel(rgb: np.ndarray, top_height: int) -> dict[str, Any]:
    top = rgb[:top_height]
    white_mask = is_white(top)
    right_edges: list[tuple[int, int]] = []
    for y in range(top_height):
        xs = np.where(white_mask[y])[0]
        if len(xs):
            right_edges.append((y, int(xs.max())))
    top_right = int(np.median([x for y, x in right_edges[: max(1, top_height // 4)]])) if right_edges else round(rgb.shape[1] * 0.226)
    bottom_right = int(np.median([x for y, x in right_edges[-max(1, top_height // 4) :]])) if right_edges else round(rgb.shape[1] * 0.21)

    panel_mask = np.zeros((top_height, rgb.shape[1]), dtype=np.uint8)
    for y in range(top_height):
        t = y / max(1, top_height - 1)
        edge = round(top_right + (bottom_right - top_right) * t)
        panel_mask[y, :edge] = 1
    yy, xx = np.indices((top_height, rgb.shape[1]))
    panel_rgb = top
    r = panel_rgb[..., 0].astype(np.int16)
    g = panel_rgb[..., 1].astype(np.int16)
    b = panel_rgb[..., 2].astype(np.int16)
    logo_like = (((b > 150) & (b - r > 20) & (b - g > 35)) | ((r < 80) & (g < 100) & (b < 120)))
    non_white_in_panel = logo_like & (panel_mask.astype(bool)) & (yy > round(top_height * 0.2)) & (xx < bottom_right - 20)
    boxes = connected_boxes(non_white_in_panel, 120)
    if boxes:
        boxes = boxes[:4]
        x0 = min(box["x"] for box in boxes)
        y0 = min(box["y"] for box in boxes)
        x1 = max(box["x"] + box["w"] for box in boxes)
        y1 = max(box["y"] + box["h"] for box in boxes)
    else:
        x0, y0, x1, y1 = 60, 44, 285, 107
    return {
        "shape": "left-white-slanted-polygon",
        "topRightPx": top_right,
        "bottomRightPx": bottom_right,
        "polygonPx": [[0, 0], [top_right, 0], [bottom_right, top_height], [0, top_height]],
        "logoDetectedBBox": bbox_payload(x0, y0, x1, y1, rgb.shape[1], rgb.shape[0]),
    }


def analyze_reference_image() -> dict[str, Any]:
    image = Image.open(REFERENCE_IMAGE).convert("RGB")
    rgb = np.array(image)
    height, width, _ = rgb.shape
    top_height, bottom_start = detect_band_bounds(rgb)
    faces = detect_faces(rgb, top_height, bottom_start)
    top_rgb = rgb[:top_height]
    bottom_rgb = rgb[bottom_start:]
    top_purple_mask = is_purple_blue(top_rgb)
    bottom_purple_mask = is_purple_blue(bottom_rgb)
    top_stops = gradient_stops_for_region(top_rgb, top_purple_mask, ["#4D15D7", "#5A2DEF", "#7863F3"])
    bottom_stops = gradient_stops_for_region(bottom_rgb, bottom_purple_mask, top_stops)
    logo_panel = detect_logo_panel(rgb, top_height)
    purple_boxes = connected_boxes(is_purple_blue(rgb) & (np.indices((height, width))[0] > top_height) & (np.indices((height, width))[0] < bottom_start), 6000)
    white_boxes = connected_boxes(is_white(rgb) & (np.indices((height, width))[0] > top_height) & (np.indices((height, width))[0] < bottom_start), 6000)

    subtitle_regions = []
    for box in purple_boxes[:3]:
        subtitle_regions.append({"kind": "purple-background-subtitle", "bbox": bbox_payload(box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"], width, height)})
    for box in white_boxes[:2]:
        subtitle_regions.append({"kind": "white-background-subtitle", "bbox": bbox_payload(box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"], width, height)})

    band_color_variation = {
        "topBandStops": top_stops,
        "bottomBandStops": bottom_stops,
        "topDominantColors": dominant_colors(top_rgb[top_purple_mask].reshape((-1, 1, 3)) if top_purple_mask.any() else top_rgb, 5),
        "bottomDominantColors": dominant_colors(bottom_rgb[bottom_purple_mask].reshape((-1, 1, 3)) if bottom_purple_mask.any() else bottom_rgb, 5),
        "note": "The referenced band reads as blue-purple; green-channel values vary subtly across the band and are preserved in sampled RGB stops.",
    }

    asset = {
        "assetId": "sample-11",
        "mediaId": "media-011",
        "collection": "layer-x",
        "kind": "image",
        "sourcePath": str(REFERENCE_IMAGE),
        "originalPath": r"C:\Users\yurin\Downloads\Screenshot 2026-06-07 101542.png",
        "sha256": sha256_file(REFERENCE_IMAGE),
        "sizeBytes": REFERENCE_IMAGE.stat().st_size,
        "relativePath": str(REFERENCE_IMAGE.relative_to(REFERENCE_ROOT / "library")),
        "name": "Screenshot 2026-06-07 101542.png",
        "extension": ".png",
        "width": width,
        "height": height,
        "duration": None,
        "fps": None,
    }
    frame = {
        "frameId": "frame_0000",
        "timeSeconds": 0.0,
        "width": width,
        "height": height,
        "samplePath": str(REFERENCE_SAMPLE),
        "debugOverlayPath": str(REFERENCE_DEBUG),
        "people": [],
        "faces": faces,
        "textOverlays": [],
        "logos": [{"role": "brand-logo", "bbox": logo_panel["logoDetectedBBox"], "source": "detected from screenshot; render uses provided project logo file"}],
        "annotations": subtitle_regions,
        "composition": {
            "topBand": {
                "bbox": bbox_payload(0, 0, width, top_height, width, height),
                "heightNorm": round(top_height / height, 6),
                "gradientStops": top_stops,
            },
            "bottomBand": {
                "bbox": bbox_payload(0, bottom_start, width, height, width, height),
                "heightNorm": round((height - bottom_start) / height, 6),
                "gradientStops": bottom_stops,
            },
            "logoPanel": logo_panel,
            "contentArea": {
                "bbox": bbox_payload(0, top_height, width, bottom_start, width, height),
                "note": "Video content begins below the top band and is protected from the header by shifting the source video down.",
            },
            "subtitleRegions": subtitle_regions,
            "bandColorVariation": band_color_variation,
        },
        "visualStyle": visual_style(rgb),
    }
    return {
        "schemaVersion": "reference-asset-analysis/v1",
        "asset": asset,
        "summary": {
            "frameCount": 1,
            "personPresent": bool(faces),
            "facePresent": bool(faces),
            "subtitlePresent": bool(subtitle_regions),
            "titlePresent": False,
            "logoPresent": True,
            "annotationPresent": bool(subtitle_regions),
            "detectedTopBandHeightPx": top_height,
            "detectedBottomBandHeightPx": height - bottom_start,
        },
        "frames": [frame],
    }


def crop_logo_source() -> Image.Image:
    logo = Image.open(PROJECT_LOGO).convert("RGBA")
    rgb = np.array(logo.convert("RGB"))
    non_white = ~(is_white(rgb))
    ys, xs = np.where(non_white)
    if len(xs) and len(ys):
        pad = 12
        logo = logo.crop((max(0, xs.min() - pad), max(0, ys.min() - pad), min(logo.width, xs.max() + pad), min(logo.height, ys.max() + pad)))
    return logo


def draw_linear_gradient(size: tuple[int, int], stops: list[str]) -> Image.Image:
    width, height = size
    colors = [rgb_from_hex(stop) for stop in stops]
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = image.load()
    for x in range(width):
        t = 0 if width <= 1 else x / (width - 1)
        segment = min(len(colors) - 2, int(t * (len(colors) - 1)))
        local_start = segment / (len(colors) - 1)
        local_end = (segment + 1) / (len(colors) - 1)
        local_t = 0 if local_end == local_start else (t - local_start) / (local_end - local_start)
        c0, c1 = colors[segment], colors[segment + 1]
        color = tuple(round(c0[i] + (c1[i] - c0[i]) * local_t) for i in range(3)) + (255,)
        for y in range(height):
            pixels[x, y] = color
    return image


def render_frame_overlay(profile: dict[str, Any]) -> None:
    analysis_frame = profile["frames"][0]
    composition = analysis_frame["composition"]
    top_norm = composition["topBand"]["heightNorm"]
    bottom_norm = composition["bottomBand"]["heightNorm"]
    top_h = round(top_norm * PREVIEW_HEIGHT)
    bottom_h = round(bottom_norm * PREVIEW_HEIGHT)
    canvas = Image.new("RGBA", (PREVIEW_WIDTH, PREVIEW_HEIGHT), (0, 0, 0, 0))

    top_gradient = draw_linear_gradient((PREVIEW_WIDTH, top_h), composition["topBand"]["gradientStops"])
    bottom_gradient = draw_linear_gradient((PREVIEW_WIDTH, bottom_h), composition["bottomBand"]["gradientStops"])
    canvas.alpha_composite(top_gradient, (0, 0))
    canvas.alpha_composite(bottom_gradient, (0, PREVIEW_HEIGHT - bottom_h))

    draw = ImageDraw.Draw(canvas)
    panel = composition["logoPanel"]
    src_w = analysis_frame["width"]
    src_h = analysis_frame["height"]
    top_right = round(panel["topRightPx"] / src_w * PREVIEW_WIDTH)
    bottom_right = round(panel["bottomRightPx"] / src_w * PREVIEW_WIDTH)
    draw.polygon([(0, 0), (top_right, 0), (bottom_right, top_h), (0, top_h)], fill=(255, 255, 255, 255))

    # Preserve the sampled color shift without drawing beyond the band edges.
    draw.polygon([(round(PREVIEW_WIDTH * 0.78), PREVIEW_HEIGHT - bottom_h + 1), (PREVIEW_WIDTH, PREVIEW_HEIGHT - bottom_h + 1), (PREVIEW_WIDTH, PREVIEW_HEIGHT), (round(PREVIEW_WIDTH * 0.84), PREVIEW_HEIGHT)], fill=(112, 141, 244, 38))

    logo_bbox = panel["logoDetectedBBox"]["xyxyPixel"]
    logo_x = round(logo_bbox[0] / src_w * PREVIEW_WIDTH)
    logo_y = round(logo_bbox[1] / src_h * PREVIEW_HEIGHT)
    logo_h = max(1, round((logo_bbox[3] - logo_bbox[1]) / src_h * PREVIEW_HEIGHT))
    logo = crop_logo_source()
    logo_w = round(logo.width * logo_h / max(1, logo.height))
    logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(logo, (logo_x, logo_y))

    FRAME_OVERLAY.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(FRAME_OVERLAY)


def write_reference_debug(profile: dict[str, Any]) -> None:
    REFERENCE_SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_DEBUG.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(REFERENCE_IMAGE).convert("RGB")
    image.save(REFERENCE_SAMPLE)
    debug = image.convert("RGBA")
    draw = ImageDraw.Draw(debug)
    frame = profile["frames"][0]
    for key, color in [("topBand", (255, 0, 255, 255)), ("bottomBand", (255, 0, 255, 255)), ("contentArea", (0, 255, 255, 255))]:
        x0, y0, x1, y1 = frame["composition"][key]["bbox"]["xyxyPixel"]
        draw.rectangle((x0, y0, x1, y1), outline=color, width=4)
    draw.polygon([tuple(point) for point in frame["composition"]["logoPanel"]["polygonPx"]], outline=(255, 220, 0, 255), width=4)
    for item in frame["annotations"]:
        x0, y0, x1, y1 = item["bbox"]["xyxyPixel"]
        draw.rectangle((x0, y0, x1, y1), outline=(0, 255, 0, 255), width=4)
    debug.convert("RGB").save(REFERENCE_DEBUG)


def ensure_reference_manifests(profile: dict[str, Any]) -> None:
    asset = profile["asset"]
    reference_manifest = load_json(REFERENCE_MANIFEST)
    assets = [item for item in reference_manifest.get("assets", []) if item.get("assetId") != asset["assetId"]]
    manifest_asset = {
        **asset,
        "analysisPath": str(REFERENCE_ANALYSIS),
        "metadata": {"width": asset["width"], "height": asset["height"], "hasVideo": False, "hasAudio": False},
    }
    assets.append(manifest_asset)
    reference_manifest["assets"] = sorted(assets, key=lambda item: item.get("mediaId", ""))
    reference_manifest["generatedAt"] = now_iso()
    write_json(REFERENCE_MANIFEST, reference_manifest)

    media_manifest = load_json(MEDIA_MANIFEST)
    media_item = {
        "id": asset["mediaId"],
        "kind": "image",
        "role": "still",
        "label": "layer-x image",
        "path": asset["sourcePath"],
        "originalPath": asset["originalPath"],
        "relativePath": asset["relativePath"],
        "name": "sample-11.png",
        "extension": ".png",
        "sizeBytes": asset["sizeBytes"],
        "confidence": 1.0,
        "reason": "reference asset copied into library collection bundle",
        "metadata": {
            "width": asset["width"],
            "height": asset["height"],
            "hasVideo": False,
            "hasAudio": False,
            "storage": "copied",
            "sha256": asset["sha256"],
            "assetId": asset["assetId"],
            "collection": asset["collection"],
        },
    }
    media_manifest["files"] = [item for item in media_manifest.get("files", []) if item.get("id") != asset["mediaId"]]
    media_manifest["files"].append(media_item)
    media_manifest["files"] = sorted(media_manifest["files"], key=lambda item: item.get("id", ""))
    media_manifest["images"] = [item for item in media_manifest.get("images", []) if item.get("id") != asset["mediaId"]]
    media_manifest["images"].append(media_item)
    media_manifest["images"] = sorted(media_manifest["images"], key=lambda item: item.get("id", ""))
    media_manifest["generatedAt"] = now_iso()
    write_json(MEDIA_MANIFEST, media_manifest)


def video_duration(path: Path, ffprobe: str) -> float:
    return float(subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True).strip())


def render_preview(profile: dict[str, Any], ffmpeg: str, ffprobe: str) -> float:
    duration = video_duration(SOURCE_VIDEO, ffprobe)
    top_h = round(profile["frames"][0]["composition"]["topBand"]["heightNorm"] * PREVIEW_HEIGHT)
    video_y = top_h
    inputs = ["-i", str(SOURCE_VIDEO)]
    filter_parts = [f"[0:v]scale={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:flags=bicubic,setpts=PTS-STARTPTS[base]", f"color=c=black:s={PREVIEW_WIDTH}x{PREVIEW_HEIGHT}:r={FPS}:d={duration:.6f}[canvas]", f"[canvas][base]overlay=0:{video_y}:format=auto[video]"]
    current = "video"
    input_index = 1
    if SUBTITLE_OVERLAY.exists():
        inputs += ["-i", str(SUBTITLE_OVERLAY)]
        filter_parts.append(f"[{current}][{input_index}:v]overlay=0:0:format=auto[subtitled]")
        current = "subtitled"
        input_index += 1
    inputs += ["-loop", "1", "-i", str(FRAME_OVERLAY)]
    filter_parts.append(f"[{current}][{input_index}:v]overlay=0:0:format=auto[v]")
    PREVIEW_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(PREVIEW_VIDEO),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)
    return duration


def extract_still(ffmpeg: str, at: str = "5") -> None:
    PREVIEW_STILL.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-y", "-ss", at, "-i", str(PREVIEW_VIDEO), "-frames:v", "1", "-update", "1", str(PREVIEW_STILL)], cwd=REPO_ROOT, check=True)


def write_timeline(profile: dict[str, Any], duration: float) -> None:
    timeline = {
        "schemaVersion": "video-edit-timeline/v1",
        "id": "timeline_test-project-1_sample11_frame_design_preview",
        "createdAt": now_iso(),
        "project": {"id": "test-project-1", "name": "Test Project 1", "root": str(PROJECT_ROOT), "sourceRoot": str(PROJECT_ROOT / "source"), "outputRoot": str(OUTPUT_DIR)},
        "timebase": {"unit": "seconds", "fps": FPS},
        "duration": round(duration, 6),
        "sources": [
            {"id": "src_master", "kind": "video", "role": "master", "path": str(SOURCE_VIDEO), "duration": round(duration, 6), "width": 1920, "height": 1080, "fps": FPS},
            {"id": "src_reference_image", "kind": "image", "role": "reference-design", "path": str(REFERENCE_IMAGE)},
            {"id": "src_reference_analysis", "kind": "data", "role": "reference-analysis", "path": str(REFERENCE_ANALYSIS)},
            {"id": "src_logo", "kind": "image", "role": "brand-logo", "path": str(PROJECT_LOGO)},
            {"id": "src_frame_overlay", "kind": "image", "role": "generated-frame-overlay", "path": str(FRAME_OVERLAY)},
            {"id": "src_design_profile", "kind": "data", "role": "frame-design-profile", "path": str(DESIGN_PROFILE)},
        ],
        "tracks": [
            {"id": "video.main", "kind": "video", "label": "Downshifted source video", "allowOverlap": False},
            {"id": "graphics.frame", "kind": "overlay", "label": "Sample-11 frame overlay", "allowOverlap": True},
            {"id": "audio.main", "kind": "audio", "label": "Source audio", "allowOverlap": False},
        ],
        "clips": [
            {"id": "clip_video_master", "trackId": "video.main", "kind": "video", "sourceId": "src_master", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "sourceIn": 0.0, "sourceOut": round(duration, 6), "fit": {"mode": "cover", "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT}, "style": {"yOffsetPx": round(profile["frames"][0]["composition"]["topBand"]["heightNorm"] * PREVIEW_HEIGHT)}},
            {"id": "clip_frame_overlay", "trackId": "graphics.frame", "kind": "generated", "sourceId": "src_frame_overlay", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "style": {"referenceAnalysis": str(REFERENCE_ANALYSIS), "designProfile": str(DESIGN_PROFILE)}},
            {"id": "clip_audio_master", "trackId": "audio.main", "kind": "audio", "sourceId": "src_master", "timelineStart": 0.0, "timelineEnd": round(duration, 6), "sourceIn": 0.0, "sourceOut": round(duration, 6)},
        ],
        "transitions": [],
        "render": {"targets": [{"id": "preview", "path": str(PREVIEW_VIDEO), "format": "mp4", "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT, "fps": FPS, "profile": "preview"}]},
        "analysis": {
            "mediaManifestPath": str(MEDIA_MANIFEST),
            "reports": [
                {"kind": "media-manifest", "path": str(MEDIA_MANIFEST), "exists": MEDIA_MANIFEST.exists()},
                {"kind": "reference-analysis", "path": str(REFERENCE_ANALYSIS), "exists": REFERENCE_ANALYSIS.exists()},
                {"kind": "frame-design-profile", "path": str(DESIGN_PROFILE), "exists": DESIGN_PROFILE.exists()},
                {"kind": "frame-design-report", "path": str(REPORT_PATH), "exists": REPORT_PATH.exists()},
            ]
        },
        "audit": {
            "createdBy": "projects/test-project-1/scripts/build_sample11_frame_design_preview.py",
            "inputs": [
                {"kind": "reference-image", "path": str(REFERENCE_IMAGE), "exists": REFERENCE_IMAGE.exists()},
                {"kind": "project-logo", "path": str(PROJECT_LOGO), "exists": PROJECT_LOGO.exists()},
                {"kind": "source-video", "path": str(SOURCE_VIDEO), "exists": SOURCE_VIDEO.exists()},
            ],
        },
    }
    write_json(TIMELINE_PATH, timeline)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register sample-11 design image and render frame-design preview.")
    parser.add_argument("--ffmpeg", default=r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
    parser.add_argument("--ffprobe", default=r"C:\ProgramData\chocolatey\bin\ffprobe.exe")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    if not REFERENCE_IMAGE.exists():
        raise SystemExit(f"Reference image missing: {REFERENCE_IMAGE}")
    if not PROJECT_LOGO.exists():
        raise SystemExit(f"Project logo missing: {PROJECT_LOGO}")

    profile = analyze_reference_image()
    write_json(REFERENCE_ANALYSIS, profile)
    write_json(DESIGN_PROFILE, profile)
    write_reference_debug(profile)
    ensure_reference_manifests(profile)
    render_frame_overlay(profile)
    duration = video_duration(SOURCE_VIDEO, args.ffprobe)
    if not args.skip_render:
        duration = render_preview(profile, args.ffmpeg, args.ffprobe)
        extract_still(args.ffmpeg, "5")
    write_timeline(profile, duration)
    report = {
        "createdAt": now_iso(),
        "referenceImage": str(REFERENCE_IMAGE),
        "referenceAnalysis": str(REFERENCE_ANALYSIS),
        "designProfile": str(DESIGN_PROFILE),
        "projectLogo": str(PROJECT_LOGO),
        "frameOverlay": str(FRAME_OVERLAY),
        "previewVideo": str(PREVIEW_VIDEO) if PREVIEW_VIDEO.exists() else "",
        "previewStill": str(PREVIEW_STILL) if PREVIEW_STILL.exists() else "",
        "timeline": str(TIMELINE_PATH),
        "detected": {
            "topBandHeightPx": profile["summary"]["detectedTopBandHeightPx"],
            "bottomBandHeightPx": profile["summary"]["detectedBottomBandHeightPx"],
            "topBandStops": profile["frames"][0]["composition"]["topBand"]["gradientStops"],
            "bottomBandStops": profile["frames"][0]["composition"]["bottomBand"]["gradientStops"],
            "logoPanel": profile["frames"][0]["composition"]["logoPanel"],
        },
        "notes": [
            "Preview render only; production render waits for user approval.",
            "The source video is shifted down by the detected top-band height so faces do not sit under the header band.",
            "Header/footer RGB stops preserve the subtle channel differences detected in the reference image.",
        ],
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
