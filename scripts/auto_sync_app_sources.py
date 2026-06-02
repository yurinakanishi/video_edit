from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from video_edit_core.paths import OUTPUT_REPORTS, ROOT as WORKSPACE_ROOT
from video_edit_core.app_config import load_app_config, nested, optional_path, transcript_manifest_fingerprint


WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
OUT = OUTPUT_REPORTS / "app_sync_offsets.json"
TRANSCRIPT_COMPARISON = OUTPUT_REPORTS / "transcript_comparison.json"
SAMPLE_RATE = 8000
FRAME_SECONDS = 0.05
WINDOW_SECONDS = 10.0
HOP_SECONDS = 5.0
FINE_FRAME_SECONDS = 0.01
FINE_WINDOW_SECONDS = 24.0
FINE_SEARCH_RADIUS = 0.75
MOUTH_FRAME_SECONDS = 0.2
MOUTH_WINDOW_SECONDS = 12.0
MOUTH_HOP_SECONDS = 4.0
CAMERA_ROLES = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}


def float_config(*keys: str, default: float) -> float:
    try:
        return float(nested(APP_CONFIG, *keys, default=default))
    except (TypeError, ValueError):
        return default


def media_manifest() -> dict[str, object]:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = nested(APP_CONFIG, "assets", "mediaManifestPath", default="")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def manifest_items(kind: str | None = None) -> list[dict[str, object]]:
    manifest = media_manifest()
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        return []
    items = [item for item in files if isinstance(item, dict)]
    if kind is not None:
        items = [item for item in items if item.get("kind") == kind]
    return items


def source_path(name: str) -> Path | None:
    value = nested(APP_CONFIG, "assets", name, default="")
    return Path(value) if value else None


def normalized_path_key(path: str | Path | None) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve()).casefold()
    except OSError:
        return str(path).casefold()


def paths_match(left: str | Path | None, right: str | Path | None) -> bool:
    left_key = normalized_path_key(left)
    right_key = normalized_path_key(right)
    return bool(left_key and right_key and left_key == right_key)


def role_sort_value(role: str) -> int:
    if role == "master":
        return 0
    if role.startswith("camera"):
        try:
            return int(role.replace("camera", ""))
        except ValueError:
            return 50
    if role.startswith("external"):
        suffix = role.replace("external", "")
        return 100 + (int(suffix) if suffix.isdigit() else 1)
    return 200


def probe_duration(path: Path) -> float | None:
    try:
        completed = subprocess.run(
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
            cwd=WORK,
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(completed.stdout.strip())
    except (OSError, subprocess.CalledProcessError, TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def item_duration(item: dict[str, object], path: Path) -> float | None:
    metadata = item.get("metadata", {})
    if isinstance(metadata, dict):
        try:
            duration = float(metadata.get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        if duration > 0:
            return duration
    return probe_duration(path)


def time_sources() -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in manifest_items():
        kind = str(item.get("kind") or "")
        role = str(item.get("role") or "")
        if kind == "video" and role not in CAMERA_ROLES:
            continue
        if kind == "audio" and not role.startswith("external"):
            continue
        if kind not in {"video", "audio"} or role == "ignore":
            continue
        path_value = str(item.get("path") or "")
        path = Path(path_value) if path_value else None
        if path is None or not path.exists():
            continue
        key = normalized_path_key(path)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "role": role or ("external" if kind == "audio" else "source"),
                "kind": kind,
                "path": path,
                "duration": item_duration(item, path),
            }
        )

    if not sources and not media_manifest():
        for role, kind, key in (
            ("master", "video", "masterVideo"),
            ("camera2", "video", "rightCloseVideo"),
            ("camera3", "video", "leftCloseVideo"),
            ("external", "audio", "externalAudio"),
        ):
            path = source_path(key)
            if path and path.exists():
                sources.append({"role": role, "kind": kind, "path": path, "duration": probe_duration(path)})

    return sorted(sources, key=lambda source: role_sort_value(str(source["role"])))


def decode_audio(path: Path) -> np.ndarray:
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "-",
    ]
    raw = subprocess.check_output(command, cwd=WORK)
    if not raw:
        raise RuntimeError(f"No audio decoded from {path}")
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def normalize_feature(feature: np.ndarray) -> np.ndarray:
    feature = feature.astype(np.float32)
    feature -= np.mean(feature)
    std = np.std(feature)
    if std > 1e-8:
        feature /= std
    return feature.astype(np.float32)


def envelope(audio: np.ndarray, frame_seconds: float = FRAME_SECONDS, emphasize_changes: bool = False) -> np.ndarray:
    frame = max(1, round(SAMPLE_RATE * frame_seconds))
    usable = len(audio) // frame * frame
    if usable == 0:
        raise RuntimeError("Audio is too short to sync")
    framed = audio[:usable].reshape(-1, frame)
    env = np.sqrt(np.mean(framed * framed, axis=1))
    env = np.log1p(env * 50.0)
    if emphasize_changes:
        smooth = np.convolve(env, np.ones(9, dtype=np.float32) / 9.0, mode="same")
        env = np.diff(smooth, prepend=smooth[0])
    return normalize_feature(env)


def fft_correlate(alt: np.ndarray, master: np.ndarray) -> tuple[int, float]:
    if len(alt) < len(master):
        raise RuntimeError("Alternate feature is shorter than the sync window.")
    master = master - float(np.mean(master))
    m = len(master)
    valid = np.correlate(alt, master, mode="valid")
    ones = np.ones(m, dtype=np.float32)
    alt_sum = np.convolve(alt, ones, mode="valid")
    alt_sum2 = np.convolve(alt * alt, ones, mode="valid")
    alt_energy = np.maximum(alt_sum2 - (alt_sum * alt_sum / m), 1e-9)
    master_energy = float(np.sum(master * master))
    denom = np.sqrt(np.maximum(alt_energy * master_energy, 1e-9))
    ncc = valid / denom
    best = int(np.argmax(ncc))
    score = float(ncc[best])
    return best, score


def best_window_offset_for_features(
    alt_feature: np.ndarray,
    master_feature: np.ndarray,
    *,
    frame_seconds: float,
    window_seconds: float,
    hop_seconds: float,
) -> tuple[float, float, float]:
    window = max(8, round(window_seconds / frame_seconds))
    window = min(window, len(master_feature), len(alt_feature))
    if window < 8:
        raise RuntimeError("Feature sequence is too short to sync")
    hop = max(1, round(hop_seconds / frame_seconds))

    if len(master_feature) <= window:
        lag, score = fft_correlate(alt_feature, master_feature[:window])
        return lag * frame_seconds, 0.0, score

    best_offset = 0.0
    best_master_start = 0.0
    best_score = -1e9
    for start in range(0, len(master_feature) - window + 1, hop):
        chunk = master_feature[start : start + window]
        if float(np.std(chunk)) < 0.05:
            continue
        lag, score = fft_correlate(alt_feature, chunk)
        if score > best_score:
            best_score = score
            best_master_start = start * frame_seconds
            best_offset = lag * frame_seconds - best_master_start
    if best_score <= -1e8:
        raise RuntimeError("No usable sync window found")
    return best_offset, best_master_start, best_score


def best_window_offset(alt_env: np.ndarray, master_env: np.ndarray) -> tuple[float, float, float]:
    return best_window_offset_for_features(
        alt_env,
        master_env,
        frame_seconds=FRAME_SECONDS,
        window_seconds=WINDOW_SECONDS,
        hop_seconds=HOP_SECONDS,
    )


def corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b) or len(a) < 100:
        return -1.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-8:
        return -1.0
    return float(np.dot(a, b) / denom)


def fine_refine_offset(
    alt_audio: np.ndarray,
    master_audio: np.ndarray,
    coarse_offset: float,
    master_start: float,
) -> dict[str, object]:
    frame_seconds = float_config("analysis", "syncFineFrameSeconds", default=FINE_FRAME_SECONDS)
    window_seconds = float_config("analysis", "syncFineWindowSeconds", default=FINE_WINDOW_SECONDS)
    search_radius = float_config("analysis", "syncFineSearchRadius", default=FINE_SEARCH_RADIUS)
    frame_seconds = max(0.005, min(frame_seconds, 0.05))
    window_seconds = max(4.0, window_seconds)
    search_radius = max(0.0, min(search_radius, 3.0))

    master_env = envelope(master_audio, frame_seconds=frame_seconds, emphasize_changes=True)
    alt_env = envelope(alt_audio, frame_seconds=frame_seconds, emphasize_changes=True)
    master_duration = len(master_env) * frame_seconds
    alt_duration = len(alt_env) * frame_seconds
    master_start = max(0.0, min(master_start, max(0.0, master_duration - 1.0)))
    window_seconds = min(window_seconds, max(1.0, master_duration - master_start))
    window_frames = max(100, round(window_seconds / frame_seconds))
    master_start = max(0.0, min(master_start, max(0.0, master_duration - window_frames * frame_seconds)))
    m0 = round(master_start / frame_seconds)
    m1 = min(len(master_env), m0 + window_frames)
    master_slice = master_env[m0:m1]
    if len(master_slice) < 100:
        return {
            "offsetSeconds": coarse_offset,
            "coarseOffsetSeconds": coarse_offset,
            "refined": False,
            "reason": "master window too short",
        }

    best: tuple[float, float] | None = None
    step_count = round(search_radius / frame_seconds)
    for shift_frame in range(-step_count, step_count + 1):
        shift = shift_frame * frame_seconds
        alt_start = coarse_offset + master_start + shift
        if alt_start < 0 or alt_start + len(master_slice) * frame_seconds > alt_duration:
            continue
        a0 = round(alt_start / frame_seconds)
        a1 = a0 + len(master_slice)
        score = corr(master_slice, alt_env[a0:a1])
        if best is None or score > best[0]:
            best = (score, shift)

    if best is None:
        return {
            "offsetSeconds": coarse_offset,
            "coarseOffsetSeconds": coarse_offset,
            "refined": False,
            "reason": "no valid fine-search window",
        }
    score, shift = best
    return {
        "offsetSeconds": coarse_offset + shift,
        "coarseOffsetSeconds": coarse_offset,
        "refinedShiftSeconds": shift,
        "refinedScore": score,
        "refined": True,
        "refinedFrameSeconds": frame_seconds,
        "refinedWindowSeconds": len(master_slice) * frame_seconds,
        "refinedMasterStartSeconds": master_start,
    }


def waveform_evidence(
    path: Path,
    reference_path: Path,
    reference_audio: np.ndarray | None,
    reference_env: np.ndarray | None,
) -> dict[str, object]:
    if paths_match(path, reference_path):
        return {"available": True, "offsetSeconds": 0.0, "score": 1.0, "kind": "reference"}
    if reference_audio is None or reference_env is None:
        return {"available": False, "reason": "reference audio unavailable"}
    try:
        alt_audio = decode_audio(path)
        alt_env = envelope(alt_audio)
        offset_seconds, master_start, score = best_window_offset(alt_env, reference_env)
        refined = fine_refine_offset(alt_audio, reference_audio, offset_seconds, master_start)
        refined_offset = float(refined.get("offsetSeconds", offset_seconds))
        return {
            "available": True,
            "offsetSeconds": round(refined_offset, 6),
            "coarseOffsetSeconds": round(offset_seconds, 6),
            "score": round(score, 6),
            "matchedMasterStartSeconds": round(master_start, 6),
            "fineRefinement": refined,
        }
    except Exception as error:
        return {"available": False, "reason": str(error)}


def transcript_class_rank(value: Any) -> int:
    text = str(value or "").strip().lower().replace("-", "_")
    if text == "strong":
        return 2
    if text in {"usable", "usable_review"}:
        return 1
    if text == "primary":
        return 3
    return 0


def transcript_report_path() -> Path:
    return Path(str(nested(APP_CONFIG, "transcriptComparison", "outputPath", default=str(TRANSCRIPT_COMPARISON))))


def transcript_evidence_by_role(reference: dict[str, object], sources: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    evidence = {
        str(source["role"]): {"available": False, "reason": "transcript comparison unavailable"}
        for source in sources
    }
    path = transcript_report_path()
    if not path.exists():
        for item in evidence.values():
            item["reason"] = "comparison report missing"
        return evidence
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        for item in evidence.values():
            item["reason"] = f"comparison report unreadable: {error}"
        return evidence
    if not isinstance(report, dict):
        return evidence

    expected_fingerprint = transcript_manifest_fingerprint(APP_CONFIG)
    actual_fingerprint = str(report.get("manifestFingerprint") or "")
    if expected_fingerprint and actual_fingerprint != expected_fingerprint:
        for item in evidence.values():
            item["reason"] = "comparison report does not match current media manifest"
        return evidence

    source_paths = {str(source["role"]): Path(source["path"]) for source in sources}
    primary = report.get("primary", {})
    primary_role = str(primary.get("role") or "") if isinstance(primary, dict) else ""
    primary_path = str(primary.get("path") or "") if isinstance(primary, dict) else ""
    if primary_role not in source_paths or (primary_path and not paths_match(primary_path, source_paths[primary_role])):
        primary_role = next(
            (role for role, source_path in source_paths.items() if primary_path and paths_match(primary_path, source_path)),
            "",
        )
    if not primary_role:
        for item in evidence.values():
            item["reason"] = "primary transcript is not one of the sync sources"
        return evidence

    offset_to_primary: dict[str, dict[str, object]] = {
        primary_role: {
            "offsetToPrimary": 0.0,
            "matchClass": "primary",
            "score": 1.0,
        }
    }
    for item in report.get("items", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if role not in source_paths:
            continue
        item_path = str(item.get("path") or "")
        if item_path and not paths_match(item_path, source_paths[role]):
            continue
        offset_value = item.get("suggestedOffsetSeconds")
        if offset_value is None and isinstance(item.get("bestMatch"), dict):
            offset_value = item["bestMatch"].get("offsetSeconds")
        try:
            offset = float(offset_value)
        except (TypeError, ValueError):
            continue
        score = item.get("bestScore")
        if score is None and isinstance(item.get("bestMatch"), dict):
            score = item["bestMatch"].get("score")
        offset_to_primary[role] = {
            "offsetToPrimary": offset,
            "matchClass": str(item.get("bestClass") or ""),
            "score": score,
        }

    reference_role = str(reference["role"])
    reference_item = offset_to_primary.get(reference_role)
    if reference_item is None:
        for item in evidence.values():
            item["reason"] = "reference transcript match unavailable"
        return evidence

    reference_to_primary = float(reference_item["offsetToPrimary"])
    for role, source_path in source_paths.items():
        item = offset_to_primary.get(role)
        if item is None:
            evidence[role] = {"available": False, "reason": "source transcript match unavailable", "path": str(path)}
            continue
        try:
            source_to_primary = float(item["offsetToPrimary"])
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            evidence[role] = {"available": False, "reason": "source transcript score unavailable", "path": str(path)}
            continue
        match_class = str(item.get("matchClass") or "")
        evidence[role] = {
            "available": transcript_class_rank(match_class) > 0,
            "offsetSeconds": round(reference_to_primary - source_to_primary, 6),
            "score": round(score, 6),
            "matchClass": match_class,
            "path": str(path),
            "primaryRole": primary_role,
            "sourcePath": str(source_path),
        }
    return evidence


def mouth_motion_signal(path: Path) -> dict[str, object]:
    max_seconds = max(5.0, float_config("analysis", "syncMouthMaxSeconds", default=120.0))
    try:
        import cv2  # type: ignore
    except Exception as error:
        return {"available": False, "reason": f"OpenCV unavailable: {error}"}

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"available": False, "reason": "could not open video"}
    face_detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    if face_detector.empty():
        cap.release()
        return {"available": False, "reason": "OpenCV face cascade unavailable"}

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    duration = frame_count / fps if fps > 0 and frame_count > 0 else probe_duration(path)
    if not duration or duration <= 0:
        cap.release()
        return {"available": False, "reason": "video duration unavailable"}
    end = min(float(duration), max_seconds)
    samples = max(2, int(end / MOUTH_FRAME_SECONDS))
    previous_crop: Any | None = None
    values: list[float] = []
    detected = 0

    for index in range(samples):
        timestamp = index * MOUTH_FRAME_SECONDS
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
        if len(faces) == 0:
            values.append(0.0)
            previous_crop = None
            continue
        x, y, w, h = max(faces, key=lambda rect: rect[2] * rect[3])
        x1, x2 = int(x + w * 0.25), int(x + w * 0.75)
        y1, y2 = int(y + h * 0.55), int(y + h * 0.86)
        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            values.append(0.0)
            previous_crop = None
            continue
        crop = cv2.resize(crop, (64, 32))
        detected += 1
        if previous_crop is None:
            values.append(0.0)
        else:
            values.append(float(np.mean(cv2.absdiff(previous_crop, crop))))
        previous_crop = crop

    cap.release()
    if detected < 8 or len(values) < 8:
        return {"available": False, "reason": "not enough mouth samples"}
    return {
        "available": True,
        "feature": normalize_feature(np.asarray(values, dtype=np.float32)),
        "sampleCount": len(values),
        "detectedCount": detected,
        "sampledSeconds": round(len(values) * MOUTH_FRAME_SECONDS, 3),
    }


def mouth_evidence_by_role(reference: dict[str, object], sources: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    evidence = {str(source["role"]): {"available": False, "reason": "mouth analysis unavailable"} for source in sources}
    if str(reference.get("kind")) != "video":
        for item in evidence.values():
            item["reason"] = "reference source is not video"
        return evidence

    cache: dict[str, dict[str, object]] = {}

    def signal_for(path: Path) -> dict[str, object]:
        key = normalized_path_key(path)
        if key not in cache:
            cache[key] = mouth_motion_signal(path)
        return cache[key]

    reference_path = Path(reference["path"])
    reference_signal = signal_for(reference_path)
    if not reference_signal.get("available"):
        for item in evidence.values():
            item["reason"] = f"reference mouth analysis unavailable: {reference_signal.get('reason')}"
        return evidence

    reference_feature = reference_signal["feature"]
    if not isinstance(reference_feature, np.ndarray):
        return evidence

    for source in sources:
        role = str(source["role"])
        path = Path(source["path"])
        if str(source.get("kind")) != "video":
            evidence[role] = {"available": False, "reason": "source is not video"}
            continue
        if paths_match(path, reference_path):
            evidence[role] = {
                "available": True,
                "offsetSeconds": 0.0,
                "score": 1.0,
                "kind": "reference",
                "sampleCount": reference_signal.get("sampleCount"),
            }
            continue
        source_signal = signal_for(path)
        if not source_signal.get("available"):
            evidence[role] = {"available": False, "reason": str(source_signal.get("reason") or "mouth analysis failed")}
            continue
        source_feature = source_signal["feature"]
        if not isinstance(source_feature, np.ndarray):
            evidence[role] = {"available": False, "reason": "mouth feature unavailable"}
            continue
        try:
            offset, master_start, score = best_window_offset_for_features(
                source_feature,
                reference_feature,
                frame_seconds=MOUTH_FRAME_SECONDS,
                window_seconds=MOUTH_WINDOW_SECONDS,
                hop_seconds=MOUTH_HOP_SECONDS,
            )
            evidence[role] = {
                "available": True,
                "offsetSeconds": round(offset, 6),
                "score": round(score, 6),
                "matchedMasterStartSeconds": round(master_start, 6),
                "sampleCount": source_signal.get("sampleCount"),
                "detectedCount": source_signal.get("detectedCount"),
            }
        except Exception as error:
            evidence[role] = {"available": False, "reason": str(error)}
    return evidence


def select_evidence(evidence: dict[str, dict[str, object]]) -> tuple[str, float, float]:
    waveform = evidence.get("waveform", {})
    transcript = evidence.get("transcript", {})
    mouth = evidence.get("mouth", {})
    waveform_threshold = float_config("render", "transcriptSyncFallbackBelowScore", default=0.65)
    mouth_threshold = float_config("analysis", "syncMouthScoreThreshold", default=0.35)

    def available(item: dict[str, object]) -> bool:
        return bool(item.get("available")) and item.get("offsetSeconds") is not None

    def offset(item: dict[str, object]) -> float:
        return float(item.get("offsetSeconds", 0.0))

    def score(item: dict[str, object]) -> float:
        try:
            return float(item.get("score", 0.0))
        except (TypeError, ValueError):
            return 0.0

    waveform_score = score(waveform)
    if available(waveform) and waveform_score >= waveform_threshold:
        return "waveform", offset(waveform), waveform_score
    if available(transcript) and transcript_class_rank(transcript.get("matchClass")) >= 1:
        return "transcript", offset(transcript), score(transcript)
    if available(mouth) and score(mouth) >= mouth_threshold:
        return "mouth", offset(mouth), score(mouth)
    if available(waveform):
        return "waveform", offset(waveform), waveform_score
    if available(transcript):
        return "transcript", offset(transcript), score(transcript)
    if available(mouth):
        return "mouth", offset(mouth), score(mouth)
    return "default", 0.0, 0.0


def rounded(value: float) -> float:
    return round(float(value), 3)


def build_timeline(sources: list[dict[str, object]], offsets: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    timeline: list[dict[str, object]] = []
    for source in sources:
        role = str(source["role"])
        duration = source.get("duration")
        try:
            duration_seconds = float(duration) if duration is not None else 0.0
        except (TypeError, ValueError):
            duration_seconds = 0.0
        if duration_seconds <= 0:
            continue
        offset_item = offsets.get(role, {})
        try:
            offset_seconds = float(offset_item.get("offsetSeconds", 0.0))
        except (TypeError, ValueError):
            offset_seconds = 0.0
        start = -offset_seconds
        end = duration_seconds - offset_seconds
        timeline.append(
            {
                "role": role,
                "kind": source.get("kind") or "",
                "path": str(source["path"]),
                "durationSeconds": rounded(duration_seconds),
                "offsetSeconds": rounded(offset_seconds),
                "timelineStartSeconds": rounded(start),
                "timelineEndSeconds": rounded(end),
                "score": offset_item.get("score", 0.0),
                "selectedEvidence": offset_item.get("selectedEvidence", "default"),
            }
        )
    return timeline


def overlap_segments(timeline: list[dict[str, object]]) -> list[dict[str, object]]:
    events: list[tuple[float, str, str]] = []
    for item in timeline:
        try:
            start = float(item["timelineStartSeconds"])
            end = float(item["timelineEndSeconds"])
        except (KeyError, TypeError, ValueError):
            continue
        role = str(item.get("role") or "")
        if role and end > start:
            events.append((start, "start", role))
            events.append((end, "end", role))
    events.sort(key=lambda event: event[0])
    if not events:
        return []

    active: set[str] = set()
    output: list[dict[str, object]] = []
    previous = events[0][0]
    index = 0
    while index < len(events):
        current = events[index][0]
        if current > previous + 1e-6 and len(active) >= 2:
            output.append(
                {
                    "startSeconds": rounded(previous),
                    "endSeconds": rounded(current),
                    "activeRoles": sorted(active, key=role_sort_value),
                }
            )
        while index < len(events) and abs(events[index][0] - current) <= 1e-9:
            _, event_type, role = events[index]
            if event_type == "end":
                active.discard(role)
            else:
                active.add(role)
            index += 1
        previous = current
    return output


def main() -> None:
    sources = time_sources()
    if not sources:
        raise RuntimeError("Select at least one video or audio source before running sync.")
    reference = next((source for source in sources if source.get("role") == "master"), sources[0])
    reference_role = str(reference["role"])
    reference_path = Path(reference["path"])

    try:
        reference_audio = decode_audio(reference_path)
        reference_env = envelope(reference_audio)
        reference_waveform_error = ""
    except Exception as error:
        reference_audio = None
        reference_env = None
        reference_waveform_error = str(error)

    transcript_evidence = transcript_evidence_by_role(reference, sources)
    mouth_evidence = mouth_evidence_by_role(reference, sources)

    offsets: dict[str, dict[str, object]] = {}
    for source in sources:
        role = str(source["role"])
        path = Path(source["path"])
        waveform = waveform_evidence(path, reference_path, reference_audio, reference_env)
        if paths_match(path, reference_path) and reference_waveform_error:
            waveform = {"available": False, "reason": reference_waveform_error}
        evidence = {
            "waveform": waveform,
            "transcript": transcript_evidence.get(role, {"available": False, "reason": "transcript comparison unavailable"}),
            "mouth": mouth_evidence.get(role, {"available": False, "reason": "mouth analysis unavailable"}),
        }
        selected_evidence, offset_seconds, score = select_evidence(evidence)
        item: dict[str, object] = {
            "path": str(path),
            "kind": source.get("kind") or "",
            "offsetSeconds": offset_seconds,
            "score": score,
            "selectedEvidence": selected_evidence,
            "evidence": evidence,
            "note": "source timestamp = synced timeline timestamp + offsetSeconds",
        }
        if waveform.get("available"):
            for key in ("coarseOffsetSeconds", "matchedMasterStartSeconds", "fineRefinement"):
                if key in waveform:
                    item[key] = waveform[key]
        if paths_match(path, reference_path):
            item["offsetSeconds"] = 0.0
            item["score"] = 1.0
            item["selectedEvidence"] = "reference"
            item["note"] = "timeline reference"
        offsets[role] = item

    timeline = build_timeline(sources, offsets)
    overlaps = overlap_segments(timeline)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timelineRole": reference_role,
        "manifestPath": nested(APP_CONFIG, "assets", "mediaManifestPath", default=""),
        "sourceCount": len(sources),
        "offsets": offsets,
        "timeline": timeline,
        "overlapSegments": overlaps,
        "hasOverlap": bool(overlaps),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUT), **payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
