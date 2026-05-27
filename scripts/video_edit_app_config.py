from __future__ import annotations

import json
import os
import re
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
from typing import Any


WORK = WORKSPACE_ROOT
DEFAULT_APP_CONFIG = WORK / "output" / "app" / "video_edit_app_config.runtime.json"


def load_app_config() -> dict[str, Any]:
    path = os.environ.get("VIDEO_EDIT_APP_CONFIG") or DEFAULT_APP_CONFIG
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = config
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


SUBTITLE_EXTENSIONS = {".srt", ".ass", ".vtt"}


def _normalize_extensions(extensions: tuple[str, ...] | list[str] | set[str] | None) -> set[str]:
    if not extensions:
        return SUBTITLE_EXTENSIONS
    return {item.lower() if item.startswith(".") else f".{item.lower()}" for item in extensions}


def _existing_subtitle_path(value: Any, extensions: set[str]) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    if path.suffix.lower() not in extensions:
        return None
    try:
        if path.exists() and path.is_file():
            return path
    except OSError:
        return None
    return None


def _append_unique(paths: list[Path], seen: set[str], path: Path | None) -> None:
    if path is None:
        return
    key = str(path.resolve()).lower()
    if key in seen:
        return
    seen.add(key)
    paths.append(path)


def subtitle_candidates(
    config: dict[str, Any] | None = None,
    *,
    extensions: tuple[str, ...] | list[str] | set[str] | None = None,
    include_legacy: bool = False,
) -> list[Path]:
    app_config = config if isinstance(config, dict) else load_app_config()
    allowed_extensions = _normalize_extensions(extensions)
    paths: list[Path] = []
    seen: set[str] = set()

    manifest = nested(app_config, "assets", "mediaManifest", default={})
    manifest_items = []
    if isinstance(manifest, dict):
        for key in ("subtitles", "files"):
            items = manifest.get(key)
            if isinstance(items, list):
                manifest_items.extend(items)
    for item in manifest_items:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "subtitle" or item.get("role") == "ignore":
            continue
        _append_unique(paths, seen, _existing_subtitle_path(item.get("path"), allowed_extensions))

    transcript_root = OUTPUT_TRANSCRIPTS / "manifest_sources"
    for candidate in (transcript_root / "primary.srt", transcript_root / "master.srt"):
        _append_unique(paths, seen, _existing_subtitle_path(candidate, allowed_extensions))

    for root in (transcript_root, OUTPUT_TRANSCRIPTS):
        try:
            if root.exists():
                for candidate in sorted(root.rglob("*")):
                    _append_unique(paths, seen, _existing_subtitle_path(candidate, allowed_extensions))
        except OSError:
            continue

    if include_legacy:
        legacy_root = SOURCE_SUBTITLES / "video_original_audio"
        for candidate in (
            legacy_root / "ST7_7550_overlap_5min_original_audio_corrected.srt",
            legacy_root / "ST7_7550_overlap_5min_original_audio.srt",
        ):
            _append_unique(paths, seen, _existing_subtitle_path(candidate, allowed_extensions))

    return paths


def selected_subtitle_path(
    config: dict[str, Any] | None = None,
    *,
    extensions: tuple[str, ...] | list[str] | set[str] | None = None,
    include_legacy: bool = False,
) -> Path | None:
    candidates = subtitle_candidates(config, extensions=extensions, include_legacy=include_legacy)
    return candidates[0] if candidates else None


def optional_path(config: dict[str, Any], *keys: str, default: Path) -> Path:
    value = nested(config, *keys)
    if not value:
        return default
    return Path(value)


def int_value(config: dict[str, Any], *keys: str, default: int) -> int:
    value = nested(config, *keys, default=default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(config: dict[str, Any], *keys: str, default: float) -> float:
    value = nested(config, *keys, default=default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def hex_rgba(value: Any, alpha: int = 255, default: tuple[int, int, int, int] = (255, 255, 255, 255)) -> tuple[int, int, int, int]:
    if not isinstance(value, str):
        return default
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return default
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), alpha)
    except ValueError:
        return default


def opacity_alpha(percent: Any, default: int) -> int:
    try:
        return max(0, min(255, round(float(percent) / 100 * 255)))
    except (TypeError, ValueError):
        return default


def timestamp_to_full(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        minutes, seconds = text.split(":")
        return f"0:{int(minutes):02d}:{int(seconds):02d}.00"
    if re.fullmatch(r"\d{1,2}:\d{2}\.\d+", text):
        minutes, seconds = text.split(":")
        return f"0:{int(minutes):02d}:{seconds}"
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}(?:\.\d+)?", text):
        hours, minutes, seconds = text.split(":")
        if "." not in seconds:
            seconds = f"{seconds}.00"
        return f"{int(hours)}:{int(minutes):02d}:{seconds}"
    return text


def parse_punchline_text(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in text.splitlines():
        line = row.strip()
        if not line:
            continue
        match = re.match(r"^(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s*[-–]\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s+(.+)$", line)
        if not match:
            continue
        start, end, body = match.groups()
        lines = tuple(part.strip() for part in body.split("/") if part.strip())
        if not lines:
            continue
        items.append({"start": timestamp_to_full(start), "end": timestamp_to_full(end), "lines": lines})
    return items
