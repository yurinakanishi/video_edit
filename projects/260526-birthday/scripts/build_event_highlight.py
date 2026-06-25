from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import math
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_FPS = 30
VIDEO_ANALYSIS_VERSION = "video-v2-stable-people"
IMAGE_ANALYSIS_VERSION = "image-v4-yunet-face-opening-gate"
YUNET_MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_MODEL_RELATIVE_PATH = Path("output") / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_FACE_SCORE_THRESHOLD = 0.78
BACKGROUND_AUDIO_FADE_SECONDS = 5.0
FINAL_STILL_FADE_SECONDS = 2.0
INTRO_TITLE_TEXT_APPEAR_START_SECONDS = 0.45
INTRO_TITLE_TEXT_FADE_IN_SECONDS = 0.65
INTRO_TITLE_TEXT_HOLD_SECONDS = 0.75
INTRO_TITLE_TEXT_FADE_OUT_SECONDS = 0.85
INTRO_TITLE_IMAGE_REVEAL_START_SECONDS = 3.05
INTRO_TITLE_IMAGE_REVEAL_SECONDS = 1.35
INTRO_IMAGE_FADE_IN_SECONDS = 1.5
AUDIO_FOCUS_MUSIC_VOLUME_MULTIPLIER = 0.15
AUDIO_FOCUS_ORIGINAL_VOLUME_MULTIPLIER = 2.0
AUDIO_FOCUS_ORIGINAL_VOLUME_MAX = 1.0
AUDIO_FOCUS_TRANSITION_SECONDS = 1.0
AUDIO_FOCUS_MERGE_GAP_SECONDS = 0.05
VISUAL_IMAGE_DISSOLVE_SECONDS = 0.65
VISUAL_IMAGE_DISSOLVE_MAX_FRACTION = 0.30
PORTRAIT_LETTERBOX_FADE_SECONDS = 0.45
PORTRAIT_LETTERBOX_ZOOM_AMOUNT = 0.032
MIN_VARIABLE_VIDEO_SECONDS = 12.0
MANUAL_IMAGE_RENDER_OVERRIDES: dict[str, dict[str, Any]] = {}
MANUAL_VIDEO_FIXED_CLIPS = {
    "a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43": (0.0, 40.0),
    "dji_20000104164015_0007_d": (463.0, 57.0),
    "dji_20000104181624_0030_d": (0.0, 103.978667),
    "dji_20000104181937_0031_d": (0.0, 203.029333),
}
MANUAL_VIDEO_RANGE_CLIPS = {
    "dji_20000104171048_0015_d": [
        {
            "sourceIn": 0.0,
            "sourceOut": 51.0,
            "labelSuffix": "clip_000_051",
            "connectedGroup": "dji_20000104171048_0015_d_cut_051_054",
        },
        {
            "sourceIn": 54.0,
            "sourceOut": 176.71,
            "labelSuffix": "clip_054_end",
            "connectedGroup": "dji_20000104171048_0015_d_cut_051_054",
        },
    ],
    "dji_20000104161921_0006_d": [
        {"sourceIn": 387.0, "sourceOut": 554.0, "labelSuffix": "clip_387_554"},
        {
            "sourceIn": 38.0,
            "sourceOut": 113.0,
            "labelSuffix": "clip_038_113",
            "connectedGroup": "dji_20000104161921_0006_d_clip_038_211_cut_113_139",
        },
        {
            "sourceIn": 139.0,
            "sourceOut": 211.0,
            "labelSuffix": "clip_139_211",
            "connectedGroup": "dji_20000104161921_0006_d_clip_038_211_cut_113_139",
        },
    ],
    "st7_8341": [
        {"sourceIn": 0.0, "sourceOut": 46.0, "labelSuffix": "clip_000_046"},
        {"sourceIn": 217.0, "sourceOut": 233.0, "labelSuffix": "clip_217_233"},
    ],
    "dji_20000104172624_0018_d": [
        {
            "sourceIn": 1.0,
            "sourceOut": 87.0,
            "labelSuffix": "clip_001_087",
            "connectedGroup": "dji_20000104172624_0018_d_cut_000_001_087_131_177_184",
        },
        {
            "sourceIn": 131.0,
            "sourceOut": 177.0,
            "labelSuffix": "clip_131_177",
            "connectedGroup": "dji_20000104172624_0018_d_cut_000_001_087_131_177_184",
        },
        {
            "sourceIn": 184.0,
            "sourceOut": 356.0,
            "labelSuffix": "clip_184_356",
            "connectedGroup": "dji_20000104172624_0018_d_cut_000_001_087_131_177_184",
        },
    ],
}
MANUAL_VIDEO_BLOCK_SWAPS = [
    (
        "st7_8341",
        "clip_000_046",
        "dji_20000104172624_0018_d_cut_000_001_087_131_177_184",
    )
]
MANUAL_VIDEO_RELOCATIONS = []
MANUAL_VIDEO_STEM_RELOCATIONS = []
MANUAL_VIDEO_CLIP_ADJACENCIES = [
    {
        "movingStem": "st7_8341",
        "movingSuffix": "clip_217_233",
        "afterStem": "st7_8341",
        "afterSuffix": "clip_000_046",
        "placement": "move-immediately-after-000-046",
    }
]
MANUAL_IMAGE_RELOCATIONS = [
    {
        "imageStem": "st-731",
        "mode": "before-video",
        "targetStem": "dji_20000104181624_0030_d",
        "placement": "move-before-video012",
    },
    {
        "imageStem": "st-668",
        "mode": "after-image",
        "targetStem": "st-675",
        "placement": "move-four-image-block-after-five-image-block",
    },
    {
        "imageStem": "st-670",
        "mode": "after-image",
        "targetStem": "st-668",
        "placement": "move-after-st668",
    },
    {
        "imageStem": "st-646",
        "mode": "after-image",
        "targetStem": "st-670",
        "placement": "move-late-from-nine-thirteen-gap",
    },
    {
        "imageStem": "st-653",
        "mode": "after-image",
        "targetStem": "st-646",
        "placement": "move-late-from-nine-thirteen-gap",
    },
    {
        "imageStem": "st-735",
        "mode": "after-image",
        "targetStem": "st-653",
        "placement": "move-late-from-four-thirteen",
    },
    {
        "imageStem": "st-667",
        "mode": "after-image",
        "targetStem": "st-735",
        "placement": "move-later-after-st735",
    },
    {
        "imageStem": "st-634",
        "mode": "after-image",
        "targetStem": "st-667",
        "placement": "move-out-of-seven-minute-cluster",
    },
    {
        "imageStem": "st-723",
        "mode": "after-image",
        "targetStem": "st-645",
        "placement": "swap-with-st725-to-late-video-gap",
    },
    {
        "imageStem": "st-725",
        "mode": "after-image",
        "targetStem": "st-713",
        "placement": "swap-with-st723-to-final-photo-block",
    },
    {
        "imageStem": "st-729",
        "mode": "after-image",
        "targetStem": "st-697",
        "placement": "move-after-st697-video019-removed",
    },
    {
        "imageStem": "st-730",
        "mode": "after-image",
        "targetStem": "st-729",
        "placement": "move-after-st729-video022-removed",
    },
    {
        "imageStem": "st-686",
        "mode": "after-image",
        "targetStem": "st-723",
        "placement": "move-end-from-six-fifty-two",
    },
    {
        "imageStem": "st-618",
        "mode": "before-video",
        "targetStem": "dji_20000104171048_0015_d",
        "targetSuffix": "clip_000_051",
        "placement": "swap-to-eight-thirteen-area",
    },
    {
        "imageStem": "st-635",
        "mode": "after-image",
        "targetStem": "st-618",
        "placement": "swap-to-eight-sixteen-area",
    },
    {
        "imageStem": "st-661",
        "mode": "after-connected-video-group",
        "targetGroup": "dji_20000104172624_0018_d_cut_000_001_087_131_177_184",
        "placement": "move-one-video-later-after-video006",
    },
    {
        "imageStem": "st-690",
        "mode": "after-image",
        "targetStem": "st-661",
        "placement": "move-one-video-later-after-st661",
    },
    {
        "imageStem": "st-677",
        "mode": "after-video",
        "targetStem": "dji_20000104172624_0018_d",
        "targetSuffix": "clip_184_356",
        "placement": "move-after-video006-184-356",
    },
    {
        "imageStem": "st-706",
        "mode": "after-image",
        "targetStem": "st-677",
        "placement": "move-after-st677-video006-184-356",
    },
    {
        "imageStem": "st-632",
        "mode": "after-image",
        "targetStem": "st-634",
        "placement": "move-before-001-087-from-eleven-thirty-cluster",
    },
    {
        "imageStem": "st-735",
        "mode": "before-video",
        "targetStem": "dji_20000104172624_0018_d",
        "targetSuffix": "clip_001_087",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-667",
        "mode": "after-image",
        "targetStem": "st-735",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-634",
        "mode": "after-image",
        "targetStem": "st-667",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-632",
        "mode": "after-image",
        "targetStem": "st-634",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-675",
        "mode": "after-image",
        "targetStem": "st-632",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-668",
        "mode": "after-image",
        "targetStem": "st-675",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-670",
        "mode": "after-image",
        "targetStem": "st-668",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-646",
        "mode": "after-image",
        "targetStem": "st-670",
        "placement": "reorder-12min-image-block-before-video006",
    },
    {
        "imageStem": "st-653",
        "mode": "after-image",
        "targetStem": "st-646",
        "placement": "reorder-12min-image-block-before-video006",
    },
]
MANUAL_VIDEO_END_TRIM_SECONDS = {}
MANUAL_VIDEO_KEEP_LAST_SECONDS = {}
RENAMED_SOURCE_PREFIX_RE = re.compile(r"^(?:video|photo|audio|sidecar)_\d{3,4}_(.+)$", re.IGNORECASE)
ALLOWED_IMAGE_SOURCE_DIRS = {"phtp2605269"}
DEFAULT_EXCLUDED_VIDEO_STEMS = {
    "dji_20000104170051_0008_d",
    "dji_20000104174652_0024_d",
    "dji_20000104174953_0026_d",
    "dji_20000104174803_0025_d",
    "dji_20000104171531_0016_d",
    "dji_20000104172535_0017_d",
    "dji_20000104175228_0028_d",
    "dji_20000104175108_0027_d",
    "st7_8342",
    "0875db90-5d21-463d-b4b0-9f0a19195ca2",
    "a2ecf072-e001-453b-8432-780011ee6fea",
    "ed5c2815-5ecc-4b02-ba3b-b0c8e02257fd",
    "e6eeaf64-3602-4238-af85-8ccfc6701205",
    "4e1e990e-0b3c-404c-9fb0-ef25073073ea",
    "8ea3f1b6-af35-4c9b-9576-71eba58d9f5e",
    "503179b6-95c2-4918-8c7c-4efc3014d757",
}
DEFAULT_EXCLUDED_IMAGE_STEMS = {
    "st-600",
    "st-604",
    "st-610",
    "st-614",
    "st-616",
    "st-617",
    "st-621",
    "st-624",
    "st-676",
    "st-641",
    "st-641w",
    "dji_20000104170445_0011_d_t004_5",
}
MANUAL_ONE_MINUTE_IMAGE_STEMS = {"st-709"}
MANUAL_ONE_MINUTE_IMAGE_ORDER = ["st-709"]
MANUAL_FIVE_TO_SEVEN_MINUTE_IMAGE_STEMS = {"st-608"}
MANUAL_FIVE_TO_SEVEN_MINUTE_IMAGE_ORDER = ["st-608"]
MANUAL_AFTER_ST738_IMAGE_STEMS = {"st-737"}
MANUAL_EARLY_IMAGE_STEMS = {
    "st-628",
    "st-638",
    "st-701",
    "st-702",
    "st-736",
    "st-735",
}
MANUAL_EARLY_IMAGE_ORDER = [
    "st-638",
    "st-628",
    "st-701",
    "st-702",
    "st-736",
    "st-735",
]
MANUAL_EARLY_IMAGE_TARGET_SECONDS = [70.0, 75.0, 80.0, 85.0, 245.0, 250.0]
MANUAL_DISTRIBUTED_IMAGE_STEMS = {"st-601", "st-618", "st-625"}
MANUAL_DISTRIBUTED_IMAGE_ORDER = ["st-601", "st-625", "st-618"]
MANUAL_DISTRIBUTED_IMAGE_TARGET_SECONDS = [405.0, 555.0, 590.0]
MANUAL_LATE_IMAGE_STEMS = {"st-686", "st-723", "st-634", "st-690", "st-667", "st-670"}
MANUAL_LATE_IMAGE_ORDER = ["st-686", "st-723", "st-634", "st-690", "st-667", "st-670"]
MANUAL_LATE_IMAGE_TARGET_SECONDS = [380.0, 385.0, 430.0, 510.0, 550.0, 625.0]
MANUAL_LATE_INTERVIDEO_IMAGE_STEMS = {"st-729", "st-730", "st-645"}
MANUAL_LATE_INTERVIDEO_IMAGE_ORDER = ["st-729", "st-730", "st-645"]
MANUAL_LATE_INTERVIDEO_IMAGE_AFTER_VIDEO = [
    ("a2ecf072-e001-453b-8432-780011ee6fea_clip56_89-114_43", "st-645"),
]
MANUAL_FINAL_PHOTO_OPENING_STEMS = {"st-682", "st-713"}
MANUAL_FINAL_PHOTO_OPENING_ORDER = ["st-682", "st-713"]
MANUAL_THIRD_FROM_LAST_IMAGE_STEMS = {"st-665"}
MANUAL_THIRD_FROM_LAST_IMAGE_ORDER = ["st-665"]
MANUAL_SECOND_FROM_LAST_IMAGE_STEMS = {"st-721"}
MANUAL_SECOND_FROM_LAST_IMAGE_ORDER = ["st-721"]
FINAL_TIMELINE_VIDEO_ORDER: list[str] = []
FINAL_TIMELINE_VIDEO_STEMS = set(FINAL_TIMELINE_VIDEO_ORDER)
CONNECTED_VIDEO_BLOCK_ORDER = ["dji_20000104181624_0030_d", "dji_20000104181937_0031_d"]
CONNECTED_VIDEO_BLOCK_STEMS = set(CONNECTED_VIDEO_BLOCK_ORDER)
REQUIRED_IMAGE_STEM_PRIORITY = {
    "st-716": 100,
    "st-707bg": 95,
    "st-707": 94,
    "st-738": 90,
    "st-737": 89,
    "st-709": 87,
    "st-638": 86,
    "st-608": 85,
    "st-682": 84,
    "st-713": 83,
    "st-628": 81,
    "st-701": 80,
    "st-702": 79,
    "st-634": 78,
    "st-677": 77,
    "st-690": 76,
    "st-686": 75,
    "st-723": 74,
}


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


def source_identity_stem(value: str) -> str:
    stem = Path(value).stem.lower()
    match = RENAMED_SOURCE_PREFIX_RE.match(stem)
    return match.group(1).lower() if match else stem


def source_display_name(item: "MediaItem") -> str:
    if isinstance(item.analysis, dict):
        override = item.analysis.get("sourceDisplayName")
        if override:
            return str(override)
    return Path(item.relative).name


def ffmpeg_drawtext_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(";", "\\;")
    )


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


def ensure_yunet_model(project_root: Path) -> Path | None:
    model_path = project_root / YUNET_MODEL_RELATIVE_PATH
    if model_path.exists() and model_path.stat().st_size > 100_000:
        return model_path
    if not hasattr(cv2, "FaceDetectorYN_create"):
        return None
    try:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(YUNET_MODEL_URL, model_path)
    except Exception as error:
        print(f"[face detector] YuNet download failed, falling back to Haar cascades: {error}", file=sys.stderr, flush=True)
        return None
    if model_path.exists() and model_path.stat().st_size > 100_000:
        return model_path
    return None


def load_face_detectors(project_root: Path) -> dict[str, Any]:
    base = Path(cv2.data.haarcascades)
    detectors: dict[str, Any] = {
        "front": cv2.CascadeClassifier(str(base / "haarcascade_frontalface_default.xml")),
        "front_alt": cv2.CascadeClassifier(str(base / "haarcascade_frontalface_alt2.xml")),
        "profile": cv2.CascadeClassifier(str(base / "haarcascade_profileface.xml")),
    }
    model_path = ensure_yunet_model(project_root)
    if model_path is not None:
        try:
            detectors["yunet"] = cv2.FaceDetectorYN_create(
                str(model_path),
                "",
                (320, 320),
                score_threshold=0.30,
                nms_threshold=0.30,
                top_k=5000,
            )
        except Exception as error:
            print(f"[face detector] YuNet init failed, falling back to Haar cascades: {error}", file=sys.stderr, flush=True)
    return detectors


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


def detect_faces(frame: np.ndarray, detectors: dict[str, Any]) -> list[dict[str, Any]]:
    height, width = frame.shape[:2]
    scale = 1.0
    working = frame
    if width > 960:
        scale = 960.0 / width
        working = cv2.resize(frame, (960, max(1, round(height * scale))))
    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    min_size = (max(32, round(working.shape[1] * 0.035)), max(32, round(working.shape[0] * 0.035)))
    raw: list[tuple[int, int, int, int, str, float]] = []

    yunet = detectors.get("yunet")
    if yunet is not None:
        try:
            yunet.setInputSize((working.shape[1], working.shape[0]))
            _, yunet_faces = yunet.detect(working)
            if yunet_faces is not None:
                for face in yunet_faces:
                    score = float(face[-1])
                    if score < YUNET_FACE_SCORE_THRESHOLD:
                        continue
                    x, y, w, h = [int(round(float(value))) for value in face[:4]]
                    if w <= 0 or h <= 0:
                        continue
                    raw.append((x, y, w, h, "yunet", score))
        except Exception:
            pass

    for x, y, w, h in detectors["front"].detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=min_size):
        raw.append((int(x), int(y), int(w), int(h), "haar_front", 0.82))
    for x, y, w, h in detectors["front_alt"].detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=min_size):
        raw.append((int(x), int(y), int(w), int(h), "haar_front_alt", 0.82))
    for x, y, w, h in detectors["profile"].detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=min_size):
        raw.append((int(x), int(y), int(w), int(h), "haar_profile", 0.80))
    flipped = cv2.flip(gray, 1)
    for x, y, w, h in detectors["profile"].detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=4, minSize=min_size):
        raw.append((int(working.shape[1] - x - w), int(y), int(w), int(h), "haar_profile_flipped", 0.80))

    faces: list[dict[str, Any]] = []
    inv = 1.0 / scale
    for x, y, w, h, source, confidence in sorted(raw, key=lambda item: (item[5], item[2] * item[3]), reverse=True):
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
                "detector": source,
                "confidence": round(confidence, 4),
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


def media_stem(item: MediaItem) -> str:
    return source_identity_stem(item.path.stem)


def strip_runtime_manual_video_metadata(analysis: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(analysis)
    for key in (
        "manualFixedClip",
        "manualRangeClip",
        "sourceDisplayName",
        "durationAllocation",
        "manualEndTrim",
        "manualKeepLast",
    ):
        cleaned.pop(key, None)
    return cleaned


def expand_manual_video_range_clips(videos: list[MediaItem]) -> list[MediaItem]:
    expanded: list[MediaItem] = []
    for video in videos:
        ranges = MANUAL_VIDEO_RANGE_CLIPS.get(media_stem(video))
        if not ranges:
            expanded.append(video)
            continue
        base_analysis = strip_runtime_manual_video_metadata(copy.deepcopy(video.analysis))
        for index, clip in enumerate(ranges, start=1):
            source_in = clamp(float(clip["sourceIn"]), 0.0, max(0.0, video.duration - (1 / TARGET_FPS)))
            source_out = clamp(float(clip["sourceOut"]), source_in + (1 / TARGET_FPS), video.duration)
            label_suffix = str(clip.get("labelSuffix") or f"clip_{index:02d}")
            clip_analysis = copy.deepcopy(base_analysis)
            clip_analysis["manualRangeClip"] = {
                "sourceStem": media_stem(video),
                "sourceIn": round(source_in, 6),
                "sourceOut": round(source_out, 6),
                "requestedLabelSuffix": label_suffix,
                "placement": "manual-middle-video",
                "method": "duplicate-source-fixed-range",
            }
            if clip.get("connectedGroup"):
                clip_analysis["manualRangeClip"]["connectedGroup"] = str(clip["connectedGroup"])
            clip_analysis["sourceDisplayName"] = f"{video.path.stem}_{label_suffix}{video.path.suffix}"
            expanded.append(
                MediaItem(
                    kind=video.kind,
                    path=video.path,
                    relative=video.relative,
                    width=video.width,
                    height=video.height,
                    duration=video.duration,
                    has_audio=video.has_audio,
                    analysis=clip_analysis,
                )
            )
    return expanded


def video_sample_times(duration: float, max_samples: int) -> list[float]:
    if duration <= 0:
        return [0.0]
    safe_start = 0.5 if duration > 1.0 else 0.0
    safe_end = max(safe_start, duration - 0.5)
    count = max(3, min(max_samples, int(math.ceil(duration / 3.0))))
    if safe_end <= safe_start:
        return [duration / 2]
    return [float(value) for value in np.linspace(safe_start, safe_end, count)]


def analyze_video(item: MediaItem, detectors: dict[str, Any], max_samples: int) -> None:
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


def analyze_image(item: MediaItem, detectors: dict[str, Any]) -> None:
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
        "faceDetection": {
            "noFaceOpeningEligible": focus["faceCount"] == 0,
            "detectors": sorted({str(face.get("detector", "unknown")) for face in faces}),
            "thresholds": {"yunetFaceScore": YUNET_FACE_SCORE_THRESHOLD},
            "faces": faces,
        },
        "visual": metrics,
    }


def discover_media(
    project_root: Path,
    ffprobe: Path,
    excluded_video_stems: set[str] | None = None,
    excluded_image_stems: set[str] | None = None,
) -> tuple[list[MediaItem], list[MediaItem]]:
    source_root = project_root / "source"
    excluded_video_stems = {source_identity_stem(stem) for stem in (excluded_video_stems or set())}
    excluded_image_stems = {source_identity_stem(stem) for stem in (excluded_image_stems or set())}
    videos: list[MediaItem] = []
    images: list[MediaItem] = []
    for path in sorted(source_root.rglob("*"), key=lambda item: natural_key(str(item.relative_to(source_root)))):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        relative = str(path.relative_to(source_root))
        if suffix in VIDEO_EXTENSIONS:
            if source_identity_stem(path.stem) in excluded_video_stems:
                continue
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
            relative_parts = path.relative_to(source_root).parts
            if not relative_parts or relative_parts[0].lower() not in ALLOWED_IMAGE_SOURCE_DIRS:
                continue
            if source_identity_stem(path.stem) in excluded_image_stems:
                continue
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


def duplicate_winner_score(item: MediaItem) -> tuple[int, float]:
    return (REQUIRED_IMAGE_STEM_PRIORITY.get(media_stem(item), 0), image_selection_score(item))


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
        winner = max(group, key=duplicate_winner_score)
        winner.analysis["duplicateGroup"] = {
            "groupId": group_index,
            "groupSize": len(group),
            "selected": True,
            "selectionReason": "required-image-priority" if REQUIRED_IMAGE_STEM_PRIORITY.get(media_stem(winner), 0) else "best-image-score",
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
                    "reason": "near-duplicate",
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
                "selected": str(max(group, key=duplicate_winner_score).path),
                "members": [
                    {
                        "path": str(item.path),
                        "relative": item.relative,
                        "score": round(image_selection_score(item), 5),
                        "requiredPriority": REQUIRED_IMAGE_STEM_PRIORITY.get(media_stem(item), 0),
                    }
                    for item in group
                ],
            }
            for index, group in enumerate(groups, start=1)
            if len(group) > 1
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
            kind = str(item.get("kind") or "")
            if kind:
                identity = source_identity_stem(Path(str(item["path"])).stem)
                cache[f"identity:{kind}:{identity}"] = dict(item["analysis"])
    return cache


def apply_analysis_cache(items: list[MediaItem], cache: dict[str, dict[str, Any]]) -> int:
    applied = 0
    for item in items:
        cached = cache.get(str(item.path.resolve()).lower()) or cache.get(f"identity:{item.kind}:{media_stem(item)}")
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


def audio_focus_intervals(sequence: list[MediaItem]) -> list[tuple[float, float, str]]:
    intervals: list[tuple[float, float, str]] = []
    current_start: float | None = None
    current_end: float | None = None
    current_labels: list[str] = []
    for item in sequence:
        if item.kind != "video":
            continue
        start = max(0.0, float(item.timeline_start))
        end = max(start, float(item.timeline_end))
        if end <= start:
            continue
        label = source_display_name(item)
        if current_start is None or current_end is None:
            current_start = start
            current_end = end
            current_labels = [label]
            continue
        if start <= current_end + AUDIO_FOCUS_MERGE_GAP_SECONDS:
            current_end = max(current_end, end)
            current_labels.append(label)
            continue
        intervals.append((current_start, current_end, " + ".join(current_labels)))
        current_start = start
        current_end = end
        current_labels = [label]
    if current_start is not None and current_end is not None:
        intervals.append((current_start, current_end, " + ".join(current_labels)))
    return intervals


def smoothstep_expr(progress: str) -> str:
    return f"(({progress})*({progress})*(3-2*({progress})))"


def focus_interval_envelope_expr(start: float, end: float, transition_seconds: float) -> str:
    duration = max(0.0, end - start)
    if duration <= 0:
        return "0"
    fade = min(max(0.0, transition_seconds), duration / 2.0)
    start_text = ffmpeg_expr_float(start)
    end_text = ffmpeg_expr_float(end)
    if fade <= 1e-6:
        return f"between(t\\,{start_text}\\,{end_text})"
    fade_text = ffmpeg_expr_float(fade)
    attack_end_text = ffmpeg_expr_float(start + fade)
    release_start_text = ffmpeg_expr_float(end - fade)
    attack = smoothstep_expr(f"(t-{start_text})/{fade_text}")
    release = smoothstep_expr(f"({end_text}-t)/{fade_text}")
    return (
        f"if(lt(t\\,{start_text})\\,0\\,"
        f"if(lt(t\\,{attack_end_text})\\,{attack}\\,"
        f"if(lt(t\\,{release_start_text})\\,1\\,"
        f"if(lt(t\\,{end_text})\\,{release}\\,0))))"
    )


def focus_envelope_expr(intervals: list[tuple[float, float, str]], transition_seconds: float) -> str:
    parts = [
        focus_interval_envelope_expr(start, end, transition_seconds)
        for start, end, _ in intervals
        if end > start
    ]
    if not parts:
        return "0"
    if len(parts) == 1:
        return parts[0]
    return f"min(1\\,{'+'.join(f'({part})' for part in parts)})"


def focus_volume_expr(base_volume: float, multiplier: float, intervals: list[tuple[float, float, str]], maximum: float | None = None) -> str:
    focused_volume = base_volume * multiplier
    if maximum is not None:
        focused_volume = min(maximum, focused_volume)
    base = ffmpeg_expr_float(base_volume)
    if not intervals or abs(focused_volume - base_volume) < 1e-9:
        return base
    delta = ffmpeg_expr_float(focused_volume - base_volume)
    envelope = focus_envelope_expr(intervals, AUDIO_FOCUS_TRANSITION_SECONDS)
    return f"({base})+({delta})*({envelope})"


def background_audio_report_with_focus(
    background_audio_report: dict[str, Any] | None,
    focus_intervals: list[tuple[float, float, str]],
) -> dict[str, Any] | None:
    if background_audio_report is None:
        return None
    report = dict(background_audio_report)
    report["focusMode"] = "all-video-segments"
    report["focusMusicVolumeMultiplier"] = AUDIO_FOCUS_MUSIC_VOLUME_MULTIPLIER
    report["focusOriginalVolumeMultiplier"] = AUDIO_FOCUS_ORIGINAL_VOLUME_MULTIPLIER
    report["focusOriginalVolumeMax"] = AUDIO_FOCUS_ORIGINAL_VOLUME_MAX
    report["focusTransitionSeconds"] = AUDIO_FOCUS_TRANSITION_SECONDS
    report["focusMergeGapSeconds"] = AUDIO_FOCUS_MERGE_GAP_SECONDS
    report["focusCurve"] = "smoothstep"
    report["focusIntervals"] = [
        {
            "timelineStart": round(start, 3),
            "timelineEnd": round(end, 3),
            "sourceLabel": label,
        }
        for start, end, label in focus_intervals
    ]
    return report


def image_clip_frames(item: MediaItem, base_image_frames: int) -> int:
    return base_image_frames


def video_duration_weight(video: MediaItem) -> float:
    analysis = video.analysis if isinstance(video.analysis, dict) else {}
    score = clamp(float(analysis.get("score") or 0.20), 0.05, 1.0)
    relation = analysis.get("personRelation") if isinstance(analysis.get("personRelation"), dict) else {}
    max_faces = float(relation.get("maxFaceCount") or relation.get("faceCountAtSelection") or 0.0)
    face_bonus = 1.0 + min(max_faces, 6.0) * 0.035
    return max(0.01, (score**2.25) * face_bonus)


def distribute_video_frames_by_analysis(videos: list[MediaItem], total_frames: int) -> None:
    if not videos:
        return
    capacities = {id(video): max(1, int(math.floor(video.duration * TARGET_FPS))) for video in videos}
    weights = {id(video): video_duration_weight(video) for video in videos}
    minimum_frames = {
        id(video): min(capacities[id(video)], max(1, int(round(MIN_VARIABLE_VIDEO_SECONDS * TARGET_FPS))))
        for video in videos
    }
    assigned = {id(video): 0 for video in videos}
    if total_frames < sum(minimum_frames.values()):
        total_weight = sum(weights.values()) or 1.0
        remaining = total_frames
        fractional: list[tuple[float, MediaItem]] = []
        for video in videos:
            raw = total_frames * weights[id(video)] / total_weight
            frames = min(capacities[id(video)], max(1, int(math.floor(raw))))
            assigned[id(video)] = frames
            remaining -= frames
            fractional.append((raw - math.floor(raw), video))
        for _, video in sorted(fractional, key=lambda item: item[0], reverse=True):
            if remaining <= 0:
                break
            available = capacities[id(video)] - assigned[id(video)]
            if available <= 0:
                continue
            assigned[id(video)] += 1
            remaining -= 1
    else:
        for video in videos:
            assigned[id(video)] = minimum_frames[id(video)]
        remaining = total_frames - sum(assigned.values())

    while remaining > 0:
        expandable = [video for video in videos if assigned[id(video)] < capacities[id(video)]]
        if not expandable:
            break
        total_weight = sum(weights[id(video)] for video in expandable) or 1.0
        planned: list[tuple[float, int, MediaItem]] = []
        allocated = 0
        for video in expandable:
            raw = remaining * weights[id(video)] / total_weight
            add = min(capacities[id(video)] - assigned[id(video)], int(math.floor(raw)))
            planned.append((raw - math.floor(raw), add, video))
            allocated += add
        if allocated == 0:
            for _, _, video in sorted(planned, key=lambda item: item[0], reverse=True):
                if remaining <= 0:
                    break
                if assigned[id(video)] >= capacities[id(video)]:
                    continue
                assigned[id(video)] += 1
                remaining -= 1
            continue
        for _, add, video in planned:
            assigned[id(video)] += add
            remaining -= add

    for video in videos:
        video.clip_frames = max(1, assigned[id(video)])
        video.clip_duration = round(video.clip_frames / TARGET_FPS, 6)
        video.analysis["durationAllocation"] = {
            "method": "analysis-weighted",
            "score": round(float(video.analysis.get("score") or 0.0), 5) if isinstance(video.analysis, dict) else 0.0,
            "weight": round(weights[id(video)], 6),
            "allocatedSeconds": video.clip_duration,
        }


def apply_manual_video_end_trims(videos: list[MediaItem]) -> None:
    for video in videos:
        trim_seconds = MANUAL_VIDEO_END_TRIM_SECONDS.get(media_stem(video))
        if not trim_seconds or video.clip_frames <= 1:
            continue
        original_source_out = video.source_out
        original_clip_duration = video.clip_duration
        trimmed_duration = max(1 / TARGET_FPS, (video.source_out - video.source_in) - trim_seconds)
        trimmed_frames = max(1, int(math.floor(trimmed_duration * TARGET_FPS + 0.5)))
        video.clip_frames = trimmed_frames
        video.clip_duration = round(trimmed_frames / TARGET_FPS, 6)
        video.source_out = round(min(video.duration, video.source_in + video.clip_duration), 6)
        video.analysis["manualEndTrim"] = {
            "sourceStem": media_stem(video),
            "trimmedSeconds": trim_seconds,
            "originalSourceOut": round(original_source_out, 6),
            "sourceOut": video.source_out,
            "originalClipDuration": round(original_clip_duration, 6),
            "clipDuration": video.clip_duration,
            "method": "trim-clip-end-after-selection",
        }


def apply_manual_video_fixed_clips(videos: list[MediaItem]) -> None:
    for video in videos:
        manual_range = video.analysis.get("manualRangeClip") if isinstance(video.analysis, dict) else None
        if isinstance(manual_range, dict):
            range_in = float(manual_range.get("sourceIn") or 0.0)
            range_out = float(manual_range.get("sourceOut") or range_in)
            fixed_clip = (range_in, max(1 / TARGET_FPS, range_out - range_in))
        else:
            fixed_clip = MANUAL_VIDEO_FIXED_CLIPS.get(media_stem(video))
        if fixed_clip is None:
            continue
        fixed_source_in, fixed_duration = fixed_clip
        source_in = clamp(float(fixed_source_in), 0.0, max(0.0, video.duration - (1 / TARGET_FPS)))
        duration = min(float(fixed_duration), max(1 / TARGET_FPS, video.duration - source_in))
        if source_in <= 1e-6 and duration >= video.duration - (1 / TARGET_FPS):
            fixed_frames = max(1, int(math.ceil(duration * TARGET_FPS)))
        else:
            fixed_frames = max(1, int(math.floor(duration * TARGET_FPS + 0.5)))
        original_source_in = video.source_in
        original_source_out = video.source_out
        original_clip_duration = video.clip_duration
        video.clip_frames = fixed_frames
        video.clip_duration = round(fixed_frames / TARGET_FPS, 6)
        video.source_in = round(source_in, 6)
        video.source_out = round(min(video.duration, video.source_in + video.clip_duration), 6)
        video.analysis["manualFixedClip"] = {
            "sourceStem": media_stem(video),
            "fixedSourceIn": round(source_in, 6),
            "fixedDuration": float(fixed_duration),
            "originalSourceIn": round(original_source_in, 6),
            "originalSourceOut": round(original_source_out, 6),
            "sourceIn": video.source_in,
            "sourceOut": video.source_out,
            "originalClipDuration": round(original_clip_duration, 6),
            "clipDuration": video.clip_duration,
            "method": "fixed-source-range",
        }
        if isinstance(manual_range, dict):
            video.analysis["manualFixedClip"]["manualRangeClip"] = manual_range


def apply_manual_video_keep_last_segments(videos: list[MediaItem]) -> None:
    for video in videos:
        keep_seconds = MANUAL_VIDEO_KEEP_LAST_SECONDS.get(media_stem(video))
        if not keep_seconds or video.clip_frames <= 1:
            continue
        original_source_in = video.source_in
        original_source_out = video.source_out
        original_clip_duration = video.clip_duration
        selected_duration = max(0.0, video.source_out - video.source_in)
        kept_duration = min(keep_seconds, selected_duration)
        kept_frames = max(1, int(math.floor(kept_duration * TARGET_FPS + 0.5)))
        video.clip_frames = kept_frames
        video.clip_duration = round(kept_frames / TARGET_FPS, 6)
        video.source_out = round(original_source_out, 6)
        video.source_in = round(max(0.0, video.source_out - video.clip_duration), 6)
        video.analysis["manualKeepLast"] = {
            "sourceStem": media_stem(video),
            "keepLastSeconds": keep_seconds,
            "originalSourceIn": round(original_source_in, 6),
            "originalSourceOut": round(original_source_out, 6),
            "sourceIn": video.source_in,
            "sourceOut": video.source_out,
            "originalClipDuration": round(original_clip_duration, 6),
            "clipDuration": video.clip_duration,
            "method": "keep-selected-clip-tail",
        }


def requested_fixed_video_frames(video: MediaItem) -> int | None:
    manual_range = video.analysis.get("manualRangeClip") if isinstance(video.analysis, dict) else None
    if isinstance(manual_range, dict):
        range_in = float(manual_range.get("sourceIn") or 0.0)
        range_out = float(manual_range.get("sourceOut") or range_in)
        duration = max(1 / TARGET_FPS, range_out - range_in)
        return max(1, int(math.floor(duration * TARGET_FPS + 0.5)))
    fixed_clip = MANUAL_VIDEO_FIXED_CLIPS.get(media_stem(video))
    if fixed_clip is not None:
        _, fixed_duration = fixed_clip
        duration = min(float(fixed_duration), max(1 / TARGET_FPS, video.duration))
        return max(1, int(math.floor(duration * TARGET_FPS + 0.5)))
    return None


def allocate_durations(videos: list[MediaItem], images: list[MediaItem], target_seconds: float, base_image_seconds: float) -> None:
    target_frames = max(1, int(round(target_seconds * TARGET_FPS)))
    image_frames = max(1, int(math.floor(base_image_seconds * TARGET_FPS + 0.5)))
    fixed_video_frames = {id(video): requested_fixed_video_frames(video) for video in videos}
    fixed_total_frames = sum(frames for frames in fixed_video_frames.values() if frames is not None)
    variable_video_min_total_frames = sum(
        min(
            max(1, int(math.floor(video.duration * TARGET_FPS))),
            max(1, int(round(MIN_VARIABLE_VIDEO_SECONDS * TARGET_FPS))),
        )
        for video in videos
        if fixed_video_frames[id(video)] is None
    )
    target_frames = max(
        target_frames,
        sum(image_clip_frames(image, image_frames) for image in images)
        + fixed_total_frames
        + variable_video_min_total_frames,
    )
    if videos:
        while image_frames > 1 and target_frames - sum(image_clip_frames(image, image_frames) for image in images) < len(videos):
            image_frames -= 1
        variable_video_count = sum(1 for frames in fixed_video_frames.values() if frames is None)
        remaining_video_frames = max(
            variable_video_count,
            target_frames - sum(image_clip_frames(image, image_frames) for image in images) - fixed_total_frames,
        )
    else:
        remaining_video_frames = 0

    for image in images:
        image.clip_frames = image_clip_frames(image, image_frames)
        image.clip_duration = round(image.clip_frames / TARGET_FPS, 6)
    variable_videos = [video for video in videos if fixed_video_frames[id(video)] is None]
    distribute_video_frames_by_analysis(variable_videos, remaining_video_frames)
    for video in videos:
        fixed_frames = fixed_video_frames[id(video)]
        if fixed_frames is not None:
            video.clip_frames = fixed_frames
            video.clip_duration = round(fixed_frames / TARGET_FPS, 6)

    image_total_frames = sum(image.clip_frames for image in images)
    unallocated_frames = max(0, target_frames - image_total_frames - sum(video.clip_frames for video in videos))
    while unallocated_frames > 0:
        expandable = [
            (video, max(1, int(math.floor(video.duration * TARGET_FPS))) - video.clip_frames)
            for video in videos
            if fixed_video_frames[id(video)] is None
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
    apply_manual_video_fixed_clips(videos)
    apply_manual_video_keep_last_segments(videos)
    apply_manual_video_end_trims(videos)
    for image in images:
        image.source_in = 0.0
        image.source_out = image.clip_duration


def image_face_count(item: MediaItem) -> int:
    relation = item.analysis.get("personRelation") if isinstance(item.analysis, dict) else {}
    if not isinstance(relation, dict):
        return 0
    return int(relation.get("faceCount") or 0)


def image_no_face_opening_eligible(item: MediaItem) -> bool:
    if not isinstance(item.analysis, dict):
        return False
    detection = item.analysis.get("faceDetection")
    if not isinstance(detection, dict):
        return False
    return bool(detection.get("noFaceOpeningEligible")) and image_face_count(item) == 0


def find_image_by_stems(images: list[MediaItem], stems: list[str]) -> MediaItem | None:
    wanted = [stem.lower() for stem in stems]
    for stem in wanted:
        for image in images:
            if media_stem(image) == stem:
                return image
    return None


def sort_images_by_stem_order(images: list[MediaItem], stems: list[str]) -> list[MediaItem]:
    order = {stem: index for index, stem in enumerate(stems)}
    return sorted(images, key=lambda item: (order.get(media_stem(item), len(order)), natural_key(media_stem(item))))


def apply_manual_image_render_overrides(images: list[MediaItem]) -> None:
    for image in images:
        if not isinstance(image.analysis, dict):
            continue
        had_manual_crop = "manualCropCenter" in image.analysis or "manualRenderMode" in image.analysis
        override = MANUAL_IMAGE_RENDER_OVERRIDES.get(media_stem(image))
        if had_manual_crop and not override:
            subject = image.analysis.get("subject")
            subject_center = subject.get("cropCenter") if isinstance(subject, dict) else None
            if isinstance(subject_center, list) and len(subject_center) >= 2:
                image.analysis["cropCenter"] = [
                    round(clamp(float(subject_center[0]), 0.0, 1.0), 4),
                    round(clamp(float(subject_center[1]), 0.0, 1.0), 4),
                ]
        image.analysis.pop("manualRenderMode", None)
        image.analysis.pop("manualRenderReason", None)
        image.analysis.pop("manualCropCenter", None)
        if not override:
            continue
        crop_center = override.get("cropCenter")
        if isinstance(crop_center, list) and len(crop_center) >= 2:
            center = [round(clamp(float(crop_center[0]), 0.0, 1.0), 4), round(clamp(float(crop_center[1]), 0.0, 1.0), 4)]
            image.analysis["cropCenter"] = center
            image.analysis["manualCropCenter"] = center
        image.analysis["manualRenderMode"] = str(override.get("renderMode") or "")
        image.analysis["manualRenderReason"] = str(override.get("reason") or "")


def prepare_special_image_sequence(images: list[MediaItem]) -> list[MediaItem]:
    apply_manual_image_render_overrides(images)
    title = find_image_by_stems(images, ["st-707bg", "st-707"])
    final = find_image_by_stems(images, ["st-716"])
    manual_one_minute = [image for image in images if media_stem(image) in MANUAL_ONE_MINUTE_IMAGE_STEMS]
    manual_five_to_seven = [image for image in images if media_stem(image) in MANUAL_FIVE_TO_SEVEN_MINUTE_IMAGE_STEMS]
    manual_after_st738 = [image for image in images if media_stem(image) in MANUAL_AFTER_ST738_IMAGE_STEMS]
    manual_early = [image for image in images if media_stem(image) in MANUAL_EARLY_IMAGE_STEMS]
    manual_distributed = [image for image in images if media_stem(image) in MANUAL_DISTRIBUTED_IMAGE_STEMS]
    manual_late = [image for image in images if media_stem(image) in MANUAL_LATE_IMAGE_STEMS]
    manual_late_intervideo = [image for image in images if media_stem(image) in MANUAL_LATE_INTERVIDEO_IMAGE_STEMS]
    manual_final_photo_opening = [image for image in images if media_stem(image) in MANUAL_FINAL_PHOTO_OPENING_STEMS]
    manual_third_from_last = [image for image in images if media_stem(image) in MANUAL_THIRD_FROM_LAST_IMAGE_STEMS]
    manual_second_from_last = [image for image in images if media_stem(image) in MANUAL_SECOND_FROM_LAST_IMAGE_STEMS]
    reserved = {id(item) for item in [title, final] if item is not None}
    reserved.update(id(image) for image in manual_one_minute)
    reserved.update(id(image) for image in manual_five_to_seven)
    reserved.update(id(image) for image in manual_after_st738)
    reserved.update(id(image) for image in manual_early)
    reserved.update(id(image) for image in manual_distributed)
    reserved.update(id(image) for image in manual_late)
    reserved.update(id(image) for image in manual_late_intervideo)
    reserved.update(id(image) for image in manual_final_photo_opening)
    reserved.update(id(image) for image in manual_third_from_last)
    reserved.update(id(image) for image in manual_second_from_last)
    regular = [image for image in images if id(image) not in reserved]

    no_people_images = [image for image in regular if image_no_face_opening_eligible(image)]
    no_people_ids = {id(image) for image in no_people_images}
    regular = [image for image in regular if id(image) not in no_people_ids]

    for image in images:
        image.analysis.pop("imageRole", None)
        image.analysis.pop("titleOverlay", None)
        image.analysis.pop("introFadeInFromWhite", None)
        image.analysis.pop("introFadeInSeconds", None)
    ordered: list[MediaItem] = []
    if title is not None:
        title.analysis["imageRole"] = "title-card"
        title.analysis["titleOverlay"] = {"date": "2026.05.26", "title": "Birthday"}
        ordered.append(title)
    for image in no_people_images:
        image.analysis["imageRole"] = "no-people-opening"
    ordered.extend(no_people_images)
    for image in manual_after_st738:
        image.analysis["imageRole"] = "after-st738-exception"
    for image in manual_one_minute:
        image.analysis["imageRole"] = "manual-one-minute-group"
    ordered.extend(sort_images_by_stem_order(manual_one_minute, MANUAL_ONE_MINUTE_IMAGE_ORDER))
    for image in manual_early:
        image.analysis["imageRole"] = "manual-early-group"
    ordered.extend(sort_images_by_stem_order(manual_early, MANUAL_EARLY_IMAGE_ORDER))
    for image in manual_five_to_seven:
        image.analysis["imageRole"] = "manual-five-to-seven-minute-group"
    ordered.extend(sort_images_by_stem_order(manual_five_to_seven, MANUAL_FIVE_TO_SEVEN_MINUTE_IMAGE_ORDER))
    ordered.extend(sorted(manual_after_st738, key=lambda item: natural_key(media_stem(item))))
    for image in manual_distributed:
        image.analysis["imageRole"] = "manual-distributed-group"
    ordered.extend(sort_images_by_stem_order(manual_distributed, MANUAL_DISTRIBUTED_IMAGE_ORDER))
    for image in manual_late:
        image.analysis["imageRole"] = "manual-late-group"
    ordered.extend(sort_images_by_stem_order(manual_late, MANUAL_LATE_IMAGE_ORDER))
    for image in manual_late_intervideo:
        image.analysis["imageRole"] = "manual-late-intervideo"
    ordered.extend(sort_images_by_stem_order(manual_late_intervideo, MANUAL_LATE_INTERVIDEO_IMAGE_ORDER))
    for image in manual_final_photo_opening:
        image.analysis["imageRole"] = "manual-final-photo-opening"
    ordered.extend(sort_images_by_stem_order(manual_final_photo_opening, MANUAL_FINAL_PHOTO_OPENING_ORDER))
    for image in manual_third_from_last:
        image.analysis["imageRole"] = "manual-third-from-last-photo"
    ordered.extend(sort_images_by_stem_order(manual_third_from_last, MANUAL_THIRD_FROM_LAST_IMAGE_ORDER))
    for image in manual_second_from_last:
        image.analysis["imageRole"] = "manual-second-from-last-photo"
    ordered.extend(sort_images_by_stem_order(manual_second_from_last, MANUAL_SECOND_FROM_LAST_IMAGE_ORDER))
    ordered.extend(regular)
    if final is not None:
        final.analysis["imageRole"] = "final-fade"
        ordered.append(final)
    return ordered


def reorder_videos_for_timeline(videos: list[MediaItem]) -> list[MediaItem]:
    regular = [video for video in videos if media_stem(video) not in FINAL_TIMELINE_VIDEO_STEMS]
    final = [video for video in videos if media_stem(video) in FINAL_TIMELINE_VIDEO_STEMS]
    order = {stem: index for index, stem in enumerate(FINAL_TIMELINE_VIDEO_ORDER)}
    regular.sort(key=lambda item: natural_key(item.relative))
    final.sort(key=lambda item: (order.get(media_stem(item), len(order)), natural_key(item.relative)))
    return regular + final


def pop_connected_video_block(videos: list[MediaItem]) -> tuple[list[MediaItem], list[MediaItem]]:
    block: list[MediaItem] = []
    rest: list[MediaItem] = []
    for video in videos:
        if media_stem(video) in CONNECTED_VIDEO_BLOCK_STEMS:
            block.append(video)
        else:
            rest.append(video)
    order = {stem: index for index, stem in enumerate(CONNECTED_VIDEO_BLOCK_ORDER)}
    block.sort(key=lambda item: (order.get(media_stem(item), len(order)), natural_key(item.relative)))
    for video in block:
        video.analysis["manualPlacement"] = "connected-full-video-block"
    return rest, block


def manual_range_connected_group(video: MediaItem) -> str | None:
    manual_range = video.analysis.get("manualRangeClip") if isinstance(video.analysis, dict) else None
    if not isinstance(manual_range, dict):
        return None
    group = manual_range.get("connectedGroup")
    return str(group) if group else None


def manual_range_label_suffix(video: MediaItem) -> str | None:
    manual_range = video.analysis.get("manualRangeClip") if isinstance(video.analysis, dict) else None
    if not isinstance(manual_range, dict):
        return None
    suffix = manual_range.get("requestedLabelSuffix")
    return str(suffix) if suffix else None


def connected_range_group_items(videos: list[MediaItem], group: str) -> list[MediaItem]:
    return [video for video in videos if manual_range_connected_group(video) == group]


def apply_manual_video_block_swaps(sequence: list[MediaItem]) -> None:
    for target_stem, target_suffix, previous_group in MANUAL_VIDEO_BLOCK_SWAPS:
        target_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "video"
                and media_stem(item) == target_stem
                and manual_range_label_suffix(item) == target_suffix
            ),
            None,
        )
        if target_index is None:
            continue
        group_index = next(
            (
                index
                for index in range(target_index - 1, -1, -1)
                if sequence[index].kind == "video" and manual_range_connected_group(sequence[index]) == previous_group
            ),
            None,
        )
        if group_index is None:
            continue
        block_start = group_index
        while block_start > 0 and manual_range_connected_group(sequence[block_start - 1]) == previous_group:
            block_start -= 1
        block_end = group_index + 1
        while block_end < target_index and manual_range_connected_group(sequence[block_end]) == previous_group:
            block_end += 1
        if block_start >= block_end or block_end > target_index:
            continue
        target = sequence[target_index]
        block = sequence[block_start:block_end]
        middle = sequence[block_end:target_index]
        target.analysis["manualSequenceSwap"] = {
            "method": "swap-with-previous-video-block",
            "previousConnectedGroup": previous_group,
        }
        for item in block:
            item.analysis["manualSequenceSwap"] = {
                "method": "swap-with-next-video",
                "swappedWithStem": target_stem,
                "swappedWithSuffix": target_suffix,
            }
        sequence[block_start : target_index + 1] = [target] + middle + block


def apply_manual_video_relocations(sequence: list[MediaItem]) -> None:
    for moving_stem, before_group, placement in MANUAL_VIDEO_RELOCATIONS:
        moving_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "video" and media_stem(item) == moving_stem
            ),
            None,
        )
        target_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "video" and manual_range_connected_group(item) == before_group
            ),
            None,
        )
        if moving_index is None or target_index is None:
            continue
        moving_item = sequence.pop(moving_index)
        if moving_index < target_index:
            target_index -= 1
        while target_index > 0 and manual_range_connected_group(sequence[target_index - 1]) == before_group:
            target_index -= 1
        moving_item.analysis["manualPlacement"] = placement
        moving_item.analysis["manualSequenceMove"] = {
            "method": "move-before-connected-video-block",
            "targetConnectedGroup": before_group,
        }
        sequence.insert(target_index, moving_item)


def apply_manual_video_stem_relocations(sequence: list[MediaItem]) -> None:
    for rule in MANUAL_VIDEO_STEM_RELOCATIONS:
        moving_stem = str(rule["movingStem"])
        before_stem = str(rule["beforeStem"])
        moving_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "video" and media_stem(item) == moving_stem
            ),
            None,
        )
        target_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "video" and media_stem(item) == before_stem
            ),
            None,
        )
        if moving_index is None or target_index is None:
            continue
        moving_item = sequence.pop(moving_index)
        if moving_index < target_index:
            target_index -= 1
        placement = str(rule["placement"])
        moving_item.analysis["manualPlacement"] = placement
        moving_item.analysis["manualSequenceMove"] = {
            "method": "move-before-video",
            "targetStem": before_stem,
        }
        sequence.insert(target_index, moving_item)


def apply_manual_video_clip_adjacencies(sequence: list[MediaItem]) -> None:
    for rule in MANUAL_VIDEO_CLIP_ADJACENCIES:
        moving_stem = str(rule["movingStem"])
        moving_suffix = str(rule["movingSuffix"])
        after_stem = str(rule["afterStem"])
        after_suffix = str(rule["afterSuffix"])
        moving_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "video"
                and media_stem(item) == moving_stem
                and manual_range_label_suffix(item) == moving_suffix
            ),
            None,
        )
        target_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "video"
                and media_stem(item) == after_stem
                and manual_range_label_suffix(item) == after_suffix
            ),
            None,
        )
        if moving_index is None or target_index is None:
            continue
        moving_item = sequence.pop(moving_index)
        if moving_index < target_index:
            target_index -= 1
        placement = str(rule["placement"])
        moving_item.analysis["manualPlacement"] = placement
        moving_item.analysis["manualSequenceMove"] = {
            "method": "move-after-video-clip",
            "targetStem": after_stem,
            "targetSuffix": after_suffix,
        }
        sequence.insert(target_index + 1, moving_item)


def apply_manual_image_relocations(sequence: list[MediaItem]) -> None:
    for rule in MANUAL_IMAGE_RELOCATIONS:
        image_stem = str(rule["imageStem"])
        moving_index = next(
            (
                index
                for index, item in enumerate(sequence)
                if item.kind == "image" and media_stem(item) == image_stem
            ),
            None,
        )
        if moving_index is None:
            continue
        moving_item = sequence.pop(moving_index)
        mode = str(rule["mode"])
        insert_index: int | None = None
        if mode == "before-image":
            target_stem = str(rule["targetStem"])
            insert_index = next(
                (
                    index
                    for index, item in enumerate(sequence)
                    if item.kind == "image" and media_stem(item) == target_stem
                ),
                None,
            )
        elif mode == "after-image":
            target_stem = str(rule["targetStem"])
            target_index = next(
                (
                    index
                    for index, item in enumerate(sequence)
                    if item.kind == "image" and media_stem(item) == target_stem
                ),
                None,
            )
            insert_index = target_index + 1 if target_index is not None else None
        elif mode == "after-connected-video-group":
            target_group = str(rule["targetGroup"])
            target_indices = [
                index
                for index, item in enumerate(sequence)
                if item.kind == "video" and manual_range_connected_group(item) == target_group
            ]
            insert_index = (max(target_indices) + 1) if target_indices else None
        elif mode == "before-video":
            target_stem = str(rule["targetStem"])
            target_suffix = rule.get("targetSuffix")
            insert_index = next(
                (
                    index
                    for index, item in enumerate(sequence)
                    if item.kind == "video"
                    and media_stem(item) == target_stem
                    and (target_suffix is None or manual_range_label_suffix(item) == str(target_suffix))
                ),
                None,
            )
        elif mode == "after-video":
            target_stem = str(rule["targetStem"])
            target_suffix = rule.get("targetSuffix")
            target_index = next(
                (
                    index
                    for index, item in enumerate(sequence)
                    if item.kind == "video"
                    and media_stem(item) == target_stem
                    and (target_suffix is None or manual_range_label_suffix(item) == str(target_suffix))
                ),
                None,
            )
            insert_index = target_index + 1 if target_index is not None else None
        if insert_index is None:
            sequence.insert(moving_index, moving_item)
            continue
        placement = str(rule["placement"])
        moving_item.analysis["manualPlacement"] = placement
        moving_item.analysis["manualImageMove"] = {
            "method": mode,
            "placement": placement,
        }
        sequence.insert(insert_index, moving_item)


def video_separated_image_runs(sequence: list[MediaItem]) -> list[tuple[int, int, int, int]]:
    runs: list[tuple[int, int, int, int]] = []
    index = 0
    while index < len(sequence):
        if sequence[index].kind != "video":
            index += 1
            continue
        left_video_index = index
        start = index + 1
        end = start
        while end < len(sequence) and sequence[end].kind == "image":
            end += 1
        if end > start and end < len(sequence) and sequence[end].kind == "video":
            runs.append((left_video_index, start, end, end))
        index = max(end, index + 1)
    return runs


def can_move_image_to_fill_video_gap(item: MediaItem) -> bool:
    if item.kind != "image":
        return False
    role = item.analysis.get("imageRole") if isinstance(item.analysis, dict) else None
    placement = item.analysis.get("manualPlacement") if isinstance(item.analysis, dict) else None
    if role:
        return False
    if placement and placement != "supplement-single-image-video-gap":
        return False
    return True


def find_single_image_video_gap(sequence: list[MediaItem]) -> tuple[int, int] | None:
    for _, start, end, _ in video_separated_image_runs(sequence):
        if end - start == 1:
            return start, end
    return None


def find_nearest_donor_for_single_image_gap(
    sequence: list[MediaItem],
    gap_start: int,
    gap_end: int,
) -> int | None:
    candidates: list[tuple[int, int]] = []
    for _, start, end, _ in video_separated_image_runs(sequence):
        if start == gap_start and end == gap_end:
            continue
        if end - start <= 2:
            continue
        eligible = [index for index in range(start, end) if can_move_image_to_fill_video_gap(sequence[index])]
        if not eligible:
            continue
        if end <= gap_start:
            donor_index = eligible[-1]
            distance = gap_start - donor_index
        elif start >= gap_end:
            donor_index = eligible[0]
            distance = donor_index - gap_end
        else:
            continue
        candidates.append((distance, donor_index))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def ensure_minimum_two_images_between_videos(sequence: list[MediaItem]) -> None:
    for _ in range(50):
        gap = find_single_image_video_gap(sequence)
        if gap is None:
            return
        gap_start, gap_end = gap
        donor_index = find_nearest_donor_for_single_image_gap(sequence, gap_start, gap_end)
        if donor_index is None:
            return
        donor = sequence.pop(donor_index)
        insert_index = gap_end
        if donor_index < insert_index:
            insert_index -= 1
        donor.analysis["manualPlacement"] = "supplement-single-image-video-gap"
        donor.analysis["manualImageMove"] = {
            "method": "ensure-minimum-two-images-between-videos",
            "targetGapImageStem": media_stem(sequence[insert_index - 1]) if insert_index > 0 else None,
        }
        sequence.insert(insert_index, donor)


def append_with_st738_exception(sequence: list[MediaItem], prefix_images: list[MediaItem], after_st738_images: list[MediaItem]) -> None:
    inserted = False
    for image in prefix_images:
        sequence.append(image)
        if media_stem(image) == "st-738":
            sequence.extend(after_st738_images)
            inserted = True
    if not inserted:
        sequence.extend(after_st738_images)


def append_due_group(sequence: list[MediaItem], pending_group: list[MediaItem], cursor_frames: int, target_seconds: float) -> bool:
    if pending_group and cursor_frames >= int(round(target_seconds * TARGET_FPS)):
        sequence.extend(pending_group)
        pending_group.clear()
        return True
    return False


def append_due_distributed_images(
    sequence: list[MediaItem],
    images: list[MediaItem],
    next_index: int,
    cursor_frames: int,
    target_seconds: list[float],
) -> int:
    while next_index < len(images):
        target_index = min(next_index, len(target_seconds) - 1)
        target_frames = int(round(target_seconds[target_index] * TARGET_FPS))
        if cursor_frames < target_frames:
            break
        image = images[next_index]
        image.analysis["manualTargetSeconds"] = target_seconds[target_index]
        sequence.append(image)
        cursor_frames += max(1, image.clip_frames)
        next_index += 1
    return next_index


def append_due_targeted_images(
    sequence: list[MediaItem],
    images: list[MediaItem],
    next_index: int,
    cursor_frames: int,
    target_seconds: list[float],
    role_label: str,
) -> int:
    while next_index < len(images):
        target_index = min(next_index, len(target_seconds) - 1)
        target_frames = int(round(target_seconds[target_index] * TARGET_FPS))
        if cursor_frames < target_frames:
            break
        image = images[next_index]
        image.analysis["manualTargetSeconds"] = target_seconds[target_index]
        image.analysis["manualPlacement"] = role_label
        sequence.append(image)
        cursor_frames += max(1, image.clip_frames)
        next_index += 1
    return next_index


def append_after_video_images(
    sequence: list[MediaItem],
    images: list[MediaItem],
    video_stem: str,
    cursor_frames: int,
) -> int:
    for anchor_stem, image_stem in MANUAL_LATE_INTERVIDEO_IMAGE_AFTER_VIDEO:
        if anchor_stem != video_stem:
            continue
        for image_index, image in enumerate(images):
            if media_stem(image) != image_stem:
                continue
            image.analysis["manualPlacement"] = f"after-video:{video_stem}"
            sequence.append(image)
            cursor_frames += max(1, image.clip_frames)
            images.pop(image_index)
            break
    return cursor_frames


def interleave_media(videos: list[MediaItem], images: list[MediaItem]) -> list[MediaItem]:
    sequence: list[MediaItem] = []
    videos = reorder_videos_for_timeline(videos)
    videos, connected_video_block = pop_connected_video_block(videos)
    prefix_images = [image for image in images if image.analysis.get("imageRole") in {"title-card", "no-people-opening"}]
    after_st738_images = [image for image in images if image.analysis.get("imageRole") == "after-st738-exception"]
    one_minute_images = [image for image in images if image.analysis.get("imageRole") == "manual-one-minute-group"]
    early_images = [image for image in images if image.analysis.get("imageRole") == "manual-early-group"]
    five_to_seven_images = [image for image in images if image.analysis.get("imageRole") == "manual-five-to-seven-minute-group"]
    distributed_images = [image for image in images if image.analysis.get("imageRole") == "manual-distributed-group"]
    late_images = [image for image in images if image.analysis.get("imageRole") == "manual-late-group"]
    late_intervideo_images = [image for image in images if image.analysis.get("imageRole") == "manual-late-intervideo"]
    final_photo_opening_images = [image for image in images if image.analysis.get("imageRole") == "manual-final-photo-opening"]
    third_from_last_images = [image for image in images if image.analysis.get("imageRole") == "manual-third-from-last-photo"]
    second_from_last_images = [image for image in images if image.analysis.get("imageRole") == "manual-second-from-last-photo"]
    suffix_images = [image for image in images if image.analysis.get("imageRole") == "final-fade"]
    middle_images = [
        image
        for image in images
        if image.analysis.get("imageRole")
        not in {
            "title-card",
            "no-people-opening",
            "after-st738-exception",
            "manual-one-minute-group",
            "manual-early-group",
            "manual-five-to-seven-minute-group",
            "manual-distributed-group",
            "manual-late-group",
            "manual-late-intervideo",
            "manual-final-photo-opening",
            "manual-third-from-last-photo",
            "manual-second-from-last-photo",
            "final-fade",
        }
    ]
    append_with_st738_exception(sequence, prefix_images, after_st738_images)
    sequence.extend(one_minute_images)
    cursor_frames = sum(max(1, item.clip_frames) for item in sequence)
    early_index = append_due_targeted_images(
        sequence,
        early_images,
        0,
        cursor_frames,
        MANUAL_EARLY_IMAGE_TARGET_SECONDS,
        "early-front-half",
    )
    late_index = append_due_targeted_images(
        sequence,
        late_images,
        0,
        cursor_frames,
        MANUAL_LATE_IMAGE_TARGET_SECONDS,
        "late-back-half",
    )
    distributed_index = append_due_distributed_images(
        sequence,
        distributed_images,
        0,
        cursor_frames,
        MANUAL_DISTRIBUTED_IMAGE_TARGET_SECONDS,
    )
    cursor_frames = sum(max(1, item.clip_frames) for item in sequence)
    image_index = 0
    appended_connected_range_groups: set[str] = set()
    for index, video in enumerate(videos, start=1):
        connected_group = manual_range_connected_group(video)
        if connected_group and connected_group in appended_connected_range_groups:
            continue
        if connected_group:
            connected_items = connected_range_group_items(videos, connected_group)
            for connected_item in connected_items:
                connected_item.analysis["manualPlacement"] = "connected-range-video-block"
            sequence.extend(connected_items)
            cursor_frames += sum(max(1, connected_item.clip_frames) for connected_item in connected_items)
            appended_connected_range_groups.add(connected_group)
        else:
            sequence.append(video)
            cursor_frames += max(1, video.clip_frames)
            cursor_frames = append_after_video_images(
                sequence,
                late_intervideo_images,
                media_stem(video),
                cursor_frames,
            )
        early_index = append_due_targeted_images(
            sequence,
            early_images,
            early_index,
            cursor_frames,
            MANUAL_EARLY_IMAGE_TARGET_SECONDS,
            "early-front-half",
        )
        append_due_group(sequence, five_to_seven_images, cursor_frames, 300.0)
        late_index = append_due_targeted_images(
            sequence,
            late_images,
            late_index,
            cursor_frames,
            MANUAL_LATE_IMAGE_TARGET_SECONDS,
            "late-back-half",
        )
        distributed_index = append_due_distributed_images(
            sequence,
            distributed_images,
            distributed_index,
            cursor_frames,
            MANUAL_DISTRIBUTED_IMAGE_TARGET_SECONDS,
        )
        cursor_frames = sum(max(1, item.clip_frames) for item in sequence)
        target_image_count = round(index * len(middle_images) / len(videos)) if videos else len(middle_images)
        while image_index < target_image_count and image_index < len(middle_images):
            sequence.append(middle_images[image_index])
            cursor_frames += max(1, middle_images[image_index].clip_frames)
            early_index = append_due_targeted_images(
                sequence,
                early_images,
                early_index,
                cursor_frames,
                MANUAL_EARLY_IMAGE_TARGET_SECONDS,
                "early-front-half",
            )
            append_due_group(sequence, five_to_seven_images, cursor_frames, 300.0)
            late_index = append_due_targeted_images(
                sequence,
                late_images,
                late_index,
                cursor_frames,
                MANUAL_LATE_IMAGE_TARGET_SECONDS,
                "late-back-half",
            )
            distributed_index = append_due_distributed_images(
                sequence,
                distributed_images,
                distributed_index,
                cursor_frames,
                MANUAL_DISTRIBUTED_IMAGE_TARGET_SECONDS,
            )
            cursor_frames = sum(max(1, item.clip_frames) for item in sequence)
            image_index += 1
    if early_index < len(early_images):
        sequence.extend(early_images[early_index:])
    if five_to_seven_images:
        sequence.extend(five_to_seven_images)
    if distributed_index < len(distributed_images):
        sequence.extend(distributed_images[distributed_index:])
    if late_index < len(late_images):
        sequence.extend(late_images[late_index:])
    sequence.extend(late_intervideo_images)
    remaining_middle_images = middle_images[image_index:]
    bridge_images: list[MediaItem] = []
    if third_from_last_images and suffix_images and not second_from_last_images:
        if remaining_middle_images:
            bridge_images = [remaining_middle_images[-1]]
            remaining_middle_images = remaining_middle_images[:-1]
        else:
            for bridge_index in range(len(sequence) - 1, -1, -1):
                candidate = sequence[bridge_index]
                if candidate.kind != "image":
                    continue
                role = candidate.analysis.get("imageRole") if isinstance(candidate.analysis, dict) else None
                if role in {"title-card", "final-fade", "manual-third-from-last-photo"}:
                    continue
                bridge_images = [sequence.pop(bridge_index)]
                break
    sequence.extend(connected_video_block)
    sequence.extend(final_photo_opening_images)
    sequence.extend(remaining_middle_images)
    sequence.extend(third_from_last_images)
    sequence.extend(bridge_images)
    sequence.extend(second_from_last_images)
    sequence.extend(suffix_images)
    apply_manual_video_block_swaps(sequence)
    apply_manual_video_relocations(sequence)
    apply_manual_video_stem_relocations(sequence)
    apply_manual_video_clip_adjacencies(sequence)
    apply_manual_image_relocations(sequence)
    ensure_minimum_two_images_between_videos(sequence)
    assign_visual_transition_timeline(sequence)
    return sequence


def media_clip_frames(item: MediaItem) -> int:
    if item.clip_frames <= 0:
        item.clip_frames = max(1, int(math.floor(item.clip_duration * TARGET_FPS + 0.5)))
        item.clip_duration = round(item.clip_frames / TARGET_FPS, 6)
    return max(1, item.clip_frames)


def visual_dissolve_frames(previous: MediaItem, current: MediaItem) -> int:
    if previous.kind != "image" and current.kind != "image":
        return 0
    requested = max(1, int(round(VISUAL_IMAGE_DISSOLVE_SECONDS * TARGET_FPS)))
    shortest = min(media_clip_frames(previous), media_clip_frames(current))
    maximum = max(0, int(math.floor(shortest * VISUAL_IMAGE_DISSOLVE_MAX_FRACTION)))
    return min(requested, maximum)


def visual_transition_report(sequence: list[MediaItem]) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for index in range(1, len(sequence)):
        frames = visual_dissolve_frames(sequence[index - 1], sequence[index])
        if frames <= 0:
            continue
        duration = frames / TARGET_FPS
        transitions.append(
            {
                "type": "dissolve",
                "transition": "fade",
                "fromIndex": index,
                "toIndex": index + 1,
                "fromSourceLabel": source_display_name(sequence[index - 1]),
                "toSourceLabel": source_display_name(sequence[index]),
                "timelineStart": round(sequence[index].timeline_start, 6),
                "timelineEnd": round(sequence[index].timeline_start + duration, 6),
                "duration": round(duration, 6),
                "durationFrames": frames,
                "reason": "image-boundary",
            }
        )
    return transitions


def assign_visual_transition_timeline(sequence: list[MediaItem]) -> None:
    time_cursor_frames = 0
    for index, item in enumerate(sequence):
        if index > 0:
            time_cursor_frames -= visual_dissolve_frames(sequence[index - 1], item)
            time_cursor_frames = max(0, time_cursor_frames)
        frames = media_clip_frames(item)
        item.timeline_start = round(time_cursor_frames / TARGET_FPS, 6)
        time_cursor_frames += frames
        item.timeline_end = round(time_cursor_frames / TARGET_FPS, 6)


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


def video_filter(item: MediaItem, width: int, height: int, fps: int, show_source_label: bool = False) -> str:
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        look_filter(item),
    ]
    if show_source_label:
        filters.append(source_label_filter(item, width))
    filters.extend([f"fps={fps}", "setsar=1", "format=yuv420p"])
    return ",".join(filters)


def source_label_filter(item: MediaItem, width: int) -> str:
    label = ffmpeg_drawtext_escape(source_display_name(item))
    font_size = max(14, round(width * 0.020))
    border = max(5, round(width * 0.009))
    x = max(10, round(width * 0.018))
    y = max(8, round(width * 0.024))
    return (
        "drawtext=fontfile='C\\:/Windows/Fonts/segoeui.ttf'"
        f":text='{label}'"
        f":x={x}:y={y}:fontsize={font_size}"
        ":fontcolor=0x3F332D"
        ":box=1:boxcolor=0xFFFAF1@0.82"
        f":boxborderw={border}"
    )


def continuous_progress(value: float) -> float:
    return clamp(value, 0.0, 1.0)


def smoothstep_value(value: float) -> float:
    progress = clamp(value, 0.0, 1.0)
    return progress * progress * (3.0 - 2.0 * progress)


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


def is_portrait_image(image: np.ndarray) -> bool:
    source_height, source_width = image.shape[:2]
    return source_height > source_width


def should_render_portrait_letterbox(item: MediaItem, image: np.ndarray) -> bool:
    if not is_portrait_image(image):
        return False
    if isinstance(item.analysis, dict) and item.analysis.get("manualRenderMode") == "landscape-crop":
        return False
    return True


def render_portrait_letterbox_frame(
    image: np.ndarray,
    *,
    width: int,
    height: int,
    progress: float,
    motion_mode: str,
) -> np.ndarray:
    source_height, source_width = image.shape[:2]
    height_fill_scale = height / max(source_height, 1)
    continuous = continuous_progress(progress)
    if motion_mode == "zoom-in":
        motion_scale = 1.0 + PORTRAIT_LETTERBOX_ZOOM_AMOUNT * continuous
    elif motion_mode == "zoom-out":
        motion_scale = 1.0 + PORTRAIT_LETTERBOX_ZOOM_AMOUNT * (1.0 - continuous)
    else:
        motion_scale = 1.0
    scale = height_fill_scale * motion_scale
    resized_width = max(1, int(round(source_width * scale)))
    resized_height = max(height, int(round(source_height * scale)))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_CUBIC)
    frame = np.full((height, width, 3), 255, dtype=np.uint8)
    if resized_height > height:
        crop_y = (resized_height - height) // 2
        resized = resized[crop_y : crop_y + height, :]
        resized_height = height
    if resized_width > width:
        crop_x = (resized_width - width) // 2
        resized = resized[:, crop_x : crop_x + width]
        resized_width = width
    x = (width - resized_width) // 2
    frame[0:height, x : x + resized_width] = resized
    return frame


def apply_linear_fade_to_white(frame: np.ndarray, progress: float) -> np.ndarray:
    alpha = clamp(progress, 0.0, 1.0)
    return np.clip(frame.astype(np.float32) * alpha + 255.0 * (1.0 - alpha), 0, 255).astype(np.uint8)


def apply_portrait_letterbox_edge_fades(frame: np.ndarray, elapsed: float, duration: float) -> np.ndarray:
    fade_seconds = min(PORTRAIT_LETTERBOX_FADE_SECONDS, max(0.0, duration / 2.0))
    if fade_seconds <= 1e-6:
        return frame
    fade_in = clamp(elapsed / fade_seconds, 0.0, 1.0)
    fade_out = clamp((duration - elapsed) / fade_seconds, 0.0, 1.0)
    return apply_linear_fade_to_white(frame, min(fade_in, fade_out))


def draw_title_overlay(frame: np.ndarray, overlay: dict[str, Any]) -> np.ndarray:
    height, width = frame.shape[:2]
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    title = str(overlay.get("title") or "Birthday")
    date = str(overlay.get("date") or "2026.05.26")
    title_font_path = Path(r"C:\Windows\Fonts\segoeprb.ttf")
    date_font_path = Path(r"C:\Windows\Fonts\segoeui.ttf")
    title_size_px = max(44, round(width * 0.062))
    date_size_px = max(20, round(width * 0.027))
    try:
        title_font = ImageFont.truetype(str(title_font_path), title_size_px)
        date_font = ImageFont.truetype(str(date_font_path), date_size_px)
    except OSError:
        title_font = ImageFont.load_default()
        date_font = ImageFont.load_default()

    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    date_bbox = draw.textbbox((0, 0), date, font=date_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    date_w = date_bbox[2] - date_bbox[0]
    date_h = date_bbox[3] - date_bbox[1]
    pad_x = max(28, round(width * 0.035))
    pad_top = max(18, round(height * 0.037))
    pad_bottom = max(24, round(height * 0.044))
    gap = max(9, round(height * 0.018))
    accent_h = max(3, round(height * 0.006))
    box_width = max(title_w, date_w) + pad_x * 2
    box_height = pad_top + date_h + gap + title_h + pad_bottom
    margin_x = max(34, round(width * 0.046))
    margin_y = max(28, round(height * 0.065))
    x0 = max(12, width - box_width - margin_x)
    y0 = margin_y
    x1 = min(width - 12, x0 + box_width)
    y1 = min(height - 12, y0 + box_height)

    shadow_offset = max(4, round(width * 0.005))
    radius = max(8, round(width * 0.014))
    draw.rounded_rectangle(
        (x0 + shadow_offset, y0 + shadow_offset, x1 + shadow_offset, y1 + shadow_offset),
        radius=radius,
        fill=(80, 58, 48, 48),
    )
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=(255, 250, 241, 218))
    draw.rectangle((x0 + pad_x, y0 + accent_h, x1 - pad_x, y0 + accent_h * 2), fill=(225, 146, 165, 185))

    text_right = x1 - pad_x
    date_visible_top = y0 + pad_top
    title_visible_top = date_visible_top + date_h + gap
    date_x = text_right - date_w - date_bbox[0]
    date_y = date_visible_top - date_bbox[1]
    title_x = text_right - title_w - title_bbox[0]
    title_y = title_visible_top - title_bbox[1]
    draw.text((date_x, date_y), date, font=date_font, fill=(126, 92, 83, 225))
    draw.text((title_x, title_y), title, font=title_font, fill=(91, 63, 56, 245))

    composited = Image.alpha_composite(image, layer).convert("RGB")
    return cv2.cvtColor(np.array(composited), cv2.COLOR_RGB2BGR)


def draw_intro_title_frame(
    width: int,
    height: int,
    progress: float,
    overlay: dict[str, Any],
    background_frame: np.ndarray | None = None,
) -> np.ndarray:
    if background_frame is None:
        image = Image.new("RGB", (width, height), (255, 255, 255))
    else:
        reveal_start = INTRO_TITLE_IMAGE_REVEAL_START_SECONDS / 5.0
        reveal_duration = max(1e-6, INTRO_TITLE_IMAGE_REVEAL_SECONDS / 5.0)
        reveal_progress = smoothstep_value((progress - reveal_start) / reveal_duration)
        revealed = apply_linear_fade_to_white(background_frame, reveal_progress)
        image = Image.fromarray(cv2.cvtColor(revealed, cv2.COLOR_BGR2RGB))
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    title = str(overlay.get("title") or "Birthday")
    date = str(overlay.get("date") or "2026.05.26")
    title_font_path = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    date_font_path = Path(r"C:\Windows\Fonts\segoeui.ttf")
    title_size_px = max(78, round(width * 0.145))
    date_size_px = max(28, round(width * 0.050))
    try:
        title_font = ImageFont.truetype(str(title_font_path), title_size_px)
        date_font = ImageFont.truetype(str(date_font_path), date_size_px)
    except OSError:
        title_font = ImageFont.load_default()
        date_font = ImageFont.load_default()

    text_start = INTRO_TITLE_TEXT_APPEAR_START_SECONDS / 5.0
    fade_in_duration = max(1e-6, INTRO_TITLE_TEXT_FADE_IN_SECONDS / 5.0)
    hold_end = (
        INTRO_TITLE_TEXT_APPEAR_START_SECONDS
        + INTRO_TITLE_TEXT_FADE_IN_SECONDS
        + INTRO_TITLE_TEXT_HOLD_SECONDS
    ) / 5.0
    fade_out_duration = max(1e-6, INTRO_TITLE_TEXT_FADE_OUT_SECONDS / 5.0)
    fade_in_alpha = smoothstep_value((progress - text_start) / fade_in_duration)
    fade_out_alpha = 1.0 - smoothstep_value((progress - hold_end) / fade_out_duration)
    alpha = int(round(235 * clamp(fade_in_alpha * fade_out_alpha, 0.0, 1.0)))
    title_fill = (84, 65, 58, alpha)
    date_fill = (132, 104, 96, max(0, int(round(alpha * 0.86))))

    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    date_bbox = draw.textbbox((0, 0), date, font=date_font)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    date_w = date_bbox[2] - date_bbox[0]
    date_h = date_bbox[3] - date_bbox[1]
    gap = max(20, round(height * 0.045))
    block_h = title_h + gap + date_h
    title_x = (width - title_w) / 2.0 - title_bbox[0]
    title_y = (height - block_h) / 2.0 - title_bbox[1]
    date_x = (width - date_w) / 2.0 - date_bbox[0]
    date_y = title_y + title_bbox[1] + title_h + gap - date_bbox[1]

    if alpha > 0:
        draw.text((title_x, title_y), title, font=title_font, fill=title_fill)
        draw.text((date_x, date_y), date, font=date_font, fill=date_fill)

    composited = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    return cv2.cvtColor(np.array(composited), cv2.COLOR_RGB2BGR)


def draw_source_label(frame: np.ndarray, label: str) -> np.ndarray:
    if not label:
        return frame
    height, width = frame.shape[:2]
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    font_path = Path(r"C:\Windows\Fonts\segoeui.ttf")
    font_size = max(14, round(width * 0.020))
    max_width = int(width * 0.72)
    try:
        font = ImageFont.truetype(str(font_path), font_size)
        while font_size > 10 and draw.textbbox((0, 0), label, font=font)[2] > max_width:
            font_size -= 1
            font = ImageFont.truetype(str(font_path), font_size)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x = max(7, round(width * 0.009))
    pad_y = max(5, round(height * 0.010))
    x0 = max(10, round(width * 0.018))
    y0 = max(8, round(height * 0.024))
    x1 = x0 + text_w + pad_x * 2
    y1 = y0 + text_h + pad_y * 2
    radius = max(4, round(width * 0.006))
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=(255, 250, 241, 214))
    draw.text((x0 + pad_x, y0 + pad_y), label, font=font, fill=(63, 51, 45, 238))

    composited = Image.alpha_composite(image, layer).convert("RGB")
    return cv2.cvtColor(np.array(composited), cv2.COLOR_RGB2BGR)


def apply_linear_fade_to_black(frame: np.ndarray, progress: float) -> np.ndarray:
    factor = 1.0 - clamp(progress, 0.0, 1.0)
    return np.clip(frame.astype(np.float32) * factor, 0, 255).astype(np.uint8)


def apply_linear_fade_to_white_out(frame: np.ndarray, progress: float) -> np.ndarray:
    return apply_linear_fade_to_white(frame, 1.0 - clamp(progress, 0.0, 1.0))


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
    show_source_label: bool = False,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, item.clip_frames or int(math.floor(item.clip_duration * fps + 0.5)))
    duration = total_frames / fps
    start_center, end_center = image_motion_centers(item, index)
    image_role = str(item.analysis.get("imageRole") or "normal") if isinstance(item.analysis, dict) else "normal"
    if image_role == "title-card":
        motion_mode = "title-card"
    elif image_role == "final-fade":
        motion_mode = "fade-out"
    else:
        motion_mode = "zoom-in" if index % 2 == 0 else "zoom-out"
    image = open_image_bgr(item.path)
    portrait_letterbox = False if image_role == "title-card" else should_render_portrait_letterbox(item, image)
    video_filter_chain = "format=yuv420p" if image_role == "title-card" or portrait_letterbox else f"{look_filter(item)},format=yuv420p"
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
        f"[0:v]{video_filter_chain}[v];[1:a]atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[a]",
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
            frame_progress = 0.0 if image_role in {"title-card", "final-fade"} else progress
            if image_role == "title-card":
                overlay = item.analysis.get("titleOverlay") if isinstance(item.analysis, dict) else {}
                title_background = render_ken_burns_frame(
                    image,
                    width=width,
                    height=height,
                    progress=0.0,
                    start_center=start_center,
                    end_center=end_center,
                    motion_mode="none",
                )
                frame = draw_intro_title_frame(
                    width,
                    height,
                    progress,
                    overlay if isinstance(overlay, dict) else {},
                    title_background,
                )
            elif portrait_letterbox:
                frame = render_portrait_letterbox_frame(
                    image,
                    width=width,
                    height=height,
                    progress=frame_progress,
                    motion_mode=motion_mode,
                )
                if image_role not in {"title-card", "final-fade"}:
                    frame = apply_portrait_letterbox_edge_fades(frame, frame_index / fps, duration)
            else:
                frame = render_ken_burns_frame(
                    image,
                    width=width,
                    height=height,
                    progress=frame_progress,
                    start_center=start_center,
                    end_center=end_center,
                    motion_mode=motion_mode,
                )
            if image_role == "final-fade":
                elapsed = frame_index / fps
                fade_seconds = min(FINAL_STILL_FADE_SECONDS, duration)
                fade_progress = clamp((elapsed - max(0.0, duration - fade_seconds)) / fade_seconds, 0.0, 1.0)
                frame = apply_linear_fade_to_white_out(frame, smoothstep_value(fade_progress))
            elif item.analysis.get("introFadeInFromWhite") if isinstance(item.analysis, dict) else False:
                elapsed = frame_index / fps
                fade_seconds = min(float(item.analysis.get("introFadeInSeconds") or INTRO_IMAGE_FADE_IN_SECONDS), duration)
                fade_progress = smoothstep_value(elapsed / max(1e-6, fade_seconds))
                frame = apply_linear_fade_to_white(frame, fade_progress)
            if show_source_label:
                frame = draw_source_label(frame, source_display_name(item))
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
                    "imageRole": image_role,
                    "portraitLetterbox": portrait_letterbox,
                    "letterboxBackground": "white" if portrait_letterbox else None,
                    "portraitFadeSeconds": PORTRAIT_LETTERBOX_FADE_SECONDS if portrait_letterbox else None,
                    "portraitZoomAmount": PORTRAIT_LETTERBOX_ZOOM_AMOUNT if portrait_letterbox else None,
                    "showSourceLabel": show_source_label,
                    "progressCurve": "linear",
                    "zoomStart": 1.032 if motion_mode == "zoom-out" else 1.0,
                    "zoomEnd": 1.0 if motion_mode == "zoom-out" else 1.032 if motion_mode == "zoom-in" else 1.0,
                    "fadeStart": 1.0 if motion_mode == "fade-out" else None,
                    "fadeEnd": 0.0 if motion_mode == "fade-out" else None,
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


def cleanup_directory_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    removed = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        path.unlink()
        removed += 1
    return removed


def used_export_name(index: int, item: MediaItem, suffix: str | None = None) -> str:
    source_name = Path(item.relative).name
    source_stem = safe_stem(Path(source_name).stem)
    if suffix:
        return f"{index:03d}_used_{source_stem}_{suffix}.mp4"
    return f"{index:03d}_used_{source_stem}{item.path.suffix.lower()}"


def export_used_video_clip(ffmpeg: Path, item: MediaItem, output: Path) -> dict[str, Any]:
    duration = max(0.1, item.source_out - item.source_in if item.source_out > item.source_in else item.clip_duration)
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
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map_metadata",
        "-1",
        "-write_tmcd",
        "0",
        "-vf",
        "scale=960:-2:force_original_aspect_ratio=decrease,setsar=1,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {
        "command": command,
        "returnCode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-4000:],
    }


def export_used_media_previews(
    sequence: list[MediaItem],
    output_root: Path,
    ffmpeg: Path,
    run_name: str,
) -> dict[str, Any]:
    export_suffix = "preview" if "preview" in run_name else "highlight"
    video_dir = output_root / f"used_video_parts_{export_suffix}"
    image_dir = output_root / f"used_images_{export_suffix}"
    video_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    removed = {
        "videos": cleanup_directory_files(video_dir),
        "images": cleanup_directory_files(image_dir),
    }

    entries: list[dict[str, Any]] = []
    for index, item in enumerate(sequence, start=1):
        if item.kind == "image":
            output = image_dir / used_export_name(index, item)
            shutil.copy2(item.path, output)
            entries.append(
                {
                    "index": index,
                    "kind": item.kind,
                    "source": str(item.path),
                    "relative": item.relative,
                    "sourceLabel": source_display_name(item),
                    "sourceIdentityStem": media_stem(item),
                    "timelineStart": item.timeline_start,
                    "timelineEnd": item.timeline_end,
                    "output": str(output),
                }
            )
        elif item.kind == "video":
            suffix = f"{item.source_in:.2f}-{item.source_out:.2f}"
            output = video_dir / used_export_name(index, item, suffix)
            result = export_used_video_clip(ffmpeg, item, output)
            if result["returnCode"]:
                log_path = video_dir / f"{output.stem}.error.log"
                log_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                raise RuntimeError(f"used video export failed: {output} (see {log_path})")
            entries.append(
                {
                    "index": index,
                    "kind": item.kind,
                    "source": str(item.path),
                    "relative": item.relative,
                    "sourceLabel": source_display_name(item),
                    "sourceIdentityStem": media_stem(item),
                    "timelineStart": item.timeline_start,
                    "timelineEnd": item.timeline_end,
                    "sourceIn": item.source_in,
                    "sourceOut": item.source_out,
                    "output": str(output),
                }
            )

    manifest = output_root / "reports" / run_name / f"{run_name}_used_media_exports.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "createdAt": now_iso(),
        "runName": run_name,
        "videoDir": str(video_dir),
        "imageDir": str(image_dir),
        "removedBeforeExport": removed,
        "media": entries,
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest": str(manifest), "videoDir": str(video_dir), "imageDir": str(image_dir), "count": len(entries)}


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
    show_source_label: bool = False,
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
            show_source_label=show_source_label,
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
    filter_complex = f"[0:v]{video_filter(item, width, height, fps, show_source_label)}[v];{audio_chain}"

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
    has_visual_transitions = any(visual_dissolve_frames(sequence[index - 1], sequence[index]) > 0 for index in range(1, len(sequence)))
    if has_visual_transitions:
        group_size = max(group_size, len(segment_paths))
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
        durations: list[float] = []
        for input_index, (path, item) in enumerate(zip(chunk_paths, chunk_items)):
            inputs.extend(["-i", str(path)])
            frames = media_clip_frames(item)
            duration = frames / TARGET_FPS
            durations.append(duration)
            pre_filters.append(
                f"[{input_index}:v:0]trim=end_frame={frames},setpts=PTS-STARTPTS,"
                f"fps={TARGET_FPS},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v{input_index}]"
            )
            pre_filters.append(
                f"[{input_index}:a:0]atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[a{input_index}]"
            )

        current_v = "v0"
        current_a = "a0"
        current_duration = durations[0] if durations else 0.0
        for local_index in range(1, len(chunk_paths)):
            previous_item = chunk_items[local_index - 1]
            current_item = chunk_items[local_index]
            transition_frames = visual_dissolve_frames(previous_item, current_item)
            next_v = f"vx{local_index}"
            next_a = f"ax{local_index}"
            if transition_frames > 0:
                transition_duration = transition_frames / TARGET_FPS
                offset = max(0.0, current_duration - transition_duration)
                left_v = f"vxl{local_index}"
                right_v = f"vxr{local_index}"
                raw_next_v = f"vxraw{local_index}"
                pre_filters.append(f"[{current_v}]fps={TARGET_FPS},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[{left_v}]")
                pre_filters.append(f"[v{local_index}]fps={TARGET_FPS},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[{right_v}]")
                pre_filters.append(
                    f"[{left_v}][{right_v}]xfade=transition=fade:"
                    f"duration={transition_duration:.9f}:offset={offset:.9f}[{raw_next_v}]"
                )
                pre_filters.append(f"[{raw_next_v}]fps={TARGET_FPS},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[{next_v}]")
                raw_next_a = f"axraw{local_index}"
                pre_filters.append(
                    f"[{current_a}][a{local_index}]acrossfade=d={transition_duration:.9f}:c1=tri:c2=tri[{raw_next_a}]"
                )
                pre_filters.append(f"[{raw_next_a}]asetpts=PTS-STARTPTS[{next_a}]")
                current_duration += durations[local_index] - transition_duration
            else:
                raw_next_v = f"vxraw{local_index}"
                raw_next_a = f"axraw{local_index}"
                pre_filters.append(
                    f"[{current_v}][{current_a}][v{local_index}][a{local_index}]"
                    f"concat=n=2:v=1:a=1[{raw_next_v}][{raw_next_a}]"
                )
                pre_filters.append(f"[{raw_next_v}]fps={TARGET_FPS},settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[{next_v}]")
                pre_filters.append(f"[{raw_next_a}]asetpts=PTS-STARTPTS[{next_a}]")
                current_duration += durations[local_index]
            current_v = next_v
            current_a = next_a

        filter_complex = (
            ";".join(pre_filters)
            + ";"
            + f"[{current_v}]fps={TARGET_FPS},setpts=N/({TARGET_FPS}*TB),format=yuv420p[v];"
            + f"[{current_a}]aresample=48000:async=1:first_pts=0[a]"
        )
        filter_script_path = group_output.with_suffix(".filter_complex.txt")
        filter_script_path.write_text(filter_complex, encoding="utf-8")
        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            *inputs,
            "-filter_complex_script",
            str(filter_script_path),
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
    focus_intervals: list[tuple[float, float, str]] | None = None,
    force: bool,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0 and not force:
        return output
    temporary_output = output.with_name(f"{output.stem}.mixing{output.suffix}")
    fade_seconds = min(BACKGROUND_AUDIO_FADE_SECONDS, max(0.1, duration / 2.0))
    fade_out_start = max(0.0, duration - fade_seconds)
    intervals = focus_intervals or []
    original_volume_expr = focus_volume_expr(
        original_volume,
        AUDIO_FOCUS_ORIGINAL_VOLUME_MULTIPLIER,
        intervals,
        AUDIO_FOCUS_ORIGINAL_VOLUME_MAX,
    )
    music_volume_expr = focus_volume_expr(music_volume, AUDIO_FOCUS_MUSIC_VOLUME_MULTIPLIER, intervals)
    filter_complex = (
        "[0:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"atrim=duration={duration:.9f},asetpts=PTS-STARTPTS,volume='{original_volume_expr}':eval=frame[orig];"
        "[1:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"atrim=duration={duration:.9f},asetpts=PTS-STARTPTS,"
        f"volume='{music_volume_expr}':eval=frame[music];"
        "[orig][music]amix=inputs=2:duration=first:dropout_transition=2,"
        f"afade=t=in:st=0:d={fade_seconds:.6f},afade=t=out:st={fade_out_start:.6f}:d={fade_seconds:.6f},"
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
    try:
        temporary_output.replace(output)
        return output
    except PermissionError:
        fallback_output = output.with_name(f"{output.stem}_latest{output.suffix}")
        if fallback_output.exists():
            fallback_output.unlink()
        temporary_output.replace(fallback_output)
        print(f"[background-audio] output locked; wrote {fallback_output}", file=sys.stderr, flush=True)
        return fallback_output


def write_timeline_report(
    project_root: Path,
    output: Path,
    sequence: list[MediaItem],
    final_path: Path,
    concat_file: Path,
    segment_results: list[dict[str, Any]],
    selection_report_path: Path | None = None,
    background_audio: dict[str, Any] | None = None,
    excluded_video_stems: set[str] | None = None,
    excluded_image_stems: set[str] | None = None,
) -> None:
    payload = {
        "createdAt": now_iso(),
        "projectRoot": str(project_root),
        "output": str(final_path),
        "duration": round(sequence[-1].timeline_end if sequence else 0.0, 3),
        "target": {"width": TARGET_WIDTH, "height": TARGET_HEIGHT, "fps": TARGET_FPS},
        "allowedImageSourceDirs": sorted(ALLOWED_IMAGE_SOURCE_DIRS),
        "concatFile": str(concat_file),
        "selectionReport": str(selection_report_path) if selection_report_path else "",
        "backgroundAudio": background_audio or {},
        "excludedVideoStems": sorted(excluded_video_stems or []),
        "excludedImageStems": sorted(excluded_image_stems or []),
        "visualTransitionPolicy": {
            "enabled": True,
            "transition": "dissolve",
            "appliesTo": "boundaries where either side is a still image",
            "targetDurationSeconds": VISUAL_IMAGE_DISSOLVE_SECONDS,
            "maxFractionOfShorterClip": VISUAL_IMAGE_DISSOLVE_MAX_FRACTION,
        },
        "visualTransitions": visual_transition_report(sequence),
        "segmentResults": segment_results,
        "media": [
            {
                "index": index,
                "kind": item.kind,
                "path": str(item.path),
                "relative": item.relative,
                "sourceIdentityStem": media_stem(item),
                "sourceLabel": source_display_name(item),
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
    parser.add_argument("--base-image-seconds", type=float, default=5.0)
    parser.add_argument("--video-max-samples", type=int, default=70)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--ffmpeg", type=Path, default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
    parser.add_argument("--ffprobe", type=Path, default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
    parser.add_argument("--preview", action="store_true", help="Render a lightweight 960x540 preview instead of the full-size output.")
    parser.add_argument(
        "--dedupe-images",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Group visually similar still images and keep the best one from each group. Enabled by default.",
    )
    parser.add_argument("--image-hash-distance", type=int, default=8, help="Perceptual-hash distance used for still-image duplicate grouping.")
    parser.add_argument("--background-audio", type=str, default=None, help="Background music path, or 'auto' to pick the best source/audio file.")
    parser.add_argument("--music-volume", type=float, default=0.24)
    parser.add_argument("--original-volume", type=float, default=0.50)
    parser.add_argument(
        "--exclude-video-stem",
        action="append",
        default=[],
        help="Additional source video stem to exclude before timeline planning. Can be repeated.",
    )
    parser.add_argument(
        "--exclude-image-stem",
        action="append",
        default=[],
        help="Additional source image stem to exclude before timeline planning. Can be repeated.",
    )
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--replan-from-report", action="store_true")
    parser.add_argument("--show-source-labels", action="store_true", help="Overlay source filenames in the upper-left corner for review renders.")
    parser.add_argument(
        "--skip-used-media-export",
        action="store_true",
        help="Skip exporting per-source review clips/images after the final video is rendered.",
    )
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
            "fadeInSeconds": BACKGROUND_AUDIO_FADE_SECONDS,
            "fadeOutSeconds": BACKGROUND_AUDIO_FADE_SECONDS,
        }
        if background_audio_path
        else None
    )
    excluded_video_stems = {source_identity_stem(stem) for stem in DEFAULT_EXCLUDED_VIDEO_STEMS}
    excluded_video_stems.update(source_identity_stem(stem) for stem in args.exclude_video_stem)
    excluded_image_stems = {source_identity_stem(stem) for stem in DEFAULT_EXCLUDED_IMAGE_STEMS}
    excluded_image_stems.update(source_identity_stem(stem) for stem in args.exclude_image_stem)

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
            images = prepare_special_image_sequence(images)
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
                excluded_video_stems,
                excluded_image_stems,
            )
    else:
        detectors = load_face_detectors(project_root)
        videos, images = discover_media(project_root, args.ffprobe, excluded_video_stems, excluded_image_stems)
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
        videos = expand_manual_video_range_clips(videos)
        for index, image in enumerate(images, start=1):
            if image.analysis.get("analysisVersion") == IMAGE_ANALYSIS_VERSION and "visual" in image.analysis:
                continue
            print(f"[analysis image {index}/{len(images)}] {image.relative}", flush=True)
            analyze_image(image, detectors)
        if args.dedupe_images:
            images, selection_report = select_best_images(images, args.image_hash_distance)
            selection_report_path.parent.mkdir(parents=True, exist_ok=True)
            selection_report_path.write_text(json.dumps(selection_report, ensure_ascii=False, indent=2), encoding="utf-8")
        images = prepare_special_image_sequence(images)
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
            excluded_video_stems,
            excluded_image_stems,
        )

    focus_intervals = audio_focus_intervals(sequence)
    background_audio_report = background_audio_report_with_focus(background_audio_report, focus_intervals)

    if args.analyze_only:
        write_timeline_report(
            project_root,
            report_path,
            sequence,
            final_path,
            concat_file,
            [],
            selection_report_path if args.dedupe_images else None,
            background_audio_report,
            excluded_video_stems,
            excluded_image_stems,
        )
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
                show_source_label=args.show_source_labels,
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
    actual_final_path = final_path
    if background_audio_path:
        actual_final_path = mix_background_music(
            args.ffmpeg,
            concat_output_path,
            background_audio_path,
            final_path,
            sequence[-1].timeline_end if sequence else args.target_seconds,
            original_volume=args.original_volume,
            music_volume=args.music_volume,
            focus_intervals=focus_intervals,
            force=args.force,
        )
        results.append(
            {
                "index": len(results) + 1,
                "kind": "background-audio",
                "path": str(background_audio_path),
                "output": str(actual_final_path),
                "focusIntervals": [
                    {"timelineStart": round(start, 3), "timelineEnd": round(end, 3), "sourceLabel": label}
                    for start, end, label in focus_intervals
                ],
            }
        )
    if args.skip_used_media_export:
        results.append({"index": len(results) + 1, "kind": "used-media-export", "status": "skipped"})
    else:
        used_export = export_used_media_previews(sequence, output_root, args.ffmpeg, run_name)
        results.append({"index": len(results) + 1, "kind": "used-media-export", **used_export})
    write_timeline_report(
        project_root,
        report_path,
        sequence,
        actual_final_path,
        concat_file,
        results,
        selection_report_path if args.dedupe_images else None,
        background_audio_report,
        excluded_video_stems,
        excluded_image_stems,
    )
    print(
        json.dumps(
            {
                "output": str(actual_final_path),
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
