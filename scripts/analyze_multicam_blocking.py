from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from project_paths import (
    CONFIG,
    OUTPUT_DIAGNOSTICS,
    OUTPUT_OVERLAYS,
    OUTPUT_REPORTS,
    OUTPUT_TRANSCRIPTS,
    OUTPUT_VIDEOS,
    ROOT as WORKSPACE_ROOT,
    SCRIPTS,
    SOURCE_AUDIO,
    SOURCE_IMAGES,
    SOURCE_SUBTITLES,
    SOURCE_VIDEO,
    multicam_source_root,
    resolve_project_path,
)
from typing import Iterable

import cv2
import numpy as np

from video_edit_app_config import load_app_config, nested, optional_path

JST = timezone(timedelta(hours=9))
APP_CONFIG = load_app_config()
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
WORK = WORKSPACE_ROOT
ROOT = multicam_source_root()
OUT = OUTPUT_DIAGNOSTICS / "opencv_blocking_analysis"


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
    clip_path = Path(path)
    info = ffprobe_json(clip_path)
    format_info = info["format"]
    video_stream = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    creation_time = format_info.get("tags", {}).get("creation_time")
    start = parse_creation_time(creation_time) if creation_time else datetime.fromtimestamp(clip_path.stat().st_mtime, JST)
    return Clip(
        label=label,
        path=clip_path,
        start=start,
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


def clip_path(*parts: str) -> Path:
    local = SOURCE_VIDEO.joinpath(*parts)
    return local if local.exists() else ROOT.joinpath(*parts)


def load_existing_clips(specs: list[tuple[str, tuple[str, ...]]]) -> list[Clip]:
    clips: list[Clip] = []
    missing: list[dict[str, str]] = []
    for label, parts in specs:
        path = clip_path(*parts)
        if path.exists():
            clips.append(load_clip(label, str(path)))
        else:
            missing.append({"label": label, "path": str(path)})
    if missing:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "missing_clips.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
    return clips


def by_label(clips: list[Clip], label: str) -> Clip | None:
    return next((clip for clip in clips if clip.label == label), None)


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_") or "clip"


def media_manifest() -> dict:
    manifest = nested(APP_CONFIG, "assets", "mediaManifest", default={})
    if isinstance(manifest, dict) and manifest.get("files"):
        return manifest
    path = str(nested(APP_CONFIG, "assets", "mediaManifestPath", default="") or "")
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def manifest_camera_specs() -> list[tuple[str, str]]:
    manifest = media_manifest()
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        return []
    camera_roles = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}

    def order(item: dict) -> int:
        role = str(item.get("role") or "")
        if role == "master":
            return 1
        if role.startswith("camera"):
            try:
                return int(role.replace("camera", ""))
            except ValueError:
                return 50
        return 100

    cameras = [
        item
        for item in files
        if isinstance(item, dict) and item.get("kind") == "video" and item.get("role") in camera_roles and item.get("path")
    ]
    cameras = sorted(cameras, key=order)
    return [(str(item.get("role") or ""), str(item.get("path") or "")) for item in cameras]


def run_manifest_analysis() -> bool:
    specs = manifest_camera_specs()
    if not specs:
        return False
    clips: list[Clip] = []
    for role, path in specs:
        clip_path = Path(path)
        if clip_path.exists():
            clips.append(load_clip(f"{role} {clip_path.stem}", str(clip_path)))
    if not clips:
        return False
    summary = write_summary(clips)
    master = next((clip for clip in clips if clip.label.startswith("master ")), clips[0])
    others = [clip for clip in clips if clip is not master]
    outputs: list[str] = [str(summary)]
    if others:
        outputs.extend(str(path) for path in make_group_sheet("manifest_multicam", master, others, [0.10, 0.45, 0.80]))
        for other in others:
            sheet = make_pair_sheet(f"pair_{safe_name(master.label)}_{safe_name(other.label)}", master, other)
            if sheet:
                outputs.append(str(sheet))
    payload = {"mode": "manifest", "clips": len(clips), "outputs": outputs}
    (OUT / "manifest_blocking_analysis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return True


def main() -> None:
    if run_manifest_analysis():
        return
    clips = load_existing_clips(
        [
            ("1cam ST7_7549", ("1cam", "ST7_7549.MP4")),
            ("3cam IMG_2140", ("3cam", "IMG_2140.MP4")),
            ("3cam IMG_2195", ("3cam", "IMG_2195.MP4")),
            ("3cam IMG_2196", ("3cam", "IMG_2196.MP4")),
            ("3cam IMG_2197", ("3cam", "IMG_2197.MP4")),
            ("1cam ST7_7550", ("1cam", "ST7_7550.MP4")),
            ("1cam ST7_7550 overlap", ("1cam", "ST7_7550_overlap_5min.mp4")),
            ("2cam 0H4A7189", ("2cam", "0H4A7189.MP4")),
            ("2cam 0H4A7190", ("2cam", "0H4A7190.MP4")),
            ("2cam 0H4A7192", ("2cam", "0H4A7192.MP4")),
            ("3cam IMG_2252", ("3cam", "IMG_2252.MP4")),
            ("3cam IMG_2316", ("3cam", "IMG_2316.MP4")),
        ]
    )
    if not clips:
        raise RuntimeError("No camera files were found under source/video or VIDEO_EDIT_SOURCE_ROOT.")
    write_summary(clips)
    group_7549_base = by_label(clips, "1cam ST7_7549")
    group_7549_others = [clip for clip in clips if clip.label in {"3cam IMG_2140", "3cam IMG_2195", "3cam IMG_2196", "3cam IMG_2197"}]
    if group_7549_base and group_7549_others:
        make_group_sheet("group_7549", group_7549_base, group_7549_others, [0.10, 0.45, 0.80])

    group_7550_base = by_label(clips, "1cam ST7_7550") or by_label(clips, "1cam ST7_7550 overlap")
    group_7550_others = [
        clip
        for clip in clips
        if clip.label in {"2cam 0H4A7189", "2cam 0H4A7190", "2cam 0H4A7192", "3cam IMG_2252", "3cam IMG_2316"}
    ]
    if group_7550_base and group_7550_others:
        make_group_sheet("group_7550", group_7550_base, group_7550_others, [0.20, 0.50, 0.82])

    label_map = {clip.label: clip for clip in clips}
    pairing_specs = [
        ("pair_7549_2140", "1cam ST7_7549", "3cam IMG_2140"),
        ("pair_7549_2195", "1cam ST7_7549", "3cam IMG_2195"),
        ("pair_7549_2196", "1cam ST7_7549", "3cam IMG_2196"),
        ("pair_7549_2197", "1cam ST7_7549", "3cam IMG_2197"),
        ("pair_7550_7189", "1cam ST7_7550", "2cam 0H4A7189"),
        ("pair_7550_7190", "1cam ST7_7550", "2cam 0H4A7190"),
        ("pair_7550_7192", "1cam ST7_7550", "2cam 0H4A7192"),
        ("pair_7550_2252", "1cam ST7_7550", "3cam IMG_2252"),
        ("pair_7550_2316", "1cam ST7_7550", "3cam IMG_2316"),
    ]
    if "1cam ST7_7550" not in label_map and "1cam ST7_7550 overlap" in label_map:
        label_map["1cam ST7_7550"] = label_map["1cam ST7_7550 overlap"]
    for name, a_label, b_label in pairing_specs:
        if a_label in label_map and b_label in label_map:
            make_pair_sheet(name, label_map[a_label], label_map[b_label])


if __name__ == "__main__":
    main()
