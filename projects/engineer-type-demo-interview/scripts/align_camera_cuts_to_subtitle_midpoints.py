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
REPORTS = PROJECT_ROOT / "output" / "reports"
STATE_PATH = PROJECT_ROOT / "project_state.json"
PLAN_PATH = REPORTS / "manual_camera_plan.json"
REPORT_PATH = REPORTS / "camera_subtitle_midpoint_plan.json"
NATURAL_CUT_REPORT = REPORTS / "natural_dialogue_cuts.json"
ONSCREEN_CLOSEUP_REPORT = REPORTS / "onscreen_closeup_camera_mask.json"
FORCED_MASTER_WINDOWS = [
    {
        "start": 19 * 60 + 17.0,
        "end": 19 * 60 + 42.0,
        "reason": "User requested wide shot through the 19:17-19:42 section; avoid the camera5 push-in.",
    }
]
ONSCREEN_CLOSEUP_DELAY_SECONDS = 1.4


def load_renderer() -> Any:
    os.environ.setdefault("VIDEO_EDIT_PROJECT", PROJECT_ID)
    sys.path.insert(0, str(WORKSPACE_ROOT))
    renderer_path = WORKSPACE_ROOT / "scripts" / "render_multicam.py"
    spec = importlib.util.spec_from_file_location("render_multicam_for_midpoint_plan", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load renderer from {renderer_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".before_subtitle_midpoints")
    if path.exists() and not backup.exists():
        backup.write_bytes(path.read_bytes())


def caption_text(item: dict[str, Any]) -> str:
    lines = item.get("lines")
    if isinstance(lines, list):
        return "".join(str(line) for line in lines)
    return str(item.get("text") or "")


def render_context(rm: Any) -> dict[str, Any]:
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
    subtitle_source_offset = rm.subtitle_source_offset_seconds(audio_role, sync_offsets)

    mode = rm.subtitle_mode()
    subtitle_items: list[dict[str, Any]] = []
    if mode != "none":
        manifest, _caption_config = rm.subtitle_manifest(mode)
        subtitle_items = rm.transform_overlay_items(
            rm.read_overlay_items(manifest, start, source_duration, subtitle_source_offset),
            replacements,
            start,
            source_duration,
            output_duration,
        )

    camera_indexes = [(name, index) for index, (name, _) in enumerate(cameras)]
    segments = rm.parse_manual_camera_plan(output_duration, camera_indexes)
    if not segments:
        segments = rm.build_segments(output_duration, camera_indexes, subtitle_items, start)

    return {
        "start": start,
        "sourceDuration": source_duration,
        "outputDuration": output_duration,
        "replacements": replacements,
        "syncOffsets": sync_offsets,
        "rawCameras": cameras,
        "cameras": camera_indexes,
        "segments": segments,
        "captions": subtitle_items,
    }


def caption_anchors(
    rm: Any,
    captions: list[dict[str, Any]],
    *,
    timeline_start: float,
    duration: float,
    min_caption_duration: float,
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for item in captions:
        local = rm.caption_local_range(item, timeline_start, duration)
        if local is None:
            continue
        start_t, end_t = local
        caption_duration = end_t - start_t
        text = caption_text(item).strip()
        if caption_duration < min_caption_duration or not text:
            continue
        anchors.append(
            {
                "mid": (start_t + end_t) / 2.0,
                "start": start_t,
                "end": end_t,
                "duration": caption_duration,
                "sourceIndex": item.get("source_index", item.get("index")),
                "text": text[:120],
            }
        )
    return anchors


def choose_anchor(
    planned: float,
    anchors: list[dict[str, Any]],
    *,
    lower: float,
    upper: float,
    search_window: float,
    preferred_caption_duration: float,
) -> dict[str, Any] | None:
    candidates = [
        anchor
        for anchor in anchors
        if lower <= float(anchor["mid"]) <= upper and abs(float(anchor["mid"]) - planned) <= search_window
    ]
    if not candidates:
        return None

    def score(anchor: dict[str, Any]) -> tuple[float, float, float]:
        midpoint = float(anchor["mid"])
        caption_duration = float(anchor["duration"])
        distance = abs(midpoint - planned)
        short_penalty = max(0.0, preferred_caption_duration - caption_duration) * 0.85
        long_caption_bonus = min(caption_duration, 4.5) * 0.16
        return distance + short_penalty - long_caption_bonus, distance, -caption_duration

    return min(candidates, key=score)


def align_segments(
    rm: Any,
    segments: list[tuple[str, int, float, float]],
    anchors: list[dict[str, Any]],
    *,
    duration: float,
    min_segment_seconds: float,
    search_window: float,
    preferred_caption_duration: float,
    fallback: tuple[str, int],
) -> tuple[list[tuple[str, int, float, float]], list[dict[str, Any]]]:
    if len(segments) <= 1:
        return segments, []

    original_boundaries = [float(segment[3]) for segment in segments[:-1]]
    adjusted_boundaries = [0.0]
    adjustments: list[dict[str, Any]] = []

    for index, planned in enumerate(original_boundaries):
        next_original = original_boundaries[index + 1] if index + 1 < len(original_boundaries) else duration
        lower = adjusted_boundaries[-1] + min_segment_seconds
        upper = next_original - min_segment_seconds
        if upper <= lower:
            chosen = max(adjusted_boundaries[-1] + 0.06, min(planned, duration - 0.06))
            anchor = None
        else:
            anchor = choose_anchor(
                planned,
                anchors,
                lower=lower,
                upper=upper,
                search_window=search_window,
                preferred_caption_duration=preferred_caption_duration,
            )
            chosen = float(anchor["mid"]) if anchor is not None else max(lower, min(planned, upper))

        adjusted_boundaries.append(chosen)
        left = segments[index]
        right = segments[index + 1]
        item: dict[str, Any] = {
            "boundary": index,
            "fromRole": left[0],
            "toRole": right[0],
            "planned": round(planned, 3),
            "chosen": round(chosen, 3),
            "shiftSeconds": round(chosen - planned, 3),
            "alignedToCaptionMidpoint": anchor is not None,
        }
        if anchor is not None:
            item.update(
                {
                    "captionStart": round(float(anchor["start"]), 3),
                    "captionEnd": round(float(anchor["end"]), 3),
                    "captionDuration": round(float(anchor["duration"]), 3),
                    "captionPosition": 0.5,
                    "captionSourceIndex": anchor.get("sourceIndex"),
                    "captionText": anchor.get("text", ""),
                }
            )
        else:
            item["reason"] = "no eligible caption midpoint near planned boundary"
        adjustments.append(item)

    adjusted_boundaries.append(duration)
    adjusted_segments = []
    for index, (role, input_index, _start_t, _end_t) in enumerate(segments):
        start_t = adjusted_boundaries[index]
        end_t = adjusted_boundaries[index + 1]
        if end_t - start_t <= 0.05:
            continue
        adjusted_segments.append((role, input_index, start_t, end_t))

    return rm.normalize_camera_segments(duration, adjusted_segments, fallback), adjustments


def coverage_output_windows(rm: Any, context: dict[str, Any]) -> dict[str, tuple[float, float]]:
    windows: dict[str, tuple[float, float]] = {}
    duration = float(context["outputDuration"])
    timeline_start = float(context["start"])
    replacements = context["replacements"]
    sync_offsets = context["syncOffsets"]
    for role, path in context["rawCameras"]:
        media_duration = rm.source_duration(role, path)
        if media_duration is None:
            continue
        offset = float(sync_offsets.get(role, 0.0))
        source_start = max(0.0, -timeline_start - offset)
        source_end = min(duration, max(0.0, media_duration - timeline_start - offset))
        output_start = rm.source_local_to_output_local(source_start, replacements) if replacements else source_start
        output_end = rm.source_local_to_output_local(source_end, replacements) if replacements else source_end
        if output_start is None or output_end is None:
            continue
        windows[role] = (max(0.0, output_start), min(duration, output_end))
    return windows


def choose_coverage_safe_anchor(
    anchors: list[dict[str, Any]],
    *,
    lower: float,
    upper: float,
    preferred_caption_duration: float,
) -> dict[str, Any] | None:
    candidates = [anchor for anchor in anchors if lower <= float(anchor["mid"]) <= upper]
    if not candidates:
        return None
    long_candidates = [anchor for anchor in candidates if float(anchor["duration"]) >= preferred_caption_duration]
    usable = long_candidates or candidates
    return max(usable, key=lambda anchor: (float(anchor["duration"]), float(anchor["mid"])))


def avoid_source_coverage_boundaries(
    rm: Any,
    segments: list[tuple[str, int, float, float]],
    anchors: list[dict[str, Any]],
    context: dict[str, Any],
    *,
    min_segment_seconds: float,
    preferred_caption_duration: float,
    fallback: tuple[str, int],
) -> tuple[list[tuple[str, int, float, float]], list[dict[str, Any]]]:
    windows = coverage_output_windows(rm, context)
    if not windows or len(segments) <= 1:
        return segments, []
    master_role = fallback[0]
    boundaries = [0.0] + [float(segment[3]) for segment in segments[:-1]] + [float(context["outputDuration"])]
    adjustments: list[dict[str, Any]] = []
    for index, (role, _input_index, start_t, end_t) in enumerate(segments[:-1]):
        if role == master_role:
            continue
        coverage = windows.get(role)
        if coverage is None:
            continue
        _coverage_start, coverage_end = coverage
        if end_t <= coverage_end - 0.05:
            continue
        lower = float(start_t) + min_segment_seconds
        upper = min(float(coverage_end) - 0.15, float(segments[index + 1][3]) - min_segment_seconds)
        if upper <= lower:
            continue
        anchor = choose_coverage_safe_anchor(
            anchors,
            lower=lower,
            upper=upper,
            preferred_caption_duration=preferred_caption_duration,
        )
        if anchor is None:
            continue
        chosen = float(anchor["mid"])
        old_boundary = boundaries[index + 1]
        boundaries[index + 1] = chosen
        adjustments.append(
            {
                "boundary": index,
                "role": role,
                "coverageEnd": round(float(coverage_end), 3),
                "oldBoundary": round(old_boundary, 3),
                "chosen": round(chosen, 3),
                "captionStart": round(float(anchor["start"]), 3),
                "captionEnd": round(float(anchor["end"]), 3),
                "captionDuration": round(float(anchor["duration"]), 3),
                "captionText": anchor.get("text", ""),
            }
        )

    adjusted_segments: list[tuple[str, int, float, float]] = []
    for index, (role, input_index, _start_t, _end_t) in enumerate(segments):
        start_t = boundaries[index]
        end_t = boundaries[index + 1]
        if end_t - start_t <= 0.05:
            continue
        adjusted_segments.append((role, input_index, start_t, end_t))
    return rm.normalize_camera_segments(float(context["outputDuration"]), adjusted_segments, fallback), adjustments


def force_master_windows(
    rm: Any,
    segments: list[tuple[str, int, float, float]],
    *,
    duration: float,
    fallback: tuple[str, int],
) -> tuple[list[tuple[str, int, float, float]], list[dict[str, Any]]]:
    if not segments:
        return segments, []

    master_role, master_index = fallback
    adjusted: list[tuple[str, int, float, float]] = []
    forced: list[dict[str, Any]] = []
    for role, input_index, start_t, end_t in segments:
        pieces = [(float(start_t), float(end_t), role, input_index)]
        for window in FORCED_MASTER_WINDOWS:
            win_start = max(0.0, float(window["start"]))
            win_end = min(float(duration), float(window["end"]))
            next_pieces: list[tuple[float, float, str, int]] = []
            for piece_start, piece_end, piece_role, piece_index in pieces:
                overlap_start = max(piece_start, win_start)
                overlap_end = min(piece_end, win_end)
                if overlap_end <= overlap_start + 0.05:
                    next_pieces.append((piece_start, piece_end, piece_role, piece_index))
                    continue
                if piece_start < overlap_start - 0.05:
                    next_pieces.append((piece_start, overlap_start, piece_role, piece_index))
                next_pieces.append((overlap_start, overlap_end, master_role, master_index))
                if piece_end > overlap_end + 0.05:
                    next_pieces.append((overlap_end, piece_end, piece_role, piece_index))
                if piece_role != master_role:
                    forced.append(
                        {
                            "start": round(overlap_start, 3),
                            "end": round(overlap_end, 3),
                            "fromRole": piece_role,
                            "toRole": master_role,
                            "reason": window["reason"],
                        }
                    )
            pieces = next_pieces
        adjusted.extend((piece_role, piece_index, piece_start, piece_end) for piece_start, piece_end, piece_role, piece_index in pieces)

    return rm.normalize_camera_segments(duration, adjusted, fallback), forced


def speaker_role_runs(
    rm: Any,
    captions: list[dict[str, Any]],
    *,
    timeline_start: float,
    duration: float,
    merge_gap_seconds: float = 1.2,
) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    for item in captions:
        role = str(item.get("speaker_role") or item.get("speakerRole") or "")
        if role not in {"interviewer", "onscreen"}:
            continue
        local = rm.caption_local_range(item, timeline_start, duration)
        if local is None:
            continue
        start_t, end_t = local
        if end_t <= start_t:
            continue
        ranges.append(
            {
                "start": float(start_t),
                "end": float(end_t),
                "role": role,
                "texts": [caption_text(item).strip()],
            }
        )
    ranges.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    merged: list[dict[str, Any]] = []
    for item in ranges:
        if not merged:
            merged.append(item)
            continue
        prev = merged[-1]
        if item["role"] == prev["role"] and float(item["start"]) <= float(prev["end"]) + merge_gap_seconds:
            prev["end"] = max(float(prev["end"]), float(item["end"]))
            prev["texts"].extend(item.get("texts", []))
            continue
        merged.append(item)
    return merged


def force_master_for_windows(
    rm: Any,
    segments: list[tuple[str, int, float, float]],
    windows: list[dict[str, Any]],
    *,
    duration: float,
    fallback: tuple[str, int],
    reason: str,
) -> tuple[list[tuple[str, int, float, float]], list[dict[str, Any]]]:
    if not segments or not windows:
        return segments, []

    master_role, master_index = fallback
    adjusted: list[tuple[str, int, float, float]] = []
    forced: list[dict[str, Any]] = []
    for role, input_index, start_t, end_t in segments:
        pieces = [(float(start_t), float(end_t), role, input_index)]
        for window in windows:
            win_start = max(0.0, float(window["start"]))
            win_end = min(float(duration), float(window["end"]))
            if win_end <= win_start + 0.05:
                continue
            next_pieces: list[tuple[float, float, str, int]] = []
            for piece_start, piece_end, piece_role, piece_index in pieces:
                overlap_start = max(piece_start, win_start)
                overlap_end = min(piece_end, win_end)
                if overlap_end <= overlap_start + 0.05:
                    next_pieces.append((piece_start, piece_end, piece_role, piece_index))
                    continue
                if piece_start < overlap_start - 0.05:
                    next_pieces.append((piece_start, overlap_start, piece_role, piece_index))
                next_pieces.append((overlap_start, overlap_end, master_role, master_index))
                if piece_end > overlap_end + 0.05:
                    next_pieces.append((overlap_end, piece_end, piece_role, piece_index))
                if piece_role != master_role:
                    forced.append(
                        {
                            "start": round(overlap_start, 3),
                            "end": round(overlap_end, 3),
                            "fromRole": piece_role,
                            "toRole": master_role,
                            "reason": reason,
                            "text": str(window.get("text") or "")[:120],
                        }
                    )
            pieces = next_pieces
        adjusted.extend((piece_role, piece_index, piece_start, piece_end) for piece_start, piece_end, piece_role, piece_index in pieces)

    return rm.normalize_camera_segments(duration, adjusted, fallback), forced


def interviewer_master_windows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "start": float(run["start"]),
            "end": float(run["end"]),
            "text": " / ".join(str(text) for text in run.get("texts", [])[:3]),
        }
        for run in runs
        if run.get("role") == "interviewer"
    ]


def onscreen_delay_master_windows(runs: list[dict[str, Any]], delay_seconds: float) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        if run.get("role") != "onscreen":
            continue
        previous_role = runs[index - 1].get("role") if index > 0 else ""
        if previous_role != "interviewer":
            continue
        start_t = float(run["start"])
        end_t = min(float(run["end"]), start_t + delay_seconds)
        if end_t <= start_t + 0.05:
            continue
        windows.append(
            {
                "start": start_t,
                "end": end_t,
                "text": " / ".join(str(text) for text in run.get("texts", [])[:2]),
            }
        )
    return windows


def merge_adjacent_same_camera(
    segments: list[tuple[str, int, float, float]],
) -> list[tuple[str, int, float, float]]:
    merged: list[tuple[str, int, float, float]] = []
    for role, input_index, start_t, end_t in segments:
        if end_t <= start_t + 0.05:
            continue
        if merged and merged[-1][0] == role and merged[-1][1] == input_index:
            prev_role, prev_index, prev_start, _prev_end = merged[-1]
            merged[-1] = (prev_role, prev_index, prev_start, float(end_t))
        else:
            merged.append((role, input_index, float(start_t), float(end_t)))
    return merged


def enforce_minimum_camera_hold(
    rm: Any,
    segments: list[tuple[str, int, float, float]],
    *,
    duration: float,
    min_hold_seconds: float,
    fallback: tuple[str, int],
) -> tuple[list[tuple[str, int, float, float]], list[dict[str, Any]]]:
    master_role = fallback[0]
    adjusted = merge_adjacent_same_camera(segments)
    changes: list[dict[str, Any]] = []
    while len(adjusted) > 1:
        short_indexes = [
            index
            for index, (_role, _input_index, start_t, end_t) in enumerate(adjusted)
            if end_t - start_t < min_hold_seconds - 0.001
        ]
        if not short_indexes:
            break
        index = min(short_indexes, key=lambda item: adjusted[item][3] - adjusted[item][2])
        role, input_index, start_t, end_t = adjusted[index]

        if index == 0:
            target = 1
        elif index == len(adjusted) - 1:
            target = index - 1
        else:
            prev = adjusted[index - 1]
            next_item = adjusted[index + 1]
            prev_len = prev[3] - prev[2]
            next_len = next_item[3] - next_item[2]
            if role != master_role and prev[0] == master_role:
                target = index - 1
            elif role != master_role and next_item[0] == master_role:
                target = index + 1
            elif role == master_role and prev[0] == master_role:
                target = index - 1
            elif role == master_role and next_item[0] == master_role:
                target = index + 1
            else:
                target = index - 1 if prev_len >= next_len else index + 1

        target_role, target_input_index, target_start, target_end = adjusted[target]
        new_start = min(start_t, target_start)
        new_end = max(end_t, target_end)
        changes.append(
            {
                "absorbedRole": role,
                "absorbedStart": round(start_t, 3),
                "absorbedEnd": round(end_t, 3),
                "absorbedDuration": round(end_t - start_t, 3),
                "targetRole": target_role,
                "targetStart": round(target_start, 3),
                "targetEnd": round(target_end, 3),
                "reason": f"camera hold shorter than {min_hold_seconds:.1f}s",
            }
        )
        if target < index:
            adjusted[target] = (target_role, target_input_index, new_start, new_end)
            del adjusted[index]
        else:
            adjusted[target] = (target_role, target_input_index, new_start, new_end)
            del adjusted[index]
        adjusted.sort(key=lambda item: item[2])
        adjusted = merge_adjacent_same_camera(adjusted)

    return rm.normalize_camera_segments(duration, adjusted, fallback), changes


def write_plan(segments: list[tuple[str, int, float, float]], duration: float, report_path: Path) -> None:
    payload = {
        "mode": "manual-plan",
        "source": str(report_path),
        "duration": round(duration, 3),
        "segments": [
            {"role": role, "start": round(float(start_t), 3), "end": round(float(end_t), 3)}
            for role, _input_index, start_t, end_t in segments
        ],
    }
    PLAN_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_project_state() -> None:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    render = state.setdefault("render", {})
    render["cameraMinSegmentSeconds"] = 10.0
    render["cameraCutsAtSubtitleBoundariesOnly"] = False
    render["naturalDialogueCuts"] = False
    render["closeupsOnlyWhenOnscreenSpeaker"] = False
    render["cameraCutAlignment"] = "subtitle-midpoints"
    render["cameraMidSubtitlePlanPath"] = str(REPORT_PATH)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def write_disabled_conflicting_reports() -> None:
    NATURAL_CUT_REPORT.write_text(
        json.dumps(
            {
                "enabled": False,
                "reason": "camera cuts are controlled by subtitle-midpoint manual plan",
                "items": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    ONSCREEN_CLOSEUP_REPORT.write_text(
        json.dumps(
            {
                "enabled": False,
                "reason": "disabled to avoid creating camera cuts at subtitle/speaker boundaries",
                "changed": False,
                "onscreenSpeechRanges": [],
                "replacedCloseupGaps": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-caption-duration", type=float, default=1.35)
    parser.add_argument("--preferred-caption-duration", type=float, default=2.15)
    parser.add_argument("--min-segment", type=float, default=10.0)
    parser.add_argument("--search-window", type=float, default=8.0)
    parser.add_argument("--onscreen-closeup-delay", type=float, default=ONSCREEN_CLOSEUP_DELAY_SECONDS)
    args = parser.parse_args()

    rm = load_renderer()
    context = render_context(rm)
    duration = float(context["outputDuration"])
    camera_indexes = context["cameras"]
    segments = context["segments"]
    anchors = caption_anchors(
        rm,
        context["captions"],
        timeline_start=float(context["start"]),
        duration=duration,
        min_caption_duration=args.min_caption_duration,
    )
    role_runs = speaker_role_runs(
        rm,
        context["captions"],
        timeline_start=float(context["start"]),
        duration=duration,
    )

    adjusted_segments, adjustments = align_segments(
        rm,
        segments,
        anchors,
        duration=duration,
        min_segment_seconds=args.min_segment,
        search_window=args.search_window,
        preferred_caption_duration=args.preferred_caption_duration,
        fallback=camera_indexes[0],
    )
    adjusted_segments, coverage_adjustments = avoid_source_coverage_boundaries(
        rm,
        adjusted_segments,
        anchors,
        context,
        min_segment_seconds=args.min_segment,
        preferred_caption_duration=args.preferred_caption_duration,
        fallback=camera_indexes[0],
    )
    adjusted_segments, forced_master_adjustments = force_master_windows(
        rm,
        adjusted_segments,
        duration=duration,
        fallback=camera_indexes[0],
    )
    adjusted_segments, interviewer_master_adjustments = force_master_for_windows(
        rm,
        adjusted_segments,
        interviewer_master_windows(role_runs),
        duration=duration,
        fallback=camera_indexes[0],
        reason="black/interviewer subtitle should use the wide master shot when possible",
    )
    adjusted_segments, onscreen_delay_adjustments = force_master_for_windows(
        rm,
        adjusted_segments,
        onscreen_delay_master_windows(role_runs, args.onscreen_closeup_delay),
        duration=duration,
        fallback=camera_indexes[0],
        reason="delay closeup after interviewer question before moving to interviewee closeup",
    )
    adjusted_segments, min_hold_adjustments = enforce_minimum_camera_hold(
        rm,
        adjusted_segments,
        duration=duration,
        min_hold_seconds=args.min_segment,
        fallback=camera_indexes[0],
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    backup_once(PLAN_PATH)
    report = {
        "strategy": "camera cuts aligned to subtitle midpoints, not subtitle boundaries",
        "inputSegments": len(segments),
        "outputSegments": len(adjusted_segments),
        "outputDuration": round(duration, 3),
        "eligibleCaptionMidpoints": len(anchors),
        "thresholds": {
            "minCaptionDuration": args.min_caption_duration,
            "preferredCaptionDuration": args.preferred_caption_duration,
            "minSegmentSeconds": args.min_segment,
            "searchWindowSeconds": args.search_window,
            "onscreenCloseupDelaySeconds": args.onscreen_closeup_delay,
        },
        "speakerRunCount": len(role_runs),
        "alignedBoundaryCount": sum(1 for item in adjustments if item.get("alignedToCaptionMidpoint")),
        "keptBoundaryCount": sum(1 for item in adjustments if not item.get("alignedToCaptionMidpoint")),
        "coverageBoundaryAdjustmentCount": len(coverage_adjustments),
        "forcedMasterAdjustmentCount": len(forced_master_adjustments),
        "interviewerMasterAdjustmentCount": len(interviewer_master_adjustments),
        "onscreenDelayAdjustmentCount": len(onscreen_delay_adjustments),
        "minHoldAdjustmentCount": len(min_hold_adjustments),
        "adjustments": adjustments,
        "coverageBoundaryAdjustments": coverage_adjustments,
        "forcedMasterAdjustments": forced_master_adjustments,
        "interviewerMasterAdjustments": interviewer_master_adjustments,
        "onscreenDelayAdjustments": onscreen_delay_adjustments,
        "minHoldAdjustments": min_hold_adjustments,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_plan(adjusted_segments, duration, REPORT_PATH)
    update_project_state()
    write_disabled_conflicting_reports()

    print(
        json.dumps(
            {
                "plan": str(PLAN_PATH),
                "report": str(REPORT_PATH),
                "inputSegments": len(segments),
                "outputSegments": len(adjusted_segments),
                "eligibleCaptionMidpoints": len(anchors),
                "alignedBoundaryCount": report["alignedBoundaryCount"],
                "keptBoundaryCount": report["keptBoundaryCount"],
                "coverageBoundaryAdjustmentCount": report["coverageBoundaryAdjustmentCount"],
                "forcedMasterAdjustmentCount": report["forcedMasterAdjustmentCount"],
                "interviewerMasterAdjustmentCount": report["interviewerMasterAdjustmentCount"],
                "onscreenDelayAdjustmentCount": report["onscreenDelayAdjustmentCount"],
                "minHoldAdjustmentCount": report["minHoldAdjustmentCount"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
