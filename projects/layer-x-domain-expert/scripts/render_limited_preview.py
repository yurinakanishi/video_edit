from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
VIDEOS = PROJECT_ROOT / "output" / "videos"
DIAGNOSTICS = PROJECT_ROOT / "output" / "diagnostics"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
FONT_FILE = Path(r"C:\Windows\Fonts\YuGothB.ttc")


MEDIA_PATHS = {
    "group_wide": PROJECT_ROOT / "source" / "video" / "three people.mp4",
    "cam_person_01": PROJECT_ROOT / "source" / "video" / "person-left.mp4",
    "cam_person_02": PROJECT_ROOT / "source" / "video" / "person-middle.mp4",
    "cam_person_03": PROJECT_ROOT / "source" / "video" / "person-right.mp4",
    "company_movie": PROJECT_ROOT / "source" / "video" / "company-movie.mp4",
}

MEDIA_TO_ROLE = {
    "cam_person_01": "camera2",
    "cam_person_02": "camera3",
    "cam_person_03": "camera4",
    "group_wide": "master",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ffmpeg_path() -> str:
    state_path = PROJECT_ROOT / "project_state.json"
    if state_path.exists():
        state = read_json(state_path)
        configured = str(((state.get("tools") or {}).get("ffmpeg")) or "").strip()
        if configured and Path(configured).exists():
            return configured
    if FFMPEG_DEFAULT.exists():
        return str(FFMPEG_DEFAULT)
    return "ffmpeg"


def app_offsets() -> dict[str, float]:
    path = REPORTS / "app_sync_offsets.json"
    if not path.exists():
        return {"master": 0.0}
    payload = read_json(path)
    offsets = payload.get("offsets") if isinstance(payload.get("offsets"), dict) else {}
    result = {"master": 0.0}
    for key, value in offsets.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            pass
    return result


def duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event["timeline_end"]) - float(event["timeline_start"]))


def clip_source(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"event {event.get('event_id')} has no source")
    return source


def audio_source(event: dict[str, Any]) -> dict[str, Any]:
    reference = event.get("reference_source")
    if isinstance(reference, dict):
        return reference
    return clip_source(event)


def ffmpeg_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("%", "\\%")
    )


def caption_filters(event: dict[str, Any]) -> str:
    filters = []
    for overlay in event.get("overlays", []):
        if not isinstance(overlay, dict) or overlay.get("type") != "caption":
            continue
        text = str(overlay.get("text") or "").strip()
        if not text:
            continue
        start = float(overlay.get("start") or 0.0)
        end = float(overlay.get("end") or duration(event))
        font = FONT_FILE.as_posix().replace(":", "\\:")
        filters.append(
            "drawtext="
            f"fontfile='{font}':"
            f"text='{ffmpeg_text(text)}':"
            "x=(w-text_w)/2:"
            "y=h-128:"
            "fontsize=38:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black@0.65:"
            "box=1:"
            "boxcolor=0x5F5AF5@0.88:"
            "boxborderw=18:"
            f"enable='between(t\\,{start:.3f}\\,{end:.3f})'"
        )
    return "," + ",".join(filters) if filters else ""


def video_filter(event: dict[str, Any]) -> str:
    section = str(event.get("section") or "")
    if section == "bridge":
        base = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1"
    else:
        base = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1"
    return base + caption_filters(event)


def synced_media_start(media_id: str, master_time: float, offsets: dict[str, float]) -> float:
    role = MEDIA_TO_ROLE.get(media_id, "master")
    return max(0.0, master_time + offsets.get(role, 0.0))


def split_media_ids(event: dict[str, Any]) -> list[str]:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    media_ids = layout.get("media_ids")
    if isinstance(media_ids, list):
        return [str(media_id) for media_id in media_ids if str(media_id) in MEDIA_PATHS]
    return []


def render_segment(ffmpeg: str, event: dict[str, Any], output: Path) -> None:
    layout = event.get("layout") if isinstance(event.get("layout"), dict) else {}
    if layout.get("type") == "split_grid" and split_media_ids(event):
        render_split_segment(ffmpeg, event, output)
        return
    src = clip_source(event)
    aud = audio_source(event)
    video_path = MEDIA_PATHS.get(str(src.get("media_id")))
    audio_path = MEDIA_PATHS.get(str(aud.get("media_id")))
    if video_path is None or not video_path.exists():
        raise FileNotFoundError(f"Video media not available for preview: {src.get('media_id')}")
    if audio_path is None or not audio_path.exists():
        raise FileNotFoundError(f"Audio media not available for preview: {aud.get('media_id')}")
    dur = duration(event)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-ss",
        f"{float(src.get('in') or 0.0):.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(video_path),
        "-ss",
        f"{float(aud.get('in') or 0.0):.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-vf",
        video_filter(event),
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-shortest",
        str(output),
    ]
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)


def render_split_segment(ffmpeg: str, event: dict[str, Any], output: Path) -> None:
    aud = audio_source(event)
    audio_path = MEDIA_PATHS.get(str(aud.get("media_id")))
    if audio_path is None or not audio_path.exists():
        raise FileNotFoundError(f"Audio media not available for preview: {aud.get('media_id')}")
    media_ids = split_media_ids(event)
    dur = duration(event)
    master_in = float((event.get("reference_source") or {}).get("in") or (event.get("source") or {}).get("in") or 0.0)
    offsets = app_offsets()
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-y"]
    for media_id in media_ids:
        video_path = MEDIA_PATHS[media_id]
        command.extend(["-ss", f"{synced_media_start(media_id, master_in, offsets):.3f}", "-t", f"{dur:.3f}", "-i", str(video_path)])
    command.extend(["-ss", f"{float(aud.get('in') or master_in):.3f}", "-t", f"{dur:.3f}", "-i", str(audio_path)])

    filters = []
    if len(media_ids) == 2:
        for index in range(2):
            filters.append(f"[{index}:v]scale=640:720:force_original_aspect_ratio=increase,crop=640:720,setsar=1[v{index}]")
        stack = "[v0][v1]hstack=inputs=2"
    elif len(media_ids) == 3:
        for index in range(3):
            filters.append(f"[{index}:v]scale=426:720:force_original_aspect_ratio=increase,crop=426:720,setsar=1[v{index}]")
        stack = "[v0][v1][v2]hstack=inputs=3,pad=1280:720:1:0"
    else:
        raise ValueError(f"Unsupported split media count: {len(media_ids)}")
    filters.append(stack + caption_filters(event) + "[vout]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            f"{len(media_ids)}:a:0?",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-shortest",
            str(output),
        ]
    )
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)


def concat_segments(ffmpeg: str, segments: list[Path], output: Path) -> None:
    list_path = DIAGNOSTICS / "limited_preview_concat.txt"
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text("".join(f"file '{path.as_posix()}'\n" for path in segments), encoding="utf-8")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            str(output),
        ],
        cwd=WORKSPACE_ROOT,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a lightweight limited preview from edit_plan.json.")
    parser.add_argument("--max-events", type=int, default=8, help="Limit preview length for fast review.")
    parser.add_argument("--output", type=Path, default=VIDEOS / "preview_limited.mp4")
    args = parser.parse_args()

    plan = read_json(REPORTS / "edit_plan.json")
    if not (plan.get("validation") or {}).get("ready_for_preview"):
        raise SystemExit("edit_plan.json is not marked ready_for_preview")
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    if args.max_events:
        events = events[: args.max_events]
    if not events:
        raise SystemExit("No timeline events to render")

    segment_dir = VIDEOS / "preview_limited_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_path()
    rendered = []
    for index, event in enumerate(events, start=1):
        segment_path = segment_dir / f"segment_{index:03d}_{event.get('event_id', 'event')}.mp4"
        render_segment(ffmpeg, event, segment_path)
        rendered.append(segment_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    concat_segments(ffmpeg, rendered, args.output)
    print(json.dumps({"output": str(args.output), "segments": len(rendered)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
