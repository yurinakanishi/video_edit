from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from composition_rules import subject_target_for_face
from project_paths import OUTPUT_REPORTS


DEFAULT_INPUT_DIR = OUTPUT_REPORTS / "person_bboxes"
DEFAULT_OUTPUT_DIR = OUTPUT_REPORTS / "person_edit_plans"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert person bbox JSON into segment-level edit guidance.")
    parser.add_argument("--input", nargs="*", type=Path, default=[], help="Person bbox JSON files.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--merge-gap", type=float, default=1.25, help="Merge adjacent compatible segments across small gaps.")
    parser.add_argument("--min-segment", type=float, default=1.0, help="Minimum segment duration in seconds.")
    return parser.parse_args()


def load_inputs(args: argparse.Namespace) -> list[Path]:
    if args.input:
        return args.input
    return sorted(args.input_dir.glob("*_person_bboxes.json"))


def main_person(frame: dict[str, Any]) -> dict[str, Any] | None:
    persons = frame.get("persons") or []
    return persons[0] if persons else None


def float_value(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def ratio_pair(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    x = float_value(value[0])
    y = float_value(value[1])
    if x is None or y is None:
        return None
    return [round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)]


def bbox_ratio(box: Any, width: float, height: float) -> list[float] | None:
    if not isinstance(box, dict) or width <= 0 or height <= 0:
        return None
    x1 = float_value(box.get("x1"))
    y1 = float_value(box.get("y1"))
    x2 = float_value(box.get("x2"))
    y2 = float_value(box.get("y2"))
    if None in {x1, y1, x2, y2}:
        return None
    left = max(0.0, min(1.0, min(float(x1), float(x2)) / width))
    top = max(0.0, min(1.0, min(float(y1), float(y2)) / height))
    right = max(0.0, min(1.0, max(float(x1), float(x2)) / width))
    bottom = max(0.0, min(1.0, max(float(y1), float(y2)) / height))
    return [round(left, 4), round(top, 4), round(right, 4), round(bottom, 4)]


def average_vector(values: list[list[float] | None], digits: int = 4) -> list[float] | None:
    usable = [value for value in values if value]
    if not usable:
        return None
    length = min(len(value) for value in usable)
    return [round(sum(float(value[index]) for value in usable) / len(usable), digits) for index in range(length)]


def expanded_face_protect_bbox(face_bbox: list[float] | None) -> list[float] | None:
    if not face_bbox or len(face_bbox) < 4:
        return None
    left, top, right, bottom = [float(value) for value in face_bbox[:4]]
    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    if width <= 0 or height <= 0:
        return None
    return [
        round(max(0.0, left - width * 0.08), 4),
        round(max(0.0, top - height * 0.16), 4),
        round(min(1.0, right + width * 0.08), 4),
        round(min(1.0, bottom + height * 0.08), 4),
    ]


def significant_persons(frame: dict[str, Any]) -> list[dict[str, Any]]:
    persons = [person for person in frame.get("persons") or [] if isinstance(person, dict)]
    if len(persons) <= 1:
        return persons
    main_area = max((float_value(person.get("area_ratio")) or 0.0 for person in persons), default=0.0)
    if main_area <= 0:
        return persons
    min_absolute_area = 0.18
    min_relative_area = main_area * 0.42
    return [
        person
        for person in persons
        if (float_value(person.get("area_ratio")) or 0.0) >= min_absolute_area
        or (float_value(person.get("area_ratio")) or 0.0) >= min_relative_area
    ]


def subject_metrics(frame: dict[str, Any], person: dict[str, Any] | None) -> dict[str, Any]:
    if person is None:
        return {
            "subject_center_ratio": None,
            "focus_ratio": None,
            "focus_source": "none",
            "face_center_ratio": None,
            "face_bbox_ratio": None,
            "face_protect_bbox_ratio": None,
            "person_bbox_ratio": None,
        }

    width = float_value(frame.get("width")) or 0.0
    height = float_value(frame.get("height")) or 0.0
    subject_center = ratio_pair(person.get("center_ratio"))
    person_box = bbox_ratio(person.get("bbox"), width, height)

    face = person.get("face") if isinstance(person.get("face"), dict) else {}
    face_center = ratio_pair(face.get("center_ratio")) if face else None
    face_box = bbox_ratio(face.get("bbox"), width, height) if face else None
    face_protect_box = expanded_face_protect_bbox(face_box)

    focus = None
    focus_source = "none"
    eye_center = face.get("eye_center") if isinstance(face.get("eye_center"), dict) else None
    if eye_center and width > 0 and height > 0:
        eye_x = float_value(eye_center.get("x"))
        eye_y = float_value(eye_center.get("y"))
        if eye_x is not None and eye_y is not None:
            focus = [round(max(0.0, min(1.0, eye_x / width)), 4), round(max(0.0, min(1.0, eye_y / height)), 4)]
            focus_source = "eye_center"
    if focus is None and face_center:
        focus = face_center
        focus_source = "face_center"
    if focus is None and person_box:
        left, top, right, bottom = [float(value) for value in person_box[:4]]
        focus = [round((left + right) / 2, 4), round(top + (bottom - top) * 0.24, 4)]
        focus_source = "estimated_face_from_person_bbox"
    if focus is None and subject_center:
        focus = subject_center
        focus_source = "person_center"

    return {
        "subject_center_ratio": subject_center,
        "focus_ratio": focus,
        "focus_source": focus_source,
        "face_center_ratio": face_center,
        "face_bbox_ratio": face_box,
        "face_protect_bbox_ratio": face_protect_box,
        "person_bbox_ratio": person_box,
    }


def dominant_fixed_camera_face_direction(payload: dict[str, Any]) -> str | None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    camera_motion = payload.get("camera_motion") if isinstance(payload.get("camera_motion"), dict) else summary.get("camera_motion", {})
    if not isinstance(camera_motion, dict) or camera_motion.get("is_fixed_camera") is not True:
        return None
    counts = summary.get("face_direction_counts") if isinstance(summary.get("face_direction_counts"), dict) else {}
    usable_counts = {key: int(counts.get(key) or 0) for key in ("left", "right", "front")}
    total = sum(usable_counts.values())
    if total <= 0:
        return None
    dominant_direction, dominant_count = max(usable_counts.items(), key=lambda item: item[1])
    if dominant_count <= 0:
        return None
    if dominant_direction in {"left", "right"} and dominant_count / total >= 0.35:
        return dominant_direction
    if dominant_direction == "front" and dominant_count / total >= 0.5:
        return "front"
    return None


def composition_values(face_direction: str, fallback: dict[str, Any]) -> dict[str, Any]:
    target = subject_target_for_face(face_direction)
    if face_direction == "left":
        return {
            "look_space": "left",
            "desired_subject_x_ratio": round(target.x, 4),
            "desired_subject_y_ratio": round(target.y, 4),
            "composition_anchor": target.anchor,
        }
    if face_direction == "right":
        return {
            "look_space": "right",
            "desired_subject_x_ratio": round(target.x, 4),
            "desired_subject_y_ratio": round(target.y, 4),
            "composition_anchor": target.anchor,
        }
    return {
        "look_space": "balanced",
        "desired_subject_x_ratio": round(target.x, 4),
        "desired_subject_y_ratio": round(target.y, 4),
        "composition_anchor": target.anchor,
    }


def frame_label(frame: dict[str, Any], fixed_camera_face_direction: str | None = None) -> dict[str, Any]:
    person = main_person(frame)
    raw_person_count = int(frame.get("person_count") or len(frame.get("persons") or []))
    significant_count = len(significant_persons(frame))
    if raw_person_count == 0 or person is None:
        return {
            "presence": "none",
            "person_count": 0,
            "raw_person_count": 0,
            "significant_person_count": 0,
            "position": "none",
            "shot_size": "none",
            "face_direction": "unknown",
            "look_space": "balanced",
            "desired_subject_x_ratio": 0.5,
            "crop_strategy": "cut_candidate",
            "direction_source": "none",
        }
    if significant_count >= 2:
        return {
            "presence": "multi",
            "person_count": significant_count,
            "raw_person_count": raw_person_count,
            "significant_person_count": significant_count,
            "position": "multi",
            "shot_size": "wide",
            "face_direction": "unknown",
            "look_space": "balanced",
            "desired_subject_x_ratio": 0.5,
            "crop_strategy": "keep_wide",
            "direction_source": "multi",
        }
    position = str(person.get("position") or "center")
    shot_size = str(person.get("shot_size") or "medium")
    raw_face_direction = str(person.get("face_direction") or "unknown")
    face_direction = raw_face_direction
    direction_source = "frame"
    if fixed_camera_face_direction in {"left", "right", "front"}:
        face_direction = fixed_camera_face_direction
        direction_source = "fixed_camera_dominant"
    look_composition = person.get("look_composition") if isinstance(person.get("look_composition"), dict) else {}
    composition = composition_values(face_direction, look_composition)
    if face_direction == "left":
        crop_strategy = "shift_subject_right_for_left_look"
    elif face_direction == "right":
        crop_strategy = "shift_subject_left_for_right_look"
    else:
        crop_strategy = "center_crop" if position == "center" else f"shift_crop_{position}"
    if shot_size == "wide":
        if face_direction == "left":
            crop_strategy = "punch_in_subject_right_for_left_look"
        elif face_direction == "right":
            crop_strategy = "punch_in_subject_left_for_right_look"
        else:
            crop_strategy = f"punch_in_{position}" if position != "center" else "punch_in_center"
    return {
        "presence": "solo",
        "person_count": 1,
        "raw_person_count": raw_person_count,
        "significant_person_count": significant_count,
        "position": position,
        "shot_size": shot_size,
        "face_direction": face_direction,
        "raw_face_direction": raw_face_direction,
        "look_space": composition["look_space"],
        "desired_subject_x_ratio": float(composition["desired_subject_x_ratio"]),
        "desired_subject_y_ratio": float(composition["desired_subject_y_ratio"]),
        "composition_anchor": str(composition["composition_anchor"]),
        "crop_strategy": crop_strategy,
        "direction_source": direction_source,
    }


def compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = ("presence", "position", "shot_size", "face_direction", "crop_strategy")
    return all(a.get(key) == b.get(key) for key in keys)


def segment_recommendation(label: dict[str, Any]) -> str:
    if label["presence"] == "none":
        return "人物なし。B-roll、資料映像、またはカット候補として扱う。"
    if label["presence"] == "multi":
        return "複数人。対談・会話区間としてワイド寄りを維持する。"
    if label["face_direction"] == "left":
        return "人物が画面左を向いている。左側に視線余白を作るため、人物は右寄せでクロップする。"
    if label["face_direction"] == "right":
        return "人物が画面右を向いている。右側に視線余白を作るため、人物は左寄せでクロップする。"
    if label["shot_size"] == "wide":
        return "人物が小さい。必要ならズームまたは寄りの別カメラを優先する。"
    if label["position"] != "center":
        return "人物が中央から外れている。縦動画/正方形化ではクロップ窓を人物側へ寄せる。"
    return "人物が中央。通常のソロトーク区間として使いやすい。"


def crop_target(
    label: dict[str, Any],
    focus_ratio: list[float] | None,
    subject_center_ratio: list[float] | None,
    face_center_ratio: list[float] | None,
    face_bbox_ratio: list[float] | None,
    face_protect_bbox_ratio: list[float] | None,
    person_bbox_ratio: list[float] | None,
    focus_source: str | None,
) -> dict[str, Any] | None:
    if label["presence"] == "none" or label["presence"] == "multi" or focus_ratio is None:
        return None
    x, y = focus_ratio
    target: dict[str, Any] = {
        "x": round(float(x), 4),
        "y": round(float(y), 4),
        "focus_x": round(float(x), 4),
        "focus_y": round(float(y), 4),
        "focus_source": focus_source or "unknown",
        "desired_subject_x_ratio": round(float(label.get("desired_subject_x_ratio") or 0.5), 4),
        "desired_subject_y_ratio": round(float(label.get("desired_subject_y_ratio") or 0.382), 4),
        "composition_anchor": str(label.get("composition_anchor") or "center"),
    }
    if subject_center_ratio:
        target["subject_center_ratio"] = subject_center_ratio
    if face_center_ratio:
        target["face_center_ratio"] = face_center_ratio
    if face_bbox_ratio:
        target["face_bbox_ratio"] = face_bbox_ratio
    if face_protect_bbox_ratio:
        target["protect_bbox_ratio"] = face_protect_bbox_ratio
    if person_bbox_ratio:
        target["person_bbox_ratio"] = person_bbox_ratio
    return target


def build_segments(payload: dict[str, Any], merge_gap: float, min_segment: float) -> list[dict[str, Any]]:
    frames = payload.get("frames") or []
    if not frames:
        return []
    fixed_camera_face_direction = dominant_fixed_camera_face_direction(payload)

    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for frame in frames:
        label = frame_label(frame, fixed_camera_face_direction)
        person = main_person(frame)
        metrics = subject_metrics(frame, person)
        center = metrics["subject_center_ratio"]
        area_ratio = person.get("area_ratio") if person else None
        point = {
            "time": float(frame["time"]),
            "label": label,
            "center_ratio": center,
            "focus_ratio": metrics["focus_ratio"],
            "focus_source": metrics["focus_source"],
            "face_center_ratio": metrics["face_center_ratio"],
            "face_bbox_ratio": metrics["face_bbox_ratio"],
            "face_protect_bbox_ratio": metrics["face_protect_bbox_ratio"],
            "person_bbox_ratio": metrics["person_bbox_ratio"],
            "area_ratio": area_ratio,
            "visual": frame.get("visual") or {},
            "person_count": int(frame.get("person_count") or 0),
            "significant_person_count": label.get("significant_person_count", 0),
        }
        if current is None:
            current = {"start": point["time"], "end": point["time"], "label": label, "points": [point]}
            continue
        gap = point["time"] - float(current["end"])
        if compatible(current["label"], label) and gap <= merge_gap:
            current["end"] = point["time"]
            current["points"].append(point)
        else:
            segments.append(current)
            current = {"start": point["time"], "end": point["time"], "label": label, "points": [point]}

    if current is not None:
        segments.append(current)

    sample_interval = float(payload.get("sample_interval") or 1.0)
    normalized: list[dict[str, Any]] = []
    for segment in segments:
        start = float(segment["start"])
        end = float(segment["end"]) + sample_interval
        duration = end - start
        if duration < min_segment and normalized and compatible(normalized[-1]["label"], segment["label"]):
            normalized[-1]["end"] = end
            normalized[-1]["duration"] = round(normalized[-1]["end"] - normalized[-1]["start"], 3)
            normalized[-1]["points"].extend(segment["points"])
            continue
        points = segment["points"]
        centers = [point["center_ratio"] for point in points if point["center_ratio"]]
        focuses = [point["focus_ratio"] for point in points if point["focus_ratio"]]
        face_centers = [point["face_center_ratio"] for point in points if point["face_center_ratio"]]
        face_boxes = [point["face_bbox_ratio"] for point in points if point["face_bbox_ratio"]]
        face_protect_boxes = [point["face_protect_bbox_ratio"] for point in points if point["face_protect_bbox_ratio"]]
        person_boxes = [point["person_bbox_ratio"] for point in points if point["person_bbox_ratio"]]
        focus_sources = [str(point["focus_source"]) for point in points if point.get("focus_source")]
        areas = [float(point["area_ratio"]) for point in points if point["area_ratio"] is not None]
        visuals = [point["visual"] for point in points if point["visual"]]
        avg_center = (
            [round(sum(center[0] for center in centers) / len(centers), 4), round(sum(center[1] for center in centers) / len(centers), 4)]
            if centers
            else None
        )
        avg_focus = average_vector(focuses)
        avg_face_center = average_vector(face_centers)
        avg_face_bbox = average_vector(face_boxes)
        avg_face_protect_bbox = average_vector(face_protect_boxes)
        avg_person_bbox = average_vector(person_boxes)
        dominant_focus_source = Counter(focus_sources).most_common(1)[0][0] if focus_sources else None
        avg_area = round(sum(areas) / len(areas), 5) if areas else None
        avg_visual = (
            {
                "brightness": round(sum(item.get("brightness", 0.0) for item in visuals) / len(visuals), 4),
                "contrast": round(sum(item.get("contrast", 0.0) for item in visuals) / len(visuals), 4),
                "saturation": round(sum(item.get("saturation", 0.0) for item in visuals) / len(visuals), 4),
                "warmth": round(sum(item.get("warmth", 0.0) for item in visuals) / len(visuals), 4),
            }
            if visuals
            else None
        )
        label = segment["label"]
        normalized.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
                "label": label,
                "avg_center_ratio": avg_center,
                "avg_focus_ratio": avg_focus,
                "avg_focus_source": dominant_focus_source,
                "avg_face_center_ratio": avg_face_center,
                "avg_face_bbox_ratio": avg_face_bbox,
                "avg_face_protect_bbox_ratio": avg_face_protect_bbox,
                "avg_person_bbox_ratio": avg_person_bbox,
                "avg_area_ratio": avg_area,
                "avg_visual": avg_visual,
                "crop_target": crop_target(
                    label,
                    avg_focus,
                    avg_center,
                    avg_face_center,
                    avg_face_bbox,
                    avg_face_protect_bbox,
                    avg_person_bbox,
                    dominant_focus_source,
                ),
                "recommendation": segment_recommendation(label),
                "points": points,
            }
        )
    return normalized


def compact_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for segment in segments:
        compact.append(
            {
                "start": segment["start"],
                "end": segment["end"],
                "duration": segment["duration"],
                "presence": segment["label"]["presence"],
                "person_count": segment["label"]["person_count"],
                "raw_person_count": segment["label"].get("raw_person_count", segment["label"]["person_count"]),
                "significant_person_count": segment["label"].get("significant_person_count", segment["label"]["person_count"]),
                "position": segment["label"]["position"],
                "shot_size": segment["label"]["shot_size"],
                "face_direction": segment["label"].get("face_direction", "unknown"),
                "raw_face_direction": segment["label"].get("raw_face_direction", segment["label"].get("face_direction", "unknown")),
                "look_space": segment["label"].get("look_space", "balanced"),
                "desired_subject_x_ratio": segment["label"].get("desired_subject_x_ratio", 0.5),
                "desired_subject_y_ratio": segment["label"].get("desired_subject_y_ratio", 0.382),
                "composition_anchor": segment["label"].get("composition_anchor", "center"),
                "crop_strategy": segment["label"]["crop_strategy"],
                "direction_source": segment["label"].get("direction_source", "frame"),
                "avg_center_ratio": segment["avg_center_ratio"],
                "avg_focus_ratio": segment["avg_focus_ratio"],
                "avg_focus_source": segment["avg_focus_source"],
                "avg_face_center_ratio": segment["avg_face_center_ratio"],
                "avg_face_bbox_ratio": segment["avg_face_bbox_ratio"],
                "avg_face_protect_bbox_ratio": segment["avg_face_protect_bbox_ratio"],
                "avg_person_bbox_ratio": segment["avg_person_bbox_ratio"],
                "avg_area_ratio": segment["avg_area_ratio"],
                "avg_visual": segment["avg_visual"],
                "crop_target": segment["crop_target"],
                "recommendation": segment["recommendation"],
            }
        )
    return compact


def build_plan(path: Path, args: argparse.Namespace) -> Path:
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = build_segments(payload, args.merge_gap, args.min_segment)
    fixed_camera_face_direction = dominant_fixed_camera_face_direction(payload)
    summary = payload.get("summary")
    camera_motion = payload.get("camera_motion")
    if not isinstance(camera_motion, dict) and isinstance(summary, dict):
        camera_motion = summary.get("camera_motion")
    output = {
        "schema_version": "person-edit-plan/v1",
        "video": payload.get("video"),
        "video_path": payload.get("video_path"),
        "source_analysis": str(path),
        "fps_sample": payload.get("fps_sample"),
        "duration": payload.get("duration"),
        "camera_motion": camera_motion,
        "camera_motion_type": camera_motion.get("camera_motion_type") if isinstance(camera_motion, dict) else None,
        "is_fixed_camera": camera_motion.get("is_fixed_camera") if isinstance(camera_motion, dict) else None,
        "fixed_camera_face_direction": fixed_camera_face_direction,
        "summary": summary,
        "segments": compact_segments(segments),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / path.name.replace("_person_bboxes.json", "_person_edit_plan.json")
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    args = parse_args()
    inputs = load_inputs(args)
    if not inputs:
        raise SystemExit(f"No person bbox JSON files found under {args.input_dir}")
    outputs = [str(build_plan(path, args)) for path in inputs]
    print(json.dumps({"outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
