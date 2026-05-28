from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from project_paths import OUTPUT_REPORTS, SOURCE_VIDEO, multicam_source_root, resolve_project_path
from composition_rules import subject_target_for_face


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
PERSON_CLASS_ID = 0


@dataclass
class Track:
    track_id: int
    center: tuple[float, float]
    bbox: tuple[float, float, float, float]
    last_seen_sample: int


class SimpleCentroidTracker:
    def __init__(self, max_missing_samples: int = 3, max_distance_ratio: float = 0.18) -> None:
        self.max_missing_samples = max_missing_samples
        self.max_distance_ratio = max_distance_ratio
        self.next_id = 1
        self.tracks: dict[int, Track] = {}

    def assign(
        self,
        detections: list[dict[str, Any]],
        sample_index: int,
        frame_width: int,
        frame_height: int,
    ) -> list[dict[str, Any]]:
        diagonal = math.hypot(frame_width, frame_height)
        max_distance = diagonal * self.max_distance_ratio
        unmatched_tracks = set(self.tracks)

        for detection in sorted(detections, key=lambda item: item["area_ratio"], reverse=True):
            center = detection["_center_tuple"]
            best_track_id: int | None = None
            best_distance = float("inf")
            for track_id in list(unmatched_tracks):
                track = self.tracks[track_id]
                if sample_index - track.last_seen_sample > self.max_missing_samples:
                    continue
                distance = math.hypot(center[0] - track.center[0], center[1] - track.center[1])
                if distance < best_distance:
                    best_distance = distance
                    best_track_id = track_id

            if best_track_id is None or best_distance > max_distance:
                best_track_id = self.next_id
                self.next_id += 1
            else:
                unmatched_tracks.remove(best_track_id)

            detection["track_id"] = best_track_id
            detection["id"] = best_track_id
            self.tracks[best_track_id] = Track(
                track_id=best_track_id,
                center=center,
                bbox=tuple(detection["_bbox_tuple"]),
                last_seen_sample=sample_index,
            )

        stale_ids = [
            track_id
            for track_id, track in self.tracks.items()
            if sample_index - track.last_seen_sample > self.max_missing_samples
        ]
        for track_id in stale_ids:
            del self.tracks[track_id]

        for detection in detections:
            detection.pop("_center_tuple", None)
            detection.pop("_bbox_tuple", None)
        return detections


def load_face_detectors() -> dict[str, cv2.CascadeClassifier]:
    base = Path(cv2.data.haarcascades)
    return {
        "front": cv2.CascadeClassifier(str(base / "haarcascade_frontalface_default.xml")),
        "profile": cv2.CascadeClassifier(str(base / "haarcascade_profileface.xml")),
        "eye": cv2.CascadeClassifier(str(base / "haarcascade_eye.xml")),
    }


def try_load_yolo(model_name: str) -> Any | None:
    try:
        from ultralytics import YOLO
    except ImportError:
        return None
    return YOLO(model_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sample source videos and write YOLO person bbox metadata JSON for editing decisions."
    )
    parser.add_argument(
        "--input",
        nargs="*",
        default=[],
        help="Video files or directories. Relative paths are resolved from the active project.",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_REPORTS / "person_bboxes")
    parser.add_argument("--model", default="yolov8n.pt", help="Ultralytics YOLO model name or local model path.")
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--fps-sample", type=float, default=1.0, help="Samples per second. 1.0 means one frame per second.")
    parser.add_argument("--start", type=float, default=0.0, help="Start time in seconds.")
    parser.add_argument("--end", type=float, default=None, help="Optional end time in seconds.")
    parser.add_argument("--max-seconds", type=float, default=None, help="Optional cap from --start for quick test runs.")
    parser.add_argument("--device", default=None, help="Optional YOLO device, for example cpu, 0, or cuda:0.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of videos to analyze.")
    parser.add_argument("--max-duration", type=float, default=None, help="Fail if any input video is longer than this many seconds.")
    parser.add_argument("--no-multicam-root", action="store_true", help="Only scan the active project video source when --input is omitted.")
    return parser.parse_args()


def discover_videos(args: argparse.Namespace) -> list[Path]:
    candidates: list[Path] = []
    if args.input:
        roots = [resolve_project_path(value) for value in args.input]
    else:
        roots = [SOURCE_VIDEO]
        root = multicam_source_root()
        if not args.no_multicam_root and root.exists() and root.resolve() != SOURCE_VIDEO.resolve():
            roots.append(root)

    for root in roots:
        if root.is_file() and root.suffix.lower() in VIDEO_EXTENSIONS:
            candidates.append(root)
        elif root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.suffix.lower() in VIDEO_EXTENSIONS)

    unique: list[Path] = []
    seen: set[str] = set()
    for path in sorted(candidates, key=lambda item: str(item).lower()):
        key = str(path.resolve()).lower()
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique[: args.limit] if args.limit else unique


def video_metadata(path: Path) -> dict[str, float | int]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
    return {"width": width, "height": height, "fps": fps, "frame_count": frame_count, "duration": duration}


def frame_at(cap: cv2.VideoCapture, time_seconds: float) -> tuple[bool, Any]:
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_seconds) * 1000.0)
    return cap.read()


def position_label(center_x_ratio: float) -> str:
    if center_x_ratio < 0.38:
        return "left"
    if center_x_ratio > 0.62:
        return "right"
    return "center"


def size_label(area_ratio: float) -> str:
    if area_ratio >= 0.38:
        return "close"
    if area_ratio >= 0.16:
        return "medium"
    return "wide"


def visual_metrics(frame: np.ndarray) -> dict[str, Any]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    bgr = frame.astype(np.float32)
    b_mean, g_mean, r_mean = [float(value) for value in np.mean(bgr, axis=(0, 1))]
    brightness = float(np.mean(gray)) / 255.0
    contrast = float(np.std(gray)) / 255.0
    saturation = float(np.mean(hsv[:, :, 1])) / 255.0
    warmth = (r_mean - b_mean) / max(r_mean + b_mean, 1.0)
    return {
        "brightness": round(brightness, 4),
        "contrast": round(contrast, 4),
        "saturation": round(saturation, 4),
        "warmth": round(warmth, 4),
        "exposure": "bright" if brightness >= 0.62 else "dark" if brightness <= 0.34 else "neutral",
        "color_temperature": "warm" if warmth >= 0.08 else "cool" if warmth <= -0.08 else "neutral",
        "mood": "vivid" if saturation >= 0.42 else "muted" if saturation <= 0.2 else "natural",
    }


def camera_motion_gray(frame: np.ndarray, target_width: int = 320) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] <= target_width:
        return gray
    target_height = max(1, int(gray.shape[0] * target_width / gray.shape[1]))
    return cv2.resize(gray, (target_width, target_height))


def fallback_motion(prev_gray: np.ndarray, gray: np.ndarray, method: str) -> dict[str, Any]:
    diff = float(cv2.absdiff(prev_gray, gray).mean()) / 255.0
    return {
        "method": method,
        "feature_count": 0,
        "inlier_ratio": 0.0,
        "translation_px": 0.0,
        "translation_ratio": 0.0,
        "scale_delta": 0.0,
        "rotation_degrees": 0.0,
        "frame_diff": round(diff, 5),
        "global_motion_score": round(diff * 0.25, 6),
    }


def estimate_camera_motion(prev_gray: np.ndarray | None, gray: np.ndarray) -> dict[str, Any] | None:
    if prev_gray is None:
        return None
    if prev_gray.shape != gray.shape:
        gray = cv2.resize(gray, (prev_gray.shape[1], prev_gray.shape[0]))
    prev_points = cv2.goodFeaturesToTrack(prev_gray, maxCorners=400, qualityLevel=0.01, minDistance=7, blockSize=7)
    if prev_points is None or len(prev_points) < 12:
        return fallback_motion(prev_gray, gray, "frame_diff_fallback")

    next_points, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, prev_points, None)
    if next_points is None or status is None:
        return fallback_motion(prev_gray, gray, "frame_diff_fallback")
    good_prev = prev_points[status.reshape(-1) == 1].reshape(-1, 2)
    good_next = next_points[status.reshape(-1) == 1].reshape(-1, 2)
    if len(good_prev) < 8:
        return fallback_motion(prev_gray, gray, "sparse_flow_fallback")

    matrix, inliers = cv2.estimateAffinePartial2D(
        good_prev,
        good_next,
        method=cv2.RANSAC,
        ransacReprojThreshold=3.0,
        maxIters=2000,
        confidence=0.98,
    )
    if matrix is None:
        return fallback_motion(prev_gray, gray, "affine_fallback")

    a, b, dx = [float(value) for value in matrix[0]]
    c, d, dy = [float(value) for value in matrix[1]]
    frame_diag = max(1.0, math.hypot(prev_gray.shape[1], prev_gray.shape[0]))
    translation_px = math.hypot(dx, dy)
    translation_ratio = translation_px / frame_diag
    scale_x = math.hypot(a, c)
    scale_y = math.hypot(b, d)
    scale_delta = abs(((scale_x + scale_y) / 2) - 1.0)
    rotation_degrees = abs(math.degrees(math.atan2(c, a)))
    frame_diff = float(cv2.absdiff(prev_gray, gray).mean()) / 255.0
    inlier_ratio = float(inliers.sum()) / len(inliers) if inliers is not None and len(inliers) else 0.0
    global_motion_score = translation_ratio + scale_delta * 0.5 + min(rotation_degrees / 180.0, 0.05)
    return {
        "method": "sparse_optical_flow_affine",
        "feature_count": int(len(good_prev)),
        "inlier_ratio": round(inlier_ratio, 4),
        "translation_px": round(translation_px, 4),
        "translation_ratio": round(translation_ratio, 6),
        "scale_delta": round(scale_delta, 6),
        "rotation_degrees": round(rotation_degrees, 4),
        "frame_diff": round(frame_diff, 5),
        "global_motion_score": round(global_motion_score, 6),
    }


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def summarize_camera_motion(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "camera_motion_type": "unknown",
            "is_fixed_camera": None,
            "sample_count": 0,
            "reason": "not enough sampled frames",
        }
    scores = [float(item.get("global_motion_score") or 0.0) for item in samples]
    translations = [float(item.get("translation_ratio") or 0.0) for item in samples]
    frame_diffs = [float(item.get("frame_diff") or 0.0) for item in samples]
    median_score = percentile(scores, 0.5)
    p90_score = percentile(scores, 0.9)
    median_translation = percentile(translations, 0.5)
    p90_translation = percentile(translations, 0.9)
    is_fixed = median_score <= 0.0045 and p90_score <= 0.014 and median_translation <= 0.0035
    return {
        "camera_motion_type": "fixed" if is_fixed else "moving",
        "is_fixed_camera": is_fixed,
        "sample_count": len(samples),
        "median_global_motion_score": round(median_score, 6),
        "p90_global_motion_score": round(p90_score, 6),
        "median_translation_ratio": round(median_translation, 6),
        "p90_translation_ratio": round(p90_translation, 6),
        "avg_frame_diff": round(sum(frame_diffs) / len(frame_diffs), 5) if frame_diffs else 0.0,
    }


def detect_eyes_in_face(
    gray: np.ndarray,
    face: dict[str, Any],
    eye_detector: cv2.CascadeClassifier,
) -> dict[str, Any]:
    height, width = gray.shape[:2]
    fx1, fy1, fx2, fy2 = [float(value) for value in face["bbox"].values()]
    face_width = max(1.0, fx2 - fx1)
    face_height = max(1.0, fy2 - fy1)
    ix1 = max(0, int(round(fx1)))
    iy1 = max(0, int(round(fy1)))
    ix2 = min(width, int(round(fx2)))
    iy2 = min(height, int(round(fy1 + face_height * 0.68)))
    if ix2 <= ix1 or iy2 <= iy1 or eye_detector.empty():
        return {
            "eyes": [],
            "eye_direction": "unknown",
            "eye_offset_from_face_center": {"x": None, "x_ratio": None},
        }

    roi = gray[iy1:iy2, ix1:ix2]
    min_eye_size = (max(10, int(face_width * 0.08)), max(8, int(face_height * 0.06)))
    raw_eyes = eye_detector.detectMultiScale(roi, scaleFactor=1.08, minNeighbors=5, minSize=min_eye_size)
    eyes: list[dict[str, Any]] = []
    for ex, ey, ew, eh in raw_eyes:
        ax1 = float(ix1 + ex)
        ay1 = float(iy1 + ey)
        ax2 = float(ix1 + ex + ew)
        ay2 = float(iy1 + ey + eh)
        center_x = ax1 + ew / 2
        center_y = ay1 + eh / 2
        rel_x = (center_x - fx1) / face_width
        rel_y = (center_y - fy1) / face_height
        if not (0.08 <= rel_x <= 0.92 and 0.12 <= rel_y <= 0.68):
            continue
        eyes.append(
            {
                "bbox": {
                    "x1": round(ax1, 2),
                    "y1": round(ay1, 2),
                    "x2": round(ax2, 2),
                    "y2": round(ay2, 2),
                },
                "center": {"x": round(center_x, 2), "y": round(center_y, 2)},
                "center_ratio_in_face": [round(rel_x, 4), round(rel_y, 4)],
                "area_ratio_in_face": round((ew * eh) / (face_width * face_height), 5),
            }
        )

    unique: list[dict[str, Any]] = []
    for eye in sorted(eyes, key=lambda item: item["area_ratio_in_face"], reverse=True):
        ex1, ey1, ex2, ey2 = eye["bbox"].values()
        duplicate = False
        for existing in unique:
            ox1, oy1, ox2, oy2 = existing["bbox"].values()
            inter_w = max(0.0, min(ex2, ox2) - max(ex1, ox1))
            inter_h = max(0.0, min(ey2, oy2) - max(ey1, oy1))
            inter = inter_w * inter_h
            area = max((ex2 - ex1) * (ey2 - ey1), 1.0)
            if inter / area > 0.45:
                duplicate = True
                break
        if not duplicate:
            unique.append(eye)
        if len(unique) >= 2:
            break

    if not unique:
        return {
            "eyes": [],
            "eye_direction": "unknown",
            "eye_offset_from_face_center": {"x": None, "x_ratio": None},
        }

    eye_center_x = sum(float(eye["center"]["x"]) for eye in unique) / len(unique)
    eye_center_y = sum(float(eye["center"]["y"]) for eye in unique) / len(unique)
    face_center_x = float(face["center"]["x"])
    offset_x = eye_center_x - face_center_x
    offset_ratio = offset_x / face_width
    if offset_ratio <= -0.075:
        eye_direction = "left"
    elif offset_ratio >= 0.075:
        eye_direction = "right"
    else:
        eye_direction = "front"

    return {
        "eyes": unique,
        "eye_center": {"x": round(eye_center_x, 2), "y": round(eye_center_y, 2)},
        "eye_center_ratio_in_face": [
            round((eye_center_x - fx1) / face_width, 4),
            round((eye_center_y - fy1) / face_height, 4),
        ],
        "eye_direction": eye_direction,
        "eye_offset_from_face_center": {"x": round(offset_x, 2), "x_ratio": round(offset_ratio, 4)},
    }


def detect_faces(frame: np.ndarray, detectors: dict[str, cv2.CascadeClassifier]) -> list[dict[str, Any]]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    height, width = gray.shape[:2]
    faces: list[dict[str, Any]] = []

    def add(raw_faces: Any, detector_direction: str, flipped: bool = False) -> None:
        for x, y, w, h in raw_faces:
            if flipped:
                x = width - x - w
            x1, y1, x2, y2 = float(x), float(y), float(x + w), float(y + h)
            center_x = x1 + w / 2
            center_y = y1 + h / 2
            faces.append(
                {
                    "bbox": {
                        "x1": round(x1, 2),
                        "y1": round(y1, 2),
                        "x2": round(x2, 2),
                        "y2": round(y2, 2),
                    },
                    "center": {"x": round(center_x, 2), "y": round(center_y, 2)},
                    "center_ratio": [round(center_x / width, 4), round(center_y / height, 4)],
                    "area_ratio": round((w * h) / (width * height), 5),
                    "detector_direction": detector_direction,
                }
            )

    front = detectors["front"].detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
    profile = detectors["profile"].detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(48, 48))
    flipped_gray = cv2.flip(gray, 1)
    profile_flipped = detectors["profile"].detectMultiScale(flipped_gray, scaleFactor=1.1, minNeighbors=4, minSize=(48, 48))
    add(front, "front")
    add(profile, "profile_original")
    add(profile_flipped, "profile_flipped", flipped=True)

    unique: list[dict[str, Any]] = []
    for face in sorted(faces, key=lambda item: item["area_ratio"], reverse=True):
        fx1, fy1, fx2, fy2 = face["bbox"].values()
        duplicate = False
        for existing in unique:
            ex1, ey1, ex2, ey2 = existing["bbox"].values()
            inter_w = max(0.0, min(fx2, ex2) - max(fx1, ex1))
            inter_h = max(0.0, min(fy2, ey2) - max(fy1, ey1))
            inter = inter_w * inter_h
            area = max((fx2 - fx1) * (fy2 - fy1), 1.0)
            if inter / area > 0.45:
                duplicate = True
                break
        if not duplicate:
            unique.append(face)
    for face in unique:
        face.update(detect_eyes_in_face(gray, face, detectors["eye"]))
    return unique


def face_for_person(person: dict[str, Any], faces: list[dict[str, Any]]) -> dict[str, Any] | None:
    x1, y1, x2, y2 = person["_bbox_tuple"]
    candidates = []
    for face in faces:
        cx, cy = face["center"]["x"], face["center"]["y"]
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            candidates.append(face)
    if candidates:
        return max(candidates, key=lambda item: item["area_ratio"])
    return None


def semantic_face_direction(person: dict[str, Any], face: dict[str, Any] | None) -> str:
    if face is None:
        return "unknown"
    x1, _, x2, _ = person["_bbox_tuple"]
    person_width = max(1.0, x2 - x1)
    person_center_x = x1 + (x2 - x1) / 2
    face_center_x = float(face["center"]["x"])
    face_position_offset = face_center_x - person_center_x
    face_position_offset_ratio = face_position_offset / person_width
    dead_zone = max(person_width * 0.06, 18.0)
    if face_center_x < person_center_x - dead_zone:
        face_position_direction = "left"
    elif face_center_x > person_center_x + dead_zone:
        face_position_direction = "right"
    else:
        face_position_direction = "front"

    eye_direction = str(face.get("eye_direction") or "unknown")
    eye_offset = face.get("eye_offset_from_face_center") if isinstance(face.get("eye_offset_from_face_center"), dict) else {}
    eye_offset_ratio = eye_offset.get("x_ratio")
    try:
        eye_offset_ratio_float = abs(float(eye_offset_ratio))
    except (TypeError, ValueError):
        eye_offset_ratio_float = 0.0

    if eye_direction in {"left", "right"}:
        if face_position_direction in {eye_direction, "front"} or eye_offset_ratio_float >= 0.12:
            direction = eye_direction
        else:
            direction = "unknown"
    elif eye_direction == "front":
        direction = "front" if face_position_direction == "front" or face.get("detector_direction") == "front" else face_position_direction
    elif face.get("detector_direction") == "front":
        direction = "front" if face_position_direction == "front" else face_position_direction
    else:
        direction = face_position_direction if face_position_direction != "front" else "unknown"

    face["direction_evidence"] = {
        "eye_direction": eye_direction,
        "eye_offset_from_face_center_ratio": round(float(eye_offset_ratio), 4)
        if isinstance(eye_offset_ratio, (int, float))
        else eye_offset_ratio,
        "face_position_direction": face_position_direction,
        "face_offset_from_person_center": {
            "x": round(face_position_offset, 2),
            "x_ratio": round(face_position_offset_ratio, 4),
        },
        "resolved_direction": direction,
        "method": "eye_center_vs_face_center_and_face_center_vs_person_center",
    }
    return direction


def look_composition(face_direction: str) -> dict[str, Any]:
    target = subject_target_for_face(face_direction)
    if face_direction == "left":
        return {
            "look_space": "left",
            "desired_subject_x_ratio": round(target.x, 4),
            "desired_subject_y_ratio": round(target.y, 4),
            "composition_anchor": target.anchor,
            "crop_bias": "left",
            "rule": "顔が画面左を向いているため、左の視線余白を広く取り、人物を右側の黄金比アンカーに置く。",
        }
    if face_direction == "right":
        return {
            "look_space": "right",
            "desired_subject_x_ratio": round(target.x, 4),
            "desired_subject_y_ratio": round(target.y, 4),
            "composition_anchor": target.anchor,
            "crop_bias": "right",
            "rule": "顔が画面右を向いているため、右の視線余白を広く取り、人物を左側の黄金比アンカーに置く。",
        }
    return {
        "look_space": "balanced",
        "desired_subject_x_ratio": round(target.x, 4),
        "desired_subject_y_ratio": round(target.y, 4),
        "composition_anchor": target.anchor,
        "crop_bias": "center",
        "rule": "正面または向き不明のため、人物は中央、目線は上側の黄金比ラインを基準にする。",
    }


def extract_persons(result: Any, width: int, height: int) -> list[dict[str, Any]]:
    persons: list[dict[str, Any]] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return persons

    for box in boxes:
        xyxy = box.xyxy[0].tolist()
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = [float(value) for value in xyxy]
        x1 = max(0.0, min(float(width), x1))
        x2 = max(0.0, min(float(width), x2))
        y1 = max(0.0, min(float(height), y1))
        y2 = max(0.0, min(float(height), y2))
        box_width = max(0.0, x2 - x1)
        box_height = max(0.0, y2 - y1)
        center_x = x1 + box_width / 2
        center_y = y1 + box_height / 2
        area_ratio = (box_width * box_height) / (width * height) if width and height else 0.0
        center_x_ratio = center_x / width if width else 0.0
        center_y_ratio = center_y / height if height else 0.0
        persons.append(
            {
                "bbox": {
                    "x1": round(x1, 2),
                    "y1": round(y1, 2),
                    "x2": round(x2, 2),
                    "y2": round(y2, 2),
                },
                "bbox_xyxy": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                "center": {"x": round(center_x, 2), "y": round(center_y, 2)},
                "center_xy": [round(center_x, 2), round(center_y, 2)],
                "center_ratio": [round(center_x_ratio, 4), round(center_y_ratio, 4)],
                "area_ratio": round(area_ratio, 5),
                "confidence": round(confidence, 4),
                "position": position_label(center_x_ratio),
                "shot_size": size_label(area_ratio),
                "_center_tuple": (center_x, center_y),
                "_bbox_tuple": (x1, y1, x2, y2),
            }
        )
    return sorted(persons, key=lambda item: item["area_ratio"], reverse=True)


def persons_from_faces(faces: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
    persons: list[dict[str, Any]] = []
    for face in faces:
        fx1, fy1, fx2, fy2 = [float(value) for value in face["bbox"].values()]
        face_width = max(1.0, fx2 - fx1)
        face_height = max(1.0, fy2 - fy1)
        face_center_x = fx1 + face_width / 2
        x1 = max(0.0, face_center_x - face_width * 1.35)
        x2 = min(float(width), face_center_x + face_width * 1.35)
        y1 = max(0.0, fy1 - face_height * 0.85)
        y2 = min(float(height), fy2 + face_height * 3.4)
        box_width = max(0.0, x2 - x1)
        box_height = max(0.0, y2 - y1)
        center_x = x1 + box_width / 2
        center_y = y1 + box_height / 2
        area_ratio = (box_width * box_height) / (width * height) if width and height else 0.0
        center_x_ratio = center_x / width if width else 0.0
        center_y_ratio = center_y / height if height else 0.0
        persons.append(
            {
                "bbox": {
                    "x1": round(x1, 2),
                    "y1": round(y1, 2),
                    "x2": round(x2, 2),
                    "y2": round(y2, 2),
                },
                "bbox_xyxy": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)],
                "center": {"x": round(center_x, 2), "y": round(center_y, 2)},
                "center_xy": [round(center_x, 2), round(center_y, 2)],
                "center_ratio": [round(center_x_ratio, 4), round(center_y_ratio, 4)],
                "area_ratio": round(area_ratio, 5),
                "confidence": round(min(0.95, float(face.get("area_ratio", 0.0)) * 8 + 0.35), 4),
                "position": position_label(center_x_ratio),
                "shot_size": size_label(area_ratio),
                "detector": "opencv_face_fallback",
                "_center_tuple": (center_x, center_y),
                "_bbox_tuple": (x1, y1, x2, y2),
            }
        )
    return sorted(persons, key=lambda item: item["area_ratio"], reverse=True)


def summarize_frames(frames: list[dict[str, Any]], camera_motion: dict[str, Any]) -> dict[str, Any]:
    sampled = len(frames)
    present = [frame for frame in frames if frame["persons"]]
    counts = [len(frame["persons"]) for frame in frames]
    main_persons = [frame["persons"][0] for frame in present]
    visuals = [frame.get("visual", {}) for frame in frames]
    face_directions = [
        person.get("face_direction")
        for frame in frames
        for person in frame.get("persons", [])
        if person.get("face_direction")
    ]
    summary = {
        "sampled_frames": sampled,
        "person_present_frames": len(present),
        "person_present_ratio": round(len(present) / sampled, 4) if sampled else 0.0,
        "max_person_count": max(counts) if counts else 0,
        "avg_person_count": round(sum(counts) / sampled, 3) if sampled else 0.0,
        "avg_main_area_ratio": round(sum(person["area_ratio"] for person in main_persons) / len(main_persons), 5)
        if main_persons
        else 0.0,
        "avg_brightness": round(sum(item.get("brightness", 0.0) for item in visuals) / sampled, 4) if sampled else 0.0,
        "avg_contrast": round(sum(item.get("contrast", 0.0) for item in visuals) / sampled, 4) if sampled else 0.0,
        "avg_saturation": round(sum(item.get("saturation", 0.0) for item in visuals) / sampled, 4) if sampled else 0.0,
        "avg_warmth": round(sum(item.get("warmth", 0.0) for item in visuals) / sampled, 4) if sampled else 0.0,
        "face_direction_counts": {direction: face_directions.count(direction) for direction in sorted(set(face_directions))},
    }
    summary["camera_motion"] = camera_motion
    summary["camera_motion_type"] = camera_motion.get("camera_motion_type")
    summary["is_fixed_camera"] = camera_motion.get("is_fixed_camera")
    return summary


def output_path_for(video: Path, output_dir: Path) -> Path:
    try:
        rel = video.relative_to(SOURCE_VIDEO)
    except ValueError:
        root = multicam_source_root()
        try:
            rel = video.relative_to(root)
        except ValueError:
            rel = video.name
    stem = "_".join(Path(rel).with_suffix("").parts) if isinstance(rel, Path) else Path(str(rel)).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_")
    return output_dir / f"{safe_stem}_person_bboxes.json"


def analyze_video(video: Path, model: Any | None, args: argparse.Namespace) -> Path:
    metadata = video_metadata(video)
    width = int(metadata["width"])
    height = int(metadata["height"])
    source_fps = float(metadata["fps"])
    duration = float(metadata["duration"])
    if args.max_duration is not None and duration > args.max_duration + 0.25:
        raise RuntimeError(f"{video} is {duration:.2f}s; expected <= {args.max_duration:.2f}s.")
    end = duration if args.end is None else min(float(args.end), duration)
    if args.max_seconds is not None:
        end = min(end, args.start + args.max_seconds)
    interval = 1.0 / args.fps_sample
    if interval <= 0:
        raise ValueError("--fps-sample must be greater than 0")

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")

    tracker = SimpleCentroidTracker()
    face_detectors = load_face_detectors()
    frames: list[dict[str, Any]] = []
    motion_samples: list[dict[str, Any]] = []
    prev_motion_gray: np.ndarray | None = None
    sample_index = 0
    time_seconds = max(0.0, float(args.start))
    while time_seconds <= end + 1e-6:
        ok, frame = frame_at(cap, time_seconds)
        if not ok or frame is None:
            break
        motion_gray = camera_motion_gray(frame)
        camera_motion_from_previous = estimate_camera_motion(prev_motion_gray, motion_gray)
        prev_motion_gray = motion_gray
        if camera_motion_from_previous is not None:
            motion_samples.append(camera_motion_from_previous)
        faces = detect_faces(frame, face_detectors)
        if model is not None:
            yolo_kwargs: dict[str, Any] = {"classes": [PERSON_CLASS_ID], "conf": args.confidence, "verbose": False}
            if args.device:
                yolo_kwargs["device"] = args.device
            results = model(frame, **yolo_kwargs)
            persons = extract_persons(results[0], width, height) if results else []
        else:
            persons = persons_from_faces(faces, width, height)
        for person in persons:
            face = face_for_person(person, faces)
            face_direction = semantic_face_direction(person, face)
            person["face"] = face
            person["face_direction"] = face_direction
            person["look_composition"] = look_composition(face_direction)
        persons = tracker.assign(persons, sample_index, width, height)
        frame_index = round(time_seconds * source_fps) if source_fps else sample_index
        frames.append(
            {
                "time": round(time_seconds, 3),
                "frame_index": int(frame_index),
                "width": width,
                "height": height,
                "visual": visual_metrics(frame),
                "camera_motion_from_previous": camera_motion_from_previous,
                "faces": faces,
                "person_count": len(persons),
                "persons": persons,
            }
        )
        sample_index += 1
        time_seconds = args.start + sample_index * interval

    cap.release()
    camera_motion = summarize_camera_motion(motion_samples)
    payload = {
        "schema_version": "person-bboxes/v1",
        "video": video.name,
        "video_path": str(video),
        "model": str(args.model) if model is not None else "opencv-face-fallback",
        "detector_backend": "ultralytics-yolo" if model is not None else "opencv-face-fallback",
        "confidence_threshold": args.confidence,
        "fps_sample": args.fps_sample,
        "sample_interval": round(interval, 4),
        "width": width,
        "height": height,
        "source_fps": round(source_fps, 4),
        "source_frame_count": int(metadata["frame_count"]),
        "duration": round(duration, 3),
        "analysis_range": {"start": round(float(args.start), 3), "end": round(end, 3)},
        "camera_motion": camera_motion,
        "summary": summarize_frames(frames, camera_motion),
        "frames": frames,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = output_path_for(video, args.output_dir)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main() -> None:
    args = parse_args()
    videos = discover_videos(args)
    if not videos:
        raise SystemExit("No source videos found.")

    model = try_load_yolo(args.model)
    if model is None:
        print(
            "ultralytics is not installed; using OpenCV face fallback for person edit metadata.",
            file=sys.stderr,
        )
    outputs = []
    for index, video in enumerate(videos, start=1):
        print(f"[{index}/{len(videos)}] analyzing {video}", file=sys.stderr)
        outputs.append(str(analyze_video(video, model, args)))
    print(json.dumps({"outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
