from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

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

import cv2
import numpy as np

from video_edit_app_config import load_app_config, selected_subtitle_path

WORK = WORKSPACE_ROOT
APP_CONFIG = load_app_config()
SRT = selected_subtitle_path(APP_CONFIG, extensions=(".srt",))
VIDEO = OUTPUT_VIDEOS / "ST7_7550_multicam_cut_1min_color_matched_base.mp4"
OUT = OUTPUT_REPORTS / "full_transcript_speaker_roles.json"


@dataclass(frozen=True)
class Caption:
    index: int
    start: float
    end: float
    text: str


def parse_time(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def parse_srt(path: Path) -> list[Caption]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    captions: list[Caption] = []
    for block in blocks:
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->")]
        captions.append(Caption(int(rows[0]), parse_time(start_raw), parse_time(end_raw), " ".join(rows[2:])))
    return captions


def mouth_motion_scores(captions: list[Caption]) -> dict[str, float | None]:
    if not VIDEO.exists():
        return {str(caption.index): None for caption in captions}

    face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def frame_at(t: float) -> np.ndarray | None:
        cap = cv2.VideoCapture(str(VIDEO))
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        cap.release()
        return frame if ok else None

    def main_face(frame: np.ndarray) -> tuple[int, int, int, int] | None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_detector.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
        if len(faces) == 0:
            return None
        return tuple(max(faces, key=lambda r: r[2] * r[3]))

    def pair_score(t: float) -> float | None:
        a = frame_at(t)
        b = frame_at(t + 0.12)
        if a is None or b is None:
            return None
        face = main_face(a)
        if face is None:
            return None
        x, y, w, h = face
        x1, x2 = x + int(w * 0.25), x + int(w * 0.75)
        y1, y2 = y + int(h * 0.55), y + int(h * 0.86)
        crop_a = cv2.cvtColor(a[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        crop_b = cv2.cvtColor(b[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        crop_b = cv2.resize(crop_b, (crop_a.shape[1], crop_a.shape[0]))
        return float(np.mean(cv2.absdiff(crop_a, crop_b)))

    scores: dict[str, float | None] = {}
    for caption in captions:
        if caption.start >= 60:
            scores[str(caption.index)] = None
            continue
        count = max(2, min(8, int((caption.end - caption.start) * 2)))
        sample_times = np.linspace(caption.start + 0.15, max(caption.start + 0.16, caption.end - 0.2), count)
        values = [score for t in sample_times if (score := pair_score(float(t))) is not None]
        scores[str(caption.index)] = round(float(np.mean(values)), 3) if values else None
    return scores


def classify(captions: list[Caption]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for caption in captions:
        role = "onscreen"

        # In the current 1-minute edit, the interviewer turn starts after the
        # first answer's closing "ありがとうございます" and ends at the question.
        if 20.0 <= caption.start < 57.0:
            role = "interviewer"

        text = caption.text
        if caption.start < 60 and ("質問" in text or "どう感じますか" in text or "伺" in text):
            role = "interviewer"
        if (caption.start < 60 or 66.0 <= caption.start < 69.0) and text in {
            "ありがとうございます",
            "そうです、ありがとうございます",
        }:
            role = "interviewer"
        if 57.0 <= caption.start < 66.0:
            role = "onscreen"

        roles[str(caption.index)] = role
    return roles


def main() -> None:
    if SRT is None:
        raise SystemExit("No subtitle file found. Run transcription or select a subtitle file before classifying speakers.")
    captions = parse_srt(SRT)
    roles = classify(captions)
    motion_scores = mouth_motion_scores(captions)
    payload = {
        "method": "turn-structure classification with OpenCV mouth-motion diagnostic scores",
        "notes": [
            "OpenCV mouth motion alone is noisy because the visible speaker nods while listening.",
            "For the current 1-minute edit, captions 6-15 are the offscreen interviewer turn.",
        ],
        "roles": roles,
        "mouth_motion_scores": motion_scores,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUT), "interviewer_count": list(roles.values()).count("interviewer")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
