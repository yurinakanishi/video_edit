from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
REFERENCE_VIDEO = REPO_ROOT / "reference-assets" / "library" / "collections" / "layer-x" / "video" / "sample-1" / "sample-1.mp4"
REFERENCE_ANALYSIS = REPO_ROOT / "reference-assets" / "library" / "collections" / "layer-x" / "video" / "sample-1" / "analysis.json"
PROJECT_SAMPLE_VIDEO = PROJECT_ROOT / "source" / "video" / "Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4"
PROJECT_TRANSCRIPT_SRT = PROJECT_ROOT / "output" / "transcripts" / "manifest_sources" / "primary_corrected.srt"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_SUBTITLES = OUTPUT_DIR / "subtitles"
OUTPUT_VIDEOS = OUTPUT_DIR / "videos"
OUTPUT_IMAGES = OUTPUT_DIR / "images"
OUTPUT_REPORTS = OUTPUT_DIR / "reports"
OUTPUT_TIMELINES = OUTPUT_DIR / "timelines"
CATCHPHRASE_JSON = OUTPUT_SUBTITLES / "sample1_catchphrase_collection.json"
PREVIEW_VIDEO = OUTPUT_VIDEOS / "preview_sample1_catchphrase_collection.mp4"
PREVIEW_STILL = OUTPUT_IMAGES / "preview_sample1_catchphrase_collection_t0005.jpg"
TIMELINE_PATH = OUTPUT_TIMELINES / "sample1_catchphrase_collection_preview.timeline.json"
REPORT_PATH = OUTPUT_REPORTS / "sample1_catchphrase_collection_preview_report.json"

PREVIEW_WIDTH = 1280
PREVIEW_HEIGHT = 720
FPS = "24000/1001"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_reference_subtitle_frames() -> list[dict[str, Any]]:
    data = json.loads(REFERENCE_ANALYSIS.read_text(encoding="utf-8"))
    frames: list[dict[str, Any]] = []
    for frame in data.get("frames", []):
        time_seconds = float(frame.get("timeSeconds", 0.0))
        if time_seconds > 10.0:
            continue
        subtitles = [
            str(item.get("text") or "")
            for item in frame.get("textOverlays", [])
            if isinstance(item, dict) and item.get("role") == "subtitle"
        ]
        if subtitles:
            frames.append({"timeSeconds": time_seconds, "subtitles": subtitles})
    return frames


def parse_srt_time(value: str) -> float:
    hours, minutes, seconds = value.strip().split(":")
    sec, millis = seconds.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(sec) + int(millis) / 1000


def load_project_transcript_segments() -> list[dict[str, Any]]:
    if not PROJECT_TRANSCRIPT_SRT.exists():
        return []
    blocks = PROJECT_TRANSCRIPT_SRT.read_text(encoding="utf-8").replace("\r\n", "\n").strip().split("\n\n")
    segments: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_text, end_text = [part.strip() for part in lines[1].split("-->", 1)]
        segments.append(
            {
                "index": lines[0],
                "start": parse_srt_time(start_text),
                "end": parse_srt_time(end_text),
                "text": " ".join(lines[2:]),
            }
        )
    return segments


def build_catchphrase_payload() -> dict[str, Any]:
    observed_reference = load_reference_subtitle_frames()
    project_transcript = load_project_transcript_segments()
    reference_hooks = [
        {
            "id": "reference_hook_01",
            "displayText": "元Palantir社員が語る / FDEの正体とは?",
            "normalizedLines": ["元Palantir社員が語る", "FDEの正体とは?"],
            "sourceTimeRange": {"start": 0.0, "end": 3.4},
            "selectionReason": "Opening hook that states the speaker credibility and the core topic.",
        },
        {
            "id": "reference_hook_02",
            "displayText": "コンサルティングやSIerとは / 性質が異なる",
            "sourceTextRaw": ["コンサルティングやSlerとは", "性質が異なる"],
            "normalizedLines": ["コンサルティングやSIerとは", "性質が異なる"],
            "sourceTimeRange": {"start": 3.5, "end": 6.8},
            "selectionReason": "Clear contrast phrase that defines what FDE is not.",
        },
        {
            "id": "reference_hook_03",
            "displayText": "基本はプロジェクトを / 進行していく仕事",
            "normalizedLines": ["基本はプロジェクトを", "進行していく仕事"],
            "sourceTimeRange": {"start": 7.0, "end": 10.0},
            "selectionReason": "Concise explanatory phrase that turns the topic into a concrete job description.",
        },
    ]
    phrases = [
        {
            "id": "project_catchphrase_01",
            "displayText": "An eye-opening experience",
            "normalizedLines": ["An eye-opening experience"],
            "sourceTimeRange": {"start": 0.0, "end": 2.5},
            "editClip": {"sourceIn": 0.0, "sourceOut": 5.0, "timelineStart": 0.0, "timelineEnd": 5.0},
            "selectionReason": "A compact opening hook from the project sample that mirrors the reference asset's first strong topic-setting phrase.",
        },
        {
            "id": "project_catchphrase_02",
            "displayText": "Something that would have negative consequences",
            "normalizedLines": ["Something that would have negative consequences"],
            "sourceTimeRange": {"start": 7.34, "end": 12.32},
            "editClip": {"sourceIn": 7.34, "sourceOut": 12.34, "timelineStart": 5.0, "timelineEnd": 10.0},
            "selectionReason": "A clear consequence phrase from the project sample, matching the reference pattern of a short explanatory contrast.",
        },
        {
            "id": "project_catchphrase_03",
            "displayText": "But now it was completely obvious",
            "normalizedLines": ["But now it was completely obvious"],
            "sourceTimeRange": {"start": 20.32, "end": 23.88},
            "editClip": {"sourceIn": 20.32, "sourceOut": 25.32, "timelineStart": 10.0, "timelineEnd": 15.0},
            "selectionReason": "A concise realization phrase from the project sample, selected as the closing hook for the 15-second collection.",
        },
    ]
    return {
        "schemaVersion": "sample1-catchphrase-collection/v1",
        "createdAt": now_iso(),
        "referenceSource": {
            "video": str(REFERENCE_VIDEO),
            "analysis": str(REFERENCE_ANALYSIS),
            "sourceWindowSeconds": [0.0, 10.0],
            "usage": "Reference only. The asset video is used to infer catchphrase structure, not as the cut-edit source.",
        },
        "observedReferenceSubtitleFrames": observed_reference,
        "referenceHookPatterns": reference_hooks,
        "projectSource": {
            "video": str(PROJECT_SAMPLE_VIDEO),
            "transcript": str(PROJECT_TRANSCRIPT_SRT),
            "usage": "Actual source for the 15-second hard-cut preview.",
        },
        "projectTranscriptSegments": project_transcript,
        "phrases": phrases,
        "edit": {
            "targetDurationSeconds": 15.0,
            "method": "hard-cut concat of three 5-second clips from the project sample video",
            "videoSize": [PREVIEW_WIDTH, PREVIEW_HEIGHT],
            "fps": FPS,
        },
    }


def render_preview(ffmpeg: str) -> None:
    payload = json.loads(CATCHPHRASE_JSON.read_text(encoding="utf-8"))
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, phrase in enumerate(payload["phrases"]):
        clip = phrase["editClip"]
        start = float(clip["sourceIn"])
        end = float(clip["sourceOut"])
        filters.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,scale={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:flags=bicubic,setsar=1[v{index}]"
        )
        filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{index}]")
        concat_inputs.append(f"[v{index}][a{index}]")
    filters.append("".join(concat_inputs) + f"concat=n={len(payload['phrases'])}:v=1:a=1[v][a]")
    PREVIEW_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(PROJECT_SAMPLE_VIDEO),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "[a]",
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
        "-movflags",
        "+faststart",
        str(PREVIEW_VIDEO),
    ]
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def extract_still(ffmpeg: str) -> None:
    PREVIEW_STILL.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-y", "-ss", "5", "-i", str(PREVIEW_VIDEO), "-frames:v", "1", "-update", "1", str(PREVIEW_STILL)], cwd=REPO_ROOT, check=True)


def write_timeline(payload: dict[str, Any]) -> None:
    duration = float(payload["edit"]["targetDurationSeconds"])
    clips = []
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
                "fit": {"mode": "contain", "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT},
                "metadata": {"catchphraseId": phrase["id"], "displayText": phrase["displayText"]},
            }
        )
    timeline = {
        "schemaVersion": "video-edit-timeline/v1",
        "id": "timeline_test-project-1_sample1_catchphrase_collection_preview",
        "createdAt": now_iso(),
        "project": {"id": "test-project-1", "name": "Test Project 1", "root": str(PROJECT_ROOT), "sourceRoot": str(PROJECT_ROOT / "source"), "outputRoot": str(OUTPUT_DIR)},
        "timebase": {"unit": "seconds", "fps": FPS},
        "duration": duration,
        "sources": [
            {"id": "src_project_sample_video", "kind": "video", "role": "master", "path": str(PROJECT_SAMPLE_VIDEO), "duration": 60.018292, "width": 1920, "height": 1080, "fps": 23.976023976023978},
            {"id": "src_reference_video", "kind": "video", "role": "reference-only", "path": str(REFERENCE_VIDEO), "duration": 61.332938, "width": 1834, "height": 1030, "fps": 30.0},
            {"id": "src_catchphrase_json", "kind": "data", "role": "catchphrase-selection", "path": str(CATCHPHRASE_JSON)},
        ],
        "tracks": [
            {"id": "video.main", "kind": "video", "label": "Catchphrase hard cuts", "allowOverlap": False},
            {"id": "audio.main", "kind": "audio", "label": "Reference audio carried by cuts", "allowOverlap": False},
        ],
        "clips": clips,
        "transitions": [],
        "render": {"targets": [{"id": "preview", "path": str(PREVIEW_VIDEO), "format": "mp4", "width": PREVIEW_WIDTH, "height": PREVIEW_HEIGHT, "fps": FPS, "profile": "preview"}]},
        "analysis": {
            "mediaManifestPath": str(REPO_ROOT / "reference-assets" / "output" / "reports" / "media_manifest.json"),
            "reports": [
                {"kind": "reference-analysis", "path": str(REFERENCE_ANALYSIS), "exists": REFERENCE_ANALYSIS.exists()},
                {"kind": "project-transcript", "path": str(PROJECT_TRANSCRIPT_SRT), "exists": PROJECT_TRANSCRIPT_SRT.exists()},
                {"kind": "catchphrase-selection", "path": str(CATCHPHRASE_JSON), "exists": CATCHPHRASE_JSON.exists()},
                {"kind": "catchphrase-report", "path": str(REPORT_PATH), "exists": REPORT_PATH.exists()},
            ],
        },
        "audit": {
            "createdBy": "projects/test-project-1/scripts/build_sample1_catchphrase_collection_preview.py",
            "inputs": [
                {"kind": "project-sample-video", "path": str(PROJECT_SAMPLE_VIDEO), "exists": PROJECT_SAMPLE_VIDEO.exists()},
                {"kind": "project-transcript", "path": str(PROJECT_TRANSCRIPT_SRT), "exists": PROJECT_TRANSCRIPT_SRT.exists()},
                {"kind": "reference-video", "path": str(REFERENCE_VIDEO), "exists": REFERENCE_VIDEO.exists()},
                {"kind": "reference-analysis", "path": str(REFERENCE_ANALYSIS), "exists": REFERENCE_ANALYSIS.exists()},
            ],
        },
    }
    write_json(TIMELINE_PATH, timeline)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a 15-second sample-1 catchphrase collection preview.")
    parser.add_argument("--ffmpeg", default=r"C:\ProgramData\chocolatey\bin\ffmpeg.exe")
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    payload = build_catchphrase_payload()
    write_json(CATCHPHRASE_JSON, payload)
    write_timeline(payload)
    if not args.skip_render:
        render_preview(args.ffmpeg)
        extract_still(args.ffmpeg)
    report = {
        "createdAt": now_iso(),
        "catchphraseJson": str(CATCHPHRASE_JSON),
        "previewVideo": str(PREVIEW_VIDEO) if PREVIEW_VIDEO.exists() else "",
        "previewStill": str(PREVIEW_STILL) if PREVIEW_STILL.exists() else "",
        "timeline": str(TIMELINE_PATH),
        "phraseCount": len(payload["phrases"]),
        "targetDurationSeconds": payload["edit"]["targetDurationSeconds"],
        "phrases": [{"id": item["id"], "displayText": item["displayText"], "editClip": item["editClip"]} for item in payload["phrases"]],
        "notes": ["Preview render only; production render waits for user approval."],
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
