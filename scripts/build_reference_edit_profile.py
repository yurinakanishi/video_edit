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
