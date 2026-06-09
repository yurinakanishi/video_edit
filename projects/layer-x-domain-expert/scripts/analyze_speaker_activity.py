from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
JST = timezone(timedelta(hours=9))

CAMERAS = {
    "person_01": {
        "media_id": "cam_person_01",
        "role": "camera2",
        "video": PROJECT_ROOT / "source" / "video" / "person-left.mp4",
        "bbox": REPORTS / "person_bboxes" / "person-left_person_bboxes.json",
    },
    "person_02": {
        "media_id": "cam_person_02",
        "role": "camera3",
        "video": PROJECT_ROOT / "source" / "video" / "person-middle.mp4",
        "bbox": REPORTS / "person_bboxes" / "person-middle_person_bboxes.json",
    },
    "person_03": {
        "media_id": "cam_person_03",
        "role": "camera4",
        "video": PROJECT_ROOT / "source" / "video" / "person-right.mp4",
        "bbox": REPORTS / "person_bboxes" / "person-right_person_bboxes.json",
    },
}


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def bbox_index(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path, {})
    frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
    indexed = []
    for frame in frames:
        persons = frame.get("persons") if isinstance(frame.get("persons"), list) else []
        if not persons:
            continue
        largest = max(
            persons,
            key=lambda person: max(0.0, float((person.get("bbox") or {}).get("x2") or 0.0) - float((person.get("bbox") or {}).get("x1") or 0.0))
            * max(0.0, float((person.get("bbox") or {}).get("y2") or 0.0) - float((person.get("bbox") or {}).get("y1") or 0.0)),
        )
        indexed.append({"time": float(frame.get("time") or 0.0), "bbox": largest.get("bbox") or {}})
    return indexed


def nearest_bbox(indexed: list[dict[str, Any]], time_sec: float, width: int, height: int) -> tuple[int, int, int, int]:
    if not indexed:
        return (int(width * 0.3), int(height * 0.08), int(width * 0.7), int(height * 0.55))
    frame = min(indexed, key=lambda item: abs(float(item.get("time") or 0.0) - time_sec))
    box = frame.get("bbox") or {}
    x1 = int(max(0, min(width - 1, float(box.get("x1") or 0.0))))
    y1 = int(max(0, min(height - 1, float(box.get("y1") or 0.0))))
    x2 = int(max(x1 + 1, min(width, float(box.get("x2") or width))))
    y2 = int(max(y1 + 1, min(height, float(box.get("y2") or height))))
    return (x1, y1, x2, y2)


def mouth_roi_from_person_bbox(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    # The detector boxes are mostly upper-body boxes. This region captures lower face and jaw motion.
    rx1 = int(x1 + w * 0.27)
    rx2 = int(x1 + w * 0.74)
    ry1 = int(y1 + h * 0.14)
    ry2 = int(y1 + h * 0.39)
    return (
        max(0, min(width - 2, rx1)),
        max(0, min(height - 2, ry1)),
        max(1, min(width, rx2)),
        max(1, min(height, ry2)),
    )


def read_gray_at(capture: cv2.VideoCapture, time_sec: float) -> np.ndarray | None:
    capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_sec) * 1000.0)
    ok, frame = capture.read()
    if not ok or frame is None:
        return None
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def motion_score(video: Path, indexed_bboxes: list[dict[str, Any]], start: float, end: float) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        return {"score": 0.0, "samples": 0, "status": "video_open_failed"}
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        capture.release()
        return {"score": 0.0, "samples": 0, "status": "invalid_dimensions"}
    sample_end = min(end, start + 3.0)
    times = np.arange(start, sample_end, 0.5)
    if len(times) < 3:
        times = np.array([start, start + 0.25, start + 0.5])
    box = nearest_bbox(indexed_bboxes, start, width, height)
    rx1, ry1, rx2, ry2 = mouth_roi_from_person_bbox(box, width, height)
    previous = None
    scores: list[float] = []
    for time_value in times:
        gray = read_gray_at(capture, float(time_value))
        if gray is None:
            continue
        roi = gray[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            continue
        roi = cv2.GaussianBlur(roi, (5, 5), 0)
        if previous is not None and previous.shape == roi.shape:
            diff = cv2.absdiff(previous, roi)
            scores.append(float(np.mean(diff)))
        previous = roi
    capture.release()
    if not scores:
        return {"score": 0.0, "samples": 0, "status": "no_motion_samples", "roi": [rx1, ry1, rx2, ry2]}
    return {
        "score": round(float(np.mean(scores)), 5),
        "peak_score": round(float(np.max(scores)), 5),
        "samples": len(scores),
        "status": "sampled",
        "roi": [rx1, ry1, rx2, ry2],
    }


def confidence(top: float, second: float) -> float:
    if top <= 0:
        return 0.0
    ratio = top / max(second, 0.001)
    value = min(1.0, max(0.0, (ratio - 1.0) / 0.9))
    return round(0.35 + value * 0.55, 3)


def main() -> None:
    semantic = read_json(REPORTS / "semantic_marks.json", {})
    offsets_payload = read_json(REPORTS / "app_sync_offsets.json", {})
    offsets = offsets_payload.get("offsets") if isinstance(offsets_payload.get("offsets"), dict) else {}
    bbox_indexes = {person_id: bbox_index(config["bbox"]) for person_id, config in CAMERAS.items()}
    segments = []
    for item in (semantic.get("punchline_subtitles") or [])[:12]:
        master_start = float(item.get("start") or 0.0)
        master_end = float(item.get("end") or master_start + 4.0)
        scores = []
        for person_id, config in CAMERAS.items():
            role = config["role"]
            source_start = max(0.0, master_start + float(offsets.get(role, 0.0)))
            source_end = max(source_start + 0.5, master_end + float(offsets.get(role, 0.0)))
            result = motion_score(config["video"], bbox_indexes[person_id], source_start, source_end)
            scores.append(
                {
                    "person_id": person_id,
                    "media_id": config["media_id"],
                    "role": role,
                    "source_start": round(source_start, 3),
                    "source_end": round(source_end, 3),
                    **result,
                }
            )
        ranked = sorted(scores, key=lambda score: float(score.get("score") or 0.0), reverse=True)
        top = float(ranked[0].get("score") or 0.0) if ranked else 0.0
        second = float(ranked[1].get("score") or 0.0) if len(ranked) > 1 else 0.0
        segments.append(
            {
                "segment_id": item.get("segment_id"),
                "start": item.get("start"),
                "end": item.get("end"),
                "text": item.get("text"),
                "active_person_id": ranked[0]["person_id"] if ranked else None,
                "reaction_person_id": ranked[1]["person_id"] if len(ranked) > 1 else None,
                "confidence": confidence(top, second),
                "activity_scores": ranked,
                "selection_note": "Heuristic mouth-region motion from synced close cameras; use as edit guidance, not identity proof.",
            }
        )
    payload = {
        "schema_version": "speaker_activity_analysis.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "method": "synced close-camera lower-face motion ranking",
        "limitations": [
            "No diarized speaker labels are available yet.",
            "Camera4 remains manual sync review, so right-participant activity is provisional.",
            "This does not verify real identity; it only ranks visible participant activity by person_id placeholder.",
        ],
        "segments": segments,
    }
    write_json(REPORTS / "speaker_activity_analysis.json", payload)
    print(json.dumps({"output": str(REPORTS / "speaker_activity_analysis.json"), "segments": len(segments)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
