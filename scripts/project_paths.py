from __future__ import annotations

import os
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_SOURCE = ROOT / "source"
DEFAULT_OUTPUT = ROOT / "output"
PROJECTS = ROOT / "projects"
CONFIG = ROOT / "config"
DOCS = ROOT / "docs"
DEFAULT_APP_CONFIG = DEFAULT_OUTPUT / "app" / "video_edit_app_config.runtime.json"


def app_config() -> dict:
    path = Path(os.environ.get("VIDEO_EDIT_APP_CONFIG") or DEFAULT_APP_CONFIG)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


APP_CONFIG = app_config()


def configured_project_root() -> Path | None:
    explicit_root = os.environ.get("VIDEO_EDIT_PROJECT_ROOT")
    if explicit_root:
        return Path(explicit_root)
    project_id = os.environ.get("VIDEO_EDIT_PROJECT")
    if not project_id:
        return None
    project_path = Path(project_id.strip())
    if project_path.is_absolute() or any(part in {"", ".", ".."} for part in project_path.parts):
        raise ValueError("VIDEO_EDIT_PROJECT must be a project id, not an absolute or parent-relative path")
    return PROJECTS / project_path


ENV_PROJECT_ROOT = configured_project_root()


def configured_project_path(kind: str, default: Path) -> Path:
    env_name = {
        "sourceRoot": "VIDEO_EDIT_PROJECT_SOURCE",
        "outputRoot": "VIDEO_EDIT_PROJECT_OUTPUT",
    }.get(kind)
    if env_name and os.environ.get(env_name):
        return Path(os.environ[env_name])
    value = APP_CONFIG.get("project", {}).get(kind)
    if value:
        return Path(value)
    if ENV_PROJECT_ROOT:
        return ENV_PROJECT_ROOT / ("source" if kind == "sourceRoot" else "output")
    return default


SOURCE = configured_project_path("sourceRoot", DEFAULT_SOURCE)
OUTPUT = configured_project_path("outputRoot", DEFAULT_OUTPUT)

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


def configured_source_root() -> Path | None:
    value = APP_CONFIG.get("assets", {}).get("sourceRoot")
    return Path(value) if value else None


def multicam_source_root() -> Path:
    configured = os.environ.get("VIDEO_EDIT_SOURCE_ROOT")
    if configured:
        return Path(configured)
    configured_from_app = configured_source_root()
    if configured_from_app:
        return configured_from_app
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
