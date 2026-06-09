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
STATE_PATH = PROJECT_ROOT / "project_state.json"
FFMPEG_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")

SOURCES = [
    ("master", "group_wide", PROJECT_ROOT / "source" / "video" / "three people.mp4"),
    ("camera2", "cam_person_01", PROJECT_ROOT / "source" / "video" / "person-left.mp4"),
    ("camera3", "cam_person_02", PROJECT_ROOT / "source" / "video" / "person-middle.mp4"),
    ("camera4", "cam_person_03", PROJECT_ROOT / "source" / "video" / "person-right.mp4"),
]


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def ffmpeg_path() -> str:
    state = read_json(STATE_PATH, {})
    configured = str(((state.get("tools") or {}).get("ffmpeg")) or "").strip()
    if configured and Path(configured).exists():
        return configured
    if FFMPEG_DEFAULT.exists():
        return str(FFMPEG_DEFAULT)
    return "ffmpeg"


def app_offsets() -> dict[str, float]:
    payload = read_json(REPORTS / "app_sync_offsets.json", {})
    offsets = payload.get("offsets") if isinstance(payload.get("offsets"), dict) else {}
    result: dict[str, float] = {}
    for key, value in offsets.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            pass
    return result


def sync_statuses() -> dict[str, str]:
    payload = read_json(REPORTS / "sync_map.json", {})
    statuses: dict[str, str] = {"master": "MASTER"}
    for item in payload.get("media_sync", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if not role:
            continue
        if role == "master" or item.get("sync_status") == "master":
            statuses[role] = "MASTER"
            continue
        try:
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if item.get("manual_review_required") or confidence < 0.9:
            statuses[role] = "REVIEW"
        elif item.get("sync_status") == "synced":
            statuses[role] = "SYNCED"
        else:
            statuses[role] = "UNCONFIRMED"
    return statuses


def drawtext(label: str, status: str) -> str:
    text = f"{label} {status}  %{{pts\\:hms}}  frame=%{{n}}"
    return (
        "drawtext="
        f"text='{text}':"
        "x=18:y=18:fontsize=24:fontcolor=white:"
        "box=1:boxcolor=black@0.62:boxborderw=8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a 4-way visual sync review grid with time/frame labels.")
    parser.add_argument("--master-start", type=float, default=140.0)
    parser.add_argument("--duration", type=float, default=24.0)
    parser.add_argument("--output", type=Path, default=VIDEOS / "sync_review_grid.mp4")
    args = parser.parse_args()

    offsets = app_offsets()
    statuses = sync_statuses()
    command = [ffmpeg_path(), "-hide_banner", "-loglevel", "warning", "-y"]
    active_sources = []
    for role, media_id, path in SOURCES:
        if not path.exists():
            continue
        start = max(0.0, args.master_start + offsets.get(role, 0.0))
        command.extend(["-ss", f"{start:.3f}", "-t", f"{args.duration:.3f}", "-i", str(path)])
        status = statuses.get(role) or ("SYNCED" if role in offsets else "UNCONFIRMED")
        active_sources.append((role, media_id, status))
    if len(active_sources) != 4:
        raise SystemExit("Expected all four interview sources to exist for sync grid.")

    filters = []
    for index, (role, media_id, status) in enumerate(active_sources):
        filters.append(
            f"[{index}:v]scale=640:360:force_original_aspect_ratio=increase,crop=640:360,setsar=1,{drawtext(role + '/' + media_id, status)}[v{index}]"
        )
    filters.append("[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|640_0|0_360|640_360[vout]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[vout]",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-shortest",
            str(args.output),
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, cwd=WORKSPACE_ROOT, check=True)
    print(json.dumps({"output": str(args.output), "master_start": args.master_start, "duration": args.duration}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
