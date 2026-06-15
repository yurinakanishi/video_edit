from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


PROJECT_ID = "engineer-type-demo-interview"
PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[1]
STATE = PROJECT / "project_state.json"
VIDEOS = PROJECT / "output" / "videos"
REPORTS = PROJECT / "output" / "reports"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    parts = raw.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Invalid time value: {value}") from error
    raise argparse.ArgumentTypeError(f"Invalid time value: {value}")


def safe_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "spot"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a short engineer-type 240p proxy preview window.")
    start = parser.add_mutually_exclusive_group()
    start.add_argument(
        "--review-start",
        type=parse_seconds,
        help="Start time in the reviewed-video baseline, after the first 85.5s source trim. Accepts seconds, M:SS, or H:MM:SS.",
    )
    start.add_argument(
        "--source-start",
        type=parse_seconds,
        help="Absolute source timeline start. Accepts seconds, M:SS, or H:MM:SS.",
    )
    parser.add_argument("--duration", type=parse_seconds, default=90.0, help="Spot preview duration. Default: 90s.")
    parser.add_argument("--height", type=int, default=240, help="Output height. Default: 240.")
    parser.add_argument("--output", type=Path, default=None, help="Optional output path.")
    parser.add_argument("--label", default="", help="Optional label for the output filename.")
    parser.add_argument("--subtitle-mode", choices=["full", "none", "punchline"], default=None)
    parser.add_argument("--dry-run", action="store_true", help="Write the temp config and print the render command without running it.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = read_json(STATE)
    render = state.setdefault("render", {})
    reviewed_trim = render.get("reviewedVideoSourceTrim") if isinstance(render.get("reviewedVideoSourceTrim"), dict) else {}
    reviewed_start_trim = float(reviewed_trim.get("startSeconds") or render.get("previewStart") or 0.0)

    if args.source_start is not None:
        source_start = float(args.source_start)
        start_label = f"src_{source_start:.3f}"
    elif args.review_start is not None:
        source_start = reviewed_start_trim + float(args.review_start)
        start_label = f"rev_{float(args.review_start):.3f}"
    else:
        source_start = float(render.get("previewStart") or reviewed_start_trim)
        start_label = f"src_{source_start:.3f}"

    duration = max(0.1, float(args.duration or 90.0))
    label = safe_label(args.label or start_label)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or (VIDEOS / f"{timestamp}_{label}_{int(args.height)}p_spot.mp4")

    temp_state = dict(state)
    temp_state["project"] = {
        **(state.get("project") if isinstance(state.get("project"), dict) else {}),
        "sourceRoot": str(PROJECT / "source"),
        "outputRoot": str(PROJECT / "output"),
    }
    temp_render = dict(render)
    temp_render.update(
        {
            "renderProfile": "preview",
            "rangeMode": "range",
            "outputHeight": int(args.height),
            "outputPath": str(output),
            "previewStart": source_start,
            "previewDuration": duration,
            "subtitleOverlayFormat": "png",
        }
    )
    if args.subtitle_mode is not None:
        temp_render["subtitleMode"] = args.subtitle_mode
    temp_state["render"] = temp_render

    config_path = REPORTS / "spot_preview_config.json"
    write_json(config_path, temp_state)
    command = [sys.executable, str(WORKSPACE / "scripts" / "render_multicam.py")]
    env = os.environ.copy()
    env["VIDEO_EDIT_PROJECT"] = PROJECT_ID
    env["VIDEO_EDIT_APP_CONFIG"] = str(config_path)

    summary = {
        "config": str(config_path),
        "output": str(output),
        "sourceStart": source_start,
        "duration": duration,
        "height": int(args.height),
        "subtitleMode": temp_render.get("subtitleMode"),
        "command": command,
        "dryRun": bool(args.dry_run),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if args.dry_run:
        return
    subprocess.run(command, cwd=WORKSPACE, env=env, check=True)


if __name__ == "__main__":
    main()
