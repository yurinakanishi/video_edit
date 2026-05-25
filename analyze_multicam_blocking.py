from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


JST = timezone(timedelta(hours=9))
FFPROBE = r"C:\ProgramData\chocolatey\bin\ffprobe.exe"
WORK = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("VIDEO_EDIT_SOURCE_ROOT", r"C:\Users\yurin\Downloads\cdc260515 mov\cdc260515 mov"))
OUT = WORK / "opencv_blocking_analysis"


@dataclass
class Clip:
    label: str
    path: Path
    start: datetime
    duration: float
    width: int
    height: int
    fps: float

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.duration)


def ffprobe_json(path: Path) -> dict:
    cmd = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,width,height,avg_frame_rate:format_tags=creation_time",
        "-of",
        "json",
        str(path),
    ]
    return json.loads(subprocess.check_output(cmd, text=True, encoding="utf-8"))


def parse_creation_time(value: str) -> datetime:
    if value.endswith("Z"):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(JST)
    return datetime.fromisoformat(value).replace(tzinfo=JST)


def parse_fps(value: str) -> float:
    if "/" in value:
        num, den = value.split("/")
        den_v = float(den)
        return float(num) / den_v if den_v else 0.0
    return float(value)


def load_clip(label: str, path: str) -> Clip:
    info = ffprobe_json(Path(path))
    format_info = info["format"]
    video_stream = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    return Clip(
        label=label,
        path=Path(path),
        start=parse_creation_time(format_info["tags"]["creation_time"]),
        duration=float(format_info["duration"]),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=parse_fps(video_stream["avg_frame_rate"]),
    )


def extract_frame(clip: Clip, offset_seconds: float) -> np.ndarray:
    cap = cv2.VideoCapture(str(clip.path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {clip.path}")
    cap.set(cv2.CAP_PROP_POS_MSEC, max(offset_seconds, 0.0) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError(f"Could not read frame at {offset_seconds:.2f} from {clip.path}")
    return frame


def overlap_window(a: Clip, b: Clip) -> tuple[datetime, datetime] | None:
    start = max(a.start, b.start)
    end = min(a.end, b.end)
    if end <= start:
        return None
    return start, end


def annotate(frame: np.ndarray, lines: Iterable[str]) -> np.ndarray:
    canvas = frame.copy()
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 72), (0, 0, 0), -1)
    y = 24
    for line in lines:
        cv2.putText(
            canvas,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        y += 22
    return canvas


def fit_width(frame: np.ndarray, width: int = 640) -> np.ndarray:
    h, w = frame.shape[:2]
    height = int(h * (width / w))
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def stack_vertical(frames: list[np.ndarray]) -> np.ndarray:
    width = max(f.shape[1] for f in frames)
    resized = []
    for frame in frames:
        if frame.shape[1] != width:
            height = int(frame.shape[0] * (width / frame.shape[1]))
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        resized.append(frame)
    gap = np.full((16, width, 3), 32, dtype=np.uint8)
    parts = []
    for idx, frame in enumerate(resized):
        parts.append(frame)
        if idx < len(resized) - 1:
            parts.append(gap)
    return np.vstack(parts)


def save_contact_sheet(name: str, rows: list[np.ndarray]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    image = stack_vertical(rows)
    path = OUT / f"{name}.png"
    cv2.imwrite(str(path), image)
    return path


def make_pair_sheet(name: str, a: Clip, b: Clip) -> Path | None:
    window = overlap_window(a, b)
    if window is None:
        return None
    midpoint = window[0] + (window[1] - window[0]) / 2
    a_offset = (midpoint - a.start).total_seconds()
    b_offset = (midpoint - b.start).total_seconds()
    a_frame = annotate(
        fit_width(extract_frame(a, a_offset)),
        [f"{a.label}  t={a_offset:0.1f}s", midpoint.strftime("%H:%M:%S")],
    )
    b_frame = annotate(
        fit_width(extract_frame(b, b_offset)),
        [f"{b.label}  t={b_offset:0.1f}s", midpoint.strftime("%H:%M:%S")],
    )
    return save_contact_sheet(name, [a_frame, b_frame])


def motion_score(clip: Clip, sample_count: int = 12) -> float:
    cap = cv2.VideoCapture(str(clip.path))
    if not cap.isOpened():
        return float("nan")
    duration = clip.duration
    samples = np.linspace(0, max(duration - 0.5, 0.5), num=sample_count)
    prev_gray = None
    total = 0.0
    used = 0
    for t in samples:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, int(gray.shape[0] * 320 / gray.shape[1])))
        if prev_gray is not None:
            total += float(cv2.absdiff(gray, prev_gray).mean())
            used += 1
        prev_gray = gray
    cap.release()
    return total / used if used else float("nan")


def make_group_sheet(group_name: str, base_clip: Clip, other_clips: list[Clip], sample_ratios: list[float]) -> list[Path]:
    outputs: list[Path] = []
    for idx, ratio in enumerate(sample_ratios, start=1):
        rows: list[np.ndarray] = []
        sample_time = base_clip.duration * ratio
        base_frame = fit_width(extract_frame(base_clip, sample_time))
        base_abs = base_clip.start + timedelta(seconds=sample_time)
        rows.append(
            annotate(
                base_frame,
                [
                    f"{base_clip.label}  t={sample_time:0.1f}s",
                    f"{base_abs.strftime('%H:%M:%S')}",
                ],
            )
        )
        for clip in other_clips:
            window = overlap_window(base_clip, clip)
            if window is None or not (window[0] <= base_abs <= window[1]):
                continue
            offset = (base_abs - clip.start).total_seconds()
            frame = fit_width(extract_frame(clip, offset))
            rows.append(
                annotate(
                    frame,
                    [
                        f"{clip.label}  t={offset:0.1f}s",
                        f"{base_abs.strftime('%H:%M:%S')}",
                    ],
                )
            )
        outputs.append(save_contact_sheet(f"{group_name}_sample_{idx}", rows))
    return outputs


def write_summary(clips: list[Clip]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "clip_metrics.json"
    payload = []
    for clip in clips:
        payload.append(
            {
                "label": clip.label,
                "path": str(clip.path),
                "start": clip.start.isoformat(),
                "end": clip.end.isoformat(),
                "duration": clip.duration,
                "resolution": f"{clip.width}x{clip.height}",
                "fps": clip.fps,
                "motion_score": motion_score(clip),
            }
        )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    clips = [
        load_clip("1cam ST7_7549", str(ROOT / "1cam" / "ST7_7549.MP4")),
        load_clip("3cam IMG_2140", str(ROOT / "3cam" / "IMG_2140.MP4")),
        load_clip("3cam IMG_2195", str(ROOT / "3cam" / "IMG_2195.MP4")),
        load_clip("3cam IMG_2196", str(ROOT / "3cam" / "IMG_2196.MP4")),
        load_clip("3cam IMG_2197", str(ROOT / "3cam" / "IMG_2197.MP4")),
        load_clip("1cam ST7_7550", str(ROOT / "1cam" / "ST7_7550.MP4")),
        load_clip("2cam 0H4A7189", str(ROOT / "2cam" / "0H4A7189.MP4")),
        load_clip("2cam 0H4A7190", str(ROOT / "2cam" / "0H4A7190.MP4")),
        load_clip("2cam 0H4A7192", str(ROOT / "2cam" / "0H4A7192.MP4")),
        load_clip("3cam IMG_2252", str(ROOT / "3cam" / "IMG_2252.MP4")),
        load_clip("3cam IMG_2316", str(ROOT / "3cam" / "IMG_2316.MP4")),
    ]
    write_summary(clips)
    make_group_sheet(
        "group_7549",
        clips[0],
        clips[1:5],
        [0.10, 0.45, 0.80],
    )
    make_group_sheet(
        "group_7550",
        clips[5],
        clips[6:],
        [0.20, 0.50, 0.82],
    )
    pairings = [
        ("pair_7549_2140", clips[0], clips[1]),
        ("pair_7549_2195", clips[0], clips[2]),
        ("pair_7549_2196", clips[0], clips[3]),
        ("pair_7549_2197", clips[0], clips[4]),
        ("pair_7550_7189", clips[5], clips[6]),
        ("pair_7550_7190", clips[5], clips[7]),
        ("pair_7550_7192", clips[5], clips[8]),
        ("pair_7550_2252", clips[5], clips[9]),
        ("pair_7550_2316", clips[5], clips[10]),
    ]
    for name, a_clip, b_clip in pairings:
        make_pair_sheet(name, a_clip, b_clip)


if __name__ == "__main__":
    main()
