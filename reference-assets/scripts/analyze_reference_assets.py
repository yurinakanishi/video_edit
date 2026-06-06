from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import shutil
import subprocess
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


LIBRARY_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = LIBRARY_ROOT / "config" / "analysis_settings.json"
MANIFEST_PATH = LIBRARY_ROOT / "output" / "reports" / "reference_assets_manifest.json"
REPORTS_ROOT = LIBRARY_ROOT / "output" / "reports"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def int_value(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def hex_color(rgb: tuple[int, int, int] | list[int] | np.ndarray) -> str:
    r, g, b = [int(clamp(float(v), 0, 255)) for v in list(rgb)[:3]]
    return f"#{r:02X}{g:02X}{b:02X}"


def bbox_payload_xyxy(x1: float, y1: float, x2: float, y2: float, width: int, height: int) -> dict[str, Any]:
    left = max(0.0, min(float(x1), float(x2)))
    top = max(0.0, min(float(y1), float(y2)))
    right = min(float(width), max(float(x1), float(x2)))
    bottom = min(float(height), max(float(y1), float(y2)))
    box_width = max(0.0, right - left)
    box_height = max(0.0, bottom - top)
    return {
        "pixel": [round(left, 2), round(top, 2), round(box_width, 2), round(box_height, 2)],
        "norm": [
            round(clamp(left / max(width, 1)), 5),
            round(clamp(top / max(height, 1)), 5),
            round(clamp(box_width / max(width, 1)), 5),
            round(clamp(box_height / max(height, 1)), 5),
        ],
        "xyxyPixel": [round(left, 2), round(top, 2), round(right, 2), round(bottom, 2)],
    }


def bbox_center_norm(bbox: dict[str, Any]) -> list[float]:
    x, y, w, h = bbox["norm"]
    return [round(x + w / 2, 5), round(y + h / 2, 5)]


def bbox_area_norm(bbox: dict[str, Any]) -> float:
    return round(float(bbox["norm"][2]) * float(bbox["norm"][3]), 6)


def expanded_pixel_bbox(bbox: dict[str, Any], width: int, height: int, pad_ratio: float = 0.14) -> tuple[int, int, int, int]:
    x, y, w, h = bbox["pixel"]
    pad_x = max(3.0, float(w) * pad_ratio)
    pad_y = max(3.0, float(h) * pad_ratio)
    x1 = int(max(0, math.floor(float(x) - pad_x)))
    y1 = int(max(0, math.floor(float(y) - pad_y)))
    x2 = int(min(width, math.ceil(float(x) + float(w) + pad_x)))
    y2 = int(min(height, math.ceil(float(y) + float(h) + pad_y)))
    return x1, y1, x2, y2


def dominant_colors(rgb: np.ndarray, count: int = 5) -> list[dict[str, Any]]:
    if rgb.size == 0:
        return []
    small = cv2.resize(rgb, (min(160, rgb.shape[1]), max(1, int(rgb.shape[0] * min(160, rgb.shape[1]) / max(rgb.shape[1], 1)))))
    pixels = small.reshape((-1, 3)).astype(np.float32)
    if len(pixels) < count:
        values, counts = np.unique(pixels.astype(np.uint8), axis=0, return_counts=True)
        order = np.argsort(-counts)
        return [{"hex": hex_color(values[i]), "ratio": round(float(counts[i]) / len(pixels), 4)} for i in order[:count]]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 0.3)
    compactness, labels, centers = cv2.kmeans(pixels, count, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    del compactness
    label_counts = Counter(int(label[0]) for label in labels)
    total = max(1, len(labels))
    colors = []
    for label, amount in label_counts.most_common(count):
        colors.append({"hex": hex_color(centers[label]), "ratio": round(amount / total, 4)})
    return colors


def visual_style(rgb: np.ndarray) -> dict[str, Any]:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    channels = rgb.astype(np.float32)
    r_mean, g_mean, b_mean = [float(v) for v in np.mean(channels, axis=(0, 1))]
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
        "colorTemperature": "warm" if warmth >= 0.08 else "cool" if warmth <= -0.08 else "neutral",
        "dominantColors": dominant_colors(rgb, 5),
    }


def load_yolo(settings: dict[str, Any], disabled: bool) -> tuple[Any | None, dict[str, Any]]:
    if disabled:
        return None, {"available": False, "reason": "disabled"}
    if importlib.util.find_spec("ultralytics") is None:
        return None, {"available": False, "reason": "ultralytics is not installed"}
    try:
        from ultralytics import YOLO

        model_name = str(settings.get("analysis", {}).get("yoloModel") or "yolov8n.pt")
        model = YOLO(model_name)
        return model, {"available": True, "model": model_name, "backend": "ultralytics"}
    except Exception as error:  # pragma: no cover - depends on external model cache
        return None, {"available": False, "reason": str(error)}


def load_easyocr(settings: dict[str, Any], disabled: bool) -> tuple[Any | None, dict[str, Any]]:
    if disabled:
        return None, {"available": False, "reason": "disabled"}
    if importlib.util.find_spec("easyocr") is None:
        return None, {"available": False, "reason": "easyocr is not installed"}
    try:
        import easyocr

        languages = settings.get("analysis", {}).get("easyOcrLanguages") or ["ja", "en"]
        reader = easyocr.Reader([str(item) for item in languages], gpu=False, verbose=False)
        return reader, {"available": True, "languages": languages, "backend": "easyocr"}
    except Exception as error:  # pragma: no cover - depends on external model cache
        return None, {"available": False, "reason": str(error)}


def ensure_download(path: Path, url: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)


def load_face_mesh(settings: dict[str, Any], disabled: bool) -> tuple[Any | None, dict[str, Any]]:
    if disabled:
        return None, {"available": False, "reason": "disabled"}
    if importlib.util.find_spec("mediapipe") is None:
        return None, {"available": False, "reason": "mediapipe is not installed"}
    try:
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision

        analysis_settings = settings.get("analysis", {}) if isinstance(settings.get("analysis"), dict) else {}
        model_path = Path(str(analysis_settings.get("faceLandmarkerModel") or ""))
        model_url = str(analysis_settings.get("faceLandmarkerModelUrl") or "")
        if model_path and model_url:
            ensure_download(model_path, model_url)
        if not model_path.exists():
            return None, {"available": False, "reason": f"face landmarker model is missing: {model_path}"}
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            num_faces=8,
            min_face_detection_confidence=0.45,
            min_face_presence_confidence=0.45,
            min_tracking_confidence=0.45,
        )
        landmarker = vision.FaceLandmarker.create_from_options(options)
        return landmarker, {"available": True, "backend": "mediapipe-face-landmarker", "model": str(model_path)}
    except Exception as error:  # pragma: no cover - depends on mediapipe runtime
        return None, {"available": False, "reason": str(error)}


def haar_face_detectors() -> dict[str, cv2.CascadeClassifier]:
    base = Path(cv2.data.haarcascades)
    return {
        "front": cv2.CascadeClassifier(str(base / "haarcascade_frontalface_default.xml")),
        "profile": cv2.CascadeClassifier(str(base / "haarcascade_profileface.xml")),
    }


def detect_people(rgb: np.ndarray, yolo_model: Any | None, confidence: float) -> list[dict[str, Any]]:
    if yolo_model is None:
        return []
    height, width = rgb.shape[:2]
    try:
        results = yolo_model.predict(rgb, conf=confidence, verbose=False, device="cpu")
    except Exception:
        return []
    people = []
    if not results:
        return people
    boxes = getattr(results[0], "boxes", None)
    if boxes is None:
        return people
    for raw in boxes:
        cls = int(raw.cls[0]) if getattr(raw, "cls", None) is not None else -1
        if cls != 0:
            continue
        x1, y1, x2, y2 = [float(v) for v in raw.xyxy[0].tolist()]
        bbox = bbox_payload_xyxy(x1, y1, x2, y2, width, height)
        people.append(
            {
                "id": f"person-{len(people) + 1:02d}",
                "bbox": bbox,
                "centerNorm": bbox_center_norm(bbox),
                "areaRatio": bbox_area_norm(bbox),
                "confidence": round(float(raw.conf[0]) if getattr(raw, "conf", None) is not None else 0.0, 4),
                "detector": "ultralytics-yolo",
            }
        )
    return sorted(people, key=lambda item: item["areaRatio"], reverse=True)


def detect_faces_mediapipe(rgb: np.ndarray, face_mesh: Any | None) -> list[dict[str, Any]]:
    if face_mesh is None:
        return []
    height, width = rgb.shape[:2]
    try:
        import mediapipe as mp

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        results = face_mesh.detect(mp_image)
    except Exception:
        return []
    faces = []
    multi = getattr(results, "face_landmarks", None) or []
    for landmarks in multi:
        points = landmarks
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        bbox = bbox_payload_xyxy(min(xs) * width, min(ys) * height, max(xs) * width, max(ys) * height, width, height)
        face_width = max(0.001, float(bbox["norm"][2]))
        nose_x = float(points[1].x)
        left_eye_x = float(points[33].x)
        right_eye_x = float(points[263].x)
        eye_mid_x = (left_eye_x + right_eye_x) / 2.0
        yaw_proxy = (nose_x - eye_mid_x) / face_width
        if yaw_proxy <= -0.045:
            direction = "left"
        elif yaw_proxy >= 0.045:
            direction = "right"
        else:
            direction = "front"
        faces.append(
            {
                "id": f"face-{len(faces) + 1:02d}",
                "bbox": bbox,
                "centerNorm": bbox_center_norm(bbox),
                "areaRatio": bbox_area_norm(bbox),
                "direction": direction,
                "directionConfidence": round(min(0.95, 0.55 + abs(yaw_proxy) * 2.5), 4),
                "yawProxy": round(yaw_proxy, 5),
                "size": {
                    "widthRatio": bbox["norm"][2],
                    "heightRatio": bbox["norm"][3],
                    "areaRatio": bbox_area_norm(bbox),
                    "label": "large" if bbox_area_norm(bbox) >= 0.045 else "medium" if bbox_area_norm(bbox) >= 0.018 else "small",
                },
                "detector": "mediapipe-face-mesh",
            }
        )
    return sorted(faces, key=lambda item: item["areaRatio"], reverse=True)


def detect_faces_haar(rgb: np.ndarray, detectors: dict[str, cv2.CascadeClassifier]) -> list[dict[str, Any]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape[:2]
    faces: list[dict[str, Any]] = []
    for direction, detector in detectors.items():
        if detector.empty():
            continue
        raw_faces = detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(36, 36))
        for x, y, w, h in raw_faces:
            bbox = bbox_payload_xyxy(float(x), float(y), float(x + w), float(y + h), width, height)
            faces.append(
                {
                    "id": f"face-{len(faces) + 1:02d}",
                    "bbox": bbox,
                    "centerNorm": bbox_center_norm(bbox),
                    "areaRatio": bbox_area_norm(bbox),
                    "direction": "front" if direction == "front" else "unknown",
                    "directionConfidence": 0.45,
                    "size": {
                        "widthRatio": bbox["norm"][2],
                        "heightRatio": bbox["norm"][3],
                        "areaRatio": bbox_area_norm(bbox),
                        "label": "large" if bbox_area_norm(bbox) >= 0.045 else "medium" if bbox_area_norm(bbox) >= 0.018 else "small",
                    },
                    "detector": f"opencv-haar-{direction}",
                }
            )
    deduped: list[dict[str, Any]] = []
    for face in sorted(faces, key=lambda item: item["areaRatio"], reverse=True):
        x, y, w, h = face["bbox"]["norm"]
        overlaps = False
        for existing in deduped:
            ex, ey, ew, eh = existing["bbox"]["norm"]
            ix = max(0.0, min(x + w, ex + ew) - max(x, ex))
            iy = max(0.0, min(y + h, ey + eh) - max(y, ey))
            if ix * iy > min(w * h, ew * eh) * 0.45:
                overlaps = True
                break
        if not overlaps:
            deduped.append(face)
    return deduped


def people_from_faces(faces: list[dict[str, Any]], width: int, height: int) -> list[dict[str, Any]]:
    people = []
    for face in faces:
        x, y, w, h = face["bbox"]["pixel"]
        center_x = x + w / 2
        x1 = max(0.0, center_x - w * 1.45)
        x2 = min(float(width), center_x + w * 1.45)
        y1 = max(0.0, y - h * 0.85)
        y2 = min(float(height), y + h * 4.25)
        bbox = bbox_payload_xyxy(x1, y1, x2, y2, width, height)
        people.append(
            {
                "id": f"person-{len(people) + 1:02d}",
                "bbox": bbox,
                "centerNorm": bbox_center_norm(bbox),
                "areaRatio": bbox_area_norm(bbox),
                "confidence": 0.42,
                "detector": "face-derived-person-fallback",
            }
        )
    return sorted(people, key=lambda item: item["areaRatio"], reverse=True)


def assign_faces_to_people(people: list[dict[str, Any]], faces: list[dict[str, Any]]) -> None:
    for person in people:
        px, py, pw, ph = person["bbox"]["norm"]
        candidates = []
        for face in faces:
            cx, cy = face["centerNorm"]
            if px <= cx <= px + pw and py <= cy <= py + ph:
                candidates.append(face)
        if candidates:
            face = sorted(candidates, key=lambda item: item["areaRatio"], reverse=True)[0]
            person["faceId"] = face["id"]
            person["faceDirection"] = face.get("direction", "unknown")
            person["faceBBox"] = face["bbox"]


def ocr_background(rgb: np.ndarray, bbox: dict[str, Any]) -> dict[str, Any]:
    height, width = rgb.shape[:2]
    x1, y1, x2, y2 = expanded_pixel_bbox(bbox, width, height, pad_ratio=0.24)
    region = rgb[y1:y2, x1:x2]
    colors = dominant_colors(region, 3)
    color = colors[0]["hex"] if colors else None
    if region.size:
        hsv = cv2.cvtColor(cv2.cvtColor(region, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
        saturation = float(np.mean(hsv[:, :, 1])) / 255.0
        brightness = float(np.mean(hsv[:, :, 2])) / 255.0
    else:
        saturation = 0.0
        brightness = 0.0
    return {
        "detected": bool(color),
        "color": color,
        "dominantColors": colors,
        "saturation": round(saturation, 4),
        "brightness": round(brightness, 4),
    }


def classify_text(text: str, bbox: dict[str, Any]) -> str:
    lower = text.lower()
    x, y, w, h = bbox["norm"]
    bottom = y + h
    if "layerx" in lower or "layer x" in lower or "layerｘ" in lower:
        return "logo_text"
    if y < 0.18 and w > 0.16:
        return "title"
    if bottom > 0.48 and h >= 0.045:
        return "subtitle"
    if h >= 0.038 or w >= 0.2:
        return "annotation"
    return "small_text"


def detect_text_overlays(rgb: np.ndarray, reader: Any | None) -> list[dict[str, Any]]:
    if reader is None:
        return []
    height, width = rgb.shape[:2]
    try:
        raw = reader.readtext(rgb)
    except Exception:
        return []
    overlays = []
    for item in raw:
        if len(item) < 3:
            continue
        points, text, confidence = item[0], str(item[1]), float(item[2])
        if not text.strip() or confidence < 0.18:
            continue
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        bbox = bbox_payload_xyxy(min(xs), min(ys), max(xs), max(ys), width, height)
        role = classify_text(text, bbox)
        overlays.append(
            {
                "id": f"text-{len(overlays) + 1:02d}",
                "text": text,
                "role": role,
                "bbox": bbox,
                "fontSizePxEstimate": round(float(bbox["pixel"][3]), 2),
                "confidence": round(confidence, 4),
                "backgroundBox": ocr_background(rgb, bbox),
                "detector": "easyocr",
            }
        )
    return overlays


def logo_candidates(text_overlays: list[dict[str, Any]], collection: str) -> list[dict[str, Any]]:
    logos = []
    for item in text_overlays:
        x, y, w, h = item["bbox"]["norm"]
        if item["role"] == "logo_text" or (collection == "layer-x" and x < 0.28 and y < 0.2 and re.search(r"layer", item["text"], re.I)):
            logos.append(
                {
                    "id": f"logo-{len(logos) + 1:02d}",
                    "kind": "brand-text",
                    "label": "LayerX" if re.search(r"layer", item["text"], re.I) else item["text"],
                    "bbox": item["bbox"],
                    "confidence": max(0.55, float(item.get("confidence") or 0.0)),
                    "sourceTextId": item["id"],
                }
            )
    return logos


def detect_vertical_split(rgb: np.ndarray) -> dict[str, Any]:
    height, width = rgb.shape[:2]
    gray = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    col_strength = edges.mean(axis=0) / 255.0
    start = int(width * 0.33)
    end = int(width * 0.67)
    if end <= start:
        return {"present": False, "xRatio": None, "confidence": 0.0}
    local = col_strength[start:end]
    max_index = int(np.argmax(local)) + start
    score = float(col_strength[max_index])
    band = rgb[:, max(0, max_index - 2) : min(width, max_index + 3)]
    band_saturation = 0.0
    if band.size:
        hsv = cv2.cvtColor(cv2.cvtColor(band, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
        band_saturation = float(np.mean(hsv[:, :, 1])) / 255.0
    present = score >= 0.18 or (score >= 0.09 and band_saturation >= 0.28)
    return {
        "present": bool(present),
        "xRatio": round(max_index / max(width, 1), 5) if present else None,
        "confidence": round(min(0.95, score * 3.4 + band_saturation * 0.35), 4) if present else round(score, 4),
    }


def union_area_norm(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    # Approximate by rasterizing normalized boxes onto a compact grid.
    grid = np.zeros((160, 240), dtype=np.uint8)
    for item in items:
        x, y, w, h = item["bbox"]["norm"]
        x1 = int(clamp(float(x)) * grid.shape[1])
        y1 = int(clamp(float(y)) * grid.shape[0])
        x2 = int(clamp(float(x + w)) * grid.shape[1])
        y2 = int(clamp(float(y + h)) * grid.shape[0])
        grid[y1:y2, x1:x2] = 1
    return round(float(grid.mean()), 5)


def frame_composition(
    rgb: np.ndarray,
    people: list[dict[str, Any]],
    text_overlays: list[dict[str, Any]],
) -> dict[str, Any]:
    height, width = rgb.shape[:2]
    split = detect_vertical_split(rgb)
    lower_text = [item for item in text_overlays if item["bbox"]["norm"][1] + item["bbox"]["norm"][3] >= 0.48]
    subject_margins = None
    if people:
        main = people[0]
        x, y, w, h = main["bbox"]["norm"]
        subject_margins = {
            "left": round(x, 5),
            "right": round(1.0 - x - w, 5),
            "top": round(y, 5),
            "bottom": round(1.0 - y - h, 5),
        }
    centers = [item["centerNorm"] for item in people]
    return {
        "aspectRatio": round(width / max(height, 1), 5),
        "orientation": "landscape" if width >= height else "portrait",
        "splitScreen": split,
        "personCount": len(people),
        "personCenters": centers,
        "mainSubjectMargins": subject_margins,
        "lowerThirdTextCoverageRatio": union_area_norm(lower_text),
        "textCoverageRatio": union_area_norm(text_overlays),
        "layoutTags": layout_tags(split, people, text_overlays),
    }


def layout_tags(split: dict[str, Any], people: list[dict[str, Any]], text_overlays: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    if split.get("present"):
        tags.append("vertical-split-screen")
    if len(people) >= 2:
        tags.append("two-person-interview")
    elif len(people) == 1:
        tags.append("single-person")
    if any(item.get("role") == "subtitle" for item in text_overlays):
        tags.append("large-lower-third-text")
    if any(item.get("role") == "title" for item in text_overlays):
        tags.append("top-title-banner")
    return tags


def draw_box(draw: ImageDraw.ImageDraw, bbox: dict[str, Any], color: str, label: str) -> None:
    x, y, w, h = bbox["pixel"]
    xy = [float(x), float(y), float(x) + float(w), float(y) + float(h)]
    draw.rectangle(xy, outline=color, width=4)
    draw.rectangle([xy[0], max(0, xy[1] - 18), xy[0] + max(60, len(label) * 7), xy[1]], fill=color)
    draw.text((xy[0] + 3, max(0, xy[1] - 17)), label, fill="white")


def save_debug_overlay(
    rgb: np.ndarray,
    people: list[dict[str, Any]],
    faces: list[dict[str, Any]],
    texts: list[dict[str, Any]],
    logos: list[dict[str, Any]],
    path: Path,
) -> None:
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    for person in people:
        draw_box(draw, person["bbox"], "#E53935", f"{person['id']}")
    for face in faces:
        draw_box(draw, face["bbox"], "#43A047", f"{face['id']} {face.get('direction', '')}")
    for text in texts:
        draw_box(draw, text["bbox"], "#1E88E5", text.get("role", "text"))
    for logo in logos:
        draw_box(draw, logo["bbox"], "#8E24AA", "logo")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=92)


def save_sample(rgb: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(path, quality=92)


def read_video_frame(path: Path, time_seconds: float) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_seconds) * 1000.0)
    ok, frame_bgr = cap.read()
    cap.release()
    if not ok or frame_bgr is None:
        return None
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)


def read_image(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    return np.array(image)


def scene_change_times(path: Path, duration: float, interval: float, max_extra: int) -> list[float]:
    if duration <= 0 or max_extra <= 0:
        return []
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    scores: list[tuple[float, float]] = []
    previous: np.ndarray | None = None
    t = 0.0
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += interval
            continue
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (96, 54))
        if previous is not None:
            score = float(np.mean(cv2.absdiff(small, previous))) / 255.0
            scores.append((score, t))
        previous = small
        t += interval
    cap.release()
    scores.sort(reverse=True)
    return [round(t, 3) for score, t in scores[:max_extra] if score >= 0.055]


def sample_times_for_video(asset: dict[str, Any], settings: dict[str, Any], max_samples_override: int | None) -> list[float]:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    duration = float_value(metadata.get("duration"), 0.0)
    sample_fps = max(0.1, float_value(settings.get("analysis", {}).get("sampleFps"), 1.0))
    max_samples = max_samples_override or int_value(settings.get("analysis", {}).get("maxVideoSamples"), 90)
    interval = float_value(settings.get("analysis", {}).get("sceneChangeProbeIntervalSeconds"), 0.5)
    max_extra = int_value(settings.get("analysis", {}).get("sceneChangeMaxExtraSamples"), 8)
    if duration <= 0:
        return [0.0]
    times = {0.0, min(duration * 0.5, max(0.0, duration - 0.05)), max(0.0, duration - 0.1)}
    step = 1.0 / sample_fps
    t = 0.0
    while t < duration:
        times.add(round(t, 3))
        t += step
    for item in scene_change_times(Path(asset["sourcePath"]), duration, interval, max_extra):
        times.add(item)
    ordered = sorted(time for time in times if 0.0 <= time <= duration)
    if len(ordered) <= max_samples:
        return ordered
    indexes = np.linspace(0, len(ordered) - 1, max_samples).round().astype(int)
    return [ordered[int(index)] for index in sorted(set(indexes))]


def analyze_frame(
    rgb: np.ndarray,
    *,
    frame_id: str,
    time_seconds: float,
    sample_path: Path,
    debug_path: Path,
    collection: str,
    yolo_model: Any | None,
    face_mesh: Any | None,
    face_detectors: dict[str, cv2.CascadeClassifier],
    ocr_reader: Any | None,
    yolo_confidence: float,
) -> dict[str, Any]:
    height, width = rgb.shape[:2]
    people = detect_people(rgb, yolo_model, yolo_confidence)
    faces = detect_faces_mediapipe(rgb, face_mesh)
    if not faces:
        faces = detect_faces_haar(rgb, face_detectors)
    if not people:
        people = people_from_faces(faces, width, height)
    assign_faces_to_people(people, faces)
    text_overlays = detect_text_overlays(rgb, ocr_reader)
    logos = logo_candidates(text_overlays, collection)
    annotations = [item for item in text_overlays if item.get("role") in {"annotation", "small_text"}]
    composition = frame_composition(rgb, people, text_overlays)
    style = visual_style(rgb)
    save_sample(rgb, sample_path)
    save_debug_overlay(rgb, people, faces, text_overlays, logos, debug_path)
    return {
        "frameId": frame_id,
        "timeSeconds": round(float(time_seconds), 3),
        "width": width,
        "height": height,
        "samplePath": str(sample_path),
        "debugOverlayPath": str(debug_path),
        "people": people,
        "faces": faces,
        "textOverlays": text_overlays,
        "logos": logos,
        "annotations": annotations,
        "composition": composition,
        "visualStyle": style,
    }


def summarize(asset: dict[str, Any], frames: list[dict[str, Any]]) -> dict[str, Any]:
    people_counts = [len(frame.get("people", [])) for frame in frames]
    face_counts = [len(frame.get("faces", [])) for frame in frames]
    face_dirs = Counter(
        str(face.get("direction") or "unknown")
        for frame in frames
        for face in frame.get("faces", [])
    )
    text_roles = Counter(
        str(item.get("role") or "unknown")
        for frame in frames
        for item in frame.get("textOverlays", [])
    )
    face_areas = [
        float(face.get("size", {}).get("areaRatio") or face.get("areaRatio") or 0.0)
        for frame in frames
        for face in frame.get("faces", [])
    ]
    person_centers = [
        person.get("centerNorm")
        for frame in frames
        for person in frame.get("people", [])[:1]
        if isinstance(person.get("centerNorm"), list)
    ]
    split_count = sum(1 for frame in frames if frame.get("composition", {}).get("splitScreen", {}).get("present"))
    color_counts = Counter(
        color.get("hex")
        for frame in frames
        for color in frame.get("visualStyle", {}).get("dominantColors", [])[:2]
        if color.get("hex")
    )
    dominant_colors_payload = [{"hex": color, "count": count} for color, count in color_counts.most_common(6)]
    summary = {
        "frameCount": len(frames),
        "sampledDurationSeconds": max((float(frame.get("timeSeconds") or 0.0) for frame in frames), default=0.0),
        "personPresent": any(count > 0 for count in people_counts),
        "maxPeople": max(people_counts, default=0),
        "avgPeople": round(sum(people_counts) / len(people_counts), 4) if people_counts else 0,
        "facePresent": any(count > 0 for count in face_counts),
        "maxFaces": max(face_counts, default=0),
        "faceDirectionCounts": dict(face_dirs),
        "avgFaceAreaRatio": round(sum(face_areas) / len(face_areas), 6) if face_areas else None,
        "mainPersonCenterAvg": average_point(person_centers),
        "subtitlePresent": text_roles.get("subtitle", 0) > 0,
        "titlePresent": text_roles.get("title", 0) > 0,
        "logoPresent": any(frame.get("logos") for frame in frames),
        "annotationPresent": any(frame.get("annotations") for frame in frames),
        "textRoleCounts": dict(text_roles),
        "splitScreenPresent": split_count > 0,
        "splitScreenFrameRatio": round(split_count / len(frames), 4) if frames else 0.0,
        "dominantColors": dominant_colors_payload,
    }
    summary["referenceNotes"] = reference_notes(asset, summary)
    return summary


def average_point(points: list[Any]) -> list[float] | None:
    usable = [point for point in points if isinstance(point, list) and len(point) >= 2]
    if not usable:
        return None
    return [
        round(sum(float(point[0]) for point in usable) / len(usable), 5),
        round(sum(float(point[1]) for point in usable) / len(usable), 5),
    ]


def reference_notes(asset: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    notes = []
    if summary.get("splitScreenPresent"):
        notes.append("Use as a split-screen interview composition reference.")
    if summary.get("maxPeople", 0) >= 2:
        notes.append("Two-person layout with separate left/right subject zones.")
    if summary.get("subtitlePresent"):
        notes.append("Large lower-third Japanese text overlays are part of the style.")
    if summary.get("titlePresent"):
        notes.append("Top title/header treatment can be reused as a branded information strip.")
    if summary.get("logoPresent"):
        notes.append("Logo placement is a persistent brand marker, usually near the upper left.")
    if summary.get("annotationPresent"):
        notes.append("Additional text annotations should be tracked separately from main subtitles.")
    if not notes:
        notes.append("Use as a general visual composition and framing reference.")
    notes.append(f"Collection: {asset.get('collection')}; asset kind: {asset.get('kind')}.")
    return notes


def analyze_asset(
    asset: dict[str, Any],
    *,
    settings: dict[str, Any],
    yolo_model: Any | None,
    face_mesh: Any | None,
    face_detectors: dict[str, cv2.CascadeClassifier],
    ocr_reader: Any | None,
    max_video_samples: int | None,
    force: bool,
) -> dict[str, Any]:
    source = Path(asset["sourcePath"])
    output_dir = Path(asset["analysisPath"]).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = Path(asset["analysisPath"])
    samples_dir = output_dir / "samples"
    debug_dir = output_dir / "debug-overlays"
    if force:
        if analysis_path.exists():
            analysis_path.unlink()
        for generated_dir in (samples_dir, debug_dir):
            if generated_dir.exists():
                shutil.rmtree(generated_dir)
    yolo_confidence = float_value(settings.get("analysis", {}).get("yoloConfidence"), 0.35)
    frames: list[dict[str, Any]] = []
    if asset["kind"] == "image":
        rgb = read_image(source)
        frames.append(
            analyze_frame(
                rgb,
                frame_id="frame-0000",
                time_seconds=0.0,
                sample_path=samples_dir / "frame_0000.jpg",
                debug_path=debug_dir / "frame_0000_debug.jpg",
                collection=str(asset["collection"]),
                yolo_model=yolo_model,
                face_mesh=face_mesh,
                face_detectors=face_detectors,
                ocr_reader=ocr_reader,
                yolo_confidence=yolo_confidence,
            )
        )
    else:
        for index, time_seconds in enumerate(sample_times_for_video(asset, settings, max_video_samples)):
            rgb = read_video_frame(source, time_seconds)
            if rgb is None:
                continue
            frames.append(
                analyze_frame(
                    rgb,
                    frame_id=f"frame-{index:04d}",
                    time_seconds=time_seconds,
                    sample_path=samples_dir / f"frame_{index:04d}_t{time_seconds:08.3f}.jpg",
                    debug_path=debug_dir / f"frame_{index:04d}_t{time_seconds:08.3f}_debug.jpg",
                    collection=str(asset["collection"]),
                    yolo_model=yolo_model,
                    face_mesh=face_mesh,
                    face_detectors=face_detectors,
                    ocr_reader=ocr_reader,
                    yolo_confidence=yolo_confidence,
                )
            )
    if not frames:
        raise RuntimeError(f"No frames could be sampled for {source}")
    analysis = {
        "schemaVersion": "reference-asset-analysis/v1",
        "generatedAt": utc_now(),
        "asset": {
            "assetId": asset["assetId"],
            "mediaId": asset.get("mediaId"),
            "collection": asset["collection"],
            "kind": asset["kind"],
            "sourcePath": asset["sourcePath"],
            "analysisPath": asset["analysisPath"],
            "originalPath": asset["originalPath"],
            "sha256": asset["sha256"],
            "sizeBytes": asset["sizeBytes"],
            "relativePath": asset.get("relativePath"),
            "name": asset.get("name"),
            "extension": asset.get("extension"),
            "width": asset.get("metadata", {}).get("width"),
            "height": asset.get("metadata", {}).get("height"),
            "duration": asset.get("metadata", {}).get("duration"),
            "fps": asset.get("metadata", {}).get("fps"),
            "codec": asset.get("metadata", {}).get("videoCodec"),
        },
        "summary": summarize(asset, frames),
        "frames": frames,
    }
    write_json(analysis_path, analysis)
    return analysis


def build_analysis_summary(analyses: list[dict[str, Any]], tool_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "reference-analysis-summary/v1",
        "generatedAt": utc_now(),
        "assetCount": len(analyses),
        "toolStatus": tool_status,
        "assets": [
            {
                "assetId": analysis["asset"]["assetId"],
                "collection": analysis["asset"]["collection"],
                "kind": analysis["asset"]["kind"],
                "analysisPath": analysis["asset"].get("analysisPath"),
                "summary": analysis["summary"],
            }
            for analysis in analyses
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze copied reference images and videos into per-asset JSON.")
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--asset-id", default="")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-video-samples", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-yolo", action="store_true")
    parser.add_argument("--no-mediapipe", action="store_true")
    parser.add_argument("--no-ocr", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_json(args.settings)
    manifest = load_json(args.manifest)
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    if args.asset_id:
        assets = [asset for asset in assets if asset.get("assetId") == args.asset_id]
    if args.limit is not None:
        assets = assets[: args.limit]
    if not assets:
        raise SystemExit("No assets selected for analysis.")

    yolo_model, yolo_status = load_yolo(settings, args.no_yolo)
    face_mesh, face_status = load_face_mesh(settings, args.no_mediapipe)
    ocr_reader, ocr_status = load_easyocr(settings, args.no_ocr)
    face_detectors = haar_face_detectors()
    tool_status = {"yolo": yolo_status, "faceMesh": face_status, "ocr": ocr_status}
    analyses: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for asset in assets:
        try:
            analyses.append(
                analyze_asset(
                    asset,
                    settings=settings,
                    yolo_model=yolo_model,
                    face_mesh=face_mesh,
                    face_detectors=face_detectors,
                    ocr_reader=ocr_reader,
                    max_video_samples=args.max_video_samples,
                    force=args.force,
                )
            )
            print(json.dumps({"assetId": asset["assetId"], "status": "done", "analysisPath": asset["analysisPath"]}, ensure_ascii=False))
        except Exception as error:
            errors.append({"assetId": str(asset.get("assetId") or ""), "error": str(error)})
            print(json.dumps({"assetId": asset.get("assetId"), "status": "error", "error": str(error)}, ensure_ascii=False))
    if face_mesh is not None:
        face_mesh.close()
    summary = build_analysis_summary(analyses, tool_status)
    if errors:
        summary["errors"] = errors
    write_json(REPORTS_ROOT / "analysis_summary.json", summary)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
