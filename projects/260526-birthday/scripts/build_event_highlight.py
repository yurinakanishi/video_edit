from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_FPS = 30
VIDEO_ANALYSIS_VERSION = "video-v2-stable-people"
IMAGE_ANALYSIS_VERSION = "image-v2-subject-square"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ffmpeg_expr_float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def safe_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "asset"


def run_json(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"command failed: {command}")
    return json.loads(completed.stdout or "{}")


def probe_video(path: Path, ffprobe: Path) -> dict[str, Any]:
    payload = run_json(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration:format_tags=creation_time:stream=codec_type,width,height,avg_frame_rate,codec_name",
            "-of",
            "json",
            str(path),
        ]
    )
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    tags = fmt.get("tags") if isinstance(fmt.get("tags"), dict) else {}
    return {
        "duration": float(fmt.get("duration") or 0.0),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": str(video.get("avg_frame_rate") or ""),
        "videoCodec": str(video.get("codec_name") or ""),
        "hasAudio": audio is not None,
        "creationTime": str(tags.get("creation_time") or ""),
    }


def probe_duration(path: Path, ffprobe: Path) -> float:
    payload = run_json(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    return float(fmt.get("duration") or 0.0)


def image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        transposed = ImageOps.exif_transpose(image)
        return int(transposed.width), int(transposed.height)


def open_image_bgr(path: Path, max_width: int | None = None) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if max_width and image.width > max_width:
            height = max(1, round(image.height * max_width / image.width))
            image = image.resize((max_width, height), Image.Resampling.LANCZOS)
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def normalize_image(path: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0 and output.stat().st_mtime >= path.stat().st_mtime:
        return output
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.save(output, quality=94, optimize=True)
    return output


def image_phash(path: Path) -> int:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("L").resize((32, 32), Image.Resampling.LANCZOS)
        pixels = np.asarray(image, dtype=np.float32)
    dct = cv2.dct(pixels)
    low = dct[:8, :8].copy()
    values = low.flatten()
    median = float(np.median(values[1:])) if values.size > 1 else float(np.median(values))
    bits = values > median
    result = 0
    for bit in bits:
        result = (result << 1) | int(bool(bit))
    return result


def hamming_distance(left: int, right: int) -> int:
    return int((left ^ right).bit_count())


def load_face_detectors() -> dict[str, cv2.CascadeClassifier]:
    base = Path(cv2.data.haarcascades)
    return {
        "front": cv2.CascadeClassifier(str(base / "haarcascade_frontalface_default.xml")),
        "profile": cv2.CascadeClassifier(str(base / "haarcascade_profileface.xml")),
    }


def overlap_ratio(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    area = min((ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1))
    return intersection / area if area > 0 else 0.0


def detect_faces(frame: np.ndarray, detectors: dict[str, cv2.CascadeClassifier]) -> list[dict[str, Any]]:
    height, width = frame.shape[:2]
    scale = 1.0
    working = frame
    if width > 960:
        scale = 960.0 / width
        working = cv2.resize(frame, (960, max(1, round(height * scale))))
    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    min_size = (max(32, round(working.shape[1] * 0.035)), max(32, round(working.shape[0] * 0.035)))
    raw: list[tuple[int, int, int, int]] = []
    for x, y, w, h in detectors["front"].detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=min_size):
        raw.append((int(x), int(y), int(w), int(h)))
    for x, y, w, h in detectors["profile"].detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=min_size):
        raw.append((int(x), int(y), int(w), int(h)))
    flipped = cv2.flip(gray, 1)
    for x, y, w, h in detectors["profile"].detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=4, minSize=min_size):
        raw.append((int(working.shape[1] - x - w), int(y), int(w), int(h)))

    faces: list[dict[str, Any]] = []
    inv = 1.0 / scale
    for x, y, w, h in sorted(raw, key=lambda item: item[2] * item[3], reverse=True):
        box = (x * inv, y * inv, (x + w) * inv, (y + h) * inv)
        if any(overlap_ratio(box, tuple(face["bbox_xyxy"])) > 0.45 for face in faces):
            continue
        x1, y1, x2, y2 = box
        area_ratio = ((x2 - x1) * (y2 - y1)) / max(width * height, 1)
        faces.append(
            {
                "bbox": {"x1": round(x1, 2), "y1": round(y1, 2), "x2": round(x2, 2), "y2": round(y2, 2)},
                "bbox_xyxy": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                "center_ratio": [round(((x1 + x2) / 2) / width, 4), round(((y1 + y2) / 2) / height, 4)],
                "area_ratio": round(area_ratio, 5),
            }
        )
    return faces


def visual_metrics(frame: np.ndarray) -> dict[str, float]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    bgr = frame.astype(np.float32)
    b_mean, _, r_mean = [float(value) for value in np.mean(bgr, axis=(0, 1))]
    brightness = float(np.mean(gray)) / 255.0
    saturation = float(np.mean(hsv[:, :, 1])) / 255.0
    contrast = float(np.std(gray)) / 255.0
    warmth = (r_mean - b_mean) / max(r_mean + b_mean, 1.0)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()
    return {
        "brightness": round(brightness, 5),
        "saturation": round(saturation, 5),
        "contrast": round(contrast, 5),
        "warmth": round(warmth, 5),
        "sharpness": round(float(laplacian), 3),
    }


def focus_from_edges(frame: np.ndarray) -> tuple[float, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] > 640:
        gray = cv2.resize(gray, (640, max(1, round(gray.shape[0] * 640 / gray.shape[1]))))
    edges = cv2.Laplacian(gray, cv2.CV_32F)
    weights = np.abs(edges)
    threshold = np.percentile(weights, 75)
    weights = np.where(weights >= threshold, weights, 0)
    total = float(np.sum(weights))
    if total <= 1e-3:
        return 0.5, 0.5
    ys, xs = np.indices(weights.shape)
    return float(np.sum(xs * weights) / total / max(weights.shape[1] - 1, 1)), float(
        np.sum(ys * weights) / total / max(weights.shape[0] - 1, 1)
    )


def read_video_frame(cap: cv2.VideoCapture, time_seconds: float) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_seconds) * 1000.0)
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    return frame


def gray_for_motion(frame: np.ndarray, width: int = 480) -> np.ndarray:
    height = max(1, round(frame.shape[0] * width / frame.shape[1]))
    return cv2.cvtColor(cv2.resize(frame, (width, height)), cv2.COLOR_BGR2GRAY)


def frame_difference_motion(left: np.ndarray, right: np.ndarray) -> float:
    left_gray = gray_for_motion(left, width=320)
    right_gray = gray_for_motion(right, width=320)
    if left_gray.shape != right_gray.shape:
        return 0.0
    return float(np.mean(cv2.absdiff(left_gray, right_gray))) / 255.0


def estimate_camera_motion(left: np.ndarray, right: np.ndarray) -> float:
    left_gray = gray_for_motion(left)
    right_gray = gray_for_motion(right)
    if left_gray.shape != right_gray.shape:
        return 0.0

    points = cv2.goodFeaturesToTrack(
        left_gray,
        maxCorners=220,
        qualityLevel=0.01,
        minDistance=8,
        blockSize=7,
    )
    if points is None or len(points) < 8:
        return round(frame_difference_motion(left, right) * 0.55, 5)

    next_points, status, _ = cv2.calcOpticalFlowPyrLK(left_gray, right_gray, points, None)
    if next_points is None or status is None:
        return round(frame_difference_motion(left, right) * 0.55, 5)

    valid = status.reshape(-1) == 1
    original = points.reshape(-1, 2)[valid]
    tracked = next_points.reshape(-1, 2)[valid]
    if len(original) < 8:
        return round(frame_difference_motion(left, right) * 0.55, 5)

    flow = tracked - original
    median_flow = np.median(flow, axis=0)
    residual = flow - median_flow
    diagonal = math.hypot(left_gray.shape[1], left_gray.shape[0])
    translation = float(np.linalg.norm(median_flow)) / max(diagonal, 1.0)
    residual_p75 = float(np.percentile(np.linalg.norm(residual, axis=1), 75)) / max(diagonal, 1.0)
    return round(translation + residual_p75 * 0.65, 5)


def group_focus(faces: list[dict[str, Any]], fallback: tuple[float, float]) -> dict[str, Any]:
    if not faces:
        return {
            "faceCount": 0,
            "center": [round(fallback[0], 4), round(fallback[1], 4)],
            "cropCenter": [round(clamp(fallback[0], 0.15, 0.85), 4), round(clamp(fallback[1], 0.25, 0.72), 4)],
            "positions": [],
            "groupBox": None,
        }
    x1 = min(float(face["bbox"]["x1"]) for face in faces)
    y1 = min(float(face["bbox"]["y1"]) for face in faces)
    x2 = max(float(face["bbox"]["x2"]) for face in faces)
    y2 = max(float(face["bbox"]["y2"]) for face in faces)
    centers = [face["center_ratio"] for face in faces]
    center_x = sum(float(center[0]) for center in centers) / len(centers)
    center_y = sum(float(center[1]) for center in centers) / len(centers)
    positions = ["left" if x < 0.38 else "right" if x > 0.62 else "center" for x, _ in centers]
    return {
        "faceCount": len(faces),
        "center": [round(center_x, 4), round(center_y, 4)],
        "cropCenter": [round(clamp(center_x, 0.12, 0.88), 4), round(clamp(center_y + 0.12, 0.28, 0.72), 4)],
        "positions": positions,
        "groupBox": {"x1": round(x1, 2), "y1": round(y1, 2), "x2": round(x2, 2), "y2": round(y2, 2)},
    }


def clamp_box(box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    x1 = clamp(x1, 0.0, float(width))
    y1 = clamp(y1, 0.0, float(height))
    x2 = clamp(x2, 0.0, float(width))
    y2 = clamp(y2, 0.0, float(height))
    if x2 <= x1:
        x1, x2 = 0.0, float(width)
    if y2 <= y1:
        y1, y2 = 0.0, float(height)
    return x1, y1, x2, y2


def square_around_box(box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = clamp_box(box, width, height)
    box_width = max(1.0, x2 - x1)
    box_height = max(1.0, y2 - y1)
    side = min(max(box_width, box_height), float(width), float(height))
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    left = clamp(center_x - side / 2.0, 0.0, max(0.0, width - side))
    top = clamp(center_y - side / 2.0, 0.0, max(0.0, height - side))
    return left, top, left + side, top + side


def box_to_payload(box: tuple[float, float, float, float], width: int, height: int) -> dict[str, Any]:
    x1, y1, x2, y2 = box
    return {
        "x1": round(x1, 2),
        "y1": round(y1, 2),
        "x2": round(x2, 2),
        "y2": round(y2, 2),
        "center": [round(((x1 + x2) / 2.0) / max(width, 1), 4), round(((y1 + y2) / 2.0) / max(height, 1), 4)],
    }


def edge_subject_box(frame: np.ndarray) -> tuple[float, float, float, float] | None:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    if int(np.count_nonzero(edges)) < 40:
        return None
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    height, width = frame.shape[:2]
    image_area = float(width * height)
    scored: list[tuple[float, tuple[float, float, float, float]]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = float(w * h)
        if area < image_area * 0.01:
            continue
        cx = (x + w / 2.0) / max(width, 1)
        cy = (y + h / 2.0) / max(height, 1)
        center_bias = 1.0 - min(math.hypot(cx - 0.5, cy - 0.5) / 0.72, 1.0)
        scored.append((area / image_area + center_bias * 0.25, (float(x), float(y), float(x + w), float(y + h))))
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]


def image_subject_analysis(frame: np.ndarray, faces: list[dict[str, Any]], fallback: tuple[float, float]) -> dict[str, Any]:
    height, width = frame.shape[:2]
    if faces:
        x1 = min(float(face["bbox"]["x1"]) for face in faces)
        y1 = min(float(face["bbox"]["y1"]) for face in faces)
        x2 = max(float(face["bbox"]["x2"]) for face in faces)
        y2 = max(float(face["bbox"]["y2"]) for face in faces)
        box_width = max(1.0, x2 - x1)
        box_height = max(1.0, y2 - y1)
        padded = (
            x1 - box_width * 0.75,
            y1 - box_height * 0.85,
            x2 + box_width * 0.75,
            y2 + box_height * 1.15,
        )
        source = "faces"
    else:
        edge_box = edge_subject_box(frame)
        if edge_box:
            x1, y1, x2, y2 = edge_box
            box_width = max(1.0, x2 - x1)
            box_height = max(1.0, y2 - y1)
            padded = (
                x1 - box_width * 0.20,
                y1 - box_height * 0.20,
                x2 + box_width * 0.20,
                y2 + box_height * 0.20,
            )
            source = "edges"
        else:
            center_x = fallback[0] * width
            center_y = fallback[1] * height
            side = min(width, height) * 0.65
            padded = (center_x - side / 2.0, center_y - side / 2.0, center_x + side / 2.0, center_y + side / 2.0)
            source = "fallback"
    subject_box = clamp_box(padded, width, height)
    subject_square = square_around_box(subject_box, width, height)
    center = box_to_payload(subject_square, width, height)["center"]
    return {
        "source": source,
        "subjectBox": box_to_payload(subject_box, width, height),
        "subjectSquare": box_to_payload(subject_square, width, height),
        "cropCenter": center,
    }


def score_frame(metrics: dict[str, float], faces: list[dict[str, Any]], motion: float) -> float:
    brightness_score = 1.0 - min(abs(metrics["brightness"] - 0.50) / 0.50, 1.0)
    saturation_score = min(metrics["saturation"] / 0.36, 1.0)
    sharpness_score = min(metrics["sharpness"] / 900.0, 1.0)
    face_score = min(len(faces), 5) / 5.0
    face_area = min(sum(float(face["area_ratio"]) for face in faces) / 0.12, 1.0)
    motion_score = min(motion / 0.18, 1.0)
    return round(
        0.22 * brightness_score
        + 0.15 * saturation_score
        + 0.20 * sharpness_score
        + 0.24 * face_score
        + 0.12 * face_area
        + 0.07 * motion_score,
        5,
    )


def score_video_sample(
    metrics: dict[str, float],
    faces: list[dict[str, Any]],
    scene_motion: float,
    camera_motion: float,
) -> float:
    brightness_score = 1.0 - min(abs(metrics["brightness"] - 0.50) / 0.50, 1.0)
    saturation_score = min(metrics["saturation"] / 0.36, 1.0)
    sharpness_score = min(metrics["sharpness"] / 900.0, 1.0)
    face_count = len(faces)
    people_score = min(face_count, 7) / 7.0
    face_area = min(sum(float(face["area_ratio"]) for face in faces) / 0.14, 1.0)
    camera_stability = 1.0 - min(camera_motion / 0.045, 1.0)
    scene_stability = 1.0 - min(scene_motion / 0.20, 1.0)
    return round(
        0.34 * people_score
        + 0.17 * face_area
        + 0.20 * camera_stability
        + 0.08 * scene_stability
        + 0.11 * sharpness_score
        + 0.06 * brightness_score
        + 0.04 * saturation_score,
        5,
    )


@dataclass
class MediaItem:
    kind: str
    path: Path
    relative: str
    width: int
    height: int
    duration: float = 0.0
    has_audio: bool = False
    analysis: dict[str, Any] = field(default_factory=dict)
    clip_duration: float = 0.0
    clip_frames: int = 0
    source_in: float = 0.0
    source_out: float = 0.0
    timeline_start: float = 0.0
    timeline_end: float = 0.0


def video_sample_times(duration: float, max_samples: int) -> list[float]:
    if duration <= 0:
        return [0.0]
    safe_start = 0.5 if duration > 1.0 else 0.0
    safe_end = max(safe_start, duration - 0.5)
    count = max(3, min(max_samples, int(math.ceil(duration / 3.0))))
    if safe_end <= safe_start:
        return [duration / 2]
    return [float(value) for value in np.linspace(safe_start, safe_end, count)]


def analyze_video(item: MediaItem, detectors: dict[str, cv2.CascadeClassifier], max_samples: int) -> None:
    cap = cv2.VideoCapture(str(item.path))
    if not cap.isOpened():
        item.analysis = {"error": "could not open video", "cropCenter": [0.5, 0.5], "score": 0.0}
        return
    samples: list[dict[str, Any]] = []
    for time_seconds in video_sample_times(item.duration, max_samples):
        frame = read_video_frame(cap, time_seconds)
        if frame is None:
            continue
        comparison_time = min(item.duration - 0.05, time_seconds + 0.35)
        if comparison_time <= time_seconds:
            comparison_time = max(0.0, time_seconds - 0.35)
        comparison_frame = read_video_frame(cap, comparison_time) if comparison_time != time_seconds else None
        metrics = visual_metrics(frame)
        motion = frame_difference_motion(frame, comparison_frame) if comparison_frame is not None else 0.0
        camera_motion = estimate_camera_motion(frame, comparison_frame) if comparison_frame is not None else 0.0
        faces = detect_faces(frame, detectors)
        fallback = focus_from_edges(frame)
        focus = group_focus(faces, fallback)
        score = score_video_sample(metrics, faces, motion, camera_motion)
        samples.append(
            {
                "time": round(time_seconds, 3),
                "score": score,
                "motion": round(motion, 5),
                "cameraMotion": round(camera_motion, 5),
                "visual": metrics,
                "faces": faces,
                "focus": focus,
            }
        )
    cap.release()
    if not samples:
        item.analysis = {"error": "no readable samples", "cropCenter": [0.5, 0.5], "score": 0.0, "samples": []}
        return
    best = max(samples, key=lambda sample: sample["score"])
    face_counts = [sample["focus"]["faceCount"] for sample in samples]
    camera_motions = [float(sample.get("cameraMotion") or 0.0) for sample in samples]
    item.analysis = {
        "analysisVersion": VIDEO_ANALYSIS_VERSION,
        "score": best["score"],
        "selectedSampleTime": best["time"],
        "cropCenter": best["focus"]["cropCenter"],
        "cameraMotionAtSelection": best.get("cameraMotion", 0.0),
        "personRelation": {
            "faceCountAtSelection": best["focus"]["faceCount"],
            "maxFaceCount": max(face_counts) if face_counts else 0,
            "positionsAtSelection": best["focus"]["positions"],
            "groupBoxAtSelection": best["focus"]["groupBox"],
        },
        "visualAtSelection": best["visual"],
        "sampleCount": len(samples),
        "sampleSummary": {
            "avgBrightness": round(sum(sample["visual"]["brightness"] for sample in samples) / len(samples), 5),
            "avgSaturation": round(sum(sample["visual"]["saturation"] for sample in samples) / len(samples), 5),
            "avgWarmth": round(sum(sample["visual"]["warmth"] for sample in samples) / len(samples), 5),
            "avgFaceCount": round(sum(face_counts) / len(face_counts), 3) if face_counts else 0.0,
            "avgCameraMotion": round(sum(camera_motions) / len(camera_motions), 5) if camera_motions else 0.0,
            "maxCameraMotion": round(max(camera_motions), 5) if camera_motions else 0.0,
        },
        "topSamples": sorted(samples, key=lambda sample: sample["score"], reverse=True)[:6],
    }


def analyze_image(item: MediaItem, detectors: dict[str, cv2.CascadeClassifier]) -> None:
    frame = open_image_bgr(item.path, max_width=1400)
    faces = detect_faces(frame, detectors)
    fallback = focus_from_edges(frame)
    focus = group_focus(faces, fallback)
    subject = image_subject_analysis(frame, faces, fallback)
    metrics = visual_metrics(frame)
    item.analysis = {
        "analysisVersion": IMAGE_ANALYSIS_VERSION,
        "score": score_frame(metrics, faces, 0.0),
        "cropCenter": subject["cropCenter"],
        "subject": subject,
        "personRelation": {
            "faceCount": focus["faceCount"],
            "positions": focus["positions"],
            "groupBox": focus["groupBox"],
        },
        "visual": metrics,
    }


def discover_media(project_root: Path, ffprobe: Path) -> tuple[list[MediaItem], list[MediaItem]]:
    source_root = project_root / "source"
    videos: list[MediaItem] = []
    images: list[MediaItem] = []
    for path in sorted(source_root.rglob("*"), key=lambda item: natural_key(str(item.relative_to(source_root)))):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        relative = str(path.relative_to(source_root))
        if suffix in VIDEO_EXTENSIONS:
            metadata = probe_video(path, ffprobe)
            if metadata["duration"] <= 0 or metadata["width"] <= 0 or metadata["height"] <= 0:
                continue
            videos.append(
                MediaItem(
                    kind="video",
                    path=path,
                    relative=relative,
                    width=metadata["width"],
                    height=metadata["height"],
                    duration=metadata["duration"],
                    has_audio=bool(metadata["hasAudio"]),
                    analysis={"probe": metadata},
                )
            )
        elif suffix in IMAGE_EXTENSIONS:
            try:
                width, height = image_dimensions(path)
            except Exception:
                continue
            images.append(MediaItem(kind="image", path=path, relative=relative, width=width, height=height, duration=0.0))
    return videos, images


def image_selection_score(item: MediaItem) -> float:
    analysis = item.analysis if isinstance(item.analysis, dict) else {}
    visual = analysis.get("visual") if isinstance(analysis.get("visual"), dict) else {}
    relation = analysis.get("personRelation") if isinstance(analysis.get("personRelation"), dict) else {}
    brightness = float(visual.get("brightness") or 0.5)
    saturation = float(visual.get("saturation") or 0.0)
    sharpness = float(visual.get("sharpness") or 0.0)
    face_count = int(relation.get("faceCount") or 0)
    brightness_score = 1.0 - min(abs(brightness - 0.52) / 0.52, 1.0)
    return (
        float(analysis.get("score") or 0.0)
        + min(face_count, 5) * 0.08
        + min(sharpness / 1000.0, 1.0) * 0.22
        + brightness_score * 0.12
        + min(saturation / 0.42, 1.0) * 0.08
    )


def select_best_images(images: list[MediaItem], hash_distance: int, max_images: int | None = None) -> tuple[list[MediaItem], dict[str, Any]]:
    for image in images:
        try:
            image.analysis["perceptualHash"] = f"{image_phash(image.path):016x}"
        except Exception as error:
            image.analysis["perceptualHashError"] = str(error)

    groups: list[list[MediaItem]] = []
    group_hashes: list[int] = []
    for image in sorted(images, key=lambda item: natural_key(item.relative)):
        hash_text = image.analysis.get("perceptualHash")
        hash_value = int(hash_text, 16) if isinstance(hash_text, str) and re.fullmatch(r"[0-9a-fA-F]+", hash_text) else None
        matched_index: int | None = None
        if hash_value is not None:
            best_distance = 999
            for index, existing_hash in enumerate(group_hashes):
                distance = hamming_distance(hash_value, existing_hash)
                if distance <= hash_distance and distance < best_distance:
                    matched_index = index
                    best_distance = distance
        if matched_index is None:
            groups.append([image])
            group_hashes.append(hash_value if hash_value is not None else 0)
        else:
            groups[matched_index].append(image)

    selected: list[MediaItem] = []
    omitted: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups, start=1):
        winner = max(group, key=image_selection_score)
        winner.analysis["duplicateGroup"] = {
            "groupId": group_index,
            "groupSize": len(group),
            "selected": True,
            "score": round(image_selection_score(winner), 5),
        }
        selected.append(winner)
        for image in group:
            if image is winner:
                continue
            image.analysis["duplicateGroup"] = {
                "groupId": group_index,
                "groupSize": len(group),
                "selected": False,
                "selectedPath": str(winner.path),
                "score": round(image_selection_score(image), 5),
            }
            omitted.append(
                {
                    "path": str(image.path),
                    "relative": image.relative,
                    "selectedPath": str(winner.path),
                    "groupId": group_index,
                    "groupSize": len(group),
                }
            )
    selected.sort(key=lambda item: natural_key(item.relative))
    if max_images is not None and len(selected) > max_images:
        keep = set(selected[:max_images])
        for image in selected[max_images:]:
            omitted.append(
                {
                    "path": str(image.path),
                    "relative": image.relative,
                    "selectedPath": "",
                    "groupId": image.analysis.get("duplicateGroup", {}).get("groupId"),
                    "groupSize": image.analysis.get("duplicateGroup", {}).get("groupSize"),
                    "reason": "trimmed-to-fit-target",
                }
            )
        selected = selected[:max_images]
    report = {
        "inputImages": len(images),
        "selectedImages": len(selected),
        "omittedImages": len(omitted),
        "hashDistance": hash_distance,
        "groups": [
            {
                "groupId": index,
                "size": len(group),
                "selected": str(max(group, key=image_selection_score).path),
                "members": [str(item.path) for item in group],
            }
            for index, group in enumerate(groups, start=1)
        ],
        "omitted": omitted,
    }
    return selected, report


def load_analysis_cache(*report_paths: Path) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for report_path in report_paths:
        if not report_path.exists():
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in payload.get("media", []):
            if not isinstance(item, dict) or not item.get("path") or not isinstance(item.get("analysis"), dict):
                continue
            path = str(Path(str(item["path"])).resolve()).lower()
            cache[path] = dict(item["analysis"])
    return cache


def apply_analysis_cache(items: list[MediaItem], cache: dict[str, dict[str, Any]]) -> int:
    applied = 0
    for item in items:
        cached = cache.get(str(item.path.resolve()).lower())
        if not cached:
            continue
        probe = item.analysis.get("probe") if isinstance(item.analysis, dict) else None
        item.analysis = dict(cached)
        if probe and "probe" not in item.analysis:
            item.analysis["probe"] = probe
        applied += 1
    return applied


def audio_candidates(source_root: Path) -> list[Path]:
    preferred = source_root / "audio"
    roots = [preferred] if preferred.exists() else []
    roots.append(source_root)
    seen: set[Path] = set()
    candidates: list[Path] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(path)
    return candidates


def find_background_audio(project_root: Path, ffprobe: Path, target_seconds: float) -> Path | None:
    source_root = project_root / "source"
    candidates: list[tuple[float, float, Path]] = []
    for path in audio_candidates(source_root):
        try:
            duration = probe_duration(path, ffprobe)
        except Exception:
            continue
        if duration <= 0:
            continue
        is_source_audio = 0.0 if (source_root / "audio") in path.resolve().parents else 10000.0
        name_bonus = -20.0 if re.search(r"(bgm|music|birthday|15min)", path.name, re.IGNORECASE) else 0.0
        candidates.append((is_source_audio + abs(duration - target_seconds) + name_bonus, duration, path))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -item[1], natural_key(str(item[2]))))
    return candidates[0][2]


def resolve_background_audio(value: str | None, project_root: Path, ffprobe: Path, target_seconds: float) -> Path | None:
    if not value:
        return None
    if value.lower() == "auto":
        return find_background_audio(project_root, ffprobe, target_seconds)
    candidate = Path(value)
    if not candidate.is_absolute():
        direct = project_root / candidate
        source_relative = project_root / "source" / candidate
        candidate = direct if direct.exists() else source_relative
    return candidate.resolve() if candidate.exists() else None


def allocate_durations(videos: list[MediaItem], images: list[MediaItem], target_seconds: float, base_image_seconds: float) -> None:
    target_frames = max(1, int(round(target_seconds * TARGET_FPS)))
    image_frames = max(1, int(math.floor(base_image_seconds * TARGET_FPS + 0.5)))
    if videos:
        while image_frames > 1 and target_frames - image_frames * len(images) < len(videos):
            image_frames -= 1
        remaining_video_frames = max(len(videos), target_frames - image_frames * len(images))
        base_video_frames = max(1, remaining_video_frames // len(videos))
        extra_video_frames = max(0, remaining_video_frames - base_video_frames * len(videos))
    else:
        base_video_frames = 0
        extra_video_frames = 0

    for image in images:
        image.clip_frames = image_frames
        image.clip_duration = round(image.clip_frames / TARGET_FPS, 6)
    for index, video in enumerate(videos):
        requested_frames = base_video_frames + (1 if index < extra_video_frames else 0)
        available_frames = max(1, int(math.floor(video.duration * TARGET_FPS)))
        video.clip_frames = max(1, min(available_frames, requested_frames))
        video.clip_duration = round(video.clip_frames / TARGET_FPS, 6)

    image_total_frames = image_frames * len(images)
    unallocated_frames = max(0, target_frames - image_total_frames - sum(video.clip_frames for video in videos))
    while unallocated_frames > 0:
        expandable = [
            (video, max(1, int(math.floor(video.duration * TARGET_FPS))) - video.clip_frames)
            for video in videos
            if max(1, int(math.floor(video.duration * TARGET_FPS))) > video.clip_frames
        ]
        if not expandable:
            break
        per_video = max(1, math.ceil(unallocated_frames / len(expandable)))
        for video, capacity in expandable:
            add_frames = min(capacity, per_video, unallocated_frames)
            video.clip_frames += add_frames
            video.clip_duration = round(video.clip_frames / TARGET_FPS, 6)
            unallocated_frames -= add_frames
            if unallocated_frames <= 0:
                break

    for video in videos:
        selected = float(video.analysis.get("selectedSampleTime") or video.duration / 2)
        half = video.clip_duration / 2
        start = clamp(selected - half, 0.0, max(0.0, video.duration - video.clip_duration))
        video.source_in = round(start, 6)
        video.source_out = round(min(video.duration, start + video.clip_duration), 6)
        video.clip_duration = round(video.clip_frames / TARGET_FPS, 6)
    for image in images:
        image.source_in = 0.0
        image.source_out = image.clip_duration


def interleave_media(videos: list[MediaItem], images: list[MediaItem]) -> list[MediaItem]:
    sequence: list[MediaItem] = []
    image_index = 0
    for index, video in enumerate(videos, start=1):
        sequence.append(video)
        target_image_count = round(index * len(images) / len(videos)) if videos else len(images)
        while image_index < target_image_count and image_index < len(images):
            sequence.append(images[image_index])
            image_index += 1
    sequence.extend(images[image_index:])
    time_cursor_frames = 0
    for item in sequence:
        if item.clip_frames <= 0:
            item.clip_frames = max(1, int(math.floor(item.clip_duration * TARGET_FPS + 0.5)))
            item.clip_duration = round(item.clip_frames / TARGET_FPS, 6)
        item.timeline_start = round(time_cursor_frames / TARGET_FPS, 6)
        time_cursor_frames += item.clip_frames
        item.timeline_end = round(time_cursor_frames / TARGET_FPS, 6)
    return sequence


def look_filter(item: MediaItem) -> str:
    visual = item.analysis.get("visualAtSelection") or item.analysis.get("visual") or item.analysis.get("sampleSummary") or {}
    brightness = float(visual.get("brightness") or visual.get("avgBrightness") or 0.50)
    saturation = float(visual.get("saturation") or visual.get("avgSaturation") or 0.32)
    warmth = float(visual.get("warmth") or visual.get("avgWarmth") or 0.0)
    brightness_offset = clamp((0.50 - brightness) * 0.12, -0.035, 0.035)
    saturation_value = clamp(0.88 + (0.32 - saturation) * 0.22, 0.78, 1.02)
    red_shadow = clamp(0.018 - warmth * 0.035, -0.012, 0.03)
    blue_shadow = clamp(-0.014 - warmth * 0.02, -0.03, 0.006)
    return (
        f"eq=contrast=0.92:saturation={saturation_value:.4f}:brightness={brightness_offset:.5f}:gamma=1.035,"
        f"colorbalance=rs={red_shadow:.5f}:gs=0.004:bs={blue_shadow:.5f}"
    )


def crop_expr(center: list[float]) -> tuple[str, str]:
    cx = ffmpeg_expr_float(float(center[0]))
    cy = ffmpeg_expr_float(float(center[1]))
    return (
        f"min(max(iw*{cx}-ow/2\\,0)\\,iw-ow)",
        f"min(max(ih*{cy}-oh/2\\,0)\\,ih-oh)",
    )


def video_filter(item: MediaItem, width: int, height: int, fps: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"{look_filter(item)},fps={fps},setsar=1,format=yuv420p"
    )


def continuous_progress(value: float) -> float:
    return clamp(value, 0.0, 1.0)


def image_motion_centers(item: MediaItem, sequence_index: int) -> tuple[tuple[float, float], tuple[float, float]]:
    center = item.analysis.get("cropCenter") if isinstance(item.analysis, dict) else None
    if not isinstance(center, list) or len(center) < 2:
        center = [0.5, 0.5]
    cx = clamp(float(center[0]), 0.12, 0.88)
    cy = clamp(float(center[1]), 0.25, 0.75)
    return (cx, cy), (cx, cy)


def render_ken_burns_frame(
    image: np.ndarray,
    *,
    width: int,
    height: int,
    progress: float,
    start_center: tuple[float, float],
    end_center: tuple[float, float],
    motion_mode: str,
) -> np.ndarray:
    source_height, source_width = image.shape[:2]
    target_aspect = width / height
    source_aspect = source_width / max(source_height, 1)
    if source_aspect >= target_aspect:
        base_view_height = float(source_height)
        base_view_width = base_view_height * target_aspect
    else:
        base_view_width = float(source_width)
        base_view_height = base_view_width / target_aspect

    continuous = continuous_progress(progress)
    if motion_mode == "zoom-in":
        zoom = 1.0 + 0.032 * continuous
    elif motion_mode == "zoom-out":
        zoom = 1.032 - 0.032 * continuous
    else:
        zoom = 1.0
    view_width = min(float(source_width), base_view_width / zoom)
    view_height = min(float(source_height), base_view_height / zoom)
    center_x_ratio = start_center[0] + (end_center[0] - start_center[0]) * continuous
    center_y_ratio = start_center[1] + (end_center[1] - start_center[1]) * continuous
    center_x = clamp(center_x_ratio * source_width, view_width / 2.0, source_width - view_width / 2.0)
    center_y = clamp(center_y_ratio * source_height, view_height / 2.0, source_height - view_height / 2.0)
    left = center_x - view_width / 2.0
    top = center_y - view_height / 2.0
    scale_x = width / view_width
    scale_y = height / view_height
    matrix = np.array([[scale_x, 0.0, -left * scale_x], [0.0, scale_y, -top * scale_y]], dtype=np.float32)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def render_image_segment_smooth(
    index: int,
    item: MediaItem,
    output: Path,
    ffmpeg: Path,
    logs_dir: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, item.clip_frames or int(math.floor(item.clip_duration * fps + 0.5)))
    duration = total_frames / fps
    start_center, end_center = image_motion_centers(item, index)
    motion_mode = "zoom-in" if index % 2 == 0 else "zoom-out"
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-f",
        "lavfi",
        "-t",
        f"{duration:.6f}",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-filter_complex",
        f"[0:v]{look_filter(item)},format=yuv420p[v];[1:a]atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[a]",
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-map_metadata",
        "-1",
        "-write_tmcd",
        "0",
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-shortest",
        str(output),
    ]

    log_path = logs_dir / f"{output.stem}.log"
    image = open_image_bgr(item.path)
    completed_stdout = ""
    completed_stderr = ""
    return_code = 0
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        assert proc.stdin is not None
        for frame_index in range(total_frames):
            progress = frame_index / max(total_frames - 1, 1)
            frame = render_ken_burns_frame(
                image,
                width=width,
                height=height,
                progress=progress,
                start_center=start_center,
                end_center=end_center,
                motion_mode=motion_mode,
            )
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        stdout_bytes = proc.stdout.read() if proc.stdout is not None else b""
        stderr_bytes = proc.stderr.read() if proc.stderr is not None else b""
        proc.wait()
        return_code = int(proc.returncode or 0)
        completed_stdout = stdout_bytes.decode("utf-8", errors="replace")
        completed_stderr = stderr_bytes.decode("utf-8", errors="replace")
    except BrokenPipeError:
        return_code = 1
        completed_stderr = "ffmpeg pipe closed while writing image frames"
    finally:
        log_path.write_text(
            json.dumps(
                {
                    "command": command,
                    "returnCode": return_code,
                    "frames": total_frames,
                    "duration": duration,
                    "startCenter": start_center,
                    "endCenter": end_center,
                    "motionMode": motion_mode,
                    "progressCurve": "linear",
                    "zoomStart": 1.032 if motion_mode == "zoom-out" else 1.0,
                    "zoomEnd": 1.0 if motion_mode == "zoom-out" else 1.032,
                    "subject": item.analysis.get("subject") if isinstance(item.analysis, dict) else {},
                    "stdout": completed_stdout[-8000:],
                    "stderr": completed_stderr[-12000:],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if return_code:
        raise RuntimeError(f"smooth image segment render failed: {output} (see {log_path})")
    return {"index": index, "path": str(output), "status": "rendered", "log": str(log_path), "renderer": "opencv-subpixel"}


def segment_output_path(segments_dir: Path, index: int, item: MediaItem) -> Path:
    return segments_dir / f"segment_{index:04d}_{item.kind}_{safe_stem(Path(item.relative).stem)[:60]}.mp4"


def remove_matching_files(directory: Path, patterns: list[str]) -> int:
    if not directory.exists():
        return 0
    removed = 0
    for pattern in patterns:
        for path in directory.glob(pattern):
            if not path.is_file():
                continue
            path.unlink()
            removed += 1
    return removed


def cleanup_force_render_outputs(segments_dir: Path, groups_dir: Path, logs_dir: Path) -> dict[str, int]:
    return {
        "segments": remove_matching_files(segments_dir, ["segment_*.mp4"]),
        "groups": remove_matching_files(groups_dir, ["*.mp4", "*.txt", "*.log"]),
        "logs": remove_matching_files(logs_dir, ["segment_*.log"]),
    }


def render_segment(
    index: int,
    item: MediaItem,
    output: Path,
    ffmpeg: Path,
    logs_dir: Path,
    normalized_images_dir: Path,
    *,
    width: int,
    height: int,
    fps: int,
    force: bool,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0 and not force:
        return {"index": index, "path": str(output), "status": "reused"}

    if item.kind == "image":
        return render_image_segment_smooth(
            index,
            item,
            output,
            ffmpeg,
            logs_dir,
            width=width,
            height=height,
            fps=fps,
        )

    duration = max(0.1, (item.clip_frames or int(math.floor(item.clip_duration * fps + 0.5))) / fps)
    if item.kind != "video":
        raise ValueError(f"Unsupported media kind: {item.kind}")

    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-ss",
        f"{item.source_in:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(item.path),
    ]
    audio_input = 0
    if not item.has_audio:
        command.extend(["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        audio_input = 1
    audio_chain = (
        f"[{audio_input}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,volume=0.96[a]"
    )
    filter_complex = f"[0:v]{video_filter(item, width, height, fps)}[v];{audio_chain}"

    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-map_metadata",
            "-1",
            "-write_tmcd",
            "0",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            str(output),
        ]
    )

    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log_path = logs_dir / f"{output.stem}.log"
    log_path.write_text(
        json.dumps(
            {
                "command": command,
                "returnCode": completed.returncode,
                "stdout": completed.stdout[-8000:],
                "stderr": completed.stderr[-12000:],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(f"segment render failed: {output} (see {log_path})")
    return {"index": index, "path": str(output), "status": "rendered", "log": str(log_path)}


def write_concat_file(paths: list[Path], concat_path: Path) -> None:
    concat_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for path in paths:
        text = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{text}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concat_segments(ffmpeg: Path, concat_file: Path, output: Path, force: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0 and not force:
        return
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-map_metadata",
        "-1",
        "-write_tmcd",
        "0",
        "-vf",
        f"fps={TARGET_FPS},setpts=N/({TARGET_FPS}*TB),format=yuv420p",
        "-af",
        "aresample=48000:async=1:first_pts=0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"concat failed: {output}")


def concat_segments_exact(
    ffmpeg: Path,
    segment_paths: list[Path],
    sequence: list[MediaItem],
    groups_dir: Path,
    output: Path,
    force: bool,
    *,
    group_size: int = 25,
) -> list[Path]:
    output.parent.mkdir(parents=True, exist_ok=True)
    groups_dir.mkdir(parents=True, exist_ok=True)
    group_paths: list[Path] = []
    for group_index, start in enumerate(range(0, len(segment_paths), group_size), start=1):
        chunk_paths = segment_paths[start : start + group_size]
        chunk_items = sequence[start : start + group_size]
        group_output = groups_dir / f"birthday_highlight_group_{group_index:02d}.mp4"
        group_paths.append(group_output)
        if group_output.exists() and group_output.stat().st_size > 0 and not force:
            continue

        inputs: list[str] = []
        pre_filters: list[str] = []
        concat_inputs: list[str] = []
        for input_index, (path, item) in enumerate(zip(chunk_paths, chunk_items)):
            inputs.extend(["-i", str(path)])
            frames = max(1, item.clip_frames or int(math.floor(item.clip_duration * TARGET_FPS + 0.5)))
            duration = frames / TARGET_FPS
            pre_filters.append(f"[{input_index}:v:0]trim=end_frame={frames},setpts=PTS-STARTPTS[v{input_index}]")
            pre_filters.append(
                f"[{input_index}:a:0]atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[a{input_index}]"
            )
            concat_inputs.append(f"[v{input_index}][a{input_index}]")
        filter_complex = (
            ";".join(pre_filters)
            + ";"
            + "".join(concat_inputs)
            + f"concat=n={len(chunk_paths)}:v=1:a=1[vc][ac];"
            + f"[vc]fps={TARGET_FPS},setpts=N/({TARGET_FPS}*TB),format=yuv420p[v];"
            + "[ac]aresample=48000:async=1:first_pts=0[a]"
        )
        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-map_metadata",
            "-1",
            "-write_tmcd",
            "0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(group_output),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode:
            log_path = groups_dir / f"{group_output.stem}.error.log"
            log_path.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
            raise RuntimeError(f"group concat failed: {group_output} (see {log_path})")

    groups_concat = groups_dir / "groups.concat.txt"
    groups_concat.write_text("".join(f"file '{path.resolve().as_posix()}'\n" for path in group_paths), encoding="utf-8")
    temporary_output = output.with_name(f"{output.stem}.groups{output.suffix}")
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(groups_concat),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-map_metadata",
        "-1",
        "-write_tmcd",
        "0",
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(temporary_output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        log_path = groups_dir / "final_concat.error.log"
        log_path.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        raise RuntimeError(f"final group concat failed (see {log_path})")
    temporary_output.replace(output)
    return group_paths


def mix_background_music(
    ffmpeg: Path,
    input_video: Path,
    music_path: Path,
    output: Path,
    duration: float,
    *,
    original_volume: float,
    music_volume: float,
    force: bool,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0 and not force:
        return
    temporary_output = output.with_name(f"{output.stem}.mixing{output.suffix}")
    fade_out_start = max(0.0, duration - 1.8)
    filter_complex = (
        "[0:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"atrim=duration={duration:.9f},asetpts=PTS-STARTPTS,volume={original_volume:.4f}[orig];"
        "[1:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"atrim=duration={duration:.9f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_start:.6f}:d=1.8,"
        f"volume={music_volume:.4f}[music];"
        "[orig][music]amix=inputs=2:duration=first:dropout_transition=2,"
        "alimiter=limit=0.95[a]"
    )
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(input_video),
        "-stream_loop",
        "-1",
        "-i",
        str(music_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-map_metadata",
        "-1",
        "-write_tmcd",
        "0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(temporary_output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        log_path = output.with_suffix(".mix-error.log")
        log_path.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        raise RuntimeError(f"background music mix failed (see {log_path})")
    temporary_output.replace(output)


def write_timeline_report(
    project_root: Path,
    output: Path,
    sequence: list[MediaItem],
    final_path: Path,
    concat_file: Path,
    segment_results: list[dict[str, Any]],
    selection_report_path: Path | None = None,
    background_audio: dict[str, Any] | None = None,
) -> None:
    payload = {
        "createdAt": now_iso(),
        "projectRoot": str(project_root),
        "output": str(final_path),
        "duration": round(sequence[-1].timeline_end if sequence else 0.0, 3),
        "target": {"width": TARGET_WIDTH, "height": TARGET_HEIGHT, "fps": TARGET_FPS},
        "concatFile": str(concat_file),
        "selectionReport": str(selection_report_path) if selection_report_path else "",
        "backgroundAudio": background_audio or {},
        "segmentResults": segment_results,
        "media": [
            {
                "index": index,
                "kind": item.kind,
                "path": str(item.path),
                "relative": item.relative,
                "width": item.width,
                "height": item.height,
                "sourceDuration": round(item.duration, 3),
                "hasAudio": item.has_audio,
                "timelineStart": item.timeline_start,
                "timelineEnd": item.timeline_end,
                "sourceIn": item.source_in,
                "sourceOut": item.source_out,
                "clipDuration": item.clip_duration,
                "clipFrames": item.clip_frames,
                "analysis": item.analysis,
            }
            for index, item in enumerate(sequence, start=1)
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an event highlight from project videos and still images.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--target-seconds", type=float, default=900.0)
    parser.add_argument("--base-image-seconds", type=float, default=4.0)
    parser.add_argument("--video-max-samples", type=int, default=70)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--ffmpeg", type=Path, default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
    parser.add_argument("--ffprobe", type=Path, default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
    parser.add_argument("--preview", action="store_true", help="Render a lightweight 960x540 preview instead of the full-size output.")
    parser.add_argument("--dedupe-images", action="store_true", help="Group visually similar still images and keep the best one from each group.")
    parser.add_argument("--image-hash-distance", type=int, default=8, help="Perceptual-hash distance used for still-image duplicate grouping.")
    parser.add_argument("--background-audio", type=str, default=None, help="Background music path, or 'auto' to pick the best source/audio file.")
    parser.add_argument("--music-volume", type=float, default=0.24)
    parser.add_argument("--original-volume", type=float, default=0.50)
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--replan-from-report", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    global TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS
    args = parse_args()
    if args.preview:
        TARGET_WIDTH = 960
        TARGET_HEIGHT = 540
        TARGET_FPS = 24
    project_root = args.project_root.resolve()
    output_root = project_root / "output"
    run_name = "birthday_preview" if args.preview else "birthday_highlight"
    reports_dir = output_root / "reports" / run_name
    videos_dir = output_root / "videos"
    segments_dir = output_root / "segments" / run_name
    groups_dir = output_root / "segments" / f"{run_name}_groups"
    logs_dir = reports_dir / "segment_logs"
    normalized_images_dir = output_root / "images" / f"{run_name}_normalized"
    report_path = reports_dir / f"{run_name}_timeline.json"
    final_path = videos_dir / ("260526-birthday-preview.mp4" if args.preview else "260526-birthday-highlight-15min.mp4")
    concat_file = reports_dir / f"{run_name}.concat.txt"
    selection_report_path = reports_dir / f"{run_name}_image_selection.json"
    cache_report_path = output_root / "reports" / "birthday_highlight" / "birthday_highlight_timeline.json"
    background_audio_path = resolve_background_audio(args.background_audio, project_root, args.ffprobe, args.target_seconds)
    background_audio_report = (
        {
            "path": str(background_audio_path),
            "duration": round(probe_duration(background_audio_path, args.ffprobe), 3),
            "musicVolume": args.music_volume,
            "originalVolume": args.original_volume,
        }
        if background_audio_path
        else None
    )

    if args.render_only and report_path.exists():
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        sequence = []
        for entry in payload.get("media", []):
            path = Path(entry["path"])
            if not path.exists():
                continue
            item = MediaItem(
                kind=entry["kind"],
                path=path,
                relative=entry["relative"],
                width=int(entry["width"]),
                height=int(entry["height"]),
                duration=float(entry.get("sourceDuration") or 0),
                has_audio=bool(entry.get("hasAudio")),
                analysis=entry.get("analysis") or {},
                clip_duration=float(entry.get("clipDuration") or 0),
                clip_frames=int(entry.get("clipFrames") or max(1, math.floor(float(entry.get("clipDuration") or 0) * TARGET_FPS + 0.5))),
                source_in=float(entry.get("sourceIn") or 0),
                source_out=float(entry.get("sourceOut") or entry.get("clipDuration") or 0),
                timeline_start=float(entry.get("timelineStart") or 0),
                timeline_end=float(entry.get("timelineEnd") or 0),
            )
            sequence.append(item)
        if args.replan_from_report:
            videos = [item for item in sequence if item.kind == "video"]
            images = [item for item in sequence if item.kind == "image"]
            if args.dedupe_images:
                images, selection_report = select_best_images(images, args.image_hash_distance)
                selection_report_path.parent.mkdir(parents=True, exist_ok=True)
                selection_report_path.write_text(json.dumps(selection_report, ensure_ascii=False, indent=2), encoding="utf-8")
            allocate_durations(videos, images, args.target_seconds, args.base_image_seconds)
            sequence = interleave_media(videos, images)
            write_timeline_report(
                project_root,
                report_path,
                sequence,
                final_path,
                concat_file,
                [],
                selection_report_path if args.dedupe_images else None,
                background_audio_report,
            )
    else:
        detectors = load_face_detectors()
        videos, images = discover_media(project_root, args.ffprobe)
        if not videos and not images:
            raise SystemExit("No videos or images found in project source.")
        analysis_cache = load_analysis_cache(report_path, cache_report_path)
        cached_videos = apply_analysis_cache(videos, analysis_cache)
        cached_images = apply_analysis_cache(images, analysis_cache)
        print(f"[analysis cache] videos={cached_videos}/{len(videos)} images={cached_images}/{len(images)}", flush=True)
        for index, video in enumerate(videos, start=1):
            if video.analysis.get("analysisVersion") == VIDEO_ANALYSIS_VERSION and "selectedSampleTime" in video.analysis:
                continue
            print(f"[analysis video {index}/{len(videos)}] {video.relative}", flush=True)
            analyze_video(video, detectors, args.video_max_samples)
        for index, image in enumerate(images, start=1):
            if image.analysis.get("analysisVersion") == IMAGE_ANALYSIS_VERSION and "visual" in image.analysis:
                continue
            print(f"[analysis image {index}/{len(images)}] {image.relative}", flush=True)
            analyze_image(image, detectors)
        if args.dedupe_images:
            images, selection_report = select_best_images(images, args.image_hash_distance)
            selection_report_path.parent.mkdir(parents=True, exist_ok=True)
            selection_report_path.write_text(json.dumps(selection_report, ensure_ascii=False, indent=2), encoding="utf-8")
        allocate_durations(videos, images, args.target_seconds, args.base_image_seconds)
        sequence = interleave_media(videos, images)
        write_timeline_report(
            project_root,
            report_path,
            sequence,
            final_path,
            concat_file,
            [],
            selection_report_path if args.dedupe_images else None,
            background_audio_report,
        )

    if args.analyze_only:
        print(json.dumps({"report": str(report_path), "mediaCount": len(sequence)}, ensure_ascii=False, indent=2))
        return

    cleanup_result: dict[str, int] | None = None
    if args.force:
        cleanup_result = cleanup_force_render_outputs(segments_dir, groups_dir, logs_dir)
        print(f"[cleanup] {cleanup_result}", flush=True)

    planned_paths = [segment_output_path(segments_dir, index, item) for index, item in enumerate(sequence, start=1)]
    results: list[dict[str, Any]] = []
    if cleanup_result is not None:
        results.append({"index": 0, "kind": "cleanup", "removed": cleanup_result})
    jobs = max(1, int(args.jobs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        future_map = {
            executor.submit(
                render_segment,
                index,
                item,
                planned_paths[index - 1],
                args.ffmpeg,
                logs_dir,
                normalized_images_dir,
                width=TARGET_WIDTH,
                height=TARGET_HEIGHT,
                fps=TARGET_FPS,
                force=args.force,
            ): index
            for index, item in enumerate(sequence, start=1)
        }
        for future in concurrent.futures.as_completed(future_map):
            result = future.result()
            results.append(result)
            print(f"[segment {result['index']}/{len(sequence)}] {result['status']} {Path(result['path']).name}", flush=True)

    results.sort(key=lambda item: item["index"])
    write_concat_file(planned_paths, concat_file)
    concat_output_path = (
        final_path.with_name(f"{final_path.stem}_without_bgm{final_path.suffix}") if background_audio_path else final_path
    )
    group_paths = concat_segments_exact(args.ffmpeg, planned_paths, sequence, groups_dir, concat_output_path, args.force)
    results.append({"index": len(results) + 1, "kind": "group-concat", "groups": [str(path) for path in group_paths]})
    if background_audio_path:
        mix_background_music(
            args.ffmpeg,
            concat_output_path,
            background_audio_path,
            final_path,
            sequence[-1].timeline_end if sequence else args.target_seconds,
            original_volume=args.original_volume,
            music_volume=args.music_volume,
            force=args.force,
        )
        results.append({"index": len(results) + 1, "kind": "background-audio", "path": str(background_audio_path)})
    write_timeline_report(
        project_root,
        report_path,
        sequence,
        final_path,
        concat_file,
        results,
        selection_report_path if args.dedupe_images else None,
        background_audio_report,
    )
    print(
        json.dumps(
            {
                "output": str(final_path),
                "report": str(report_path),
                "segments": len(planned_paths),
                "duration": round(sequence[-1].timeline_end if sequence else 0.0, 3),
                "backgroundAudio": str(background_audio_path) if background_audio_path else "",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
