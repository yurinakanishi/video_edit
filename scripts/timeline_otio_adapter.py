from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_paths import OUTPUT, OUTPUT_REPORTS, ROOT as WORK
from timeline_validate import SCHEMA_VERSION, configured_timeline_path, load_timeline, validate_timeline
from video_edit_app_config import load_app_config, nested


APP_CONFIG = load_app_config()
DEFAULT_OTIO = OUTPUT / "timelines" / "current.otio"
COMMAND_DIR = OUTPUT_REPORTS / "renderer_commands"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_stem(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "timeline"


def fps_number(value: Any) -> float:
    text = str(value or "30000/1001")
    if "/" in text:
        top, bottom = text.split("/", 1)
        denominator = as_float(bottom, 1.0)
        return as_float(top, 30.0) / denominator if denominator else 30.0
    return as_float(text, 30.0)


def rational_time(seconds: float, rate: float) -> dict[str, Any]:
    return {"OTIO_SCHEMA": "RationalTime.1", "value": seconds * rate, "rate": rate}


def time_range(start: float, duration: float, rate: float) -> dict[str, Any]:
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": rational_time(start, rate),
        "duration": rational_time(duration, rate),
    }


def source_by_id(timeline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(source.get("id")): source for source in timeline.get("sources", []) if isinstance(source, dict)}


def clip_to_otio(clip: dict[str, Any], sources: dict[str, dict[str, Any]], rate: float) -> dict[str, Any]:
    source = sources.get(str(clip.get("sourceId") or ""))
    source_path = str(source.get("path") or "") if source else ""
    source_in = as_float(clip.get("sourceIn"), 0.0)
    duration = max(0.0, as_float(clip.get("timelineEnd")) - as_float(clip.get("timelineStart")))
    return {
        "OTIO_SCHEMA": "Clip.2",
        "name": str(clip.get("id") or ""),
        "source_range": time_range(source_in, duration, rate),
        "media_reference": {
            "OTIO_SCHEMA": "ExternalReference.1" if source_path else "MissingReference.1",
            "name": str(source.get("id") or clip.get("sourceId") or "") if source else "",
            "target_url": source_path,
            "available_range": time_range(0.0, as_float(source.get("duration"), duration) if source else duration, rate),
            "metadata": {"videoEditSource": source or {}},
        },
        "metadata": {
            "videoEditClip": clip,
            "timelineStart": as_float(clip.get("timelineStart")),
            "timelineEnd": as_float(clip.get("timelineEnd")),
            "trackId": clip.get("trackId"),
        },
    }


def gap_to_otio(start: float, end: float, rate: float) -> dict[str, Any]:
    return {
        "OTIO_SCHEMA": "Gap.1",
        "name": f"gap_{int(start * 1000):08d}_{int(end * 1000):08d}",
        "source_range": time_range(0.0, max(0.0, end - start), rate),
        "metadata": {"timelineStart": start, "timelineEnd": end},
    }


def track_to_otio(track: dict[str, Any], clips: list[dict[str, Any]], sources: dict[str, dict[str, Any]], rate: float) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    cursor = 0.0
    for clip in sorted(clips, key=lambda item: (as_float(item.get("timelineStart")), as_float(item.get("timelineEnd")))):
        start = as_float(clip.get("timelineStart"))
        end = as_float(clip.get("timelineEnd"))
        if start > cursor + 0.001:
            children.append(gap_to_otio(cursor, start, rate))
        children.append(clip_to_otio(clip, sources, rate))
        cursor = max(cursor, end)
    return {
        "OTIO_SCHEMA": "Track.1",
        "name": str(track.get("id") or ""),
        "kind": "Video" if track.get("kind") in {"video", "overlay", "subtitle"} else "Audio",
        "children": children,
        "metadata": {"videoEditTrack": track},
    }


def export_otio(timeline: dict[str, Any]) -> dict[str, Any]:
    rate = fps_number(timeline.get("timebase", {}).get("fps"))
    sources = source_by_id(timeline)
    tracks = timeline.get("tracks") if isinstance(timeline.get("tracks"), list) else []
    clips = timeline.get("clips") if isinstance(timeline.get("clips"), list) else []
    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": str(timeline.get("id") or "video_edit_timeline"),
        "global_start_time": rational_time(0.0, rate),
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "children": [
                track_to_otio(
                    track,
                    [clip for clip in clips if isinstance(clip, dict) and clip.get("trackId") == track.get("id")],
                    sources,
                    rate,
                )
                for track in tracks
                if isinstance(track, dict)
            ],
        },
        "metadata": {
            "videoEditTimelineSchema": SCHEMA_VERSION,
            "videoEditTimeline": timeline,
            "exportedBy": "timeline_otio_adapter.py",
            "exportedAt": now_iso(),
        },
    }


def configured_project() -> dict[str, Any]:
    project = APP_CONFIG.get("project") if isinstance(APP_CONFIG.get("project"), dict) else {}
    return {
        "id": str(project.get("id") or ""),
        "name": str(project.get("name") or ""),
        "root": str(project.get("root") or ""),
        "sourceRoot": str(project.get("sourceRoot") or ""),
        "outputRoot": str(project.get("outputRoot") or OUTPUT),
    }


def default_render_target(duration: float, fps: str) -> dict[str, Any]:
    output_path = str(nested(APP_CONFIG, "render", "outputPath", default=str(OUTPUT / "videos" / "otio_import.mp4")))
    return {
        "id": "final",
        "path": output_path,
        "format": "mp4",
        "width": as_int(nested(APP_CONFIG, "render", "width", default=1920), 1920),
        "height": as_int(nested(APP_CONFIG, "render", "height", default=1080), 1080),
        "fps": fps,
        "profile": "final",
        "videoCodec": str(nested(APP_CONFIG, "render", "videoEncoder", default="libx264") or "libx264"),
        "audioCodec": "aac",
    }


def import_otio(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    embedded = metadata.get("videoEditTimeline")
    if isinstance(embedded, dict):
        return embedded

    tracks_payload = payload.get("tracks") if isinstance(payload.get("tracks"), dict) else {}
    children = tracks_payload.get("children") if isinstance(tracks_payload.get("children"), list) else []
    sources: list[dict[str, Any]] = []
    source_by_path: dict[str, str] = {}
    tracks: list[dict[str, Any]] = []
    clips: list[dict[str, Any]] = []
    duration = 0.0
    fps = "30000/1001"
    for track_index, track in enumerate(children, start=1):
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("name") or f"track_{track_index:02d}")
        kind = "audio" if str(track.get("kind") or "").lower() == "audio" else "video"
        tracks.append({"id": track_id, "kind": kind, "label": track_id, "allowOverlap": False})
        cursor = 0.0
        for child_index, child in enumerate(track.get("children") if isinstance(track.get("children"), list) else [], start=1):
            if not isinstance(child, dict):
                continue
            source_range = child.get("source_range") if isinstance(child.get("source_range"), dict) else {}
            duration_payload = source_range.get("duration") if isinstance(source_range.get("duration"), dict) else {}
            start_payload = source_range.get("start_time") if isinstance(source_range.get("start_time"), dict) else {}
            clip_duration = as_float(duration_payload.get("value"), 0.0) / max(as_float(duration_payload.get("rate"), 30.0), 1.0)
            source_in = as_float(start_payload.get("value"), 0.0) / max(as_float(start_payload.get("rate"), 30.0), 1.0)
            if child.get("OTIO_SCHEMA") == "Gap.1":
                cursor += clip_duration
                continue
            media_ref = child.get("media_reference") if isinstance(child.get("media_reference"), dict) else {}
            path = str(media_ref.get("target_url") or "")
            source_id = ""
            if path:
                source_id = source_by_path.get(path, "")
                if not source_id:
                    source_id = f"src_{len(sources) + 1:04d}"
                    source_by_path[path] = source_id
                    sources.append({"id": source_id, "kind": kind, "role": track_id, "path": path})
            clip_id = str(child.get("name") or f"{track_id}_clip_{child_index:04d}")
            clips.append(
                {
                    "id": clip_id,
                    "trackId": track_id,
                    "kind": kind if kind in {"video", "audio"} else "video",
                    **({"sourceId": source_id} if source_id else {}),
                    "timelineStart": cursor,
                    "timelineEnd": cursor + clip_duration,
                    "sourceIn": source_in,
                    "sourceOut": source_in + clip_duration,
                    "metadata": {"importedFromOtio": True},
                }
            )
            cursor += clip_duration
            duration = max(duration, cursor)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "id": safe_stem(str(payload.get("name") or "otio_import")),
        "createdAt": now_iso(),
        "project": configured_project(),
        "timebase": {"unit": "seconds", "fps": fps},
        "duration": max(duration, 0.001),
        "sources": sources,
        "tracks": tracks,
        "clips": clips,
        "transitions": [],
        "render": {"targets": [default_render_target(duration, fps)], "preview": {"enabled": True, "rangeStart": 0, "rangeEnd": max(duration, 0.001), "proxy": True}},
        "analysis": {"mediaManifestPath": "", "reports": []},
        "audit": {"createdBy": "timeline_otio_adapter.py import", "inputs": []},
    }


def report_path(output_path: Path, mode: str) -> Path:
    COMMAND_DIR.mkdir(parents=True, exist_ok=True)
    return COMMAND_DIR / f"{safe_stem(output_path.stem)}.otio_{mode}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export/import the normalized timeline as OpenTimelineIO-style JSON.")
    parser.add_argument("--mode", choices=["export", "import"], default="export")
    parser.add_argument("--timeline", type=Path, default=None, help="Timeline JSON path for export. Defaults to render.timelinePath.")
    parser.add_argument("--otio", type=Path, default=DEFAULT_OTIO, help="OTIO JSON file path.")
    parser.add_argument("--output-timeline", type=Path, default=None, help="Timeline JSON path for import. Defaults to render.timelinePath.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "export":
        timeline_path = args.timeline or configured_timeline_path(APP_CONFIG)
        timeline = load_timeline(timeline_path)
        errors, warnings = validate_timeline(timeline)
        if errors:
            raise SystemExit("Timeline validation failed before OTIO export: " + "; ".join(errors))
        payload = export_otio(timeline)
        args.otio.parent.mkdir(parents=True, exist_ok=True)
        args.otio.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report = {
            "createdAt": now_iso(),
            "adapter": "otio",
            "mode": "export",
            "timelinePath": str(timeline_path),
            "otioPath": str(args.otio),
            "validationWarnings": warnings,
            "clipCount": len(timeline.get("clips", [])),
            "trackCount": len(timeline.get("tracks", [])),
        }
    else:
        try:
            payload = json.loads(args.otio.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise SystemExit(f"OTIO file does not exist: {args.otio}") from error
        if not isinstance(payload, dict):
            raise SystemExit("OTIO root must be a JSON object.")
        timeline = import_otio(payload)
        errors, warnings = validate_timeline(timeline)
        if errors:
            raise SystemExit("Imported timeline validation failed: " + "; ".join(errors))
        output_timeline = args.output_timeline or configured_timeline_path(APP_CONFIG)
        output_timeline.parent.mkdir(parents=True, exist_ok=True)
        output_timeline.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
        report = {
            "createdAt": now_iso(),
            "adapter": "otio",
            "mode": "import",
            "timelinePath": str(output_timeline),
            "otioPath": str(args.otio),
            "validationWarnings": warnings,
            "clipCount": len(timeline.get("clips", [])),
            "trackCount": len(timeline.get("tracks", [])),
        }
    path = report_path(args.otio, args.mode)
    path.write_text(json.dumps({**report, "commandReport": str(path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report, "commandReport": str(path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
