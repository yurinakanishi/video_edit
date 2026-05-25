from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SOURCE = ROOT / "source"
OUTPUT = ROOT / "output"
CONFIG = ROOT / "config"
DOCS = ROOT / "docs"

SOURCE_VIDEO = SOURCE / "video"
SOURCE_AUDIO = SOURCE / "audio"
SOURCE_IMAGES = SOURCE / "images"
SOURCE_SUBTITLES = SOURCE / "subtitles"
SOURCE_TEXT = SOURCE / "text"

OUTPUT_VIDEOS = OUTPUT / "videos"
OUTPUT_OVERLAYS = OUTPUT / "overlays"
OUTPUT_REPORTS = OUTPUT / "reports"
OUTPUT_TRANSCRIPTS = OUTPUT / "transcripts"
OUTPUT_AUDIO = OUTPUT / "audio"
OUTPUT_DIAGNOSTICS = OUTPUT / "diagnostics"

LEGACY_MULTICAM_SOURCE_ROOT = Path(r"C:\Users\yurin\Downloads\cdc260515 mov\cdc260515 mov")


def multicam_source_root() -> Path:
    configured = os.environ.get("VIDEO_EDIT_SOURCE_ROOT")
    if configured:
        return Path(configured)
    if (SOURCE_VIDEO / "2cam").exists() or (SOURCE_VIDEO / "3cam").exists():
        return SOURCE_VIDEO
    return LEGACY_MULTICAM_SOURCE_ROOT


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] in {"sound", "sound-2", "sond-low"}:
        return SOURCE_AUDIO / path
    if parts and parts[0] in {"1cam", "2cam", "3cam"}:
        return SOURCE_VIDEO / path
    if parts and parts[0] in {"subs", "subs_corrected"}:
        return SOURCE_SUBTITLES / path
    if parts and parts[0] == "subs_video_original_audio":
        return SOURCE_SUBTITLES / "video_original_audio" / Path(*parts[1:])
    if path.suffix.lower() in {".mp4", ".mov", ".m4v", ".avi", ".mkv"} and len(parts) == 1:
        return OUTPUT_VIDEOS / path
    return ROOT / path


def overlay_manifest_path(item_file: str) -> Path:
    path = Path(item_file)
    if path.is_absolute():
        return path
    return ROOT / path
