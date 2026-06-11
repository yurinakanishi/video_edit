from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
VIDEOS = PROJECT_ROOT / "output" / "videos"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_test_project1_style_preview as preview  # noqa: E402


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event_start(event: dict[str, Any]) -> float:
    return float(event.get("timeline_start") or 0.0)


def event_end(event: dict[str, Any]) -> float:
    return float(event.get("timeline_end") or 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a tail preview from the current edit plan.")
    parser.add_argument("--duration-sec", type=float, default=30.0)
    parser.add_argument("--output-height", type=int, default=240)
    parser.add_argument("--output", type=Path, default=VIDEOS / "preview_tail_last30_240p.mp4")
    args = parser.parse_args()

    plan = read_json(REPORTS / "edit_plan.json")
    if not (plan.get("validation") or {}).get("ready_for_preview"):
        raise SystemExit("edit_plan.json is not marked ready_for_preview")
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    if not events:
        raise SystemExit("edit_plan.json timeline is empty")

    final_end = max(event_end(event) for event in events)
    tail_start = max(0.0, final_end - args.duration_sec)
    selected = [event for event in events if event_end(event) > tail_start]
    if not selected:
        raise SystemExit("No events overlap requested tail range")

    render_start = event_start(selected[0])
    trim_start = max(0.0, tail_start - render_start)
    segment_dir = VIDEOS / "tail_preview_segments"
    if segment_dir.exists():
        shutil.rmtree(segment_dir)
    segment_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = preview.ffmpeg_path()
    rendered: list[Path] = []
    for index, event in enumerate(selected, start=1):
        segment_id = f"tail_segment_{index:03d}_{event.get('event_id', 'event')}"
        segment_path = segment_dir / f"{segment_id}.mp4"
        preview.render_segment(ffmpeg, event, segment_path, segment_id)
        rendered.append(segment_path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    untrimmed = args.output.with_name(f"{args.output.stem}_untrimmed{args.output.suffix}")
    preview.concat_segments(ffmpeg, rendered, untrimmed, args.output_height)

    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-y",
            "-ss",
            f"{trim_start:.3f}",
            "-i",
            str(untrimmed),
            "-t",
            f"{args.duration_sec:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "25",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(args.output),
        ],
        cwd=preview.WORKSPACE_ROOT,
        check=True,
    )
    try:
        untrimmed.unlink()
    except OSError:
        pass

    report = {
        "schema_version": "tail_preview_report.v1",
        "project_id": plan.get("project_id"),
        "output": str(args.output),
        "duration_sec": args.duration_sec,
        "output_height": args.output_height,
        "timeline_start_sec": round(tail_start, 3),
        "timeline_end_sec": round(final_end, 3),
        "rendered_from_timeline_sec": round(render_start, 3),
        "trim_start_sec": round(trim_start, 3),
        "event_ids": [str(event.get("event_id")) for event in selected],
        "segment_count": len(rendered),
    }
    write_json(REPORTS / "tail_preview_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
