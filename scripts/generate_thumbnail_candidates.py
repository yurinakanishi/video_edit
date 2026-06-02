from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from video_edit_core.paths import OUTPUT_IMAGES
from video_edit_core.app_config import hex_rgba, load_app_config, nested, optional_path


APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
TARGET_SIZE = (1280, 720)
THUMB_SIZE = (320, 180)
SUPPORTED_MODES = {"standard", "closeup_bottom_title", "right_face_title_stack", "left_face_title_stack"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


FONT_CANDIDATES_BOLD = [
    Path(r"C:\Windows\Fonts\YuGothB.ttc"),
    Path(r"C:\Windows\Fonts\meiryob.ttc"),
    Path(r"C:\Windows\Fonts\arialbd.ttf"),
]
FONT_CANDIDATES_REGULAR = [
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
]


MAIN_COLORS: dict[str, tuple[int, int, int]] = {
    "yellow": (255, 218, 36),
    "red": (238, 35, 30),
    "orange": (255, 128, 0),
    "green": (0, 190, 95),
    "blue": (0, 174, 239),
    "cyan": (0, 210, 220),
    "purple": (165, 92, 255),
    "pink": (255, 76, 180),
    "white": (255, 255, 255),
}


@dataclass
class FaceBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]


@dataclass
class CandidateSource:
    source_path: Path
    source_kind: str
    timestamp: str
    title: str
    subtitle: str
    hook: str
    label: str


def text_value(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


def int_value(*keys: str, default: int) -> int:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(*keys: str, default: float) -> float:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def media_manifest() -> dict[str, Any]:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = text_value("assets", "mediaManifestPath")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def manifest_items(kind: str | None = None) -> list[dict[str, Any]]:
    files = media_manifest().get("files", [])
    if not isinstance(files, list):
        return []
    items = [item for item in files if isinstance(item, dict)]
    if kind:
        items = [item for item in items if item.get("kind") == kind]
    return items


def manifest_cameras() -> list[Path]:
    camera_roles = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}
    cameras = [
        (str(item.get("role") or ""), Path(str(item.get("path") or "")))
        for item in manifest_items("video")
        if item.get("role") in camera_roles and item.get("path")
    ]

    def role_order(item: tuple[str, Path]) -> int:
        role = item[0]
        if role == "master":
            return 1
        if role.startswith("camera"):
            try:
                return int(role.replace("camera", ""))
            except ValueError:
                return 50
        return 100

    return [path for _, path in sorted(cameras, key=role_order) if path.exists()]


def manifest_images() -> list[Path]:
    logo_path = selected_logo_path()
    images: list[Path] = []
    for item in manifest_items("image"):
        role = str(item.get("role") or "")
        path = Path(str(item.get("path") or ""))
        if not path.exists() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if role == "logo" or (logo_path and path.resolve() == logo_path.resolve()):
            continue
        images.append(path)
    for raw_path in nested(APP_CONFIG, "assets", "stillImages", default=[]):
        path = Path(str(raw_path or ""))
        if path.exists() and path.suffix.lower() in IMAGE_EXTENSIONS and path not in images:
            images.append(path)
    return images


def selected_logo_path() -> Path | None:
    configured = text_value("assets", "logo")
    if configured and Path(configured).exists():
        return Path(configured)
    for item in manifest_items("image"):
        if item.get("role") == "logo" and item.get("path"):
            path = Path(str(item["path"]))
            if path.exists():
                return path
    return None


def source_video() -> Path | None:
    candidates = [
        text_value("thumbnail", "inputVideoPath"),
        text_value("workflow", "inputVideoPath"),
        text_value("assets", "masterVideo"),
        text_value("render", "outputPath"),
    ]
    for value in candidates:
        path = Path(value) if value else None
        if path and path.exists():
            return path
    for path in manifest_cameras():
        return path
    return None


def output_dir() -> Path:
    configured = text_value("thumbnail", "candidatesOutputDir")
    return Path(configured) if configured else OUTPUT_IMAGES / "thumbnail_candidates"


def default_title() -> str:
    return (
        text_value("thumbnail", "title")
        or text_value("style", "titleText")
        or text_value("project", "name")
        or "Project thumbnail"
    )


def default_hook() -> str:
    return text_value("thumbnail", "hook") or text_value("project", "name") or "Highlight"


def default_subtitle() -> str:
    return text_value("thumbnail", "subtitle")


def selected_mode() -> str:
    mode = text_value("thumbnail", "mode", default=text_value("thumbnails", "mode", default="standard"))
    return mode if mode in SUPPORTED_MODES else "standard"


def selected_main_color() -> str:
    return text_value("thumbnail", "mainColor", default=text_value("style", "highlightColor", default="yellow"))


def parse_time_value(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    text = text.split("-", 1)[0].strip()
    text = text.split("–", 1)[0].strip()
    try:
        return float(text)
    except ValueError:
        pass
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None
    return None


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    whole = int(seconds)
    ms = round((seconds - whole) * 1000)
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def probe_duration(path: Path) -> float | None:
    try:
        output = subprocess.check_output(
            [
                str(FFPROBE),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        ).strip()
        duration = float(output)
        return duration if duration > 0 else None
    except Exception:
        return None


def parse_candidate_lines(raw: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in re.split(r"\s*\|\s*", line)]
        time_token = parts[0]
        if parse_time_value(time_token) is None:
            match = re.match(r"^([0-9:.]+(?:\s*[-–]\s*[0-9:.]+)?)\s+(.+)$", line)
            if not match:
                continue
            time_token = match.group(1)
            parts = [time_token, match.group(2).strip()]
        items.append(
            {
                "time": time_token,
                "hook": parts[1] if len(parts) > 1 else "",
                "title": parts[2] if len(parts) > 2 else "",
                "subtitle": parts[3] if len(parts) > 3 else "",
            }
        )
    return items


def automatic_times(video: Path, count: int) -> list[str]:
    configured = parse_time_value(text_value("thumbnail", "time"))
    if count <= 1 and configured is not None:
        return [format_timestamp(configured)]
    start = float_value("render", "previewStart", default=0.0)
    requested_duration = float_value("render", "previewDuration", default=60.0)
    video_duration = probe_duration(video)
    if video_duration is not None:
        start = min(start, max(0.0, video_duration - 0.25))
        duration = min(requested_duration, max(0.5, video_duration - start))
    else:
        duration = max(0.5, requested_duration)
    return [format_timestamp(start + duration * (index + 1) / (count + 1)) for index in range(count)]


def extract_frame(video: Path, timestamp: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        timestamp,
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(target),
    ]
    subprocess.run(command, check=True)


def font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size, index=1)
            except OSError:
                try:
                    return ImageFont.truetype(str(path), size)
                except OSError:
                    continue
    return ImageFont.load_default()


def color_tuple(value: str) -> tuple[int, int, int]:
    key = value.strip().lower()
    if key in MAIN_COLORS:
        return MAIN_COLORS[key]
    rgba = hex_rgba(value, default=(255, 218, 36, 255))
    return rgba[:3]


def detect_faces(image: Image.Image) -> list[FaceBox]:
    try:
        import cv2  # type: ignore
        import numpy as np
    except Exception:
        return []

    rgb = image.convert("RGB")
    arr = np.asarray(rgb)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    boxes: list[FaceBox] = []
    for cascade_name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / cascade_name))
        if cascade.empty():
            continue
        for x, y, w, h in cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(60, 60)):
            boxes.append(FaceBox(int(x), int(y), int(w), int(h)))
    boxes.sort(key=lambda box: box.area, reverse=True)
    return boxes[:5]


def cover_crop(
    image: Image.Image,
    size: tuple[int, int],
    *,
    focus_x: float = 0.5,
    focus_y: float = 0.5,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    image = image.convert("RGB")
    scale = max(size[0] / image.width, size[1] / image.height)
    resized_size = (round(image.width * scale), round(image.height * scale))
    resized = image.resize(resized_size, Image.Resampling.LANCZOS)
    max_left = max(0, resized.width - size[0])
    max_top = max(0, resized.height - size[1])
    left = round(max_left * min(1.0, max(0.0, focus_x)))
    top = round(max_top * min(1.0, max(0.0, focus_y)))
    crop = resized.crop((left, top, left + size[0], top + size[1]))
    source_crop = (
        round(left / scale),
        round(top / scale),
        round((left + size[0]) / scale),
        round((top + size[1]) / scale),
    )
    return crop, source_crop


def focus_for_mode(image: Image.Image, faces: list[FaceBox], mode: str) -> tuple[float, float]:
    if faces:
        face = faces[0]
        cx, cy = face.center
        fx = cx / max(1, image.width)
        fy = cy / max(1, image.height)
        if mode == "right_face_title_stack":
            return min(0.82, fx + 0.12), fy
        if mode == "left_face_title_stack":
            return max(0.18, fx - 0.12), fy
        return fx, min(0.55, fy)
    if mode == "right_face_title_stack":
        return 0.68, 0.45
    if mode == "left_face_title_stack":
        return 0.32, 0.45
    return 0.5, 0.45


def add_gradient(image: Image.Image, side: str, opacity: int = 178) -> Image.Image:
    overlay = Image.new("RGBA", TARGET_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = TARGET_SIZE
    if side == "left":
        for x in range(width):
            alpha = round(opacity * max(0.0, 1.0 - x / (width * 0.64)))
            draw.line((x, 0, x, height), fill=(0, 0, 0, alpha))
    elif side == "right":
        for x in range(width):
            alpha = round(opacity * max(0.0, (x - width * 0.36) / (width * 0.64)))
            draw.line((x, 0, x, height), fill=(0, 0, 0, alpha))
    else:
        for y in range(height):
            alpha = round(opacity * max(0.0, (y - height * 0.42) / (height * 0.58)))
            draw.line((0, y, width, y), fill=(0, 0, 0, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def wrap_text(text: str, draw: ImageDraw.ImageDraw, text_font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    text = " ".join(str(text or "").split())
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        width = draw.textbbox((0, 0), candidate, font=text_font, stroke_width=4)[2]
        if current and width > max_width:
            lines.append(current)
            current = char
            if len(lines) >= max_lines - 1:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        remaining = text[len("".join(lines)) :] if len(lines) == max_lines - 1 else current
        lines.append(remaining)
    return [line.strip() for line in lines if line.strip()]


def fitted_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    *,
    start: int,
    minimum: int,
    max_lines: int,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    size = start
    while size >= minimum:
        text_font = font(size, True)
        stroke = max(4, size // 11)
        lines = wrap_text(text, draw, text_font, max_width, max_lines)
        if not lines:
            return text_font, [], stroke
        bboxes = [draw.textbbox((0, 0), line, font=text_font, stroke_width=stroke) for line in lines]
        total_height = sum(box[3] - box[1] for box in bboxes) + max(0, len(lines) - 1) * max(6, size // 8)
        widest = max(box[2] - box[0] for box in bboxes)
        if total_height <= max_height and widest <= max_width:
            return text_font, lines, stroke
        size -= 4
    text_font = font(minimum, True)
    return text_font, wrap_text(text, draw, text_font, max_width, max_lines), max(4, minimum // 11)


def draw_hook(draw: ImageDraw.ImageDraw, hook: str, accent: tuple[int, int, int], text_box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    if not hook:
        return None
    hook_font = font(34, True)
    bbox = draw.textbbox((0, 0), hook, font=hook_font, stroke_width=1)
    pad_x, pad_y = 18, 10
    width = min(TARGET_SIZE[0] - 72, bbox[2] - bbox[0] + pad_x * 2)
    height = bbox[3] - bbox[1] + pad_y * 2
    x = max(34, min(TARGET_SIZE[0] - width - 34, text_box[0]))
    y = max(28, text_box[1] - height - 14)
    draw.rectangle((x, y, x + width, y + height), fill=accent)
    draw.text((x + pad_x - bbox[0], y + pad_y - bbox[1]), hook, font=hook_font, fill=(0, 0, 0), stroke_width=1, stroke_fill=(255, 255, 255))
    return (x, y, width, height)


def draw_title_block(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    subtitle: str,
    accent: tuple[int, int, int],
    *,
    align: str = "left",
) -> None:
    x, y, w, h = box
    title_font, title_lines, stroke = fitted_font_size(
        draw,
        title,
        w,
        h - (54 if subtitle else 0),
        start=104,
        minimum=58,
        max_lines=3,
    )
    line_gap = 8
    bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke) for line in title_lines]
    total_height = sum(box_[3] - box_[1] for box_ in bboxes) + max(0, len(bboxes) - 1) * line_gap
    current_y = y + max(0, h - total_height - (48 if subtitle else 8))
    for line, bbox in zip(title_lines, bboxes):
        text_width = bbox[2] - bbox[0]
        text_x = x + (w - text_width if align == "right" else 0) - bbox[0]
        draw.text(
            (text_x, current_y - bbox[1]),
            line,
            font=title_font,
            fill=accent,
            stroke_width=stroke,
            stroke_fill=(0, 0, 0),
        )
        current_y += bbox[3] - bbox[1] + line_gap
    if subtitle:
        subtitle_font = font(30, True)
        subtitle_y = min(y + h - 38, current_y + 4)
        subtitle_x = x if align == "left" else max(x, x + w - draw.textbbox((0, 0), subtitle, font=subtitle_font)[2])
        draw.text((subtitle_x, subtitle_y), subtitle, font=subtitle_font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))


def draw_bottom_title(draw: ImageDraw.ImageDraw, title: str, accent: tuple[int, int, int]) -> tuple[int, int, int, int]:
    box = (34, 538, TARGET_SIZE[0] - 68, 150)
    title_font, title_lines, stroke = fitted_font_size(draw, title, box[2], box[3], start=92, minimum=52, max_lines=2)
    bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke) for line in title_lines]
    line_gap = 6
    total_height = sum(item[3] - item[1] for item in bboxes) + max(0, len(bboxes) - 1) * line_gap
    y = box[1] + box[3] - total_height
    for line, bbox in zip(title_lines, bboxes):
        text_width = bbox[2] - bbox[0]
        x = box[0] + (box[2] - text_width) // 2 - bbox[0]
        draw.text((x, y - bbox[1]), line, font=title_font, fill=accent, stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += bbox[3] - bbox[1] + line_gap
    return box


def paste_logo(canvas: Image.Image, side: str) -> str | None:
    logo_path = selected_logo_path()
    if not logo_path:
        return None
    try:
        logo = Image.open(logo_path).convert("RGBA")
    except Exception:
        return None
    alpha_bbox = logo.getbbox()
    if alpha_bbox:
        logo = logo.crop(alpha_bbox)
    target_h = 52
    scale = target_h / max(1, logo.height)
    logo = logo.resize((round(logo.width * scale), target_h), Image.Resampling.LANCZOS)
    pad_x, pad_y = 10, 8
    plate = Image.new("RGBA", (logo.width + pad_x * 2, logo.height + pad_y * 2), (255, 255, 255, 226))
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=5, fill=(255, 255, 255, 226))
    plate.alpha_composite(logo, (pad_x, pad_y))
    x = 36 if side == "left" else TARGET_SIZE[0] - plate.width - 36
    y = 30
    canvas.alpha_composite(plate, (x, y))
    return str(logo_path)


def render_candidate(
    index: int,
    source: CandidateSource,
    mode: str,
    main_color: str,
    destination: Path,
    *,
    debug_faces: bool = False,
) -> dict[str, Any]:
    raw = Image.open(source.source_path).convert("RGB")
    faces = detect_faces(raw)
    focus_x, focus_y = focus_for_mode(raw, faces, mode)
    canvas, source_crop = cover_crop(raw, TARGET_SIZE, focus_x=focus_x, focus_y=focus_y)
    canvas = ImageEnhance.Color(canvas).enhance(1.12)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.08)
    canvas = ImageEnhance.Sharpness(canvas).enhance(1.08).convert("RGBA")

    if mode == "right_face_title_stack":
        canvas = add_gradient(canvas, "left")
        text_box = (42, 282, 600, 386)
        align = "left"
        logo_side = "right"
    elif mode == "left_face_title_stack":
        canvas = add_gradient(canvas, "right")
        text_box = (638, 282, 600, 386)
        align = "right"
        logo_side = "left"
    else:
        canvas = add_gradient(canvas, "bottom")
        text_box = (56, 382, 1110, 286)
        align = "left"
        logo_side = "right"

    accent = color_tuple(main_color)
    draw = ImageDraw.Draw(canvas)
    if mode == "closeup_bottom_title":
        bottom_box = draw_bottom_title(draw, source.title, accent)
        draw_hook(draw, source.hook, accent, (40, bottom_box[1], bottom_box[2], bottom_box[3]))
        if source.subtitle:
            sub_font = font(28, True)
            draw.text((42, 472), source.subtitle, font=sub_font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    else:
        draw_hook(draw, source.hook, accent, text_box)
        draw_title_block(draw, text_box, source.title, source.subtitle, accent, align=align)
    logo = paste_logo(canvas, logo_side)
    for i in range(6):
        draw.rectangle((i, i, TARGET_SIZE[0] - i - 1, TARGET_SIZE[1] - i - 1), outline=accent)
    if debug_faces:
        for face in faces:
            draw.rectangle((face.x, face.y, face.x + face.w, face.y + face.h), outline=(255, 255, 0), width=3)

    output = destination / f"thumbnail_candidate_{index:02d}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, quality=94)
    return {
        "output": str(output),
        "source": str(source.source_path),
        "sourceKind": source.source_kind,
        "timestamp": source.timestamp,
        "title": source.title,
        "subtitle": source.subtitle,
        "hook": source.hook,
        "mode": mode,
        "mainColor": main_color,
        "sourceCrop": list(source_crop),
        "detectedFaces": [face.as_list() for face in faces],
        "logo": logo or "",
    }


def write_contact_sheet(items: list[dict[str, Any]], destination: Path) -> Path:
    cols = min(4, max(1, len(items)))
    rows = math.ceil(len(items) / cols)
    label_h = 30
    sheet = Image.new("RGB", (cols * THUMB_SIZE[0], rows * (THUMB_SIZE[1] + label_h)), (244, 244, 244))
    draw = ImageDraw.Draw(sheet)
    label_font = font(18, True)
    for index, item in enumerate(items):
        image = Image.open(Path(item["output"])).convert("RGB").resize(THUMB_SIZE, Image.Resampling.LANCZOS)
        x = (index % cols) * THUMB_SIZE[0]
        y = (index // cols) * (THUMB_SIZE[1] + label_h)
        sheet.paste(image, (x, y))
        draw.rectangle((x, y + THUMB_SIZE[1], x + THUMB_SIZE[0], y + THUMB_SIZE[1] + label_h), fill=(24, 24, 24))
        draw.text((x + 8, y + THUMB_SIZE[1] + 5), Path(item["output"]).name, font=label_font, fill=(255, 255, 255))
    output = destination / "thumbnail_candidates_contact_sheet.jpg"
    sheet.save(output, quality=92)
    return output


def build_sources(video: Path | None, destination: Path, count: int, times_text: str) -> list[CandidateSource]:
    sources: list[CandidateSource] = []
    parsed_times = parse_candidate_lines(times_text)
    image_sources = manifest_images()

    with tempfile.TemporaryDirectory(prefix="video_edit_thumbnail_candidates_") as tmp_raw:
        temp_dir = Path(tmp_raw)
        if parsed_times:
            if not video:
                raise SystemExit("Candidate time rows require an input video.")
            for index, item in enumerate(parsed_times[:count], start=1):
                seconds = parse_time_value(item["time"])
                if seconds is None:
                    continue
                frame_path = temp_dir / f"frame_{index:02d}.jpg"
                timestamp = format_timestamp(seconds)
                extract_frame(video, timestamp, frame_path)
                stable_frame = destination / "frames" / frame_path.name
                stable_frame.parent.mkdir(parents=True, exist_ok=True)
                Image.open(frame_path).convert("RGB").save(stable_frame, quality=92)
                sources.append(
                    CandidateSource(
                        source_path=stable_frame,
                        source_kind="video_frame",
                        timestamp=timestamp,
                        title=item["title"] or default_title(),
                        subtitle=item["subtitle"] or default_subtitle(),
                        hook=item["hook"] or default_hook(),
                        label=f"frame {index:02d}",
                    )
                )
        else:
            for path in image_sources[:count]:
                sources.append(
                    CandidateSource(
                        source_path=path,
                        source_kind="project_image",
                        timestamp="",
                        title=default_title(),
                        subtitle=default_subtitle(),
                        hook=default_hook(),
                        label=path.name,
                    )
                )
            remaining = max(0, count - len(sources))
            if video and remaining:
                for index, timestamp in enumerate(automatic_times(video, remaining), start=1):
                    frame_path = temp_dir / f"frame_{index:02d}.jpg"
                    extract_frame(video, timestamp, frame_path)
                    stable_frame = destination / "frames" / frame_path.name
                    stable_frame.parent.mkdir(parents=True, exist_ok=True)
                    Image.open(frame_path).convert("RGB").save(stable_frame, quality=92)
                    sources.append(
                        CandidateSource(
                            source_path=stable_frame,
                            source_kind="video_frame",
                            timestamp=timestamp,
                            title=default_title(),
                            subtitle=default_subtitle(),
                            hook=default_hook(),
                            label=f"frame {index:02d}",
                        )
                    )

    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate project thumbnail candidates from the current app runtime config.")
    parser.add_argument("--count", type=int, default=int_value("thumbnail", "candidateCount", default=6))
    parser.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default=selected_mode())
    parser.add_argument("--main-color", default=selected_main_color())
    parser.add_argument("--times", default=text_value("thumbnail", "candidateTimesText"))
    parser.add_argument("--output-dir", type=Path, default=output_dir())
    parser.add_argument("--debug-faces", dest="debug_faces", action="store_true", default=bool_value("thumbnail", "debugFaces", default=False))
    parser.add_argument("--no-debug-faces", dest="debug_faces", action="store_false")
    args = parser.parse_args()

    count = max(1, min(24, args.count))
    destination = args.output_dir
    destination.mkdir(parents=True, exist_ok=True)
    video = source_video()
    sources = build_sources(video, destination, count, args.times)
    if not sources:
        raise SystemExit("No thumbnail candidate sources found. Select a video or project image material first.")

    candidates = [
        render_candidate(index, source, args.mode, args.main_color, destination, debug_faces=args.debug_faces)
        for index, source in enumerate(sources, start=1)
    ]
    contact_sheet = write_contact_sheet(candidates, destination)
    report = {
        "outputDir": str(destination),
        "contactSheet": str(contact_sheet),
        "inputVideo": str(video) if video else "",
        "candidateCount": len(candidates),
        "mode": args.mode,
        "mainColor": args.main_color,
        "candidates": candidates,
    }
    report_path = destination / "thumbnail_candidates_manifest.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(report_path), **report}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
