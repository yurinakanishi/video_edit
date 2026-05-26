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
