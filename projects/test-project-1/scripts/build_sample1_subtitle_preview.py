from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE_VIDEO = PROJECT_ROOT / "source" / "video" / "Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4"
TRANSCRIPT_DIR = PROJECT_ROOT / "output" / "transcripts" / "manifest_sources"
PRIMARY_SRT = TRANSCRIPT_DIR / "primary.srt"
CORRECTED_SRT = TRANSCRIPT_DIR / "primary_corrected.srt"
CORRECTED_TXT = TRANSCRIPT_DIR / "primary_corrected.txt"
OUTPUT_SUBTITLES = PROJECT_ROOT / "output" / "subtitles"
OUTPUT_TIMELINES = PROJECT_ROOT / "output" / "timelines"
OUTPUT_REPORTS = PROJECT_ROOT / "output" / "reports"
OUTPUT_IMAGES = PROJECT_ROOT / "output" / "images"
OUTPUT_VIDEOS = PROJECT_ROOT / "output" / "videos"
REFERENCE_ANALYSIS = REPO_ROOT / "reference-assets" / "library" / "collections" / "layer-x" / "video" / "sample-1" / "analysis.json"
MEDIA_MANIFEST = OUTPUT_REPORTS / "media_manifest.json"
ASS_PATH = OUTPUT_SUBTITLES / "sample1_style.ass"
TIMELINE_PATH = OUTPUT_TIMELINES / "sample1_subtitle_preview.timeline.json"
REPORT_PATH = OUTPUT_REPORTS / "sample1_subtitle_preview_report.json"
PREVIEW_VIDEO = OUTPUT_VIDEOS / "preview_sample1_subtitles.mp4"
PREVIEW_STILL = OUTPUT_IMAGES / "preview_sample1_subtitles_t0005.jpg"

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
PREVIEW_WIDTH = 1280
PREVIEW_HEIGHT = 720
FPS = "24000/1001"
PURPLE = "#5A45EF"
TEXT_DARK = "#253238"
WHITE = "#FFFFFF"
MAX_CHARS_PER_CHUNK = 62
MAX_CHARS_PER_LINE = 38


class Caption(dict):
    @property
    def index(self) -> int:
        return int(self["index"])

    @property
    def start(self) -> float:
        return float(self["start"])

    @property
    def end(self) -> float:
        return float(self["end"])

    @property
    def text(self) -> str:
        return str(self["text"])


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_srt_time(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid SRT timestamp: {value}")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def format_srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_ass_time(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    hours, rem = divmod(cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def parse_srt(path: Path) -> list[Caption]:
    raw = path.read_text(encoding="utf-8-sig").strip()
    captions: list[Caption] = []
    if not raw:
        return captions
    for block in re.split(r"\n\s*\n", raw):
        rows = [row.strip() for row in block.splitlines() if row.strip()]
        if len(rows) < 3 or "-->" not in rows[1]:
            continue
        start_raw, end_raw = [part.strip() for part in rows[1].split("-->", 1)]
        captions.append(
            Caption(
                index=int(rows[0]),
                start=parse_srt_time(start_raw),
                end=parse_srt_time(end_raw),
                text=normalize_text(" ".join(rows[2:])),
            )
        )
    return captions


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        "a high-opening experience.": "an eye-opening experience.",
        "A high-opening experience.": "An eye-opening experience.",
    }
    return replacements.get(text, text)


def write_srt(path: Path, captions: list[Caption]) -> None:
    rows: list[str] = []
    for index, caption in enumerate(captions, start=1):
        rows.extend(
            [
                str(index),
                f"{format_srt_time(caption.start)} --> {format_srt_time(caption.end)}",
                caption.text,
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows), encoding="utf-8")


def write_transcript_text(path: Path, captions: list[Caption]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(" ".join(caption.text for caption in captions).strip() + "\n", encoding="utf-8")


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def ass_color(hex_color: str, alpha: str = "00") -> str:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"invalid color: {hex_color}")
    rr, gg, bb = value[0:2], value[2:4], value[4:6]
    return f"&H{alpha}{bb}{gg}{rr}"


def split_words(text: str, limit: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > limit:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def wrap_lines(text: str, limit: int) -> list[str]:
    chunks = split_words(text, limit)
    if len(chunks) <= 2:
        return chunks
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(merged[-1]) + 1 + len(chunk) <= limit + 8:
            merged[-1] = f"{merged[-1]} {chunk}"
        else:
            merged.append(chunk)
    return merged[:2] if len(merged) > 2 else merged


def chunk_caption(caption: Caption) -> list[Caption]:
    chunks = split_words(caption.text, MAX_CHARS_PER_CHUNK)
    if len(chunks) <= 1:
        return [caption]
    duration = max(0.1, caption.end - caption.start)
    weights = [max(1, len(chunk)) for chunk in chunks]
    total = sum(weights)
    output: list[Caption] = []
    cursor = caption.start
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        if index == len(chunks) - 1:
            end = caption.end
        else:
            end = min(caption.end, cursor + duration * weight / total)
        output.append(Caption(index=caption.index, start=cursor, end=end, text=chunk))
        cursor = end
    return output


def reference_style_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    subtitle_boxes: list[dict[str, Any]] = []
    title_boxes: list[dict[str, Any]] = []
    logo_boxes: list[dict[str, Any]] = []
    for frame in data.get("frames", []):
        if not isinstance(frame, dict):
            continue
        for item in frame.get("textOverlays", []):
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role == "subtitle":
                subtitle_boxes.append(item)
            elif role == "title":
                title_boxes.append(item)
            elif role == "logo_text":
                logo_boxes.append(item)
    return {
        "analysisPath": str(path),
        "asset": data.get("asset", {}),
        "summary": data.get("summary", {}),
        "derivedStyle": {
            "subtitleBoxCount": len(subtitle_boxes),
            "titleBoxCount": len(title_boxes),
            "logoBoxCount": len(logo_boxes),
            "subtitleColor": PURPLE,
            "subtitleTreatment": "large lower-third opaque boxes with white/purple alternation",
            "topTreatment": "LayerX-style brand marker plus purple title banner",
        },
    }


def ass_header(font_size: int = 74) -> str:
    purple_ass = ass_color(PURPLE)
    white_ass = ass_color(WHITE)
    dark_ass = ass_color(TEXT_DARK)
    return f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PurpleBox,Yu Gothic UI,{font_size},{white_ass},{white_ass},{purple_ass},{purple_ass},-1,0,0,0,100,100,0,0,3,20,0,2,70,70,50,1
Style: WhiteBox,Yu Gothic UI,{font_size},{purple_ass},{purple_ass},{white_ass},{white_ass},-1,0,0,0,100,100,0,0,3,20,0,2,70,70,50,1
Style: TopTitle,Yu Gothic UI,50,{white_ass},{white_ass},{purple_ass},{purple_ass},-1,0,0,0,100,100,0,0,3,14,0,8,40,40,30,1
Style: Logo,Yu Gothic UI,58,{dark_ass},{dark_ass},{white_ass},{white_ass},-1,0,0,0,100,100,0,0,1,0,0,7,45,45,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass_events(captions: list[Caption], duration: float) -> list[str]:
    events = [
        f"Dialogue: 3,{format_ass_time(0)},{format_ass_time(duration)},Logo,,0,0,0,,{{\\an7\\pos(64,38)}}LayerX",
        f"Dialogue: 3,{format_ass_time(0)},{format_ass_time(duration)},TopTitle,,0,0,0,,{{\\an8\\pos(1410,58)}}Michael Eisen on Open Access",
    ]
    for caption in captions:
        for chunk in chunk_caption(caption):
            lines = wrap_lines(chunk.text, MAX_CHARS_PER_LINE)
            if not lines:
                continue
            if len(lines) == 1:
                events.append(
                    "Dialogue: 5,"
                    f"{format_ass_time(chunk.start)},{format_ass_time(chunk.end)},PurpleBox,,0,0,0,,"
                    f"{{\\an2\\pos(960,905)}}{ass_escape(lines[0])}"
                )
                continue
            events.append(
                "Dialogue: 5,"
                f"{format_ass_time(chunk.start)},{format_ass_time(chunk.end)},PurpleBox,,0,0,0,,"
                f"{{\\an2\\pos(960,805)}}{ass_escape(lines[0])}"
            )
            events.append(
                "Dialogue: 6,"
                f"{format_ass_time(chunk.start)},{format_ass_time(chunk.end)},WhiteBox,,0,0,0,,"
                f"{{\\an2\\pos(960,930)}}{ass_escape(lines[1])}"
            )
    return events


def video_duration(path: Path, ffprobe: str) -> float:
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    output = subprocess.check_output(command, cwd=REPO_ROOT, text=True).strip()
    return float(output)


def render_preview(ffmpeg: str, video: Path, ass_path: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    relative_ass = ass_path.relative_to(REPO_ROOT).as_posix()
    vf = f"ass={relative_ass},scale={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:flags=bicubic"
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(video),
        "-vf",
        vf,
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
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def extract_still(ffmpeg: str, video: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-ss",
        "5",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def write_timeline(duration: float) -> None:
    timeline = {
        "schemaVersion": "video-edit-timeline/v1",
        "id": "timeline_test-project-1_sample1_subtitle_preview",
        "createdAt": now_iso(),
        "project": {
            "id": "test-project-1",
            "name": "Test Project 1",
            "root": str(PROJECT_ROOT),
            "sourceRoot": str(PROJECT_ROOT / "source"),
            "outputRoot": str(PROJECT_ROOT / "output"),
        },
        "timebase": {"unit": "seconds", "fps": FPS},
        "duration": round(duration, 6),
        "sources": [
            {
                "id": "src_master",
                "kind": "video",
                "role": "master",
                "path": str(SOURCE_VIDEO),
                "duration": round(duration, 6),
                "width": VIDEO_WIDTH,
                "height": VIDEO_HEIGHT,
                "fps": FPS,
                "codec": "h264",
            },
            {"id": "src_corrected_srt", "kind": "subtitle", "role": "subtitle", "path": str(CORRECTED_SRT)},
            {"id": "src_sample1_ass", "kind": "subtitle", "role": "styled-subtitle", "path": str(ASS_PATH)},
        ],
        "tracks": [
            {"id": "video.main", "kind": "video", "label": "Main video", "allowOverlap": False},
            {"id": "audio.main", "kind": "audio", "label": "Source audio", "allowOverlap": False},
            {"id": "subtitle.main", "kind": "subtitle", "label": "Sample-1 styled subtitles", "allowOverlap": True},
        ],
        "clips": [
            {
                "id": "clip_video_master",
                "trackId": "video.main",
                "kind": "video",
                "sourceId": "src_master",
                "timelineStart": 0.0,
                "timelineEnd": round(duration, 6),
                "sourceIn": 0.0,
                "sourceOut": round(duration, 6),
                "fit": {"mode": "contain", "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
            },
            {
                "id": "clip_audio_master",
                "trackId": "audio.main",
                "kind": "audio",
                "sourceId": "src_master",
                "timelineStart": 0.0,
                "timelineEnd": round(duration, 6),
                "sourceIn": 0.0,
                "sourceOut": round(duration, 6),
            },
            {
                "id": "clip_subtitles_sample1",
                "trackId": "subtitle.main",
                "kind": "subtitle",
                "sourceId": "src_sample1_ass",
                "timelineStart": 0.0,
                "timelineEnd": round(duration, 6),
                "style": {
                    "referenceAnalysisPath": str(REFERENCE_ANALYSIS),
                    "subtitleColor": PURPLE,
                    "fontSize": 74,
                    "renderMethod": "ffmpeg-ass-burn-in-preview",
                },
            },
        ],
        "transitions": [],
        "render": {
            "targets": [
                {
                    "id": "preview",
                    "path": str(PREVIEW_VIDEO),
                    "format": "mp4",
                    "width": PREVIEW_WIDTH,
                    "height": PREVIEW_HEIGHT,
                    "fps": FPS,
                    "profile": "preview",
                    "videoCodec": "libx264",
                    "audioCodec": "aac",
                }
            ],
            "preview": {"enabled": True, "rangeStart": 0.0, "rangeEnd": round(duration, 6), "proxy": True},
        },
        "analysis": {
            "mediaManifestPath": str(MEDIA_MANIFEST),
            "reports": [
                {"kind": "media-manifest", "path": str(MEDIA_MANIFEST), "exists": MEDIA_MANIFEST.exists()},
                {"kind": "reference-analysis", "path": str(REFERENCE_ANALYSIS), "exists": REFERENCE_ANALYSIS.exists()},
            ],
        },
        "audit": {
            "createdBy": "projects/test-project-1/scripts/build_sample1_subtitle_preview.py",
            "inputs": [
                {"kind": "primary-srt", "path": str(PRIMARY_SRT), "exists": PRIMARY_SRT.exists()},
                {"kind": "reference-analysis", "path": str(REFERENCE_ANALYSIS), "exists": REFERENCE_ANALYSIS.exists()},
            ],
        },
    }
    TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TIMELINE_PATH.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a sample-1 styled subtitle preview for test-project-1.")
    parser.add_argument("--ffmpeg", default=r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
    parser.add_argument("--ffprobe", default=r"C:\ProgramData\chocolatey\bin\ffprobe.exe")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    if not PRIMARY_SRT.exists():
        raise SystemExit(f"Transcript SRT is missing: {PRIMARY_SRT}")
    if not REFERENCE_ANALYSIS.exists():
        raise SystemExit(f"Reference analysis is missing: {REFERENCE_ANALYSIS}")

    duration = video_duration(SOURCE_VIDEO, args.ffprobe)
    captions = parse_srt(PRIMARY_SRT)
    if not captions:
        raise SystemExit("No captions found in primary SRT.")

    corrected = [Caption(index=item.index, start=item.start, end=item.end, text=normalize_text(item.text)) for item in captions]
    write_srt(CORRECTED_SRT, corrected)
    write_transcript_text(CORRECTED_TXT, corrected)

    ASS_PATH.parent.mkdir(parents=True, exist_ok=True)
    events = build_ass_events(corrected, duration)
    ASS_PATH.write_text(ass_header() + "\n".join(events) + "\n", encoding="utf-8")
    write_timeline(duration)

    if not args.skip_render:
        render_preview(args.ffmpeg, SOURCE_VIDEO, ASS_PATH, PREVIEW_VIDEO)
        extract_still(args.ffmpeg, PREVIEW_VIDEO, PREVIEW_STILL)

    report = {
        "createdAt": now_iso(),
        "sourceVideo": str(SOURCE_VIDEO),
        "reference": reference_style_summary(REFERENCE_ANALYSIS),
        "primarySrt": str(PRIMARY_SRT),
        "correctedSrt": str(CORRECTED_SRT),
        "correctedTranscriptText": str(CORRECTED_TXT),
        "ass": str(ASS_PATH),
        "timeline": str(TIMELINE_PATH),
        "previewVideo": str(PREVIEW_VIDEO) if PREVIEW_VIDEO.exists() else "",
        "previewStill": str(PREVIEW_STILL) if PREVIEW_STILL.exists() else "",
        "captionCount": len(corrected),
        "assEventCount": len(events),
        "duration": round(duration, 6),
        "notes": [
            "Preview render only; production render should wait for user approval.",
            "Subtitle style derived from sample-1 analysis: large lower-third boxes, LayerX-style logo text, and purple top title banner.",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
