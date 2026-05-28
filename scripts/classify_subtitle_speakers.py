from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project_paths import OUTPUT_REPORTS
from video_edit_app_config import load_app_config, nested, selected_subtitle_path


APP_CONFIG = load_app_config()


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


def mouth_motion_diagnostics(captions: list[Caption], video_path: Path | None, enabled: bool) -> dict[str, Any]:
    report: dict[str, Any] = {
        "enabled": enabled,
        "video": str(video_path) if video_path else "",
        "scores": {},
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

    max_seconds = float_value("subtitleSpeakers", "motionMaxSeconds", default=120.0)
    max_samples = max(2, int(float_value("subtitleSpeakers", "motionSamplesPerCaption", default=4.0)))

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

    scores: dict[str, float | None] = {}
    for caption in captions:
        if caption.start >= max_seconds:
            scores[str(caption.index)] = None
            continue
        sample_count = max(2, min(max_samples, int(max(2.0, (caption.end - caption.start) * 2.0))))
        start_t = caption.start + 0.15
        end_t = max(start_t + 0.01, caption.end - 0.2)
        values = [
            score
            for index in range(sample_count)
            if (score := pair_score(start_t + (end_t - start_t) * index / max(1, sample_count - 1))) is not None
        ]
        scores[str(caption.index)] = round(float(sum(values) / len(values)), 3) if values else None
    cap.release()
    sampled = sum(1 for value in scores.values() if value is not None)
    report["scores"] = scores
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
        help="Add OpenCV mouth-motion diagnostic scores for the current project video.",
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
            }
        )
    payload = {
        "source": str(srt),
        "roles": roles,
        "captions": items,
        "mouthMotion": motion,
        "mouthMotionScores": motion.get("scores", {}),
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
