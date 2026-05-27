from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_OVERLAYS,
    OUTPUT_REPORTS,
    OUTPUT_TRANSCRIPTS,
    OUTPUT_VIDEOS,
    ROOT as WORKSPACE_ROOT,
    SCRIPTS,
    SOURCE_AUDIO,
    SOURCE_IMAGES,
    SOURCE_SUBTITLES,
    SOURCE_VIDEO,
    multicam_source_root,
    resolve_project_path,
)

from shorten_silences import DEFAULT_KEEP_SILENCE, DEFAULT_MIN_SILENCE, DEFAULT_NOISE, SilenceShortenConfig, shorten_silences
from video_edit_app_config import int_value, load_app_config, nested, optional_path, selected_subtitle_path
from composition_rules import crop_window_center_for_subject, subject_target_for_face, visible_ratio_for_area


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
TITLE = OUTPUT_OVERLAYS / "ai_engineer_now_title.png"
DEFAULT_LOGO = SOURCE_IMAGES / "type-logo-transparent-cropped.png"
DEFAULT_SYNC = OUTPUT_REPORTS / "app_sync_offsets.json"
DEFAULT_DENOISE_STRENGTH = 10
DEFAULT_REFERENCE_PROFILE = OUTPUT_REPORTS / "reference_edit_profile.json"
DEFAULT_STILL_DURATION = 3.5
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def path_value(*keys: str) -> Path | None:
    value = nested(APP_CONFIG, *keys, default="")
    return Path(value) if value else None


def list_value(*keys: str) -> list[Any]:
    value = nested(APP_CONFIG, *keys, default=[])
    return value if isinstance(value, list) else []


def media_manifest() -> dict[str, Any]:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = nested(APP_CONFIG, "assets", "mediaManifestPath", default="")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def manifest_files(kind: str | None = None) -> list[dict[str, Any]]:
    manifest = media_manifest()
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        return []
    items = [item for item in files if isinstance(item, dict)]
    if kind is not None:
        items = [item for item in items if item.get("kind") == kind]
    return items


def camera_role_sort(role: str) -> int:
    if role == "master":
        return 1
    if role.startswith("camera"):
        try:
            return int(role.replace("camera", ""))
        except ValueError:
            return 50
    return 100


def manifest_cameras() -> list[tuple[str, Path]]:
    camera_roles = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}
    cameras = [
        (str(item.get("role") or ""), Path(str(item.get("path") or "")))
        for item in manifest_files("video")
        if item.get("role") in camera_roles and item.get("path")
    ]
    cameras = [(role, path) for role, path in cameras if path.exists()]
    cameras.sort(key=lambda item: camera_role_sort(item[0]))
    return cameras


def manifest_audio_sources() -> list[tuple[str, Path]]:
    audio = [
        (str(item.get("role") or "external"), Path(str(item.get("path") or "")))
        for item in manifest_files("audio")
        if str(item.get("role") or "").startswith("external") and item.get("path")
    ]
    return [(role, path) for role, path in audio if path.exists()]


def manifest_image(role: str) -> Path | None:
    for item in manifest_files("image"):
        if item.get("role") == role and item.get("path"):
            path = Path(str(item["path"]))
            if path.exists():
                return path
    return None


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def audio_cleanup_filter(strength: int) -> str:
    nr = max(0, min(30, int(strength)))
    if nr <= 0:
        return "highpass=f=80"
    return f"highpass=f=80,afftdn=nr={nr}:nf=-35"


def normalize_text(text: str) -> str:
    return re.sub(r"[\s　、。,.!！?？:：;；・/\\|_\-()\[\]（）「」『』\"'`]+", "", text.lower())


def sidecar_text(path: Path) -> str:
    text_path = path.with_suffix(".txt")
    if text_path.exists():
        return text_path.read_text(encoding="utf-8", errors="ignore").strip()
    return ""


def optional_ocr_text(path: Path) -> str:
    try:
        import pytesseract  # type: ignore

        return pytesseract.image_to_string(str(path), lang="jpn+eng").strip()
    except Exception:
        return ""


def text_density(path: Path) -> float:
    try:
        image = Image.open(path).convert("L").resize((360, 202))
    except Exception:
        return 0.0
    edges = image.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    return float(stat.mean[0]) / 255.0


def still_kind(path: Path, extracted_text: str) -> str:
    if len(normalize_text(extracted_text)) >= 4:
        return "text"
    density = text_density(path)
    return "diagram" if density >= 0.115 else "photo"


def still_text(path: Path) -> str:
    return " ".join(part for part in [sidecar_text(path), optional_ocr_text(path), path.stem.replace("_", " ")] if part).strip()


def visual_text(path: Path) -> str:
    return " ".join(part for part in [sidecar_text(path), optional_ocr_text(path)] if part).strip()


def weighted_focus(path: Path) -> tuple[float, float]:
    try:
        image = Image.open(path).convert("L")
    except Exception:
        return (0.5, 0.5)
    width, height = image.size
    if width <= 0 or height <= 0:
        return (0.5, 0.5)

    sample_width = 160
    sample_height = max(1, round(sample_width * height / width))
    sample = image.resize((sample_width, sample_height))
    edges = sample.filter(ImageFilter.FIND_EDGES)
    edge_data = list(edges.getdata())
    light_data = list(sample.getdata())
    total = 0.0
    sum_x = 0.0
    sum_y = 0.0
    for index, edge in enumerate(edge_data):
        x = index % sample_width
        y = index // sample_width
        light = light_data[index]
        weight = float(edge) * 0.85 + max(0.0, float(light) - 96.0) * 0.15
        total += weight
        sum_x += x * weight
        sum_y += y * weight
    if total <= 0:
        return (0.5, 0.5)
    return (clamp((sum_x / total) / max(1, sample_width - 1), 0.22, 0.78), clamp((sum_y / total) / max(1, sample_height - 1), 0.24, 0.76))


def detect_photo_faces(path: Path) -> list[dict[str, float]]:
    try:
        import cv2  # type: ignore

        image = cv2.imread(str(path))
        if image is None:
            return []
        height, width = image.shape[:2]
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(str(cascade_path))
        if cascade.empty():
            return []
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        min_size = max(24, min(width, height) // 12)
        boxes = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_size, min_size))
    except Exception:
        return []

    faces = []
    for x, y, box_width, box_height in boxes:
        area = float(box_width * box_height)
        faces.append(
            {
                "x": round(float(x) / width, 4),
                "y": round(float(y) / height, 4),
                "width": round(float(box_width) / width, 4),
                "height": round(float(box_height) / height, 4),
                "center_x": round((float(x) + float(box_width) / 2) / width, 4),
                "center_y": round((float(y) + float(box_height) / 2) / height, 4),
                "area": round(area / float(width * height), 5),
            }
        )
    return sorted(faces, key=lambda face: face["area"], reverse=True)


def photo_effect(photo_kind: str) -> dict[str, float | str]:
    if photo_kind == "person":
        return {"name": "portrait_face_push", "zoom_start": 1.045, "zoom_end": 1.075, "pan_x": 18.0, "pan_y": 8.0}
    if photo_kind == "landscape":
        return {"name": "landscape_slow_drift", "zoom_start": 1.03, "zoom_end": 1.065, "pan_x": 82.0, "pan_y": 18.0}
    return {"name": "object_focus_push", "zoom_start": 1.04, "zoom_end": 1.07, "pan_x": 42.0, "pan_y": 14.0}


def analyze_still_image(path: Path, kind: str) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except Exception:
        width, height = 0, 0
    aspect = (width / height) if height else 1.0
    if kind in {"text", "diagram"}:
        return {
            "kind": kind,
            "width": width,
            "height": height,
            "aspect": round(aspect, 4),
            "photo_kind": None,
            "focus": [0.5, 0.5],
            "faces": [],
            "effect": {"name": "static_readable_fade"},
        }

    faces = detect_photo_faces(path)
    if faces:
        primary = faces[0]
        photo_kind = "person"
        focus = (float(primary["center_x"]), float(primary["center_y"]))
    else:
        photo_kind = "landscape" if aspect >= 1.25 else "object"
        focus = weighted_focus(path)

    return {
        "kind": "photo",
        "width": width,
        "height": height,
        "aspect": round(aspect, 4),
        "photo_kind": photo_kind,
        "focus": [round(focus[0], 4), round(focus[1], 4)],
        "faces": faces[:3],
        "effect": photo_effect(photo_kind),
    }


def parse_still_images() -> list[dict[str, Any]]:
    stills = []
    configured_stills = list_value("assets", "stillImages")
    if not configured_stills:
        configured_stills = [
            item
            for item in manifest_files("image")
            if item.get("role") == "still"
        ]
    for item in configured_stills:
        path = Path(item.get("path", "")) if isinstance(item, dict) else Path(str(item))
        if not path or path.suffix.lower() not in IMAGE_EXTENSIONS or not path.exists():
            continue
        explicit_text = str(item.get("text", "")).strip() if isinstance(item, dict) else ""
        image_text = explicit_text or visual_text(path)
        text = image_text or path.stem.replace("_", " ")
        kind = str(item.get("kind", "")).strip() if isinstance(item, dict) else ""
        kind = kind or still_kind(path, image_text)
        analysis = analyze_still_image(path, kind)
        duration = float(item.get("duration", 0) or 0) if isinstance(item, dict) else 0.0
        stills.append(
            {
                "path": path,
                "text": text,
                "kind": analysis["kind"],
                "analysis": analysis,
                "effect": analysis["effect"],
                "duration": duration if duration > 0 else float(nested(APP_CONFIG, "render", "stillDuration", default=DEFAULT_STILL_DURATION)),
            }
        )
    return stills


def text_match_score(query: str, candidate: str) -> float:
    query_norm = normalize_text(query)
    candidate_norm = normalize_text(candidate)
    if len(query_norm) < 3 or len(candidate_norm) < 3:
        return 0.0
    query_chars = set(query_norm)
    candidate_chars = set(candidate_norm)
    overlap = len(query_chars & candidate_chars) / max(1, min(len(query_chars), len(candidate_chars)))
    substring_bonus = 0.22 if query_norm in candidate_norm or candidate_norm in query_norm else 0.0
    return min(1.0, overlap + substring_bonus)


def transcript_captions(captions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if captions:
        return [
            {
                "start": seconds(item["start"]),
                "end": seconds(item["end"]),
                "text": "".join(item.get("lines") or []),
            }
            for item in captions
        ]
    srt = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
    if srt is None:
        return []
    rows = []
    for block in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8", errors="ignore")):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]
        rows.append({"start": seconds(timestamp_to_filter_time(start_raw)), "end": seconds(timestamp_to_filter_time(end_raw)), "text": "".join(lines[2:])})
    return rows


def timestamp_to_filter_time(value: str) -> str:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return f"{int(hours)}:{int(minutes):02d}:{float(rest):05.2f}"


def plan_still_inserts(stills: list[dict[str, Any]], captions: list[dict[str, Any]], timeline_start: float, duration: float) -> list[dict[str, Any]]:
    if not stills:
        return []
    transcript = transcript_captions(captions)
    inserts: list[dict[str, Any]] = []
    fallback_index = 0
    for index, still in enumerate(stills):
        still_duration = max(1.0, min(float(still["duration"]), max(1.0, duration / 3)))
        best = None
        if still["kind"] in {"text", "diagram"} and transcript:
            scored = [
                (text_match_score(str(still["text"]), row["text"]), row)
                for row in transcript
                if timeline_start <= row["start"] < timeline_start + duration
            ]
            best = max(scored, key=lambda item: item[0]) if scored else None
        if best and best[0] >= 0.34:
            start_t = max(0.0, min(float(best[1]["start"]) - timeline_start, duration - still_duration))
            reason = f"matched transcript score {best[0]:.3f}: {best[1]['text'][:40]}"
        else:
            fallback_index += 1
            start_t = min(max(1.0, duration * fallback_index / (len(stills) + 1)), max(0.0, duration - still_duration))
            reason = "fallback evenly spaced insert"
        while any(start_t < item["end"] and start_t + still_duration > item["start"] for item in inserts):
            start_t = min(start_t + 1.0, max(0.0, duration - still_duration))
            if start_t + still_duration >= duration:
                break
        inserts.append({**still, "start": round(start_t, 3), "end": round(start_t + still_duration, 3), "reason": reason, "input_index": None})
    return sorted(inserts, key=lambda item: item["start"])


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_reference_profile() -> dict[str, object]:
    if not path_value("assets", "referenceVideo"):
        return {}
    path = Path(nested(APP_CONFIG, "analysis", "referenceEditProfilePath", default=str(DEFAULT_REFERENCE_PROFILE)))
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def reference_video_filter(profile: dict[str, object]) -> str:
    target = profile.get("target") if isinstance(profile.get("target"), dict) else {}
    center = target.get("person_center_ratio") if isinstance(target.get("person_center_ratio"), list) else None
    area = target.get("person_area_ratio")
    face_direction = str(target.get("dominant_face_direction") or "unknown")
    desired_subject_x = target.get("desired_subject_x_ratio")
    desired_subject_y = target.get("desired_subject_y_ratio")
    visual = target.get("visual_style") if isinstance(target.get("visual_style"), dict) else {}

    center_x = clamp(float(center[0]), 0.2, 0.8) if center and center[0] is not None else 0.5
    center_y = clamp(float(center[1]), 0.25, 0.75) if center and center[1] is not None else 0.5
    area_ratio = float(area) if area is not None else 0.0
    visible_ratio = visible_ratio_for_area(area_ratio)

    if desired_subject_x is None:
        desired_subject_x = subject_target_for_face(face_direction).x
    if desired_subject_y is None:
        desired_subject_y = subject_target_for_face(face_direction).y
    desired_subject_x = clamp(float(desired_subject_x), 0.35, 0.65)
    desired_subject_y = clamp(float(desired_subject_y), 0.30, 0.52)
    center_x = crop_window_center_for_subject(center_x, desired_subject_x, visible_ratio)
    center_y = crop_window_center_for_subject(center_y, desired_subject_y, visible_ratio)

    brightness = visual.get("brightness")
    contrast = visual.get("contrast")
    saturation = visual.get("saturation")
    brightness_adj = clamp((float(brightness) - 0.48) * 0.22, -0.08, 0.08) if brightness is not None else 0.0
    contrast_adj = clamp(0.88 + float(contrast) * 1.15, 0.88, 1.24) if contrast is not None else 1.0
    saturation_adj = clamp(0.78 + float(saturation) * 1.15, 0.78, 1.34) if saturation is not None else 1.0

    scale_w = round(1920 / visible_ratio / 2) * 2
    scale_h = round(1080 / visible_ratio / 2) * 2
    crop_x = f"min(max(iw*{center_x:.4f}-960\\,0)\\,iw-1920)"
    crop_y = f"min(max(ih*{center_y:.4f}-540\\,0)\\,ih-1080)"
    return (
        f"scale={scale_w}:{scale_h},crop=1920:1080:x='{crop_x}':y='{crop_y}',"
        f"eq=brightness={brightness_adj:.4f}:contrast={contrast_adj:.4f}:saturation={saturation_adj:.4f}"
    )


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, cwd=WORK)


def load_sync_offsets(sources: list[tuple[str, Path]]) -> dict[str, float]:
    sync_path = Path(nested(APP_CONFIG, "render", "syncOffsetsPath", default=str(DEFAULT_SYNC)))
    offsets = {role: 0.0 for role, _ in sources}
    offsets.setdefault("master", 0.0)
    if not sync_path.exists():
        return offsets
    data = json.loads(sync_path.read_text(encoding="utf-8")).get("offsets", {})
    for role, path in sources:
        item = data.get(role)
        if item and Path(item.get("path", "")) == path:
            offsets[role] = float(item.get("offsetSeconds", 0.0))
    return offsets


def build_segments(duration: float, cameras: list[tuple[str, int]]) -> list[tuple[str, int, float, float]]:
    if not cameras:
        raise RuntimeError("At least one camera input is required.")
    mode = nested(APP_CONFIG, "render", "multicamMode", default="master-first")
    if mode == "master-first" or len(cameras) == 1:
        if len(cameras) == 1:
            return [(cameras[0][0], cameras[0][1], 0.0, duration)]
        segments = [(cameras[0][0], cameras[0][1], 0.0, min(8.0, duration))]
        t = 8.0
        closeups = cameras[1:] or cameras[:1]
        index = 0
        while t < duration:
            end = min(duration, t + 12.0)
            role, input_index = closeups[index % len(closeups)]
            segments.append((role, input_index, t, end))
            t = end
            index += 1
        return segments

    # For speaker-aware/manual requests without transcript data, use deterministic
    # close-up rotation and keep the master as fallback.
    order = cameras[1:] + cameras[:1] if len(cameras) > 1 else cameras
    segments = []
    t = 0.0
    index = 0
    while t < duration:
        end = min(duration, t + 15.0)
        role, input_index = order[index % len(order)]
        segments.append((role, input_index, t, end))
        t = end
        index += 1
    return segments


def video_segments_with_stills(
    duration: float,
    camera_segments: list[tuple[str, int, float, float]],
    still_inserts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cuts = {0.0, duration}
    for _, _, start_t, end_t in camera_segments:
        cuts.add(max(0.0, min(duration, start_t)))
        cuts.add(max(0.0, min(duration, end_t)))
    for still in still_inserts:
        cuts.add(float(still["start"]))
        cuts.add(float(still["end"]))
    timeline = sorted(cuts)
    segments = []
    for start_t, end_t in zip(timeline, timeline[1:]):
        if end_t - start_t <= 0.02:
            continue
        midpoint = (start_t + end_t) / 2
        still = next((item for item in still_inserts if float(item["start"]) <= midpoint < float(item["end"])), None)
        if still:
            segments.append({"type": "still", "still": still, "start": start_t, "end": end_t})
            continue
        camera = next((item for item in camera_segments if item[2] <= midpoint < item[3]), camera_segments[-1])
        role, input_index, _, _ = camera
        segments.append({"type": "camera", "role": role, "input_index": input_index, "start": start_t, "end": end_t})
    return segments


def still_filter(input_index: int, label: str, duration: float, still: dict[str, Any], phase: int) -> str:
    fade_out = max(0.0, duration - 0.25)
    kind = str(still["kind"])
    if kind in {"text", "diagram"}:
        base = (
            f"[{input_index}:v]fps=60,scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1"
        )
    else:
        analysis = still.get("analysis") if isinstance(still.get("analysis"), dict) else {}
        effect = still.get("effect") if isinstance(still.get("effect"), dict) else {}
        focus = analysis.get("focus") if isinstance(analysis.get("focus"), list) else [0.5, 0.5]
        focus_x = clamp(float(focus[0]), 0.08, 0.92)
        focus_y = clamp(float(focus[1]), 0.10, 0.90)
        zoom_start = float(effect.get("zoom_start", 1.04))
        zoom_end = float(effect.get("zoom_end", 1.07))
        pan_x = float(effect.get("pan_x", 42.0)) * (1 if phase % 2 else -1)
        pan_y = float(effect.get("pan_y", 14.0)) * (1 if phase % 3 == 0 else -1)
        progress = f"min(1,max(0,t/{max(duration, 0.1):.3f}))"
        zoom = f"({zoom_start:.5f}+({zoom_end:.5f}-{zoom_start:.5f})*{progress})"
        x_expr = f"min(max(iw*{focus_x:.5f}-960+{pan_x:.3f}*({progress}-0.5),0),iw-1920)"
        y_expr = f"min(max(ih*{focus_y:.5f}-540+{pan_y:.3f}*({progress}-0.5),0),ih-1080)"
        base = (
            f"[{input_index}:v]fps=60,"
            f"scale=w='if(gte(iw/ih,1.777778),-2,1920*{zoom})':h='if(gte(iw/ih,1.777778),1080*{zoom},-2)':eval=frame,"
            f"crop=1920:1080:x='{x_expr}':y='{y_expr}',setsar=1"
        )
    return f"{base},trim=duration={duration:.6f},setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.22,fade=t=out:st={fade_out:.3f}:d=0.25[{label}]"


def still_report(still_inserts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "file": str(item["path"]),
            "kind": item["kind"],
            "start": item["start"],
            "end": item["end"],
            "reason": item["reason"],
            "photo_kind": item.get("analysis", {}).get("photo_kind") if isinstance(item.get("analysis"), dict) else None,
            "focus": item.get("analysis", {}).get("focus") if isinstance(item.get("analysis"), dict) else None,
            "faces": len(item.get("analysis", {}).get("faces", [])) if isinstance(item.get("analysis"), dict) else 0,
            "effect": item.get("effect", {}).get("name") if isinstance(item.get("effect"), dict) else None,
        }
        for item in still_inserts
    ]


def subtitle_mode() -> str:
    mode = nested(APP_CONFIG, "render", "subtitleMode", default="none")
    return mode if mode in {"full", "punchline"} else "none"


def subtitle_manifest(mode: str) -> tuple[Path, dict[str, object]]:
    modes = {
        "full": {
            "generator": SCRIPTS / "generate_full_transcript_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json",
            "bottom_margin": 16,
            "slide_px": 0,
            "pop": False,
            "animate": False,
        },
        "punchline": {
            "generator": SCRIPTS / "generate_punchline_png_overlays.py",
            "manifest": OUTPUT_OVERLAYS / "punchline_png_overlays" / "manifest.json",
            "bottom_margin": 12,
            "slide_px": 44,
            "pop": True,
            "animate": True,
        },
    }
    config = modes[mode]
    run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])
    run([sys.executable, str(config["generator"])])
    return Path(config["manifest"]), config


def main() -> None:
    manifest_camera_sources = manifest_cameras()
    master = path_value("assets", "masterVideo")
    right = path_value("assets", "rightCloseVideo")
    left = path_value("assets", "leftCloseVideo")
    legacy_external_audio = path_value("assets", "externalAudio")
    audio_sources = manifest_audio_sources()
    external_audio = audio_sources[0][1] if audio_sources else legacy_external_audio
    external_audio_role = audio_sources[0][0] if audio_sources else "external"
    logo = path_value("assets", "logo") or manifest_image("logo") or DEFAULT_LOGO
    output = Path(nested(APP_CONFIG, "render", "outputPath", default=OUTPUT_VIDEOS / "app_interview_output.mp4"))
    start = float(nested(APP_CONFIG, "render", "previewStart", default=0.0) or 0.0)
    duration = float(nested(APP_CONFIG, "render", "previewDuration", default=60.0) or 60.0)
    logo_height = int_value(APP_CONFIG, "style", "logoHeight", default=48)
    audio_denoise = bool_value("render", "audioDenoise", default=True)
    audio_denoise_strength = int_value(APP_CONFIG, "render", "audioDenoiseStrength", default=DEFAULT_DENOISE_STRENGTH)
    output.parent.mkdir(parents=True, exist_ok=True)
    reference_profile = load_reference_profile()
    reference_filter = reference_video_filter(reference_profile) if reference_profile else "scale=1920:1080"

    cameras: list[tuple[str, Path]] = []
    if manifest_camera_sources:
        cameras = manifest_camera_sources
    else:
        if master:
            cameras.append(("master", master))
        if right:
            cameras.append(("camera2", right))
        if left:
            cameras.append(("camera3", left))
    if not cameras:
        raise RuntimeError("Drop or select at least a Camera 1 / master video before running render_app_interview.py.")
    sync_sources = cameras + audio_sources
    if external_audio and not audio_sources:
        sync_sources.append(("external", external_audio))
    sync_offsets = load_sync_offsets(sync_sources)
    run([sys.executable, str(SCRIPTS / "generate_title_png_overlay.py")])

    mode = subtitle_mode()
    captions = []
    caption_config: dict[str, object] = {}
    if mode != "none":
        manifest, caption_config = subtitle_manifest(mode)
        captions = [
            item
            for item in json.loads(manifest.read_text(encoding="utf-8"))
            if seconds(item["start"]) < start + duration and seconds(item["end"]) > start
        ]

    still_inserts = plan_still_inserts(parse_still_images(), captions, start, duration)
    audio_source = nested(APP_CONFIG, "render", "audioSource", default="external-if-selected")
    audio_input_index = 0
    if audio_source == "rightCloseVideo":
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "camera2"), 0)
    elif audio_source == "leftCloseVideo":
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "camera3"), 0)
    elif audio_source == "external-if-selected" and external_audio:
        audio_input_index = len(cameras) + len(still_inserts) + 2 + len(captions)

    camera_indexes = [(name, index) for index, (name, _) in enumerate(cameras)]
    timeline_segments = build_segments(duration, camera_indexes)
    video_segments = video_segments_with_stills(duration, timeline_segments, still_inserts)
    source_ranges: dict[int, list[float]] = {}
    for role, input_index, seg_start, seg_end in timeline_segments:
        source_start = max(0.0, sync_offsets.get(role, 0.0) + start + seg_start)
        source_end = max(source_start, sync_offsets.get(role, 0.0) + start + seg_end)
        current_range = source_ranges.setdefault(input_index, [source_start, source_end])
        current_range[0] = min(current_range[0], source_start)
        current_range[1] = max(current_range[1], source_end)

    if audio_input_index < len(cameras):
        audio_role = cameras[audio_input_index][0]
        audio_start = max(0.0, sync_offsets.get(audio_role, 0.0) + start)
        audio_end = audio_start + duration
        current_range = source_ranges.setdefault(audio_input_index, [audio_start, audio_end])
        current_range[0] = min(current_range[0], audio_start)
        current_range[1] = max(current_range[1], audio_end)

    input_seek: dict[int, float] = {}
    command = [str(FFMPEG), "-hide_banner", "-y"]
    for index, (_, camera_path) in enumerate(cameras):
        range_start, range_end = source_ranges.get(index, [start, start + duration])
        input_seek[index] = range_start
        command.extend(["-ss", f"{range_start:.6f}", "-t", f"{max(0.1, range_end - range_start):.6f}", "-i", str(camera_path)])

    for still_index, still in enumerate(still_inserts):
        still["input_index"] = len(cameras) + still_index
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{max(0.1, float(still['end']) - float(still['start'])):.6f}", "-i", str(still["path"])])

    logo_index = len(cameras) + len(still_inserts)
    command.extend(["-i", str(logo)])
    title_index = logo_index + 1
    command.extend(["-i", str(TITLE)])
    for item in captions:
        command.extend(["-loop", "1", "-framerate", "60", "-t", f"{duration:.3f}", "-i", str(WORK / item["file"])])
    if audio_source == "external-if-selected" and external_audio:
        external_audio_start = max(0.0, sync_offsets.get(external_audio_role, 0.0) + start)
        command.extend(["-ss", f"{external_audio_start:.6f}", "-t", f"{duration:.6f}", "-i", str(external_audio)])

    filters: list[str] = []
    segment_labels: list[str] = []
    for segment_index, segment in enumerate(video_segments):
        label = f"seg{segment_index}"
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        if segment["type"] == "still":
            still = segment["still"]
            filters.append(still_filter(int(still["input_index"]), label, seg_end - seg_start, still, segment_index))
        else:
            role = str(segment["role"])
            input_index = int(segment["input_index"])
            source_start = max(0.0, sync_offsets.get(role, 0.0) + start + seg_start)
            source_end = max(source_start, sync_offsets.get(role, 0.0) + start + seg_end)
            local_start = max(0.0, source_start - input_seek.get(input_index, 0.0))
            local_end = max(local_start, source_end - input_seek.get(input_index, 0.0))
            filters.append(
                f"[{input_index}:v]setpts=PTS-STARTPTS,trim=start={local_start:.6f}:end={local_end:.6f},"
                f"setpts=PTS-STARTPTS,{reference_filter}[{label}]"
            )
        segment_labels.append(label)

    if len(segment_labels) == 1:
        filters.append(f"[{segment_labels[0]}]copy[vbase]")
    else:
        filters.append("".join(f"[{label}]" for label in segment_labels) + f"concat=n={len(segment_labels)}:v=1:a=0[vbase]")

    filters.extend(
        [
            f"[{logo_index}:v]scale=-1:{logo_height}[logo]",
            "[vbase][logo]overlay=W-w-40:40[vlogo]",
            f"[vlogo][{title_index}:v]overlay=42:42[vtitle]",
        ]
    )

    current = "vtitle"
    first_caption_index = len(cameras) + len(still_inserts) + 2
    for index, item in enumerate(captions, start=1):
        stream_index = first_caption_index + index - 1
        start_t = max(0.0, seconds(item["start"]) - start)
        end_t = min(duration, seconds(item["end"]) - start)
        fade_out = max(start_t, end_t - 0.18)
        base_scale = "if(gt(iw,1760),1760/iw,1)"
        if caption_config.get("pop"):
            pop_scale = f"if(between(t,{start_t:.3f},{start_t + 0.22:.3f}),0.88+0.12*(t-{start_t:.3f})/0.22,1)"
        else:
            pop_scale = "1"
        if caption_config.get("animate"):
            y_expr = (
                f"H-h-{caption_config['bottom_margin']}+"
                f"if(between(t,{start_t:.3f},{start_t + 0.26:.3f}),"
                f"{caption_config['slide_px']}*(1-(t-{start_t:.3f})/0.26),0)"
            )
            filters.append(
                f"[{stream_index}:v]format=rgba,"
                f"fade=t=in:st={start_t:.3f}:d=0.16:alpha=1,"
                f"fade=t=out:st={fade_out:.3f}:d=0.18:alpha=1,"
                f"scale=w='iw*{base_scale}*{pop_scale}':h='ih*{base_scale}*{pop_scale}':eval=frame[p{index}]"
            )
        else:
            y_expr = f"H-h-{caption_config['bottom_margin']}"
            filters.append(f"[{stream_index}:v]format=rgba,scale=w='iw*{base_scale}':h='ih*{base_scale}':eval=init[p{index}]")
        next_label = f"vsub{index}"
        filters.append(f"[{current}][p{index}]overlay=x='(W-w)/2':y='{y_expr}':enable='between(t,{start_t:.3f},{end_t:.3f})'[{next_label}]")
        current = next_label

    audio_role = cameras[audio_input_index][0] if audio_input_index < len(cameras) else external_audio_role
    audio_start = max(0.0, sync_offsets.get(audio_role, 0.0) + start)
    audio_local_start = 0.0 if audio_role.startswith("external") else max(0.0, audio_start - input_seek.get(audio_input_index, 0.0))
    audio_filters = f"atrim=start={audio_local_start:.6f}:duration={duration:.6f},asetpts=PTS-STARTPTS"
    if audio_denoise:
        audio_filters += f",{audio_cleanup_filter(audio_denoise_strength)}"
    filters.append(f"[{audio_input_index}:a]{audio_filters}[a]")

    render_output = output
    if nested(APP_CONFIG, "render", "shortenSilence", default=True):
        render_output = output.with_name(f"{output.stem}_uncut{output.suffix}")

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{current}]",
            "-map",
            "[a]",
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
            "192k",
            "-shortest",
            str(render_output),
        ]
    )
    run(command)

    if nested(APP_CONFIG, "render", "shortenSilence", default=True):
        report = shorten_silences(
            render_output,
            output,
            SilenceShortenConfig(
                min_silence=float(nested(APP_CONFIG, "render", "minSilence", default=DEFAULT_MIN_SILENCE)),
                keep_silence=float(nested(APP_CONFIG, "render", "keepSilence", default=DEFAULT_KEEP_SILENCE)),
                noise=str(nested(APP_CONFIG, "render", "silenceNoise", default=DEFAULT_NOISE)),
            ),
        )
        if not nested(APP_CONFIG, "render", "keepUncut", default=False):
            render_output.unlink(missing_ok=True)
        print(
            json.dumps(
                {"output": str(output), "audio_denoise": audio_denoise, "still_inserts": still_report(still_inserts), "silence_shortening": report},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(json.dumps({"output": str(output), "audio_denoise": audio_denoise, "still_inserts": still_report(still_inserts)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
