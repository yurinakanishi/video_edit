from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ID = PROJECT_ROOT.name
REPORT_PATH = PROJECT_ROOT / "output" / "reports" / "cut_boundary_camera_audit.json"


def load_renderer() -> Any:
    os.environ.setdefault("VIDEO_EDIT_PROJECT", PROJECT_ID)
    sys.path.insert(0, str(WORKSPACE_ROOT))
    renderer_path = WORKSPACE_ROOT / "scripts" / "render_multicam.py"
    spec = importlib.util.spec_from_file_location("render_multicam_for_audit", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load renderer from {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:05.2f}"


def rendered_camera_plan(rm: Any) -> dict[str, Any]:
    cameras = rm.manifest_cameras()
    if not cameras:
        raise RuntimeError("No project cameras found.")

    audio_sources = rm.manifest_audio_sources()
    external_audio = audio_sources[0][1] if audio_sources else rm.path_value("assets", "externalAudio")
    external_audio_role = audio_sources[0][0] if audio_sources else "external"

    start = float(rm.nested(rm.APP_CONFIG, "render", "previewStart", default=0.0) or 0.0)
    source_duration = float(rm.nested(rm.APP_CONFIG, "render", "previewDuration", default=60.0) or 60.0)
    if rm.render_range_mode() == "full":
        start = 0.0
        source_duration = rm.full_range_duration(cameras, source_duration)

    replacements, output_duration = rm.build_omission_replacements(start, source_duration)

    sync_sources = cameras + audio_sources
    if external_audio and not audio_sources:
        sync_sources.append(("external", external_audio))
    sync_offsets = rm.load_sync_offsets(sync_sources)

    audio_source = rm.nested(rm.APP_CONFIG, "render", "audioSource", default="external-if-selected")
    use_external_audio = audio_source == "external-if-selected" and external_audio
    audio_input_index = 0
    if audio_source == "rightCloseVideo":
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "camera2"), 0)
    elif audio_source == "leftCloseVideo":
        audio_input_index = next((i for i, (name, _) in enumerate(cameras) if name == "camera3"), 0)
    elif use_external_audio:
        audio_input_index = -1

    audio_role = cameras[audio_input_index][0] if 0 <= audio_input_index < len(cameras) else external_audio_role
    natural_cut_audio_path = external_audio if use_external_audio else cameras[audio_input_index][1]
    subtitle_source_offset = rm.subtitle_source_offset_seconds(audio_role, sync_offsets)

    subtitle_items: list[dict[str, Any]] = []
    mode = rm.subtitle_mode()
    if mode != "none":
        manifest, _caption_config = rm.subtitle_manifest(mode)
        subtitle_items = rm.transform_overlay_items(
            rm.read_overlay_items(manifest, start, source_duration, subtitle_source_offset),
            replacements,
            start,
            source_duration,
            output_duration,
        )
    planning_subtitle_items = subtitle_items or rm.subtitle_planning_items()

    camera_indexes = [(name, index) for index, (name, _) in enumerate(cameras)]
    segments = rm.build_segments(output_duration, camera_indexes, planning_subtitle_items, start)
    segments, natural_report = rm.adjust_segments_to_dialogue_gaps(
        segments,
        duration=output_duration,
        audio_path=natural_cut_audio_path,
        audio_role=audio_role,
        timeline_start=start,
        sync_offsets=sync_offsets,
        replacements=replacements,
    )
    segments, onscreen_report = rm.restrict_closeups_to_onscreen_speech(
        segments,
        duration=output_duration,
        cameras=camera_indexes,
        captions=planning_subtitle_items,
        timeline_start=start,
    )
    segments, source_coverage_report = rm.constrain_segments_to_source_coverage(
        segments,
        [(role, index, path) for index, (role, path) in enumerate(cameras)],
        duration=output_duration,
        timeline_start=start,
        sync_offsets=sync_offsets,
        replacements=replacements,
    )
    external_sync_report = None
    if use_external_audio:
        segments, external_sync_report = rm.guard_segments_by_external_audio_sync(
            segments,
            [(role, index, path) for index, (role, path) in enumerate(cameras)],
            duration=output_duration,
            timeline_start=start,
            sync_offsets=sync_offsets,
            external_audio_path=external_audio,
            audio_role=audio_role,
            replacements=replacements,
        )
    segments, subtitle_snap_report = rm.snap_camera_segments_to_subtitle_boundaries(
        segments,
        duration=output_duration,
        captions=planning_subtitle_items,
        timeline_start=start,
        fallback=camera_indexes[0],
    )
    segments, min_segment_report = rm.enforce_minimum_camera_segment_duration(
        segments,
        duration=output_duration,
        fallback=camera_indexes[0],
    )

    still_inserts = rm.plan_still_inserts(rm.parse_still_images(), subtitle_items, start, output_duration)
    video_segments = rm.video_segments_with_stills(output_duration, segments, still_inserts, replacements)
    camera_segments = [
        item for item in video_segments
        if item.get("type") == "camera" and float(item["end"]) - float(item["start"]) > 0.02
    ]

    return {
        "renderStart": start,
        "sourceDuration": source_duration,
        "outputDuration": output_duration,
        "replacements": replacements,
        "cameraSegments": camera_segments,
        "planningCameraSegments": [
            {"role": role, "inputIndex": input_index, "start": start_t, "end": end_t}
            for role, input_index, start_t, end_t in segments
        ],
        "reports": {
            "naturalDialogue": natural_report,
            "onscreenCloseup": onscreen_report,
            "sourceCoverage": source_coverage_report,
            "externalAudioSync": external_sync_report,
            "subtitleSnap": subtitle_snap_report,
            "minimumCameraSegment": min_segment_report,
        },
    }


def segment_role(segment: dict[str, Any]) -> str:
    return str(segment.get("role") or segment.get("type") or "")


def transition_times(camera_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transitions = []
    for left, right in zip(camera_segments, camera_segments[1:]):
        if segment_role(left) == segment_role(right) and int(left.get("input_index", -1)) == int(right.get("input_index", -2)):
            continue
        t = float(left["end"])
        transitions.append(
            {
                "time": t,
                "timeText": fmt_time(t),
                "fromRole": segment_role(left),
                "toRole": segment_role(right),
                "leftDuration": round(float(left["end"]) - float(left["start"]), 3),
                "rightDuration": round(float(right["end"]) - float(right["start"]), 3),
            }
        )
    return transitions


def audit(plan: dict[str, Any], *, near_window: float, align_tolerance: float, short_segment: float) -> dict[str, Any]:
    camera_segments = plan["cameraSegments"]
    transitions = transition_times(camera_segments)
    replacements = [item for item in plan["replacements"] if item.get("kind") == "cut"]
    cut_boundaries = [
        {
            "sourceStart": float(item["source_start"]) + float(plan["renderStart"]),
            "sourceEnd": float(item["source_end"]) + float(plan["renderStart"]),
            "outputTime": float(item["output_start"]),
            "outputTimeText": fmt_time(float(item["output_start"])),
        }
        for item in replacements
    ]

    short_segments = []
    for segment in camera_segments:
        start_t = float(segment["start"])
        end_t = float(segment["end"])
        duration = end_t - start_t
        if duration >= short_segment:
            continue
        nearest_cut = min(cut_boundaries, key=lambda cut: min(abs(cut["outputTime"] - start_t), abs(cut["outputTime"] - end_t)), default=None)
        if nearest_cut is None:
            continue
        distance = min(abs(nearest_cut["outputTime"] - start_t), abs(nearest_cut["outputTime"] - end_t))
        if distance > near_window:
            continue
        short_segments.append(
            {
                "role": segment_role(segment),
                "start": round(start_t, 3),
                "end": round(end_t, 3),
                "startText": fmt_time(start_t),
                "endText": fmt_time(end_t),
                "duration": round(duration, 3),
                "nearestCutOutput": round(nearest_cut["outputTime"], 3),
                "nearestCutOutputText": nearest_cut["outputTimeText"],
                "distanceToCut": round(distance, 3),
            }
        )

    nearby_transitions = []
    for cut in cut_boundaries:
        near = []
        for transition in transitions:
            delta = float(transition["time"]) - float(cut["outputTime"])
            if abs(delta) <= near_window and abs(delta) > align_tolerance:
                near.append({**transition, "deltaFromCut": round(delta, 3)})
        if near:
            nearby_transitions.append({**cut, "nearbyTransitions": near})

    clustered_transitions = []
    for left, right in zip(transitions, transitions[1:]):
        distance = float(right["time"]) - float(left["time"])
        if distance <= short_segment:
            nearest_cut = min(
                cut_boundaries,
                key=lambda cut: min(abs(cut["outputTime"] - float(left["time"])), abs(cut["outputTime"] - float(right["time"]))),
                default=None,
            )
            if nearest_cut is None:
                continue
            if min(abs(nearest_cut["outputTime"] - float(left["time"])), abs(nearest_cut["outputTime"] - float(right["time"]))) > near_window:
                continue
            clustered_transitions.append(
                {
                    "first": left,
                    "second": right,
                    "distance": round(distance, 3),
                    "nearestCutOutput": round(nearest_cut["outputTime"], 3),
                    "nearestCutOutputText": nearest_cut["outputTimeText"],
                }
            )

    return {
        "thresholds": {
            "nearWindowSeconds": near_window,
            "alignToleranceSeconds": align_tolerance,
            "shortSegmentSeconds": short_segment,
        },
        "renderStart": plan["renderStart"],
        "sourceDuration": plan["sourceDuration"],
        "outputDuration": plan["outputDuration"],
        "cutCount": len(cut_boundaries),
        "cameraSegmentCount": len(camera_segments),
        "transitionCount": len(transitions),
        "cutBoundaries": cut_boundaries,
        "shortCameraSegmentsNearCuts": short_segments,
        "cameraTransitionsNearCutsButNotAligned": nearby_transitions,
        "clusteredCameraTransitionsNearCuts": clustered_transitions,
        "rendererReports": plan["reports"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--near-window", type=float, default=1.0)
    parser.add_argument("--align-tolerance", type=float, default=0.06)
    parser.add_argument("--short-segment", type=float, default=1.0)
    args = parser.parse_args()

    rm = load_renderer()
    plan = rendered_camera_plan(rm)
    report = audit(
        plan,
        near_window=args.near_window,
        align_tolerance=args.align_tolerance,
        short_segment=args.short_segment,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "report": str(REPORT_PATH),
        "cutCount": report["cutCount"],
        "cameraSegmentCount": report["cameraSegmentCount"],
        "transitionCount": report["transitionCount"],
        "shortCameraSegmentsNearCuts": len(report["shortCameraSegmentsNearCuts"]),
        "cameraTransitionsNearCutsButNotAligned": len(report["cameraTransitionsNearCutsButNotAligned"]),
        "clusteredCameraTransitionsNearCuts": len(report["clusteredCameraTransitionsNearCuts"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
