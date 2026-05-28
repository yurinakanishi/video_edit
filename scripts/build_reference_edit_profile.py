from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from project_paths import OUTPUT_REPORTS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact editing reference profile from person bbox metadata.")
    parser.add_argument("--input-dir", type=Path, default=OUTPUT_REPORTS / "reference_person_bboxes")
    parser.add_argument("--plan-dir", type=Path, default=OUTPUT_REPORTS / "reference_edit_plans")
    parser.add_argument("--output", type=Path, default=OUTPUT_REPORTS / "reference_edit_profile.json")
    return parser.parse_args()


def average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 5) if values else None


def float_value(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def average_vector(values: list[list[float] | None], digits: int = 4) -> list[float] | None:
    usable = [value for value in values if value]
    if not usable:
        return None
    length = min(len(value) for value in usable)
    return [round(sum(float(value[index]) for value in usable) / len(usable), digits) for index in range(length)]


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


def face_focus_ratio(frame: dict[str, Any]) -> list[float] | None:
    persons = frame.get("persons") or []
    person = persons[0] if persons and isinstance(persons[0], dict) else None
    if person is None:
        return None
    face = person.get("face") if isinstance(person.get("face"), dict) else None
    if not face:
        return None
    width = float_value(frame.get("width")) or 0.0
    height = float_value(frame.get("height")) or 0.0
    eye_center = face.get("eye_center") if isinstance(face.get("eye_center"), dict) else None
    if eye_center and width > 0 and height > 0:
        eye_x = float_value(eye_center.get("x"))
        eye_y = float_value(eye_center.get("y"))
        if eye_x is not None and eye_y is not None:
            return [round(max(0.0, min(1.0, eye_x / width)), 4), round(max(0.0, min(1.0, eye_y / height)), 4)]
    center = face.get("center_ratio")
    if isinstance(center, list) and len(center) >= 2:
        x = float_value(center[0])
        y = float_value(center[1])
        if x is not None and y is not None:
            return [round(max(0.0, min(1.0, x)), 4), round(max(0.0, min(1.0, y)), 4)]
    return None


def face_bbox_ratio(frame: dict[str, Any]) -> list[float] | None:
    persons = frame.get("persons") or []
    person = persons[0] if persons and isinstance(persons[0], dict) else None
    face = person.get("face") if person and isinstance(person.get("face"), dict) else None
    if not face:
        return None
    return bbox_ratio(face.get("bbox"), float_value(frame.get("width")) or 0.0, float_value(frame.get("height")) or 0.0)


def dominant(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def load_json_files(path: Path, suffix: str) -> list[dict[str, Any]]:
    return [json.loads(item.read_text(encoding="utf-8")) for item in sorted(path.glob(f"*{suffix}"))]


def build_profile(analyses: list[dict[str, Any]], plans: list[dict[str, Any]]) -> dict[str, Any]:
    frames = [frame for analysis in analyses for frame in analysis.get("frames", [])]
    main_persons = [frame["persons"][0] for frame in frames if frame.get("persons")]
    visuals = [frame.get("visual", {}) for frame in frames if frame.get("visual")]
    face_directions = Counter(person.get("face_direction", "unknown") for person in main_persons)
    positions = Counter(person.get("position", "unknown") for person in main_persons)
    shot_sizes = Counter(person.get("shot_size", "unknown") for person in main_persons)
    desired_subject_x_values = [
        float(person.get("look_composition", {}).get("desired_subject_x_ratio"))
        for person in main_persons
        if isinstance(person.get("look_composition"), dict)
        and person.get("look_composition", {}).get("desired_subject_x_ratio") is not None
    ]
    desired_subject_y_values = [
        float(person.get("look_composition", {}).get("desired_subject_y_ratio"))
        for person in main_persons
        if isinstance(person.get("look_composition"), dict)
        and person.get("look_composition", {}).get("desired_subject_y_ratio") is not None
    ]
    composition_anchors = Counter(
        str(person.get("look_composition", {}).get("composition_anchor"))
        for person in main_persons
        if isinstance(person.get("look_composition"), dict)
        and person.get("look_composition", {}).get("composition_anchor")
    )
    segments = [segment for plan in plans for segment in plan.get("segments", [])]

    center_x = [float(person["center_ratio"][0]) for person in main_persons if person.get("center_ratio")]
    center_y = [float(person["center_ratio"][1]) for person in main_persons if person.get("center_ratio")]
    face_focus_values = [face_focus_ratio(frame) for frame in frames]
    face_bbox_values = [face_bbox_ratio(frame) for frame in frames]
    face_protect_bbox_values = [expanded_face_protect_bbox(value) for value in face_bbox_values]
    area = [float(person["area_ratio"]) for person in main_persons if person.get("area_ratio") is not None]
    brightness = [float(item["brightness"]) for item in visuals if item.get("brightness") is not None]
    contrast = [float(item["contrast"]) for item in visuals if item.get("contrast") is not None]
    saturation = [float(item["saturation"]) for item in visuals if item.get("saturation") is not None]
    warmth = [float(item["warmth"]) for item in visuals if item.get("warmth") is not None]

    target_center = [average(center_x), average(center_y)] if center_x and center_y else None
    visual_style = {
        "brightness": average(brightness),
        "contrast": average(contrast),
        "saturation": average(saturation),
        "warmth": average(warmth),
    }
    target = {
        "person_center_ratio": target_center,
        "face_focus_ratio": average_vector(face_focus_values),
        "face_bbox_ratio": average_vector(face_bbox_values),
        "face_protect_bbox_ratio": average_vector(face_protect_bbox_values),
        "person_area_ratio": average(area),
        "dominant_position": dominant(positions),
        "dominant_shot_size": dominant(shot_sizes),
        "dominant_face_direction": dominant(face_directions),
        "face_direction_counts": dict(face_directions),
        "desired_subject_x_ratio": average(desired_subject_x_values),
        "desired_subject_y_ratio": average(desired_subject_y_values),
        "dominant_composition_anchor": dominant(composition_anchors),
        "composition_anchor_counts": dict(composition_anchors),
        "visual_style": visual_style,
    }

    instructions = [
        "参考動画の人物配置を、出力動画のクロップ中心とズーム量の初期値として使う。",
        "person_area_ratio が大きい場合は寄り、低い場合は引きの画を維持する。",
        "dominant_position が left/right の場合は縦動画や正方形クロップの中心を同じ方向へ寄せる。",
        "dominant_face_direction が left の場合は左の視線余白を広く取り、人物を右寄せにする。",
        "dominant_face_direction が right の場合は右の視線余白を広く取り、人物を左寄せにする。",
        "dominant_face_direction が front の場合は人物を中央基準にする。",
        "desired_subject_x_ratio / desired_subject_y_ratio は黄金比・三分割系の構図アンカーとしてクロップ目標に使う。",
        "visual_style の brightness/contrast/saturation/warmth を、色補正と露出の目標値として使う。",
    ]

    return {
        "schema_version": "reference-edit-profile/v1",
        "source_videos": [analysis.get("video_path") for analysis in analyses],
        "duration": max((float(analysis.get("duration") or 0.0) for analysis in analyses), default=0.0),
        "fps_sample": analyses[0].get("fps_sample") if analyses else None,
        "sampled_frames": len(frames),
        "target": target,
        "reference_segments": segments,
        "editing_instructions": instructions,
    }


def main() -> None:
    args = parse_args()
    analyses = load_json_files(args.input_dir, "_person_bboxes.json")
    plans = load_json_files(args.plan_dir, "_person_edit_plan.json")
    if not analyses:
        raise SystemExit(f"No reference person bbox JSON files found under {args.input_dir}")
    profile = build_profile(analyses, plans)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "target": profile["target"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
