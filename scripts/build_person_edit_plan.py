from __future__ import annotations

import argparse
import json
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
    person_count = int(frame.get("person_count") or len(frame.get("persons") or []))
    if person_count == 0 or person is None:
        return {
            "presence": "none",
            "person_count": 0,
            "position": "none",
            "shot_size": "none",
            "face_direction": "unknown",
            "look_space": "balanced",
            "desired_subject_x_ratio": 0.5,
            "crop_strategy": "cut_candidate",
            "direction_source": "none",
        }
    if person_count >= 2:
        return {
            "presence": "multi",
            "person_count": person_count,
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
        "person_count": person_count,
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


def crop_target(label: dict[str, Any], center_ratio: list[float] | None) -> dict[str, float] | None:
    if label["presence"] == "none" or label["presence"] == "multi" or center_ratio is None:
        return None
    x, y = center_ratio
    return {
        "x": round(float(x), 4),
        "y": round(float(y), 4),
        "desired_subject_x_ratio": round(float(label.get("desired_subject_x_ratio") or 0.5), 4),
        "desired_subject_y_ratio": round(float(label.get("desired_subject_y_ratio") or 0.382), 4),
        "composition_anchor": str(label.get("composition_anchor") or "center"),
    }


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
        center = person.get("center_ratio") if person else None
        area_ratio = person.get("area_ratio") if person else None
        point = {
            "time": float(frame["time"]),
            "label": label,
            "center_ratio": center,
            "area_ratio": area_ratio,
            "visual": frame.get("visual") or {},
            "person_count": int(frame.get("person_count") or 0),
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
        areas = [float(point["area_ratio"]) for point in points if point["area_ratio"] is not None]
        visuals = [point["visual"] for point in points if point["visual"]]
        avg_center = (
            [round(sum(center[0] for center in centers) / len(centers), 4), round(sum(center[1] for center in centers) / len(centers), 4)]
            if centers
            else None
        )
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
                "avg_area_ratio": avg_area,
                "avg_visual": avg_visual,
                "crop_target": crop_target(label, avg_center),
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
