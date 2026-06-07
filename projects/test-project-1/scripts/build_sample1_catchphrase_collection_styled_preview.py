from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

PROJECT_SAMPLE_VIDEO = PROJECT_ROOT / "source" / "video" / "Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4"
CATCHPHRASE_JSON = PROJECT_ROOT / "output" / "subtitles" / "sample1_catchphrase_collection.json"

OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_SUBTITLES = OUTPUT_DIR / "subtitles"
OUTPUT_VIDEOS = OUTPUT_DIR / "videos"
OUTPUT_IMAGES = OUTPUT_DIR / "images"
OUTPUT_REPORTS = OUTPUT_DIR / "reports"
OUTPUT_TIMELINES = OUTPUT_DIR / "timelines"

STYLE_PROFILE = OUTPUT_SUBTITLES / "sample1_catchphrase_collection_styled_profile.json"
SUBTITLE_OVERLAY_VIDEO = OUTPUT_SUBTITLES / "sample1_catchphrase_collection_subtitle_overlay.mov"
PREVIEW_VIDEO = OUTPUT_VIDEOS / "preview_sample1_catchphrase_collection_styled.mp4"
PREVIEW_STILL = OUTPUT_IMAGES / "preview_sample1_catchphrase_collection_styled_t0005.jpg"
TIMELINE_PATH = OUTPUT_TIMELINES / "sample1_catchphrase_collection_styled_preview.timeline.json"
REPORT_PATH = OUTPUT_REPORTS / "sample1_catchphrase_collection_styled_preview_report.json"

PREVIEW_WIDTH = 1280
PREVIEW_HEIGHT = 720
FPS = "24000/1001"
FPS_NUM = 24000
FPS_DEN = 1001
FPS_FLOAT = FPS_NUM / FPS_DEN


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


speech = load_module("test_project_1_speech_subtitles", SCRIPTS_DIR / "build_sample1_speech_subtitle_preview.py")
frame_design = load_module("test_project_1_frame_design", SCRIPTS_DIR / "build_sample11_frame_design_preview.py")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_payload() -> dict[str, Any]:
    if not CATCHPHRASE_JSON.exists():
        raise SystemExit(f"Catchphrase JSON is missing: {CATCHPHRASE_JSON}")
    return json.loads(CATCHPHRASE_JSON.read_text(encoding="utf-8"))


def build_caption_items(payload: dict[str, Any]) -> list[Any]:
    captions = []
    for index, phrase in enumerate(payload["phrases"], start=1):
        clip = phrase["editClip"]
        captions.append(
            speech.Caption(
                index=index,
                start=float(clip["timelineStart"]) + 0.12,
                end=float(clip["timelineEnd"]) - 0.15,
                text=str(phrase["displayText"]),
            )
        )
    return captions


def adapt_subtitle_profile_for_catchphrase(profile: dict[str, Any]) -> None:
    subtitle = profile["speechSubtitle"]
    subtitle["text"]["fontSizePx"] = min(int(subtitle["text"]["fontSizePx"]), 74)
    subtitle["text"]["minFontSizePx"] = min(int(subtitle["text"]["minFontSizePx"]), 56)
    subtitle["background"]["paddingY"] = min(int(subtitle["background"]["paddingY"]), 10)
    subtitle["placement"]["adaptation"] = {
        "target": "project-sample catchphrase preview",
        "reason": "Keep the sampled subtitle styling while moving upper reference patterns below the speaker face.",
        "minimumYNorm": 0.708,
    }
    rows = subtitle["placement"]["rows"]
    rows[0]["yPx"] = round(PREVIEW_HEIGHT * 0.667)
    rows[0]["yNorm"] = 0.667
    rows[0]["heightPx"] = 96
    rows[1]["yPx"] = round(PREVIEW_HEIGHT * 0.822)
    rows[1]["yNorm"] = 0.822
    rows[1]["heightPx"] = 96
    for pattern in subtitle.get("referencePatterns", {}).get("patterns", []):
        lines = pattern.get("lines", [])
        for line_index, line in enumerate(lines):
            if len(lines) > 1:
                line["yNorm"] = 0.667 if line_index == 0 else 0.822
                line["rowBand"] = "catchphrase-two-line-lower-speech"
            elif float(line.get("yNorm", 0.0)) < 0.708:
                line["yNorm"] = 0.708
                line["rowBand"] = "catchphrase-single-line-lower-speech"


def render_subtitle_overlay(ffmpeg: str, captions: list[Any], profile: dict[str, Any], duration: float) -> None:
    SUBTITLE_OVERLAY_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    chunks = captions
    total_frames = math.ceil(duration * FPS_FLOAT)
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{PREVIEW_WIDTH}x{PREVIEW_HEIGHT}",
        "-r",
        FPS,
        "-i",
        "-",
        "-an",
        "-c:v",
        "qtrle",
        str(SUBTITLE_OVERLAY_VIDEO),
    ]
    process = subprocess.Popen(command, cwd=REPO_ROOT, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(total_frames):
            time_seconds = frame_index / FPS_FLOAT
            canvas = Image.new("RGBA", (PREVIEW_WIDTH, PREVIEW_HEIGHT), (0, 0, 0, 0))
            for chunk in chunks:
                animation = profile["speechSubtitle"]["animation"]
                if chunk.start <= time_seconds <= chunk.end + float(animation["out"]["durationSeconds"]):
                    speech.draw_caption_on_canvas(canvas, chunk, profile, time_seconds=time_seconds)
            process.stdin.write(canvas.tobytes())
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise subprocess.CalledProcessError(process.returncode, command)


def ensure_frame_overlay() -> tuple[dict[str, Any], int]:
    profile = frame_design.analyze_reference_image()
    write_json(frame_design.REFERENCE_ANALYSIS, profile)
    write_json(frame_design.DESIGN_PROFILE, profile)
    frame_design.render_frame_overlay(profile)
    return profile, frame_design.content_video_y_offset(profile)


def render_preview(ffmpeg: str, payload: dict[str, Any], video_y: int) -> None:
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, phrase in enumerate(payload["phrases"]):
        clip = phrase["editClip"]
        start = float(clip["sourceIn"])
        end = float(clip["sourceOut"])
        duration = end - start
        filters.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,scale={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:flags=bicubic,setsar=1[vsrc{index}]"
        )
        filters.append(f"color=c=black:s={PREVIEW_WIDTH}x{PREVIEW_HEIGHT}:r={FPS}:d={duration:.6f}[canvas{index}]")
        filters.append(f"[canvas{index}][vsrc{index}]overlay=0:{video_y}:format=auto[v{index}]")
        filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{index}]")
        concat_inputs.append(f"[v{index}][a{index}]")
    filters.append("".join(concat_inputs) + f"concat=n={len(payload['phrases'])}:v=1:a=1[basev][basea]")
    filters.append("[basev][1:v]overlay=0:0:format=auto[subv]")
    filters.append("[subv][2:v]overlay=0:0:format=auto[v]")

    PREVIEW_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(PROJECT_SAMPLE_VIDEO),
        "-i",
        str(SUBTITLE_OVERLAY_VIDEO),
        "-loop",
        "1",
        "-i",
        str(frame_design.FRAME_OVERLAY),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "[basea]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(PREVIEW_VIDEO),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def extract_still(ffmpeg: str) -> None:
    PREVIEW_STILL.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-hide_banner", "-y", "-ss", "5", "-i", str(PREVIEW_VIDEO), "-frames:v", "1", "-update", "1", str(PREVIEW_STILL)],
        cwd=REPO_ROOT,
        check=True,
    )


def write_timeline(payload: dict[str, Any], duration: float, video_y: int) -> None:
    clips: list[dict[str, Any]] = []
    for phrase in payload["phrases"]:
        clip = phrase["editClip"]
        clips.append(
            {
                "id": f"clip_{phrase['id']}",
                "trackId": "video.main",
                "kind": "video",
                "sourceId": "src_project_sample_video",
                "timelineStart": float(clip["timelineStart"]),
                "timelineEnd": float(clip["timelineEnd"]),
                "sourceIn": float(clip["sourceIn"]),
                "sourceOut": float(clip["sourceOut"]),
                "fit": {"mode": "cover", "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT},
                "style": {"yOffsetPx": video_y},
                "metadata": {"catchphraseId": phrase["id"], "displayText": phrase["displayText"]},
            }
        )
    clips.extend(
        [
            {
                "id": "clip_subtitle_overlay",
                "trackId": "subtitle.main",
                "kind": "generated",
                "sourceId": "src_subtitle_overlay",
                "timelineStart": 0.0,
                "timelineEnd": duration,
                "sourceIn": 0.0,
                "sourceOut": duration,
                "style": {"styleProfile": str(STYLE_PROFILE), "catchphraseJson": str(CATCHPHRASE_JSON)},
            },
            {
                "id": "clip_frame_overlay",
                "trackId": "graphics.frame",
                "kind": "generated",
                "sourceId": "src_frame_overlay",
                "timelineStart": 0.0,
                "timelineEnd": duration,
                "style": {"designProfile": str(frame_design.DESIGN_PROFILE), "referenceAnalysis": str(frame_design.REFERENCE_ANALYSIS)},
            },
        ]
    )
    timeline = {
        "schemaVersion": "video-edit-timeline/v1",
        "id": "timeline_test-project-1_sample1_catchphrase_collection_styled_preview",
        "createdAt": now_iso(),
        "project": {
            "id": "test-project-1",
            "name": "Test Project 1",
            "root": str(PROJECT_ROOT),
            "sourceRoot": str(PROJECT_ROOT / "source"),
            "outputRoot": str(OUTPUT_DIR),
        },
        "timebase": {"unit": "seconds", "fps": FPS},
        "duration": duration,
        "sources": [
            {"id": "src_project_sample_video", "kind": "video", "role": "master", "path": str(PROJECT_SAMPLE_VIDEO), "duration": 60.018292, "width": 1920, "height": 1080, "fps": FPS},
            {"id": "src_catchphrase_json", "kind": "data", "role": "catchphrase-selection", "path": str(CATCHPHRASE_JSON)},
            {"id": "src_style_profile", "kind": "data", "role": "speech-subtitle-style-profile", "path": str(STYLE_PROFILE)},
            {"id": "src_subtitle_overlay", "kind": "video", "role": "speech-subtitle-animated-overlay", "path": str(SUBTITLE_OVERLAY_VIDEO), "duration": duration, "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT, "fps": FPS, "codec": "qtrle"},
            {"id": "src_frame_overlay", "kind": "image", "role": "sample-11-frame-overlay", "path": str(frame_design.FRAME_OVERLAY)},
            {"id": "src_design_profile", "kind": "data", "role": "sample-11-frame-design-profile", "path": str(frame_design.DESIGN_PROFILE)},
        ],
        "tracks": [
            {"id": "video.main", "kind": "video", "label": "Project catchphrase hard cuts", "allowOverlap": False},
            {"id": "subtitle.main", "kind": "subtitle", "label": "Sample-1 speech subtitle style", "allowOverlap": True},
            {"id": "graphics.frame", "kind": "overlay", "label": "Sample-11 band and logo design", "allowOverlap": True},
            {"id": "audio.main", "kind": "audio", "label": "Project sample audio carried by cuts", "allowOverlap": False},
        ],
        "clips": clips,
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
            "preview": {"enabled": True, "rangeStart": 0.0, "rangeEnd": duration, "proxy": True},
        },
        "analysis": {
            "mediaManifestPath": str(PROJECT_ROOT / "output" / "reports" / "media_manifest.json"),
            "reports": [
                {"kind": "catchphrase-selection", "path": str(CATCHPHRASE_JSON), "exists": CATCHPHRASE_JSON.exists()},
                {"kind": "speech-subtitle-style-profile", "path": str(STYLE_PROFILE), "exists": STYLE_PROFILE.exists()},
                {"kind": "sample-11-frame-design-profile", "path": str(frame_design.DESIGN_PROFILE), "exists": frame_design.DESIGN_PROFILE.exists()},
                {"kind": "styled-preview-report", "path": str(REPORT_PATH), "exists": REPORT_PATH.exists()},
            ],
        },
        "audit": {
            "createdBy": "projects/test-project-1/scripts/build_sample1_catchphrase_collection_styled_preview.py",
            "inputs": [
                {"kind": "project-sample-video", "path": str(PROJECT_SAMPLE_VIDEO), "exists": PROJECT_SAMPLE_VIDEO.exists()},
                {"kind": "catchphrase-json", "path": str(CATCHPHRASE_JSON), "exists": CATCHPHRASE_JSON.exists()},
                {"kind": "reference-subtitle-analysis", "path": str(speech.REFERENCE_ANALYSIS), "exists": speech.REFERENCE_ANALYSIS.exists()},
                {"kind": "reference-frame-analysis", "path": str(frame_design.REFERENCE_ANALYSIS), "exists": frame_design.REFERENCE_ANALYSIS.exists()},
            ],
        },
    }
    write_json(TIMELINE_PATH, timeline)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a styled 15-second catchphrase collection preview.")
    parser.add_argument("--ffmpeg", default=r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    payload = load_payload()
    duration = float(payload["edit"]["targetDurationSeconds"])
    style_profile = speech.style_profile_from_reference(speech.REFERENCE_ANALYSIS)
    adapt_subtitle_profile_for_catchphrase(style_profile)
    style_profile["usage"] = {
        "target": "sample1 catchphrase collection styled preview",
        "subtitleTextSource": str(CATCHPHRASE_JSON),
        "designSource": str(frame_design.REFERENCE_ANALYSIS),
    }
    write_json(STYLE_PROFILE, style_profile)
    frame_profile, video_y = ensure_frame_overlay()
    captions = build_caption_items(payload)
    if not args.skip_render:
        render_subtitle_overlay(args.ffmpeg, captions, style_profile, duration)
        render_preview(args.ffmpeg, payload, video_y)
        extract_still(args.ffmpeg)
    write_timeline(payload, duration, video_y)
    report = {
        "createdAt": now_iso(),
        "catchphraseJson": str(CATCHPHRASE_JSON),
        "styleProfile": str(STYLE_PROFILE),
        "subtitleOverlayVideo": str(SUBTITLE_OVERLAY_VIDEO) if SUBTITLE_OVERLAY_VIDEO.exists() else "",
        "frameDesignProfile": str(frame_design.DESIGN_PROFILE),
        "frameOverlay": str(frame_design.FRAME_OVERLAY),
        "previewVideo": str(PREVIEW_VIDEO) if PREVIEW_VIDEO.exists() else "",
        "previewStill": str(PREVIEW_STILL) if PREVIEW_STILL.exists() else "",
        "timeline": str(TIMELINE_PATH),
        "duration": duration,
        "contentVideoYOffsetPx": video_y,
        "phrases": [{"id": item["id"], "displayText": item["displayText"], "editClip": item["editClip"]} for item in payload["phrases"]],
        "notes": [
            "Preview render only; production render waits for user approval.",
            "Project sample video is the only cut source; sample-1 asset video is used only as subtitle-style and hook-structure reference.",
            "Sample-11 band/logo design is composited above the animated speech subtitle overlay.",
        ],
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
