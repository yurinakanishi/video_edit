from __future__ import annotations

import json
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
DIAGNOSTICS = PROJECT_ROOT / "output" / "diagnostics" / "person_left_closeup_centering"
EDIT_PLAN_PATH = REPORTS / "edit_plan.json"
REPORT_PATH = REPORTS / "person_left_closeup_centering_report.json"
VIDEO_PATH = PROJECT_ROOT / "source" / "video" / "person-left.mp4"
FFMPEG = "ffmpeg"

WIDTH = 1280
HEIGHT = 720
TARGET_FACE_X = 640
TARGET_FACE_Y = 255


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def event_id(event: dict[str, Any]) -> str:
    return str(event.get("event_id") or event.get("id") or "")


def is_left_single_closeup(event: dict[str, Any]) -> bool:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    return (
        source.get("media_id") == "cam_person_01"
        and layout.get("type") == "single"
        and layout.get("crop_mode") in {"person_centered", "single_intro_reference_fullscreen"}
    )


def extract_frame(time_sec: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{time_sec:.3f}",
            "-i",
            str(VIDEO_PATH),
            "-frames:v",
            "1",
            str(output),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
    )


def detect_face(path: Path, cascade: cv2.CascadeClassifier) -> dict[str, Any] | None:
    image = cv2.imread(str(path))
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=4, minSize=(80, 80))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda item: int(item[2]) * int(item[3]))
    return {
        "box": [int(x), int(y), int(w), int(h)],
        "center_x": round(float(x + w / 2), 3),
        "center_y": round(float(y + h / 2), 3),
    }


def output_x(face_center_x: float, scale_h: int) -> float:
    scale = scale_h / 1080.0
    scaled_w = round(scale_h * 16 / 9)
    if scaled_w % 2:
        scaled_w += 1
    crop_x = round(face_center_x * scale - TARGET_FACE_X)
    crop_x = max(0, min(crop_x, max(0, scaled_w - WIDTH)))
    return round(face_center_x * scale - crop_x, 3)


def sample_times(start: float, end: float) -> list[float]:
    duration = max(0.01, end - start)
    if duration < 2.0:
        return [start + duration / 2]
    return [
        start + min(0.75, duration * 0.25),
        start + duration / 2,
        end - min(0.75, duration * 0.25),
    ]


def main() -> None:
    plan = read_json(EDIT_PLAN_PATH)
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)

    event_reports = []
    updated_count = 0
    for event in plan["timeline"]:
        if not is_left_single_closeup(event):
            continue
        source = event["source"]
        times = sample_times(float(source["in"]), float(source["out"]))
        detections = []
        for index, time_sec in enumerate(times):
            frame_path = DIAGNOSTICS / f"{event_id(event)}_{index}_{time_sec:.3f}.png"
            extract_frame(time_sec, frame_path)
            detected = detect_face(frame_path, cascade)
            detections.append(
                {
                    "time_sec": round(time_sec, 3),
                    "frame": str(frame_path),
                    "face": detected,
                }
            )
        xs = [item["face"]["center_x"] for item in detections if item["face"]]
        ys = [item["face"]["center_y"] for item in detections if item["face"]]
        if not xs or not ys:
            event_reports.append(
                {
                    "event_id": event_id(event),
                    "status": "no_face_detected",
                    "source": source,
                    "detections": detections,
                }
            )
            continue

        face_x = float(statistics.median(xs))
        face_y = float(statistics.median(ys))
        # 1080 keeps the left participant centerable even when the face is near
        # the source frame's left safe boundary. At 900 the same frames drift left.
        scale_h = 1080
        layout = event["layout"]
        layout["face_center_x"] = round(face_x, 3)
        layout["face_center_y"] = round(face_y, 3)
        layout["single_scale_h"] = scale_h
        layout["single_target_face_y"] = TARGET_FACE_Y
        layout["crop_analysis"] = {
            "method": "opencv_haar_face_detection_median_of_event_frames",
            "sample_count": len(detections),
            "detected_count": len(xs),
            "old_static_profile_output_x_at_900h": output_x(face_x, 900),
            "new_output_x_at_1080h": output_x(face_x, scale_h),
            "target_output_x": TARGET_FACE_X,
            "note": "When source face_x is below 640, exact centering is physically limited without padding; 1080h crop minimizes the residual.",
        }
        updated_count += 1
        event_reports.append(
            {
                "event_id": event_id(event),
                "status": "updated",
                "source": source,
                "median_face_center": {"x": round(face_x, 3), "y": round(face_y, 3)},
                "single_scale_h": scale_h,
                "old_output_x_at_900h": output_x(face_x, 900),
                "new_output_x_at_1080h": output_x(face_x, scale_h),
                "detections": detections,
            }
        )

    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": plan["updated_at"],
            "script": Path(__file__).name,
            "summary": f"Analyzed and centered {updated_count} left-person single close-up events using event-level face detection.",
        }
    )
    write_json(EDIT_PLAN_PATH, plan)
    write_json(
        REPORT_PATH,
        {
            "schema_version": "person_left_closeup_centering_report.v1",
            "project_id": "layer-x-domain-expert",
            "generated_at": plan["updated_at"],
            "cascade": str(cascade_path),
            "updated_events": updated_count,
            "events": event_reports,
        },
    )
    print(json.dumps({"updated_events": updated_count, "report": str(REPORT_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
