from __future__ import annotations

import argparse
import json
import math
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from face_mesh_metrics import create_face_mesh, extract_face_mesh_faces
from project_paths import OUTPUT_REPORTS, OUTPUT_TRANSCRIPTS
from video_edit_app_config import load_app_config, nested, selected_subtitle_path


APP_CONFIG = load_app_config()
TRANSCRIPT_MANIFEST = OUTPUT_TRANSCRIPTS / "manifest_sources" / "manifest_transcripts.json"


@dataclass
class Caption:
    index: int
    start_raw: str
    end_raw: str
    start: float
    end: float
    text: str


def text_value(*keys: str, default: str = "") -> str:
    value = nested(APP_CONFIG, *keys, default=default)
    return str(value) if value is not None else default


def bool_value(*keys: str, default: bool = False) -> bool:
    value = nested(APP_CONFIG, *keys, default=default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def float_value(*keys: str, default: float) -> float:
    value = nested(APP_CONFIG, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_time(value: str) -> float | None:
    text = value.strip().replace(",", ".")
    if not text:
        return None
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


def parse_srt(path: Path) -> list[Caption]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    captions: list[Caption] = []
    for block in re.split(r"\n\s*\n", text):
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        try:
            index = int(rows[0])
        except ValueError:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
        start = parse_time(start_raw)
        end = parse_time(end_raw)
        if start is None or end is None:
            continue
        captions.append(Caption(index=index, start_raw=start_raw, end_raw=end_raw, start=start, end=end, text=" ".join(rows[2:])))
    return captions


def parse_ranges_text(raw: str) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    for row in raw.splitlines():
        line = row.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([0-9:.,]+)\s*[-–]\s*([0-9:.,]+)(?:\s*\|\s*(.+))?$", line)
        if not match:
            continue
        start = parse_time(match.group(1))
        end = parse_time(match.group(2))
        if start is None or end is None or end <= start:
            continue
        ranges.append({"start": start, "end": end, "reason": (match.group(3) or "").strip()})
    return ranges


def configured_ranges() -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    raw_ranges = nested(APP_CONFIG, "subtitleSpeakers", "interviewerRanges", default=[])
    if isinstance(raw_ranges, list):
        for item in raw_ranges:
            if not isinstance(item, dict):
                continue
            try:
                start = float(item.get("start", 0.0))
                end = float(item.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            if end > start:
                ranges.append({"start": start, "end": end, "reason": str(item.get("reason") or "").strip()})
    ranges.extend(parse_ranges_text(text_value("subtitleSpeakers", "interviewerRangesText")))
    return ranges


def configured_patterns() -> list[str]:
    patterns: list[str] = []
    raw_patterns = nested(APP_CONFIG, "subtitleSpeakers", "interviewerPatterns", default=[])
    if isinstance(raw_patterns, list):
        patterns.extend(str(item).strip() for item in raw_patterns if str(item).strip())
    for row in text_value("subtitleSpeakers", "interviewerPatternsText").splitlines():
        pattern = row.strip()
        if pattern and not pattern.startswith("#"):
            patterns.append(pattern)
    seen: set[str] = set()
    unique: list[str] = []
    for pattern in patterns:
        if pattern in seen:
            continue
        seen.add(pattern)
        unique.append(pattern)
    return unique


def configured_manual_roles() -> dict[int, dict[str, str]]:
    roles: dict[int, dict[str, str]] = {}
    raw_roles = nested(APP_CONFIG, "subtitleSpeakers", "manualRoles", default=[])
    if isinstance(raw_roles, list):
        for item in raw_roles:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            role = str(item.get("role") or "").strip().lower()
            if role in {"interviewer", "onscreen"}:
                roles[index] = {"role": role, "reason": str(item.get("reason") or "manual").strip()}
    for row in text_value("subtitleSpeakers", "manualRolesText").splitlines():
        line = row.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in re.split(r"\s*\|\s*", line)]
        if len(parts) < 2:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            continue
        role = parts[1].lower()
        if role in {"interviewer", "onscreen"}:
            roles[index] = {"role": role, "reason": parts[2] if len(parts) > 2 else "manual"}
    return roles


def configured_motion_video_path() -> Path | None:
    candidates = [
        text_value("subtitleSpeakers", "motionVideoPath"),
        text_value("workflow", "inputVideoPath"),
        text_value("render", "outputPath"),
        text_value("assets", "masterVideo"),
    ]
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        if path.exists() and path.is_file():
            return path
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            if item.get("kind") != "video" or item.get("role") != "master" or not item.get("path"):
                continue
            path = Path(str(item["path"]))
            if path.exists() and path.is_file():
                return path
    return None


def configured_primary_audio_path() -> Path | None:
    if not TRANSCRIPT_MANIFEST.exists():
        return None
    try:
        manifest = json.loads(TRANSCRIPT_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return None
    transcripts = manifest.get("transcripts", [])
    if not isinstance(transcripts, list):
        return None
    primary = next((item for item in transcripts if isinstance(item, dict) and item.get("primary")), None)
    if primary is None:
        primary = next((item for item in transcripts if isinstance(item, dict)), None)
    if not isinstance(primary, dict):
        return None
    for key in ("audio", "path"):
        value = str(primary.get(key) or "")
        if value:
            path = Path(value)
            if path.exists() and path.is_file():
                return path
    return None


def summarize_values(values: list[float | None], digits: int = 5) -> dict[str, Any]:
    usable = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not usable:
        return {"sampleCount": 0, "mean": None, "peak": None, "min": None}
    return {
        "sampleCount": len(usable),
        "mean": round(sum(usable) / len(usable), digits),
        "peak": round(max(usable), digits),
        "min": round(min(usable), digits),
    }


def pearson_correlation(a_values: list[float | None], b_values: list[float | None]) -> float | None:
    pairs = [
        (float(a), float(b))
        for a, b in zip(a_values, b_values)
        if a is not None and b is not None and math.isfinite(float(a)) and math.isfinite(float(b))
    ]
    if len(pairs) < 2:
        return None
    a_mean = sum(a for a, _ in pairs) / len(pairs)
    b_mean = sum(b for _, b in pairs) / len(pairs)
    numerator = sum((a - a_mean) * (b - b_mean) for a, b in pairs)
    a_den = math.sqrt(sum((a - a_mean) ** 2 for a, _ in pairs))
    b_den = math.sqrt(sum((b - b_mean) ** 2 for _, b in pairs))
    if a_den <= 1e-9 or b_den <= 1e-9:
        return None
    return round(numerator / (a_den * b_den), 5)


def mouth_motion_diagnostics(captions: list[Caption], video_path: Path | None, enabled: bool) -> dict[str, Any]:
    report: dict[str, Any] = {
        "enabled": enabled,
        "video": str(video_path) if video_path else "",
        "scores": {},
        "openingScores": {},
        "audioRmsScores": {},
        "alignmentScores": {},
        "details": {},
        "sampledCount": 0,
    }
    if not enabled:
        report["reason"] = "disabled"
        return report
    if video_path is None:
        report["reason"] = "motion diagnostic video not found"
        return report
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception as error:
        report["reason"] = f"OpenCV unavailable: {error}"
        return report

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        report["reason"] = "could not open motion diagnostic video"
        return report
    face_detector = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    if face_detector.empty():
        cap.release()
        report["reason"] = "OpenCV face cascade unavailable"
        return report

    face_mesh = create_face_mesh(max_num_faces=1, static_image_mode=True)
    max_seconds = float_value("subtitleSpeakers", "motionMaxSeconds", default=120.0)
    max_samples = max(2, int(float_value("subtitleSpeakers", "motionSamplesPerCaption", default=4.0)))
    audio_sample_window = max(0.04, float_value("subtitleSpeakers", "audioSampleWindow", default=0.16))
    audio_path = configured_primary_audio_path()
    audio_samples: Any | None = None
    audio_sample_rate = 0
    audio_meta: dict[str, Any] = {
        "available": False,
        "path": str(audio_path) if audio_path else "",
        "reason": "primary transcript audio not found",
    }
    if audio_path is not None:
        try:
            with wave.open(str(audio_path), "rb") as handle:
                channels = max(1, handle.getnchannels())
                audio_sample_rate = int(handle.getframerate())
                sample_width = int(handle.getsampwidth())
                raw = handle.readframes(handle.getnframes())
            samples = None
            if sample_width == 2:
                samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            elif sample_width == 4:
                samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
            elif sample_width == 1:
                samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                audio_meta["reason"] = f"unsupported WAV sample width: {sample_width}"
            if samples is not None:
                if channels > 1 and len(samples) >= channels:
                    samples = samples[: len(samples) - (len(samples) % channels)].reshape(-1, channels).mean(axis=1)
                audio_samples = samples.astype(np.float32)
                audio_meta = {
                    "available": True,
                    "path": str(audio_path),
                    "sampleRate": audio_sample_rate,
                    "channels": channels,
                    "duration": round(len(audio_samples) / audio_sample_rate, 3) if audio_sample_rate else 0,
                    "sampleWindowSeconds": round(audio_sample_window, 3),
                }
        except Exception as error:
            audio_meta["reason"] = str(error)
    report["audio"] = audio_meta
    report["mouthOpeningBackend"] = "mediapipe-face-mesh" if face_mesh is not None else "opencv-lower-face-proxy"

    def frame_at(timestamp: float) -> Any | None:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, timestamp) * 1000.0)
        ok, frame = cap.read()
        return frame if ok else None

    def main_face(frame: Any) -> tuple[int, int, int, int] | None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda rect: rect[2] * rect[3])
        return int(x), int(y), int(w), int(h)

    def pair_score(timestamp: float) -> float | None:
        first = frame_at(timestamp)
        second = frame_at(timestamp + 0.12)
        if first is None or second is None:
            return None
        face = main_face(first)
        if face is None:
            return None
        x, y, w, h = face
        x1, x2 = x + int(w * 0.25), x + int(w * 0.75)
        y1, y2 = y + int(h * 0.55), y + int(h * 0.86)
        if x2 <= x1 or y2 <= y1:
            return None
        crop_a = cv2.cvtColor(first[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        crop_b = cv2.cvtColor(second[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        if crop_a.size == 0 or crop_b.size == 0:
            return None
        crop_b = cv2.resize(crop_b, (crop_a.shape[1], crop_a.shape[0]))
        return float(np.mean(cv2.absdiff(crop_a, crop_b)))

    def opencv_mouth_opening_proxy(frame: Any, face: tuple[int, int, int, int]) -> dict[str, Any] | None:
        x, y, w, h = face
        x1, x2 = x + int(w * 0.23), x + int(w * 0.77)
        y1, y2 = y + int(h * 0.58), y + int(h * 0.88)
        if x2 <= x1 or y2 <= y1:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        crop = cv2.GaussianBlur(crop, (5, 5), 0)
        threshold = float(np.percentile(crop, 32))
        dark = crop <= threshold
        if dark.size == 0:
            return None
        row_density = dark.mean(axis=1)
        active_rows = np.where(row_density >= max(0.16, float(dark.mean()) * 1.2))[0]
        dark_span = int(active_rows[-1] - active_rows[0] + 1) if len(active_rows) else 0
        mouth_width = max(1.0, float(x2 - x1))
        open_ratio = min(0.35, max(0.0, dark_span / mouth_width))
        label = "wide_open" if open_ratio >= 0.18 else "open" if open_ratio >= 0.1 else "slight" if open_ratio >= 0.045 else "closed"
        return {
            "available": True,
            "method": "opencv_lower_face_dark_gap_proxy",
            "open_ratio": round(open_ratio, 5),
            "inner_open_px": round(float(dark_span), 3),
            "mouth_width_px": round(mouth_width, 3),
            "label": label,
        }

    def mouth_opening_at(timestamp: float) -> dict[str, Any] | None:
        frame = frame_at(timestamp)
        if frame is None:
            return None
        if face_mesh is not None:
            faces = extract_face_mesh_faces(frame, face_mesh)
            if faces:
                mesh_face = max(faces, key=lambda item: float(item.get("area_ratio") or 0.0))
                mouth = mesh_face.get("mouth") if isinstance(mesh_face.get("mouth"), dict) else None
                if mouth and mouth.get("available"):
                    return mouth
        face = main_face(frame)
        if face is None:
            return None
        return opencv_mouth_opening_proxy(frame, face)

    def audio_stats(start: float, end: float) -> dict[str, Any] | None:
        if audio_samples is None or audio_sample_rate <= 0:
            return None
        start_index = max(0, int(start * audio_sample_rate))
        end_index = min(len(audio_samples), max(start_index + 1, int(end * audio_sample_rate)))
        if end_index <= start_index:
            return None
        window = audio_samples[start_index:end_index]
        if len(window) == 0:
            return None
        rms = float(np.sqrt(np.mean(np.square(window))))
        peak = float(np.max(np.abs(window)))
        return {
            "rms": round(rms, 6),
            "peak": round(peak, 6),
            "dbfs": round(20.0 * math.log10(max(rms, 1e-9)), 3),
            "sampleCount": int(len(window)),
        }

    scores: dict[str, float | None] = {}
    opening_scores: dict[str, float | None] = {}
    audio_rms_scores: dict[str, float | None] = {}
    alignment_scores: dict[str, float | None] = {}
    details: dict[str, Any] = {}
    for caption in captions:
        key = str(caption.index)
        if caption.start >= max_seconds:
            scores[key] = None
            opening_scores[key] = None
            audio_rms_scores[key] = None
            alignment_scores[key] = None
            details[key] = {"reason": "outside mouth diagnostic max seconds"}
            continue
        sample_count = max(2, min(max_samples, int(max(2.0, (caption.end - caption.start) * 2.0))))
        start_t = caption.start + 0.15
        end_t = max(start_t + 0.01, caption.end - 0.2)
        sample_rows: list[dict[str, Any]] = []
        motion_values: list[float | None] = []
        open_values: list[float | None] = []
        audio_values: list[float | None] = []
        for index in range(sample_count):
            timestamp = start_t + (end_t - start_t) * index / max(1, sample_count - 1)
            motion_score = pair_score(timestamp)
            mouth = mouth_opening_at(timestamp)
            audio = audio_stats(timestamp - audio_sample_window / 2, timestamp + audio_sample_window / 2)
            open_ratio = float(mouth["open_ratio"]) if mouth and mouth.get("open_ratio") is not None else None
            audio_rms = float(audio["rms"]) if audio and audio.get("rms") is not None else None
            motion_values.append(motion_score)
            open_values.append(open_ratio)
            audio_values.append(audio_rms)
            sample_rows.append(
                {
                    "time": round(timestamp, 3),
                    "mouthMotion": round(float(motion_score), 3) if motion_score is not None else None,
                    "mouthOpenRatio": round(float(open_ratio), 5) if open_ratio is not None else None,
                    "mouthOpenLabel": mouth.get("label") if mouth else None,
                    "audioRms": round(float(audio_rms), 6) if audio_rms is not None else None,
                    "audioDbfs": audio.get("dbfs") if audio else None,
                }
            )
        motion_summary = summarize_values(motion_values, digits=3)
        opening_summary = summarize_values(open_values, digits=5)
        caption_audio = audio_stats(caption.start, caption.end)
        correlation = pearson_correlation(open_values, audio_values)
        scores[key] = motion_summary["mean"]
        opening_scores[key] = opening_summary["mean"]
        audio_rms_scores[key] = caption_audio["rms"] if caption_audio else None
        alignment_scores[key] = correlation
        details[key] = {
            "mouthMotion": motion_summary,
            "mouthOpening": opening_summary,
            "audio": caption_audio,
            "mouthAudioCorrelation": correlation,
            "samples": sample_rows,
        }
    cap.release()
    if face_mesh is not None:
        face_mesh.close()
    sampled = sum(
        1
        for key in set(scores) | set(opening_scores)
        if scores.get(key) is not None or opening_scores.get(key) is not None
    )
    report["scores"] = scores
    report["openingScores"] = opening_scores
    report["audioRmsScores"] = audio_rms_scores
    report["alignmentScores"] = alignment_scores
    report["details"] = details
    report["sampledCount"] = sampled
    if sampled == 0:
        report["reason"] = "no face motion samples found"
    return report


def overlaps(caption: Caption, range_item: dict[str, Any]) -> bool:
    return min(caption.end, float(range_item["end"])) > max(caption.start, float(range_item["start"]))


def matching_patterns(text: str, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        try:
            if re.search(pattern, text):
                matches.append(pattern)
        except re.error:
            if pattern in text:
                matches.append(pattern)
    return matches


def classify_caption(
    caption: Caption,
    ranges: list[dict[str, Any]],
    patterns: list[str],
    manual_roles: dict[int, dict[str, str]],
) -> dict[str, Any]:
    manual = manual_roles.get(caption.index)
    if manual:
        return {"role": manual["role"], "reason": manual["reason"], "matchedPatterns": []}
    matched_ranges = [item for item in ranges if overlaps(caption, item)]
    if matched_ranges:
        reason = "; ".join(str(item.get("reason") or "configured range") for item in matched_ranges)
        return {"role": "interviewer", "reason": reason, "matchedPatterns": []}
    matched_patterns = matching_patterns(caption.text, patterns)
    if matched_patterns:
        return {"role": "interviewer", "reason": "configured pattern", "matchedPatterns": matched_patterns}
    return {"role": "onscreen", "reason": "default", "matchedPatterns": []}


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify project subtitle speaker roles from runtime-config ranges and patterns.")
    parser.add_argument("--output", type=Path, default=Path(text_value("subtitleSpeakers", "outputPath", default=str(OUTPUT_REPORTS / "full_transcript_speaker_roles.json"))))
    parser.add_argument(
        "--mouth-motion-diagnostics",
        action="store_true",
        default=bool_value("subtitleSpeakers", "mouthMotionDiagnostics", default=False),
        help="Add mouth-motion, mouth-opening, and audio-timeline diagnostic scores for the current project video.",
    )
    parser.add_argument("--motion-video", type=Path, default=configured_motion_video_path())
    args = parser.parse_args()

    srt = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
    if srt is None:
        raise SystemExit("No subtitle file found. Run transcription or select a subtitle file before classifying speaker roles.")
    captions = parse_srt(srt)
    ranges = configured_ranges()
    patterns = configured_patterns()
    manual_roles = configured_manual_roles()
    motion = mouth_motion_diagnostics(captions, args.motion_video, args.mouth_motion_diagnostics)
    roles: dict[str, str] = {}
    items: list[dict[str, Any]] = []
    for caption in captions:
        classification = classify_caption(caption, ranges, patterns, manual_roles)
        role = classification["role"]
        motion_scores = motion.get("scores", {})
        opening_scores = motion.get("openingScores", {})
        audio_scores = motion.get("audioRmsScores", {})
        alignment_scores = motion.get("alignmentScores", {})
        details = motion.get("details", {})
        detail = details.get(str(caption.index), {}) if isinstance(details, dict) else {}
        mouth_opening = detail.get("mouthOpening") if isinstance(detail, dict) else None
        audio = detail.get("audio") if isinstance(detail, dict) else None
        roles[str(caption.index)] = role
        items.append(
            {
                "index": caption.index,
                "start": caption.start,
                "end": caption.end,
                "text": caption.text,
                "role": role,
                "reason": classification["reason"],
                "matchedPatterns": classification["matchedPatterns"],
                "mouthMotionScore": motion_scores.get(str(caption.index)) if isinstance(motion_scores, dict) else None,
                "mouthOpeningMean": opening_scores.get(str(caption.index)) if isinstance(opening_scores, dict) else None,
                "mouthOpeningPeak": mouth_opening.get("peak") if isinstance(mouth_opening, dict) else None,
                "audioRmsMean": audio_scores.get(str(caption.index)) if isinstance(audio_scores, dict) else None,
                "audioDbfsMean": audio.get("dbfs") if isinstance(audio, dict) else None,
                "mouthAudioCorrelation": alignment_scores.get(str(caption.index))
                if isinstance(alignment_scores, dict)
                else None,
                "mouthTimeline": detail.get("samples", []) if isinstance(detail, dict) else [],
            }
        )
    payload = {
        "source": str(srt),
        "roles": roles,
        "captions": items,
        "mouthMotion": motion,
        "mouthMotionScores": motion.get("scores", {}),
        "mouthOpeningScores": motion.get("openingScores", {}),
        "audioRmsScores": motion.get("audioRmsScores", {}),
        "mouthAudioAlignmentScores": motion.get("alignmentScores", {}),
        "mouth_motion_scores": motion.get("scores", {}),
        "interviewerCount": sum(1 for role in roles.values() if role == "interviewer"),
        "onscreenCount": sum(1 for role in roles.values() if role == "onscreen"),
        "configuredRanges": ranges,
        "configuredPatterns": patterns,
        "configuredManualRoles": manual_roles,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "interviewerCount": payload["interviewerCount"], "onscreenCount": payload["onscreenCount"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
