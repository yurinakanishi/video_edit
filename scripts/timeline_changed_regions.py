from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from video_edit_core.paths import OUTPUT_REPORTS, SCRIPTS
from video_edit_core.timeline.validation import configured_timeline_path, load_timeline, validate_timeline
from video_edit_core.app_config import load_app_config, nested


APP_CONFIG = load_app_config()
REPORT_PATH = OUTPUT_REPORTS / "timeline_changed_regions.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def ms(value: float) -> int:
    return int(round(value * 1000))


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def first_target(timeline: dict[str, Any]) -> dict[str, Any]:
    render = timeline.get("render") if isinstance(timeline.get("render"), dict) else {}
    targets = render.get("targets") if isinstance(render.get("targets"), list) else []
    final = next((target for target in targets if isinstance(target, dict) and target.get("id") == "final"), None)
    if isinstance(final, dict):
        return final
    first = next((target for target in targets if isinstance(target, dict)), None)
    if isinstance(first, dict):
        return first
    return {"path": "changed_region.mp4"}


def clip_range(clip: dict[str, Any]) -> tuple[float, float]:
    return as_float(clip.get("timelineStart")), as_float(clip.get("timelineEnd"))


def clamp_range(start: float, end: float, duration: float) -> tuple[float, float] | None:
    clamped_start = max(0.0, min(duration, start))
    clamped_end = max(0.0, min(duration, end))
    if clamped_end <= clamped_start:
        return None
    return clamped_start, clamped_end


def add_region(
    regions: list[dict[str, Any]],
    start: float,
    end: float,
    duration: float,
    reason: str,
    item_id: str = "",
) -> None:
    clamped = clamp_range(start, end, duration)
    if clamped is None:
        return
    regions.append(
        {
            "start": clamped[0],
            "end": clamped[1],
            "reasons": [{"reason": reason, "id": item_id}],
        }
    )


def merge_regions(regions: list[dict[str, Any]], duration: float, padding: float) -> list[dict[str, Any]]:
    padded: list[dict[str, Any]] = []
    for region in regions:
        start = as_float(region.get("start")) - padding
        end = as_float(region.get("end")) + padding
        clamped = clamp_range(start, end, duration)
        if clamped is None:
            continue
        padded.append({"start": clamped[0], "end": clamped[1], "reasons": region.get("reasons", [])})
    padded.sort(key=lambda item: (item["start"], item["end"]))

    merged: list[dict[str, Any]] = []
    for region in padded:
        if not merged or region["start"] > merged[-1]["end"]:
            merged.append(region)
            continue
        merged[-1]["end"] = max(merged[-1]["end"], region["end"])
        merged[-1]["reasons"].extend(region.get("reasons", []))

    for index, region in enumerate(merged, start=1):
        region["id"] = f"changed_region_{index:03d}"
        region["duration"] = region["end"] - region["start"]
    return merged


def source_ids_changed(current: dict[str, Any], previous: dict[str, Any]) -> set[str]:
    current_sources = {str(source.get("id")): source for source in current.get("sources", []) if isinstance(source, dict)}
    previous_sources = {str(source.get("id")): source for source in previous.get("sources", []) if isinstance(source, dict)}
    changed: set[str] = set()
    for source_id, source in current_sources.items():
        if source_id not in previous_sources or fingerprint(source) != fingerprint(previous_sources[source_id]):
            changed.add(source_id)
    return changed


def render_signature(timeline: dict[str, Any]) -> dict[str, Any]:
    render = timeline.get("render") if isinstance(timeline.get("render"), dict) else {}
    targets = render.get("targets") if isinstance(render.get("targets"), list) else []
    normalized_targets = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        normalized_targets.append(
            {
                key: target.get(key)
                for key in ("id", "format", "width", "height", "fps", "profile", "videoCodec", "audioCodec")
            }
        )
    return {"timebase": timeline.get("timebase"), "targets": normalized_targets}


def transition_ranges(timeline: dict[str, Any], duration: float) -> list[tuple[float, float, str]]:
    ranges: list[tuple[float, float, str]] = []
    for transition in timeline.get("transitions", []):
        if not isinstance(transition, dict):
            continue
        at = as_float(transition.get("at"))
        half = max(0.0, as_float(transition.get("duration"), 0.0)) / 2.0
        start = max(0.0, at - half)
        end = min(duration, at + half)
        if end <= start:
            end = min(duration, at + 0.001)
        ranges.append((start, end, str(transition.get("id") or "")))
    return ranges


def changed_regions(current: dict[str, Any], previous: dict[str, Any] | None, padding: float) -> list[dict[str, Any]]:
    duration = as_float(current.get("duration"), 0.0)
    if previous is None:
        return merge_regions(
            [{"start": 0.0, "end": duration, "reasons": [{"reason": "missing_previous_timeline", "id": ""}]}],
            duration,
            0.0,
        )

    regions: list[dict[str, Any]] = []
    previous_duration = as_float(previous.get("duration"), duration)
    if fingerprint(render_signature(current)) != fingerprint(render_signature(previous)):
        add_region(regions, 0.0, duration, duration, "render_settings_changed")
    elif abs(previous_duration - duration) > 0.001:
        add_region(regions, min(previous_duration, duration), max(previous_duration, duration), duration, "duration_changed")

    changed_sources = source_ids_changed(current, previous)
    current_clips = {str(clip.get("id")): clip for clip in current.get("clips", []) if isinstance(clip, dict)}
    previous_clips = {str(clip.get("id")): clip for clip in previous.get("clips", []) if isinstance(clip, dict)}

    for clip_id, clip in current_clips.items():
        start, end = clip_range(clip)
        previous_clip = previous_clips.get(clip_id)
        if previous_clip is None:
            add_region(regions, start, end, duration, "clip_added", clip_id)
            continue
        previous_start, previous_end = clip_range(previous_clip)
        if fingerprint(clip) != fingerprint(previous_clip):
            add_region(regions, min(start, previous_start), max(end, previous_end), duration, "clip_changed", clip_id)
            continue
        source_id = str(clip.get("sourceId") or "")
        if source_id and source_id in changed_sources:
            add_region(regions, start, end, duration, "clip_source_changed", clip_id)

    for clip_id, clip in previous_clips.items():
        if clip_id in current_clips:
            continue
        start, end = clip_range(clip)
        add_region(regions, start, end, duration, "clip_removed", clip_id)

    if fingerprint(current.get("transitions", [])) != fingerprint(previous.get("transitions", [])):
        for start, end, transition_id in transition_ranges(current, duration):
            add_region(regions, start, end, duration, "transition_changed", transition_id)
        for start, end, transition_id in transition_ranges(previous, duration):
            add_region(regions, start, end, duration, "transition_changed_previous", transition_id)

    return merge_regions(regions, duration, padding)


def default_previous_path(timeline_path: Path) -> Path:
    configured = str(nested(APP_CONFIG, "render", "previousTimelinePath", default="") or "").strip()
    return Path(configured) if configured else timeline_path.with_name("previous.timeline.json")


def output_path_for_region(timeline: dict[str, Any], region: dict[str, Any], proxy: bool) -> Path:
    target = first_target(timeline)
    base = Path(str(target.get("path") or "changed_region.mp4"))
    proxy_suffix = ".proxy" if proxy else ""
    suffix = f".{region['id']}_{ms(region['start']):08d}_{ms(region['end']):08d}{proxy_suffix}"
    return base.with_name(f"{base.stem}{suffix}{base.suffix}")


def command_plan_for_regions(
    timeline: dict[str, Any],
    regions: list[dict[str, Any]],
    *,
    proxy: bool,
    with_remotion_overlays: bool,
    with_blender_overlays: bool,
    execute: bool,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for region in regions:
        commands: list[list[str]] = []
        start = f"{region['start']:.6f}"
        end = f"{region['end']:.6f}"
        if with_remotion_overlays:
            remotion = [
                sys.executable,
                str(SCRIPTS / "timeline_graphics_adapter.py"),
                "--adapter",
                "remotion",
                "--range-start",
                start,
                "--range-end",
                end,
            ]
            if execute:
                remotion.append("--execute")
            commands.append(remotion)
        if with_blender_overlays:
            blender = [
                sys.executable,
                str(SCRIPTS / "timeline_graphics_adapter.py"),
                "--adapter",
                "blender",
                "--range-start",
                start,
                "--range-end",
                end,
            ]
            if execute:
                blender.append("--execute")
            commands.append(blender)
        ffmpeg = [
            sys.executable,
            str(SCRIPTS / "ffmpeg_timeline_adapter.py"),
            "--range-start",
            start,
            "--range-end",
            end,
            "--output",
            str(output_path_for_region(timeline, region, proxy)),
        ]
        if proxy:
            ffmpeg.append("--proxy")
        if with_remotion_overlays:
            ffmpeg.append("--with-remotion-overlays")
        if with_blender_overlays:
            ffmpeg.append("--with-blender-overlays")
        if execute:
            ffmpeg.append("--execute")
        commands.append(ffmpeg)
        plan.append({"regionId": region["id"], "commands": commands})
    return plan


def execute_plan(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total = sum(len(item["commands"]) for item in plan)
    stage = 0
    for item in plan:
        for command in item["commands"]:
            stage += 1
            print(json.dumps({"stage": stage, "stageCount": total, "regionId": item["regionId"], "command": command}, ensure_ascii=False), flush=True)
            completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1])
            result = {"regionId": item["regionId"], "command": command, "returnCode": int(completed.returncode)}
            results.append(result)
            if completed.returncode:
                return results
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect changed timeline regions and optionally generate/render per-region commands.")
    parser.add_argument("--timeline", type=Path, default=None, help="Current timeline JSON. Defaults to render.timelinePath.")
    parser.add_argument("--previous", type=Path, default=None, help="Previous/baseline timeline JSON. Defaults to previous.timeline.json next to the current timeline.")
    parser.add_argument("--output", type=Path, default=REPORT_PATH, help="Changed-region report JSON path.")
    parser.add_argument("--padding", type=float, default=2.0, help="Seconds of context to add around changed regions.")
    parser.add_argument("--render", action="store_true", help="Include FFmpeg command plans for each changed region.")
    parser.add_argument("--execute", action="store_true", help="Execute generated per-region commands.")
    parser.add_argument("--proxy", action="store_true", help="Render low-resolution proxy outputs for changed regions.")
    parser.add_argument("--with-remotion-overlays", action="store_true", help="Render Remotion overlay frames for each region before FFmpeg composition.")
    parser.add_argument("--with-blender-overlays", action="store_true", help="Render Blender overlay frames for each region before FFmpeg composition.")
    parser.add_argument("--update-baseline", action="store_true", help="Copy the current timeline to the previous timeline path after a successful run.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timeline_path = args.timeline or configured_timeline_path(APP_CONFIG)
    timeline = load_timeline(timeline_path)
    errors, warnings = validate_timeline(timeline)
    if errors:
        raise SystemExit("Timeline validation failed before changed-region detection: " + "; ".join(errors))

    previous_path = args.previous or default_previous_path(timeline_path)
    previous = load_timeline(previous_path) if previous_path.exists() else None
    regions = changed_regions(timeline, previous, max(0.0, args.padding))
    command_plan = command_plan_for_regions(
        timeline,
        regions,
        proxy=args.proxy,
        with_remotion_overlays=args.with_remotion_overlays,
        with_blender_overlays=args.with_blender_overlays,
        execute=args.execute,
    ) if args.render or args.execute else []
    report = {
        "createdAt": now_iso(),
        "timelinePath": str(timeline_path),
        "previousTimelinePath": str(previous_path),
        "previousTimelineExists": previous_path.exists(),
        "valid": True,
        "validationWarnings": warnings,
        "padding": max(0.0, args.padding),
        "regionCount": len(regions),
        "regions": regions,
        "commandPlan": command_plan,
        "executed": False,
        "executionResults": [],
    }

    if args.execute and command_plan:
        results = execute_plan(command_plan)
        report["executed"] = True
        report["executionResults"] = results
        if any(result["returnCode"] for result in results):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"report": str(args.output), "regionCount": len(regions), "executed": True, "failed": True}, ensure_ascii=False, indent=2))
            raise SystemExit(next(result["returnCode"] for result in results if result["returnCode"]))

    if args.update_baseline and (not args.execute or not any(result["returnCode"] for result in report["executionResults"])):
        previous_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(timeline_path, previous_path)
        report["baselineUpdated"] = True

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(args.output), "regionCount": len(regions), "executed": report["executed"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
