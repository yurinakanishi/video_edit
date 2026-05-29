from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from project_paths import OUTPUT_OVERLAYS


def seconds(value: str) -> float:
    text = str(value).strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(text)


def ffconcat_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def write_frame(path: Path, item: dict[str, Any] | None, width: int, height: int, bottom_margin: int) -> None:
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if item is not None:
        overlay_path = Path(str(item["file"]))
        if not overlay_path.is_absolute():
            overlay_path = Path.cwd() / overlay_path
        with Image.open(overlay_path).convert("RGBA") as overlay:
            x = round((width - overlay.width) / 2)
            y = height - overlay.height - bottom_margin
            canvas.alpha_composite(overlay, (x, y))
    canvas.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompose timed PNG subtitle overlays into one transparent video.")
    parser.add_argument("--manifest", type=Path, default=OUTPUT_OVERLAYS / "full_transcript_png_overlays" / "manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sequence-dir", type=Path, default=None)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--bottom-margin", type=int, default=16)
    parser.add_argument("--fps", default="60000/1001")
    args = parser.parse_args()

    items = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("overlay manifest must be a list")
    rows = sorted(items, key=lambda item: seconds(item["start"]))
    duration = args.duration if args.duration is not None else max((seconds(item["end"]) for item in rows), default=0.0)
    sequence_dir = args.sequence_dir or args.output.with_suffix("")
    sequence_dir.mkdir(parents=True, exist_ok=True)

    frames: list[tuple[Path, float]] = []
    cursor = 0.0
    frame_index = 1
    blank_path: Path | None = None

    def add_blank(length: float) -> None:
        nonlocal blank_path
        if length <= 0.001:
            return
        if blank_path is None:
            blank_path = sequence_dir / "blank.png"
            write_frame(blank_path, None, args.width, args.height, args.bottom_margin)
        frames.append((blank_path, length))

    for item in rows:
        start = max(0.0, seconds(item["start"]))
        end = min(duration, seconds(item["end"]))
        if end <= 0 or start >= duration or end <= start:
            continue
        add_blank(start - cursor)
        frame_path = sequence_dir / f"frame_{frame_index:04d}.png"
        frame_index += 1
        write_frame(frame_path, item, args.width, args.height, args.bottom_margin)
        frames.append((frame_path, end - start))
        cursor = max(cursor, end)
    add_blank(duration - cursor)
    if not frames:
        blank_path = sequence_dir / "blank.png"
        write_frame(blank_path, None, args.width, args.height, args.bottom_margin)
        frames.append((blank_path, max(duration, 0.1)))

    concat = sequence_dir / "concat.txt"
    lines: list[str] = []
    for frame_path, frame_duration in frames:
        lines.append(f"file '{ffconcat_path(frame_path)}'")
        lines.append(f"duration {frame_duration:.6f}")
    lines.append(f"file '{ffconcat_path(frames[-1][0])}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-vf",
        f"fps={args.fps},format=argb",
        "-c:v",
        "qtrle",
        "-pix_fmt",
        "argb",
        str(args.output),
    ]
    subprocess.run(command, check=True)
    print(json.dumps({"output": str(args.output), "frames": len(frames), "duration": duration}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
