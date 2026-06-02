from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PROJECTS = ROOT / "projects"
CONFIG = ROOT / "config"
DOCS = ROOT / "docs"


def app_config() -> dict:
    configured = os.environ.get("VIDEO_EDIT_APP_CONFIG")
    if not configured:
        project_root = os.environ.get("VIDEO_EDIT_PROJECT_ROOT")
        if not project_root:
            project_id = os.environ.get("VIDEO_EDIT_PROJECT")
            if project_id:
                project_path = Path(project_id.strip())
                if project_path.is_absolute() or any(part in {"", ".", ".."} for part in project_path.parts):
                    return {}
                project_root = str(PROJECTS / project_path)
        if not project_root:
            return {}
        path = Path(project_root) / "project_state.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    path = Path(configured)
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


def configured_project_path(kind: str) -> Path:
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
    raise RuntimeError(
        "Project context is required. Set VIDEO_EDIT_APP_CONFIG, VIDEO_EDIT_PROJECT, "
        "VIDEO_EDIT_PROJECT_ROOT, or VIDEO_EDIT_PROJECT_SOURCE/VIDEO_EDIT_PROJECT_OUTPUT."
    )


class ProjectContextPath(os.PathLike[str]):
    def __init__(self, kind: str, parts: tuple[str, ...] = ()) -> None:
        self.kind = kind
        self.parts = parts

    def _path(self) -> Path:
        return configured_project_path(self.kind).joinpath(*self.parts)

    def __fspath__(self) -> str:
        return os.fspath(self._path())

    def __str__(self) -> str:
        return str(self._path())

    def __repr__(self) -> str:
        return f"ProjectContextPath({self.kind!r}, {self.parts!r})"

    def __truediv__(self, value: str | Path) -> "ProjectContextPath":
        return self.joinpath(value)

    def joinpath(self, *values: str | Path) -> "ProjectContextPath":
        parts = list(self.parts)
        for value in values:
            parts.extend(str(part) for part in Path(value).parts)
        return ProjectContextPath(self.kind, tuple(parts))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._path(), name)


def configured_project_path_or_lazy(kind: str) -> Path | ProjectContextPath:
    try:
        return configured_project_path(kind)
    except RuntimeError:
        return ProjectContextPath(kind)


SOURCE = configured_project_path_or_lazy("sourceRoot")
OUTPUT = configured_project_path_or_lazy("outputRoot")

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
OUTPUT_IMAGES = OUTPUT / "images"
OUTPUT_DIAGNOSTICS = OUTPUT / "diagnostics"

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
    return SOURCE_VIDEO


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    parts = path.parts
    if parts and parts[0] == "audio":
        return SOURCE_AUDIO / path
    if parts and parts[0] == "video":
        return SOURCE_VIDEO / path
    if parts and parts[0] == "subtitles":
        return SOURCE_SUBTITLES / path
    if path.suffix.lower() in {".mp4", ".mov", ".m4v", ".avi", ".mkv"} and len(parts) == 1:
        return OUTPUT_VIDEOS / path
    return ROOT / path


def overlay_manifest_path(item_file: str) -> Path:
    path = Path(item_file)
    if path.is_absolute():
        return path
    return ROOT / path
