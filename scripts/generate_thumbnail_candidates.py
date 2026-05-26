from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from project_paths import OUTPUT, OUTPUT_REPORTS, SOURCE_IMAGES, SOURCE_TEXT, SOURCE_VIDEO, ROOT


CANVAS_SIZE = (1280, 720)
ASSET_SOURCE_DEFAULT = Path(r"C:\Users\yurin\Downloads\etype260515 p-takei\etype260515 p-takei")
ASSET_DIR = ROOT / "source" / "thumbnail" / "etype260515_p_takei"
REFERENCE_DIR = ROOT / "source" / "thumbnail" / "references"
OUTPUT_DIR = OUTPUT / "thumbnails"
REFERENCE_STYLE_PATH = OUTPUT_DIR / "thumbnail_reference_style.json"
VIDEO_PATH = OUTPUT / "videos" / "ST7_7550_multicam_cut_1min_onepass_full_transcript.mp4"
TRANSCRIPT_PATH = OUTPUT / "transcripts" / "sound2" / "140101-001.json"
LOGO_PATH = SOURCE_IMAGES / "type-logo-transparent-cropped.png"

FONT_BOLD = Path(r"C:\Windows\Fonts\meiryob.ttc")
FONT_REGULAR = Path(r"C:\Windows\Fonts\meiryo.ttc")


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    def expanded(self, margin_x: int, margin_y: int, width: int, height: int) -> "Rect":
        x1 = max(0, self.x - margin_x)
        y1 = max(0, self.y - margin_y)
        x2 = min(width, self.x + self.w + margin_x)
        y2 = min(height, self.y + self.h + margin_y)
        return Rect(x1, y1, x2 - x1, y2 - y1)

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x + self.w <= other.x
            or other.x + other.w <= self.x
            or self.y + self.h <= other.y
            or other.y + other.h <= self.y
        )

    def intersection_area(self, other: "Rect") -> int:
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x + self.w, other.x + other.w)
        y2 = min(self.y + self.h, other.y + other.h)
        return max(0, x2 - x1) * max(0, y2 - y1)


def import_assets(source_dir: Path) -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(source_dir.glob("ST-*.jpg")):
        shutil.copy2(src, ASSET_DIR / src.name)
        count += 1
    return count


def load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold and FONT_BOLD.exists() else FONT_REGULAR
    return ImageFont.truetype(str(path), size)


def crop_to_canvas(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    src_w, src_h = image.size
    target_w, target_h = CANVAS_SIZE
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
        left = (src_w - crop_w) // 2
        top = 0
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
        left = 0
        top = max(0, (src_h - crop_h) // 2)
    crop = (left, top, left + crop_w, top + crop_h)
    return image.crop(crop).resize(CANVAS_SIZE, Image.Resampling.LANCZOS), crop


def crop_face_closeup_to_canvas(image: Image.Image, source_faces: list[Rect], variant_index: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    if not source_faces:
        return crop_to_canvas(image)

    src_w, src_h = image.size
    target_ratio = CANVAS_SIZE[0] / CANVAS_SIZE[1]
    face = sorted(source_faces, key=lambda item: item.area, reverse=True)[0]
    face_cx = face.x + face.w / 2
    face_cy = face.y + face.h / 2

    crop_h = int(min(src_h, face.h * 1.55))
    crop_w = int(crop_h * target_ratio)
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)
    if crop_h > src_h:
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)

    # Keep the face centered horizontally and slightly above the vertical midpoint
    # so the one-line bottom title sits over torso/background rather than the face.
    horizontal_nudge = ((variant_index % 5) - 2) * face.w * 0.12
    left = int(face_cx + horizontal_nudge - crop_w / 2)
    top = int(face_cy - crop_h * 0.42)
    left = max(0, min(src_w - crop_w, left))
    top = max(0, min(src_h - crop_h, top))
    crop = (left, top, left + crop_w, top + crop_h)
    return image.crop(crop).resize(CANVAS_SIZE, Image.Resampling.LANCZOS), crop


def crop_face_right_closeup_to_canvas(image: Image.Image, source_faces: list[Rect], variant_index: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    if not source_faces:
        return crop_to_canvas(image)

    src_w, src_h = image.size
    target_ratio = CANVAS_SIZE[0] / CANVAS_SIZE[1]
    face = sorted(source_faces, key=lambda item: item.area, reverse=True)[0]
    face_cx = face.x + face.w / 2
    face_cy = face.y + face.h / 2

    crop_h = int(min(src_h, face.h * 1.95))
    crop_w = int(crop_h * target_ratio)
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)
    if crop_h > src_h:
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)

    target_x = 0.8 + ((variant_index % 3) - 1) * 0.02
    target_y = 0.43
    if face_cx - crop_w * target_x < 0:
        crop_w = int(face_cx / target_x)
        crop_h = int(crop_w / target_ratio)
    if face_cx + crop_w * (1 - target_x) > src_w:
        crop_w = int((src_w - face_cx) / (1 - target_x))
        crop_h = int(crop_w / target_ratio)
    crop_w = max(1, min(src_w, crop_w))
    crop_h = max(1, min(src_h, crop_h))
    left = int(face_cx - crop_w * target_x)
    top = int(face_cy - crop_h * target_y)
    left = max(0, min(src_w - crop_w, left))
    top = max(0, min(src_h - crop_h, top))
    crop = (left, top, left + crop_w, top + crop_h)
    return image.crop(crop).resize(CANVAS_SIZE, Image.Resampling.LANCZOS), crop


def crop_face_left_closeup_to_canvas(image: Image.Image, source_faces: list[Rect], variant_index: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    if not source_faces:
        return crop_to_canvas(image)

    src_w, src_h = image.size
    target_ratio = CANVAS_SIZE[0] / CANVAS_SIZE[1]
    face = sorted(source_faces, key=lambda item: item.area, reverse=True)[0]
    face_cx = face.x + face.w / 2
    face_cy = face.y + face.h / 2

    crop_h = int(min(src_h, face.h * 1.95))
    crop_w = int(crop_h * target_ratio)
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)
    if crop_h > src_h:
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)

    target_x = 0.2 + ((variant_index % 3) - 1) * 0.02
    target_y = 0.43
    if face_cx - crop_w * target_x < 0:
        crop_w = int(face_cx / target_x)
        crop_h = int(crop_w / target_ratio)
    if face_cx + crop_w * (1 - target_x) > src_w:
        crop_w = int((src_w - face_cx) / (1 - target_x))
        crop_h = int(crop_w / target_ratio)
    crop_w = max(1, min(src_w, crop_w))
    crop_h = max(1, min(src_h, crop_h))
    left = int(face_cx - crop_w * target_x)
    top = int(face_cy - crop_h * target_y)
    left = max(0, min(src_w - crop_w, left))
    top = max(0, min(src_h - crop_h, top))
    crop = (left, top, left + crop_w, top + crop_h)
    return image.crop(crop).resize(CANVAS_SIZE, Image.Resampling.LANCZOS), crop


def map_rect_to_canvas(rect: Rect, crop: tuple[int, int, int, int]) -> Rect | None:
    left, top, right, bottom = crop
    x1 = max(rect.x, left)
    y1 = max(rect.y, top)
    x2 = min(rect.x + rect.w, right)
    y2 = min(rect.y + rect.h, bottom)
    if x2 <= x1 or y2 <= y1:
        return None
    sx = CANVAS_SIZE[0] / (right - left)
    sy = CANVAS_SIZE[1] / (bottom - top)
    return Rect(
        int((x1 - left) * sx),
        int((y1 - top) * sy),
        int((x2 - x1) * sx),
        int((y2 - y1) * sy),
    )


def detect_faces(image_path: Path) -> list[dict[str, object]]:
    img = cv2.imread(str(image_path))
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    detectors = [
        ("frontal", "haarcascade_frontalface_default.xml"),
        ("frontal_alt2", "haarcascade_frontalface_alt2.xml"),
        ("profile", "haarcascade_profileface.xml"),
    ]
    found: list[tuple[str, Rect]] = []
    for kind, cascade_name in detectors:
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / cascade_name))
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(80, 80),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        for x, y, w, h in faces:
            found.append((kind, Rect(int(x), int(y), int(w), int(h))))
        if kind == "profile":
            flipped = cv2.flip(gray, 1)
            faces = cascade.detectMultiScale(
                flipped,
                scaleFactor=1.08,
                minNeighbors=4,
                minSize=(80, 80),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )
            width = gray.shape[1]
            for x, y, w, h in faces:
                found.append(("profile_flipped", Rect(int(width - x - w), int(y), int(w), int(h))))

    merged: list[tuple[str, Rect]] = []
    for kind, rect in sorted(found, key=lambda item: item[1].area, reverse=True):
        if not any(rect.intersection_area(existing) / max(1, min(rect.area, existing.area)) > 0.35 for _, existing in merged):
            merged.append((kind, rect))
    return [{"method": kind, "box": rect.as_list()} for kind, rect in merged[:4]]


def choose_text_box(face_boxes: list[Rect], variant_index: int, preferred: str | None = None) -> tuple[str, Rect]:
    choices = [
        ("left", Rect(32, 112, 560, 490)),
        ("right", Rect(688, 112, 560, 490)),
        ("lower_left", Rect(38, 392, 610, 282)),
        ("lower_right", Rect(632, 392, 610, 282)),
        ("bottom", Rect(38, 430, 1198, 244)),
        ("top", Rect(38, 84, 1198, 254)),
    ]
    protected = [box.expanded(70, 85, *CANVAS_SIZE) for box in face_boxes]
    scored: list[tuple[float, str, Rect]] = []
    for name, rect in choices:
        face_overlap = sum(rect.intersection_area(box) for box in face_boxes)
        protected_overlap = sum(rect.intersection_area(box) for box in protected)
        side_bias = 25_000 if (variant_index % 2 == 0 and name == "right") or (variant_index % 2 == 1 and name == "left") else 0
        if preferred == name:
            side_bias += 380_000
            if face_overlap == 0:
                side_bias += 260_000
        scored.append((rect.area - face_overlap * 1_200 - protected_overlap * 3 + side_bias, name, rect))
    _, name, rect = max(scored, key=lambda item: item[0])
    return name, rect


def rect_from_list(values: list[int] | tuple[int, int, int, int]) -> Rect:
    return Rect(int(values[0]), int(values[1]), int(values[2]), int(values[3]))


def choose_logo_box(face_boxes: list[Rect], text_box: Rect, extra_avoid: list[Rect] | None = None, preferred: str | None = None) -> Rect:
    logo_w, logo_h = 292, 54
    candidates = {
        "top_left": Rect(20, 22, logo_w, logo_h),
        "top_right": Rect(CANVAS_SIZE[0] - logo_w - 20, 22, logo_w, logo_h),
        "bottom_left": Rect(20, CANVAS_SIZE[1] - logo_h - 22, logo_w, logo_h),
        "bottom_right": Rect(CANVAS_SIZE[0] - logo_w - 20, CANVAS_SIZE[1] - logo_h - 22, logo_w, logo_h),
        "mid_right": Rect(CANVAS_SIZE[0] - logo_w - 20, 96, logo_w, logo_h),
    }
    protected = [box.expanded(45, 45, *CANVAS_SIZE) for box in face_boxes] + [text_box.expanded(10, 10, *CANVAS_SIZE)]
    if extra_avoid:
        protected.extend(box.expanded(10, 10, *CANVAS_SIZE) for box in extra_avoid)
    scored = []
    for name, rect in candidates.items():
        overlap = sum(rect.intersection_area(box) for box in protected)
        preference_penalty = 0 if preferred == name else 12_000
        scored.append((overlap + preference_penalty, rect))
    return min(scored, key=lambda item: item[0])[1]


def fit_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in [part for part in text.split("\n") if part]:
        line = ""
        tokens: list[str] = []
        token = ""
        for char in paragraph:
            if char.isascii() and char.isalnum():
                token += char
            else:
                if token:
                    tokens.append(token)
                    token = ""
                tokens.append(char)
        if token:
            tokens.append(token)
        for token in tokens:
            trial = line + token
            if font.getbbox(trial)[2] <= max_width or not line:
                line = trial
            else:
                lines.append(line)
                line = token
        if line:
            lines.append(line)
    return lines


def fit_title_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int = 2) -> list[str]:
    manual_lines = [line for line in text.split("\n") if line]
    if 0 < len(manual_lines) <= max_lines:
        return manual_lines
    wrapped = fit_lines(text, font, max_width)
    if len(wrapped) <= max_lines:
        return wrapped
    return wrapped[: max_lines - 1] + ["".join(wrapped[max_lines - 1 :])]


def title_box_to_edge(box: Rect, region: str) -> Rect:
    edge = 10
    bottom_edge = CANVAS_SIZE[1] - 12
    if region in {"lower_left", "left"}:
        return Rect(edge, box.y, box.w + box.x - edge, max(box.h, bottom_edge - box.y))
    if region in {"lower_right", "right"}:
        x = max(edge, CANVAS_SIZE[0] - box.w - edge)
        return Rect(x, box.y, box.w, max(box.h, bottom_edge - box.y))
    if region in {"bottom", "top"}:
        return Rect(edge, box.y, CANVAS_SIZE[0] - edge * 2, max(box.h, bottom_edge - box.y))
    return box


def draw_attached_hook(draw: ImageDraw.ImageDraw, text: str, palette: dict[str, tuple[int, int, int]], title_box: Rect, align: str = "left") -> Rect:
    font = load_font(58, True)
    stroke_width = 3
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    pad_x, pad_y = 16, 9
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    w = min(CANVAS_SIZE[0] - 36, text_w + pad_x * 2)
    h = text_h + pad_y * 2
    y = max(14, title_box.y - h - 8)
    if align == "right":
        x = min(CANVAS_SIZE[0] - w - 18, title_box.x + title_box.w - w)
    elif align == "center":
        x = title_box.x + (title_box.w - w) // 2
    else:
        x = title_box.x + 8
    x = max(18, min(CANVAS_SIZE[0] - w - 18, x))
    rect = Rect(x, y, w, h)
    draw.rectangle((rect.x, rect.y, rect.x + rect.w, rect.y + rect.h), fill=palette["hook_bg"])
    draw.text(
        (rect.x + pad_x - bbox[0], rect.y + (rect.h - text_h) // 2 - bbox[1]),
        text,
        font=font,
        fill=palette["hook_text"],
        stroke_width=stroke_width,
        stroke_fill=palette["hook_shadow"],
    )
    return rect


def draw_text_block(draw: ImageDraw.ImageDraw, box: Rect, title: str, subtitle: str, palette: dict[str, tuple[int, int, int]]) -> None:
    stroke_margin = 10
    bottom_padding = 10
    max_width = box.w - stroke_margin * 2
    title_size = min(178, max(140, int(box.h * 0.68)))
    while title_size >= 92:
        title_font = load_font(title_size, True)
        stroke_width = max(9, title_size // 10)
        lines = fit_title_lines(title, title_font, max_width)
        bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke_width) for line in lines]
        line_gap = max(8, int(title_size * 0.08))
        total_h = sum(bbox[3] - bbox[1] for bbox in bboxes) + line_gap * max(0, len(lines) - 1)
        if total_h <= box.h - bottom_padding and all(bbox[2] - bbox[0] <= max_width for bbox in bboxes):
            break
        title_size -= 4
    title_font = load_font(title_size, True)
    stroke_width = max(9, title_size // 10)
    lines = fit_title_lines(title, title_font, max_width)
    bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke_width) for line in lines]
    line_gap = max(8, int(title_size * 0.08))
    total_h = sum(bbox[3] - bbox[1] for bbox in bboxes) + line_gap * max(0, len(lines) - 1)
    y = box.y + max(0, box.h - total_h - bottom_padding)
    for line, bbox in zip(lines, bboxes):
        line_h = bbox[3] - bbox[1]
        draw.text(
            (box.x + stroke_margin - bbox[0], y - bbox[1]),
            line,
            font=title_font,
            fill=palette["text"],
            stroke_width=stroke_width,
            stroke_fill=palette["shadow"],
        )
        y += line_h + line_gap


def draw_bottom_single_line_title(draw: ImageDraw.ImageDraw, title: str, palette: dict[str, tuple[int, int, int]]) -> Rect:
    box = Rect(8, 548, CANVAS_SIZE[0] - 16, 164)
    title_size = 156
    while title_size >= 96:
        font = load_font(title_size, True)
        stroke_width = max(9, title_size // 11)
        bbox = draw.textbbox((0, 0), title, font=font, stroke_width=stroke_width)
        if bbox[2] - bbox[0] <= box.w - 14 and bbox[3] - bbox[1] <= box.h - 12:
            break
        title_size -= 4

    font = load_font(title_size, True)
    stroke_width = max(9, title_size // 11)
    bbox = draw.textbbox((0, 0), title, font=font, stroke_width=stroke_width)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = box.x + (box.w - text_w) // 2 - bbox[0]
    y = box.y + box.h - text_h - 8 - bbox[1]
    draw.text(
        (x, y),
        title,
        font=font,
        fill=palette["text"],
        stroke_width=stroke_width,
        stroke_fill=palette["shadow"],
    )
    return box


def draw_left_stacked_title(draw: ImageDraw.ImageDraw, title: str, hook: str, palette: dict[str, tuple[int, int, int]]) -> tuple[Rect, Rect]:
    title_box = Rect(18, 374, 840, 330)
    hook_rect = draw_attached_hook(draw, hook, palette, title_box, "left")
    max_width = title_box.w - 28
    title_size = 174
    while title_size >= 104:
        title_font = load_font(title_size, True)
        stroke_width = max(9, title_size // 10)
        lines = fit_title_lines(title, title_font, max_width)
        bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke_width) for line in lines]
        line_gap = max(8, int(title_size * 0.08))
        total_h = sum(bbox[3] - bbox[1] for bbox in bboxes) + line_gap * max(0, len(lines) - 1)
        if total_h <= title_box.h and all(bbox[2] - bbox[0] <= max_width for bbox in bboxes):
            break
        title_size -= 4

    title_font = load_font(title_size, True)
    stroke_width = max(9, title_size // 10)
    lines = fit_title_lines(title, title_font, max_width)
    bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke_width) for line in lines]
    line_gap = max(8, int(title_size * 0.08))
    total_h = sum(bbox[3] - bbox[1] for bbox in bboxes) + line_gap * max(0, len(lines) - 1)
    y = title_box.y + title_box.h - total_h - 6
    for line, bbox in zip(lines, bboxes):
        line_h = bbox[3] - bbox[1]
        draw.text(
            (title_box.x + 10 - bbox[0], y - bbox[1]),
            line,
            font=title_font,
            fill=palette["text"],
            stroke_width=stroke_width,
            stroke_fill=palette["shadow"],
        )
        y += line_h + line_gap

    return hook_rect, title_box


def draw_right_stacked_title(draw: ImageDraw.ImageDraw, title: str, hook: str, palette: dict[str, tuple[int, int, int]]) -> tuple[Rect, Rect]:
    title_box = Rect(CANVAS_SIZE[0] - 850, 374, 840, 330)
    hook_rect = draw_attached_hook(draw, hook, palette, title_box, "right")
    max_width = title_box.w - 28
    title_size = 174
    while title_size >= 104:
        title_font = load_font(title_size, True)
        stroke_width = max(9, title_size // 10)
        lines = fit_title_lines(title, title_font, max_width)
        bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke_width) for line in lines]
        line_gap = max(8, int(title_size * 0.08))
        total_h = sum(bbox[3] - bbox[1] for bbox in bboxes) + line_gap * max(0, len(lines) - 1)
        if total_h <= title_box.h and all(bbox[2] - bbox[0] <= max_width for bbox in bboxes):
            break
        title_size -= 4

    title_font = load_font(title_size, True)
    stroke_width = max(9, title_size // 10)
    lines = fit_title_lines(title, title_font, max_width)
    bboxes = [draw.textbbox((0, 0), line, font=title_font, stroke_width=stroke_width) for line in lines]
    line_gap = max(8, int(title_size * 0.08))
    total_h = sum(bbox[3] - bbox[1] for bbox in bboxes) + line_gap * max(0, len(lines) - 1)
    y = title_box.y + title_box.h - total_h - 6
    for line, bbox in zip(lines, bboxes):
        line_h = bbox[3] - bbox[1]
        line_w = bbox[2] - bbox[0]
        draw.text(
            (title_box.x + title_box.w - 10 - line_w - bbox[0], y - bbox[1]),
            line,
            font=title_font,
            fill=palette["text"],
            stroke_width=stroke_width,
            stroke_fill=palette["shadow"],
        )
        y += line_h + line_gap

    return hook_rect, title_box


def add_gradient_overlay(image: Image.Image, side: str, color: tuple[int, int, int]) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    arr = np.zeros((CANVAS_SIZE[1], CANVAS_SIZE[0], 4), dtype=np.uint8)
    for x in range(CANVAS_SIZE[0]):
        if side == "left":
            strength = max(0, 1 - x / 680)
        elif side == "right":
            strength = max(0, (x - 520) / 760)
        elif side == "top":
            strength = np.maximum(0, 1 - np.arange(CANVAS_SIZE[1])[:, None] / 360)
            break
        else:
            strength = np.maximum(0, (np.arange(CANVAS_SIZE[1])[:, None] - 320) / 400)
            break
        arr[:, x, :3] = color
        arr[:, x, 3] = int(188 * min(1, strength))
    if side in {"top", "bottom"}:
        arr[:, :, :3] = color
        arr[:, :, 3] = (188 * np.clip(strength, 0, 1)).astype(np.uint8)
    overlay = Image.fromarray(arr, "RGBA")
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def paste_logo(canvas: Image.Image, logo_box: Rect) -> None:
    logo = Image.open(LOGO_PATH).convert("RGBA")
    alpha_bbox = logo.getbbox()
    if alpha_bbox:
        logo = logo.crop(alpha_bbox)
    pad_x, pad_y = 10, 8
    logo.thumbnail((logo_box.w - pad_x * 2, logo_box.h - pad_y * 2), Image.Resampling.LANCZOS)
    plate = Image.new("RGBA", (logo.width + pad_x * 2, logo.height + pad_y * 2), (255, 255, 255, 232))
    plate_draw = ImageDraw.Draw(plate)
    plate_draw.rounded_rectangle((0, 0, plate.width - 1, plate.height - 1), radius=4, fill=(255, 255, 255, 232))
    plate.alpha_composite(logo, (pad_x, pad_y))
    canvas.alpha_composite(plate, (logo_box.x, logo_box.y))


def draw_top_hook(draw: ImageDraw.ImageDraw, text: str, palette: dict[str, tuple[int, int, int]], position: str = "top_left") -> Rect:
    font = load_font(58, True)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=3)
    pad_x, pad_y = 16, 9
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    w = min(CANVAS_SIZE[0] - 36, text_w + pad_x * 2)
    h = text_h + pad_y * 2
    if position == "top_right":
        rect = Rect(CANVAS_SIZE[0] - w - 18, 16, w, h)
    elif position == "bottom_left":
        rect = Rect(18, CANVAS_SIZE[1] - h - 18, w, h)
    else:
        rect = Rect(18, 16, w, h)
    draw.rounded_rectangle((rect.x, rect.y, rect.x + rect.w, rect.y + rect.h), radius=0, fill=palette["hook_bg"])
    text_x = rect.x + pad_x - bbox[0]
    text_y = rect.y + (rect.h - text_h) // 2 - bbox[1]
    draw.text((text_x, text_y), text, font=font, fill=palette["hook_text"], stroke_width=3, stroke_fill=palette["hook_shadow"])
    return rect


def opposite_top_corner(position: str) -> str:
    return "top_left" if "right" in position else "top_right"


def draw_duration_chip(draw: ImageDraw.ImageDraw, text: str = "17:55") -> None:
    font = load_font(24, True)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 16
    h = bbox[3] - bbox[1] + 8
    x = CANVAS_SIZE[0] - w - 8
    y = CANVAS_SIZE[1] - h - 8
    draw.rounded_rectangle((x, y, x + w, y + h), radius=3, fill=(10, 10, 10, 235))
    draw.text((x + 8, y + 3), text, font=font, fill=(255, 255, 255))


def draw_reference_frame(draw: ImageDraw.ImageDraw, palette: dict[str, tuple[int, int, int]]) -> None:
    color = palette["frame"]
    for i in range(7):
        draw.rectangle((i, i, CANVAS_SIZE[0] - i - 1, CANVAS_SIZE[1] - i - 1), outline=color)


def draw_face_debug(canvas: Image.Image, face_boxes: list[Rect]) -> None:
    draw = ImageDraw.Draw(canvas)
    for rect in face_boxes:
        protected = rect.expanded(70, 85, *CANVAS_SIZE)
        draw.rectangle(
            (protected.x, protected.y, protected.x + protected.w, protected.y + protected.h),
            outline=(255, 220, 0),
            width=3,
        )


def read_video_context() -> dict[str, object]:
    segments: list[dict[str, object]] = []
    if TRANSCRIPT_PATH.exists():
        data = json.loads(TRANSCRIPT_PATH.read_text(encoding="utf-8"))
        for segment in data.get("segments", []):
            if float(segment.get("start", 0)) <= 60:
                segments.append(
                    {
                        "start": segment.get("start"),
                        "end": segment.get("end"),
                        "text": segment.get("text"),
                    }
                )
    return {
        "source_video": str(VIDEO_PATH),
        "transcript": str(TRANSCRIPT_PATH) if TRANSCRIPT_PATH.exists() else None,
        "summary": "PdM / freelance positioning / AI engineer context; discussion starts from why the PdM freelance debate happens.",
        "chosen_title": "PdMはフリーで通用する？",
        "segments_used": segments[:14],
    }


def analyze_assets() -> dict[str, object]:
    images = []
    for path in sorted(ASSET_DIR.glob("ST-*.jpg")):
        image = Image.open(path).convert("RGB")
        _, crop = crop_to_canvas(image)
        raw_faces = detect_faces(path)
        kept_source_faces = []
        canvas_faces = []
        for face in raw_faces:
            mapped = map_rect_to_canvas(Rect(*face["box"]), crop)
            if mapped and mapped.w >= 120 and mapped.h >= 120:
                kept_source_faces.append(face)
                canvas_faces.append({"method": face["method"], "box": mapped.as_list()})
        images.append(
            {
                "file": str(path),
                "size": list(image.size),
                "canvas_crop_source_box": list(crop),
                "faces_source": kept_source_faces,
                "faces_canvas": canvas_faces,
            }
        )
    return {
        "generated_by": "scripts/generate_thumbnail_candidates.py",
        "canvas": list(CANVAS_SIZE),
        "video_context": read_video_context(),
        "reference_style": {
            "saved_reference_dir": str(REFERENCE_DIR),
            "notes_path": str(REFERENCE_STYLE_PATH),
        },
        "images": images,
    }


def render_candidate(
    index: int,
    candidate: dict[str, object],
    analysis: dict[str, object],
    output_stem: str,
    debug: bool = False,
) -> dict[str, object]:
    source_name = str(candidate["source"])
    title = str(candidate["title"])
    subtitle = str(candidate["subtitle"])
    hook = str(candidate["hook"])
    palette = candidate["palette"]
    image_info = next(item for item in analysis["images"] if Path(item["file"]).name == source_name)
    image = Image.open(image_info["file"]).convert("RGB")
    source_faces = [Rect(*face["box"]) for face in image_info.get("faces_source", [])]
    if candidate.get("left_face_closeup"):
        canvas, crop = crop_face_left_closeup_to_canvas(image, source_faces, index)
    elif candidate.get("right_face_closeup"):
        canvas, crop = crop_face_right_closeup_to_canvas(image, source_faces, index)
    elif candidate.get("closeup"):
        canvas, crop = crop_face_closeup_to_canvas(image, source_faces, index)
    else:
        canvas, crop = crop_to_canvas(image)
    canvas = ImageEnhance.Color(canvas).enhance(1.18)
    canvas = ImageEnhance.Contrast(canvas).enhance(1.13)
    canvas = ImageEnhance.Sharpness(canvas).enhance(1.18)
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=1.7, percent=150, threshold=3)).convert("RGBA")
    if candidate.get("left_face_closeup") or candidate.get("right_face_closeup") or candidate.get("closeup"):
        face_boxes = [mapped for face in source_faces if (mapped := map_rect_to_canvas(face, crop)) is not None]
    else:
        face_boxes = [Rect(*face["box"]) for face in image_info["faces_canvas"]]
    if candidate.get("text_box"):
        text_side = str(candidate.get("region") or "manual")
        text_box = rect_from_list(candidate["text_box"])
    else:
        text_side, text_box = choose_text_box(face_boxes, index, str(candidate.get("region") or ""))
    canvas = add_gradient_overlay(canvas, text_side, palette["overlay"])
    draw = ImageDraw.Draw(canvas)

    if candidate.get("right_stacked_title"):
        hook_rect, text_box = draw_right_stacked_title(draw, title, hook, palette)
    elif candidate.get("left_stacked_title"):
        hook_rect, text_box = draw_left_stacked_title(draw, title, hook, palette)
    elif candidate.get("single_line_bottom_title"):
        text_box = Rect(8, 548, CANVAS_SIZE[0] - 16, 164)
        hook_position = opposite_top_corner(str(candidate.get("logo_position") or "top_right"))
        hook_rect = draw_top_hook(draw, hook, palette, hook_position)
        text_box = draw_bottom_single_line_title(draw, title, palette)
    elif not candidate.get("left_stacked_title") and not candidate.get("right_stacked_title"):
        text_box = title_box_to_edge(text_box, text_side)
        hook_align = "right" if text_side in {"right", "lower_right"} else "left"
        if text_side in {"bottom", "top"}:
            hook_align = "center"
        hook_rect = draw_attached_hook(draw, hook, palette, text_box, hook_align)
        draw_text_block(draw, text_box, title, subtitle, palette)
    draw_reference_frame(draw, palette)
    if candidate.get("logo_box"):
        logo_box = rect_from_list(candidate["logo_box"])
    else:
        logo_box = choose_logo_box(face_boxes, text_box, [hook_rect], str(candidate.get("logo_position") or ""))
    paste_logo(canvas, logo_box)
    if debug:
        draw_face_debug(canvas, face_boxes)
    out = OUTPUT_DIR / f"{output_stem}_candidate_{index:02d}.png"
    canvas.convert("RGB").save(out, quality=95)
    return {
        "output": str(out),
        "source_image": str(image_info["file"]),
        "title": title.replace("\n", ""),
        "subtitle": subtitle,
        "hook": hook,
        "reference_style": "bold Japanese documentary/interview thumbnail: large yellow/white text, thick black stroke, top strap, angled white banner, small duration chip, accent border",
        "layout_reason": str(candidate.get("layout_reason") or ""),
        "text_region_name": text_side,
        "text_region_canvas": text_box.as_list(),
        "logo_region_canvas": logo_box.as_list(),
        "protected_faces_canvas": [box.as_list() for box in face_boxes],
    }


def write_contact_sheet(paths: list[str], output_stem: str) -> Path:
    thumb_w, thumb_h = 320, 180
    cols = 4
    rows = math.ceil(len(paths) / cols)
    label_h = 28
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + label_h)), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    font = load_font(18, True)
    for idx, raw_path in enumerate(paths):
        path = Path(raw_path)
        thumb = Image.open(path).convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        x = (idx % cols) * thumb_w
        y = (idx // cols) * (thumb_h + label_h)
        sheet.paste(thumb, (x, y))
        draw.rectangle((x, y + thumb_h, x + thumb_w, y + thumb_h + label_h), fill=(25, 25, 25))
        draw.text((x + 8, y + thumb_h + 4), f"{idx + 1:02d}  {path.name}", fill=(255, 255, 255), font=font)
    out = OUTPUT_DIR / f"{output_stem}_candidates_contact_sheet.jpg"
    sheet.save(out, quality=92)
    return out


MAIN_COLOR_STYLES = {
    "yellow": {
        "text": (255, 218, 36),
        "accent": (255, 230, 54),
        "hook_text": (0, 0, 0),
        "hook_shadow": (255, 255, 255),
        "overlay": (18, 16, 5),
    },
    "red": {
        "text": (238, 35, 30),
        "accent": (237, 28, 36),
        "hook_text": (255, 255, 255),
        "hook_shadow": (0, 0, 0),
        "overlay": (26, 8, 8),
    },
    "orange": {
        "text": (255, 128, 0),
        "accent": (255, 132, 0),
        "hook_text": (0, 0, 0),
        "hook_shadow": (255, 255, 255),
        "overlay": (26, 14, 4),
    },
    "green": {
        "text": (0, 205, 95),
        "accent": (0, 178, 90),
        "hook_text": (255, 255, 255),
        "hook_shadow": (0, 0, 0),
        "overlay": (3, 22, 13),
    },
    "blue": {
        "text": (0, 174, 239),
        "accent": (0, 142, 214),
        "hook_text": (255, 255, 255),
        "hook_shadow": (0, 0, 0),
        "overlay": (4, 14, 28),
    },
    "cyan": {
        "text": (0, 225, 230),
        "accent": (0, 185, 200),
        "hook_text": (0, 0, 0),
        "hook_shadow": (255, 255, 255),
        "overlay": (3, 22, 24),
    },
    "purple": {
        "text": (175, 92, 255),
        "accent": (145, 68, 226),
        "hook_text": (255, 255, 255),
        "hook_shadow": (0, 0, 0),
        "overlay": (18, 10, 28),
    },
    "pink": {
        "text": (255, 76, 180),
        "accent": (238, 73, 185),
        "hook_text": (0, 0, 0),
        "hook_shadow": (255, 255, 255),
        "overlay": (26, 8, 21),
    },
    "white": {
        "text": (255, 255, 255),
        "accent": (255, 255, 255),
        "hook_text": (0, 0, 0),
        "hook_shadow": (255, 255, 255),
        "overlay": (10, 10, 10),
    },
}


def apply_main_color(palette: dict[str, tuple[int, int, int]], main_color: str) -> dict[str, tuple[int, int, int]]:
    style = MAIN_COLOR_STYLES[main_color]
    updated = dict(palette)
    updated.update(
        {
            "overlay": style["overlay"],
            "hook_bg": style["accent"],
            "hook_text": style["hook_text"],
            "hook_shadow": style["hook_shadow"],
            "text": style["text"],
            "frame": style["accent"],
            "banner": style["accent"],
            "banner_text": style["hook_text"],
            "banner_shadow": style["hook_shadow"],
        }
    )
    return updated


def thumbnail_output_stem(mode: str, main_color: str) -> str:
    color_suffix = "" if main_color == "yellow" else f"_{main_color}"
    return f"thumbnail_{mode}{color_suffix}"


def write_reference_style_notes() -> dict[str, object]:
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    local_files = [path for path in sorted(REFERENCE_DIR.glob("*")) if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    image_analysis = []
    for path in local_files:
        image = Image.open(path).convert("RGB").resize((320, 180), Image.Resampling.LANCZOS)
        arr = np.asarray(image)
        top_band = arr[:40].reshape(-1, 3).mean(axis=0).round().astype(int).tolist()
        bottom_band = arr[130:].reshape(-1, 3).mean(axis=0).round().astype(int).tolist()
        left_half_luma = float(np.mean(arr[:, :160].mean(axis=2)))
        right_half_luma = float(np.mean(arr[:, 160:].mean(axis=2)))
        bright_mask = np.mean(arr, axis=2) > 210
        dark_mask = np.mean(arr, axis=2) < 45
        image_analysis.append(
            {
                "file": str(path),
                "source_size": list(Image.open(path).size),
                "top_band_average_rgb": top_band,
                "bottom_band_average_rgb": bottom_band,
                "left_half_luma": round(left_half_luma, 2),
                "right_half_luma": round(right_half_luma, 2),
                "bright_pixel_ratio": round(float(bright_mask.mean()), 4),
                "dark_pixel_ratio": round(float(dark_mask.mean()), 4),
            }
        )
    notes = {
        "local_reference_files": [str(path) for path in local_files],
        "image_analysis": image_analysis,
        "manual_layout_read": [
            "The reference thumbnails use one dominant headline, often 35-50% of canvas height.",
            "Auxiliary labels are minimal: a top topic strap and a duration chip. Small angled callouts are not part of the main structure.",
            "Main headline text is white or yellow with a very thick black stroke. It is not placed inside a dark card.",
            "Text placement follows the subject: if the face is high or left, the headline moves to the lower or opposite side.",
            "Brand/logo appears once, separate from the headline copy.",
        ],
        "applied_rules": [
            "Use huge Japanese text with thick black stroke and no dark boxed panels.",
            "Keep the face area clear using OpenCV face boxes and record the final text/logo boxes in JSON.",
            "Use only one short top strap for topic framing; do not draw small subtitle diamonds or angled badges.",
            "Use yellow or white as the main text color, with red/green/cyan accents per candidate.",
            "Add only a duration chip and an accent border as secondary UI.",
            "Place the Engineer Type logo once in the least-overlapping corner and do not repeat the brand name in text.",
        ],
    }
    REFERENCE_STYLE_PATH.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    return notes


def validate_candidate_copy(candidates: list[dict[str, object]]) -> None:
    context_terms = ("PdM", "AI", "キャリア", "プロダクト", "フリー")
    vague_only = ("条件", "真相", "立ち位置", "価値", "強み")
    for index, candidate in enumerate(candidates, start=1):
        title = str(candidate["title"]).replace("\n", "")
        hook = str(candidate["hook"])
        if not any(term in title for term in context_terms):
            raise ValueError(f"candidate {index:02d} title lacks context term: {title}")
        if title in vague_only:
            raise ValueError(f"candidate {index:02d} title is too vague: {title}")
        if "エンジニアtype" in title or "エンジニアtype" in hook:
            raise ValueError(f"candidate {index:02d} repeats brand text outside the logo")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze source images and generate thumbnail candidates.")
    parser.add_argument("--import-assets", action="store_true", help="Copy ST-*.jpg assets into source/thumbnail/etype260515_p_takei first.")
    parser.add_argument("--asset-source", type=Path, default=ASSET_SOURCE_DEFAULT)
    parser.add_argument("--debug-faces", action="store_true", help="Draw protected face areas on output thumbnails.")
    parser.add_argument(
        "--main-color",
        choices=sorted(MAIN_COLOR_STYLES),
        default="yellow",
        help="Main thumbnail color for title text, hook background, accent frame, and overlay tint.",
    )
    parser.add_argument(
        "--closeup-bottom-title",
        action="store_true",
        help="Use face-centered close-up crops and a one-line title along the bottom edge.",
    )
    parser.add_argument(
        "--right-face-title-stack",
        action="store_true",
        help="Use a tight right-side face crop with the hook stacked above the wrapped title on the left.",
    )
    parser.add_argument(
        "--left-face-title-stack",
        action="store_true",
        help="Use a tight left-side face crop with the hook stacked above the wrapped title on the right.",
    )
    args = parser.parse_args()
    selected_modes = [args.closeup_bottom_title, args.right_face_title_stack, args.left_face_title_stack]
    if sum(1 for selected in selected_modes if selected) > 1:
        raise SystemExit("Choose only one thumbnail layout mode.")
    if args.left_face_title_stack:
        thumbnail_mode = "left_face_title_stack"
    elif args.right_face_title_stack:
        thumbnail_mode = "right_face_title_stack"
    elif args.closeup_bottom_title:
        thumbnail_mode = "closeup_bottom_title"
    else:
        thumbnail_mode = "standard"
    output_stem = thumbnail_output_stem(thumbnail_mode, args.main_color)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.import_assets:
        copied = import_assets(args.asset_source)
        if copied == 0:
            raise SystemExit(f"No ST-*.jpg files found under {args.asset_source}")

    if not list(ASSET_DIR.glob("ST-*.jpg")):
        raise SystemExit(f"No source thumbnail assets found under {ASSET_DIR}")

    reference_notes = write_reference_style_notes()
    analysis = analyze_assets()
    analysis["reference_style_notes"] = reference_notes

    palettes = {
        "red_yellow": {"overlay": (12, 12, 12), "hook_bg": (237, 28, 36), "hook_text": (255, 255, 255), "hook_shadow": (0, 0, 0), "text": (255, 218, 36), "shadow": (0, 0, 0), "banner": (255, 255, 255), "banner_text": (238, 35, 30), "banner_shadow": (255, 255, 255), "frame": (237, 28, 36)},
        "teal_white": {"overlay": (3, 33, 41), "hook_bg": (0, 180, 170), "hook_text": (255, 255, 255), "hook_shadow": (0, 0, 0), "text": (255, 255, 255), "shadow": (0, 0, 0), "banner": (255, 230, 54), "banner_text": (0, 0, 0), "banner_shadow": (255, 230, 54), "frame": (0, 180, 170)},
        "lime_black": {"overlay": (10, 10, 10), "hook_bg": (178, 238, 92), "hook_text": (0, 0, 0), "hook_shadow": (255, 255, 255), "text": (255, 255, 255), "shadow": (0, 0, 0), "banner": (255, 255, 255), "banner_text": (0, 0, 0), "banner_shadow": (255, 255, 255), "frame": (178, 238, 92)},
        "magenta_white": {"overlay": (18, 13, 28), "hook_bg": (238, 73, 185), "hook_text": (0, 0, 0), "hook_shadow": (255, 255, 255), "text": (255, 255, 255), "shadow": (0, 0, 0), "banner": (255, 255, 255), "banner_text": (238, 35, 30), "banner_shadow": (255, 255, 255), "frame": (238, 73, 185)},
        "yellow_teal": {"overlay": (9, 24, 30), "hook_bg": (255, 230, 54), "hook_text": (0, 0, 0), "hook_shadow": (255, 255, 255), "text": (255, 255, 255), "shadow": (0, 0, 0), "banner": (0, 160, 150), "banner_text": (255, 255, 255), "banner_shadow": (0, 0, 0), "frame": (255, 230, 54)},
    }

    candidates = [
        {"source": "ST-500.jpg", "hook": "フリーランスPdM", "title": "フリーPdM\n通用する？", "subtitle": "", "region": "lower_left", "text_box": [38, 430, 760, 240], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "顔は中央上寄りなので、タイトルは顔下の胴体・空き壁側に寄せる。", "duration": "17:55", "palette": palettes["red_yellow"]},
        {"source": "ST-516.jpg", "hook": "AI時代のキャリア", "title": "AI人材の\n立ち位置", "subtitle": "", "region": "lower_left", "text_box": [38, 402, 760, 266], "hook_position": "top_left", "logo_position": "bottom_right", "layout_reason": "顔は右上寄りで下半身側に暗い余白があるため、タイトルを左下に寄せて表情を残す。", "duration": "37:01", "palette": palettes["teal_white"]},
        {"source": "ST-522.jpg", "hook": "PdMの仕事論", "title": "PdMは\n踏み込めるか", "subtitle": "", "region": "lower_left", "text_box": [36, 424, 770, 246], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "顔は中央上寄りなので、目線を残して左下の肩・背景側に文字をまとめる。", "duration": "20:16", "palette": palettes["lime_black"]},
        {"source": "ST-528.jpg", "hook": "フリーランスPdM", "title": "フリーPdM\n通用する人", "subtitle": "", "region": "lower_left", "text_box": [38, 374, 760, 294], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "人物2人は中央から右なので、左下の余白にタイトルを置いて全身を残す。", "duration": "37:23", "palette": palettes["red_yellow"]},
        {"source": "ST-532.jpg", "hook": "AI時代のキャリア", "title": "AI時代の\nキャリア戦略", "subtitle": "", "region": "lower_right", "text_box": [470, 384, 760, 286], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "顔は左上なので、胴体と背景のある右下にタイトルを寄せる。", "duration": "17:55", "palette": palettes["yellow_teal"]},
        {"source": "ST-503.jpg", "hook": "PdM論争の入口", "title": "客観視できる\nPdMが強い", "subtitle": "", "region": "lower_right", "text_box": [520, 420, 700, 250], "hook_position": "top_left", "logo_position": "bottom_left", "layout_reason": "顔は左上寄りなので、右下の背景側に大きく置く。", "duration": "17:55", "palette": palettes["magenta_white"]},
        {"source": "ST-506.jpg", "hook": "プロダクト中心で戦う", "title": "プロダクトで\n勝てるPdM", "subtitle": "", "region": "lower_left", "text_box": [36, 470, 760, 200], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "顔は中央上寄り、手元と胴体側の左下に文字を逃がす。", "duration": "20:16", "palette": palettes["lime_black"]},
        {"source": "ST-510.jpg", "hook": "フリーPdMの条件", "title": "フリーPdM\n何が強い？", "subtitle": "", "region": "lower_right", "text_box": [500, 430, 730, 240], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "顔は左中央寄りなので、右下の空きに主文字を置く。", "duration": "37:01", "palette": palettes["teal_white"]},
        {"source": "ST-513.jpg", "hook": "PdMの市場価値", "title": "選ばれる\nPdMとは", "subtitle": "", "region": "lower_left", "text_box": [36, 486, 670, 184], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "顔は右寄りなので、左下の壁と胴体側に文字を配置。", "duration": "17:55", "palette": palettes["yellow_teal"]},
        {"source": "ST-517.jpg", "hook": "AI時代の生存戦略", "title": "AI時代に\n残るPdM", "subtitle": "", "region": "lower_left", "text_box": [40, 380, 760, 292], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "全身素材なので顔を上に残し、下の余白にタイトルを置く。", "duration": "20:16", "palette": palettes["magenta_white"]},
        {"source": "ST-520.jpg", "hook": "個別に踏み込め", "title": "PdMの仕事は\nセミオーダー", "subtitle": "", "region": "lower_right", "text_box": [500, 390, 730, 278], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "顔は左上寄り、右下の背景と胴体側へ文字を逃がす。", "duration": "37:23", "palette": palettes["red_yellow"]},
        {"source": "ST-524.jpg", "hook": "フリーPdMの条件", "title": "フリーPdMは\n通用する？", "subtitle": "", "region": "lower_left", "text_box": [40, 500, 760, 170], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "顔は右上なので、左下の暗い服側に強い文字を置く。", "duration": "17:55", "palette": palettes["teal_white"]},
        {"source": "ST-526.jpg", "hook": "逆転できるキャリア", "title": "PdMは\n発信が武器", "subtitle": "", "region": "lower_left", "text_box": [38, 412, 760, 258], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "顔は右上寄り、左下に文字をまとめる。", "duration": "20:16", "palette": palettes["lime_black"]},
        {"source": "ST-529.jpg", "hook": "2人の視点で見る", "title": "PdMの価値は\nどこにある？", "subtitle": "", "region": "bottom", "text_box": [48, 448, 1050, 218], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "2人の顔が上側なので、下の胴体側に横長で置く。", "duration": "37:01", "palette": palettes["magenta_white"]},
        {"source": "ST-530.jpg", "hook": "キャリアは設計できる", "title": "PdMの\nキャリア設計", "subtitle": "", "region": "lower_right", "text_box": [470, 392, 760, 278], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "2人の顔は中央上、右下の空きに主文字を置く。", "duration": "17:55", "palette": palettes["yellow_teal"]},
        {"source": "ST-531.jpg", "hook": "フリーPdMの真相", "title": "稼げるPdMの\n共通点", "subtitle": "", "region": "lower_left", "text_box": [36, 390, 760, 282], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "2人は中央から右なので、左下に文字を寄せる。", "duration": "20:16", "palette": palettes["red_yellow"]},
        {"source": "ST-533.jpg", "hook": "逆転できるキャリア", "title": "PdMキャリアは\n逆転できる", "subtitle": "", "region": "lower_right", "text_box": [500, 390, 730, 278], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "顔が左上寄りなので右下の背景側に大きく置く。", "duration": "37:23", "palette": palettes["teal_white"]},
        {"source": "ST-535.jpg", "hook": "AI時代のPdM", "title": "AI時代も\nPdMは必要", "subtitle": "", "region": "lower_right", "text_box": [500, 386, 730, 284], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "人物は左、右側の青背景をタイトル面として使う。", "duration": "20:16", "palette": palettes["lime_black"]},
        {"source": "ST-536.jpg", "hook": "PdMは燃やす方が安い？", "title": "フリーPdMは\n安売りか？", "subtitle": "", "region": "lower_right", "text_box": [500, 386, 730, 284], "hook_position": "top_left", "logo_position": "top_right", "layout_reason": "顔は左寄り、右下背景に大きいキーワードを置く。", "duration": "17:55", "palette": palettes["red_yellow"]},
        {"source": "ST-538.jpg", "hook": "PdMキャリア", "title": "選ばれるPdMの\n立ち位置", "subtitle": "", "region": "lower_left", "text_box": [40, 390, 760, 282], "hook_position": "top_right", "logo_position": "top_left", "layout_reason": "人物は右寄りなので、左下にタイトルを置く。", "duration": "37:01", "palette": palettes["yellow_teal"]},
    ]
    closeup_sources = [
        "ST-500.jpg",
        "ST-503.jpg",
        "ST-504.jpg",
        "ST-505.jpg",
        "ST-506.jpg",
        "ST-507.jpg",
        "ST-509.jpg",
        "ST-510.jpg",
        "ST-511.jpg",
        "ST-512.jpg",
        "ST-513.jpg",
        "ST-515.jpg",
        "ST-516.jpg",
        "ST-517.jpg",
        "ST-518.jpg",
        "ST-520.jpg",
        "ST-521.jpg",
        "ST-522.jpg",
        "ST-523.jpg",
        "ST-524.jpg",
    ]
    if args.closeup_bottom_title:
        for index, (candidate, source) in enumerate(zip(candidates, closeup_sources), start=1):
            candidate["source"] = source
            candidate["title"] = "フリーPdMは通用する？"
            candidate["hook"] = "AI時代のキャリア論"
            candidate["subtitle"] = ""
            candidate["region"] = "bottom"
            candidate["text_box"] = [8, 548, 1264, 164]
            candidate["logo_position"] = "top_right" if index % 2 else "top_left"
            candidate["closeup"] = True
            candidate["single_line_bottom_title"] = True
            candidate["layout_reason"] = "顔検出位置を中央に寄せて強めにアップで切り出し、一行タイトルを最下部、サブタイトルをロゴの反対側上角に置く。"
    elif args.right_face_title_stack:
        for candidate, source in zip(candidates, closeup_sources):
            candidate["source"] = source
            candidate["title"] = "フリーPdMは\n通用する？"
            candidate["hook"] = "AI時代のキャリア論"
            candidate["subtitle"] = ""
            candidate["region"] = "left"
            candidate["text_box"] = [20, 360, 600, 330]
            candidate["logo_position"] = "top_left"
            candidate["right_face_closeup"] = True
            candidate["left_stacked_title"] = True
            candidate["closeup"] = False
            candidate["single_line_bottom_title"] = False
            candidate["layout_reason"] = "顔を右側に大きく寄せ、左側の余白にサブタイトルと折り返しタイトルを積む。"
    elif args.left_face_title_stack:
        for candidate, source in zip(candidates, closeup_sources):
            candidate["source"] = source
            candidate["title"] = "フリーPdMは\n通用する？"
            candidate["hook"] = "AI時代のキャリア論"
            candidate["subtitle"] = ""
            candidate["region"] = "right"
            candidate["text_box"] = [690, 360, 570, 330]
            candidate["logo_position"] = "top_right"
            candidate["left_face_closeup"] = True
            candidate["right_stacked_title"] = True
            candidate["right_face_closeup"] = False
            candidate["left_stacked_title"] = False
            candidate["closeup"] = False
            candidate["single_line_bottom_title"] = False
            candidate["layout_reason"] = "顔を左側に大きく寄せ、右側の余白にサブタイトルと折り返しタイトルを積む。"
    else:
        for candidate in candidates:
            candidate["title"] = "フリーPdMは\n通用する？"
            candidate["hook"] = "AI時代のキャリア論"
            candidate["subtitle"] = ""
            candidate["closeup"] = False
            candidate["single_line_bottom_title"] = False
            candidate["right_face_closeup"] = False
            candidate["left_face_closeup"] = False
            candidate["left_stacked_title"] = False
            candidate["right_stacked_title"] = False

    for candidate in candidates:
        candidate["palette"] = apply_main_color(candidate["palette"], args.main_color)

    validate_candidate_copy(candidates)
    layouts = []
    for i, candidate in enumerate(candidates, start=1):
        layouts.append(render_candidate(i, candidate, analysis, output_stem, args.debug_faces))
    contact_sheet_path = write_contact_sheet([item["output"] for item in layouts], output_stem)

    title_path = SOURCE_TEXT / "thumbnail_title_pdm_freelance.txt"
    title_path.write_text("フリーPdMは通用する？\n", encoding="utf-8")
    analysis["candidate_layouts"] = layouts
    analysis["thumbnail_mode"] = thumbnail_mode
    analysis["thumbnail_main_color"] = args.main_color
    analysis["contact_sheet"] = str(contact_sheet_path)
    analysis["title_path"] = str(title_path)
    analysis_path = OUTPUT_DIR / f"{output_stem}_asset_analysis.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "analysis": str(analysis_path),
                "title": str(title_path),
                "contact_sheet": str(contact_sheet_path),
                "mode": analysis["thumbnail_mode"],
                "main_color": analysis["thumbnail_main_color"],
                "outputs": [item["output"] for item in layouts],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
