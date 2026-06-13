from __future__ import annotations

import json
import hashlib
import os
import re
from pathlib import Path

from video_edit_core.paths import (
    APP_CONFIG as PROJECT_PATHS_APP_CONFIG,
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


def load_app_config() -> dict[str, Any]:
    path = os.environ.get("VIDEO_EDIT_APP_CONFIG")
    if not path:
        return PROJECT_PATHS_APP_CONFIG if isinstance(PROJECT_PATHS_APP_CONFIG, dict) else {}
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


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_item_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("id") or ""),
        str(item.get("role") or ""),
        str(item.get("path") or ""),
    )


def _merge_manifest_proxy_metadata(inline_manifest: dict[str, Any], file_manifest: dict[str, Any]) -> dict[str, Any]:
    inline_files = inline_manifest.get("files")
    file_files = file_manifest.get("files")
    if not isinstance(inline_files, list) or not isinstance(file_files, list):
        return inline_manifest

    proxy_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in file_files:
        if not isinstance(item, dict) or not isinstance(item.get("proxy"), dict):
            continue
        proxy_by_key[_manifest_item_key(item)] = item["proxy"]

    if not proxy_by_key:
        return inline_manifest

    merged = dict(inline_manifest)
    merged_files: list[Any] = []
    for item in inline_files:
        if not isinstance(item, dict):
            merged_files.append(item)
            continue
        item_id = str(item.get("id") or "")
        item_role = str(item.get("role") or "")
        item_path = str(item.get("path") or "")
        proxy = proxy_by_key.get(_manifest_item_key(item))
        if proxy is None:
            for key, candidate in proxy_by_key.items():
                same_id = bool(key[0] and key[0] == item_id)
                same_role_path = key[1] == item_role and key[2] == item_path
                if same_id or same_role_path:
                    proxy = candidate
                    break
        merged_item = dict(item)
        if proxy is not None:
            merged_item["proxy"] = proxy
        merged_files.append(merged_item)
    merged["files"] = merged_files
    return merged


SUBTITLE_EXTENSIONS = {".srt", ".ass", ".vtt"}
TRANSCRIBE_CAMERA_ROLES = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}


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


def media_manifest(config: dict[str, Any] | None = None) -> dict[str, Any]:
    app_config = config if isinstance(config, dict) else load_app_config()
    manifest = nested(app_config, "assets", "mediaManifest", default={})
    manifest_path = nested(app_config, "assets", "mediaManifestPath", default="")
    file_manifest: dict[str, Any] = {}
    if manifest_path:
        path = Path(str(manifest_path))
        if path.exists():
            file_manifest = _load_json_object(path)
    if isinstance(manifest, dict) and manifest.get("files"):
        return _merge_manifest_proxy_metadata(manifest, file_manifest) if file_manifest else manifest
    if file_manifest:
        return file_manifest
    return {}


def transcript_manifest_fingerprint(config: dict[str, Any] | None = None) -> str:
    manifest = media_manifest(config)
    files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        return ""
    entries: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        role = str(item.get("role") or "")
        if kind == "audio" and role.startswith("external"):
            pass
        elif kind == "video" and role in TRANSCRIBE_CAMERA_ROLES and item.get("metadata", {}).get("hasAudio", True) is not False:
            pass
        else:
            continue
        path = Path(str(item.get("path") or ""))
        if not path.exists():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(
            {
                "kind": kind,
                "role": role,
                "path": str(path.resolve()).lower(),
                "size": stat.st_size,
                "mtimeMs": round(stat.st_mtime * 1000),
            }
        )
    if not entries:
        return ""
    payload = json.dumps(
        sorted(entries, key=lambda item: (item["kind"], item["role"], item["path"])),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def transcript_report(config: dict[str, Any] | None = None) -> dict[str, Any]:
    app_config = config if isinstance(config, dict) else load_app_config()
    report_path = OUTPUT_TRANSCRIPTS / "manifest_sources" / "manifest_transcripts.json"
    if not report_path.exists():
        return {}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(report, dict):
        return {}
    expected = transcript_manifest_fingerprint(app_config)
    if not expected or report.get("manifestFingerprint") != expected:
        return {}
    return report if isinstance(report, dict) else {}


def subtitle_candidates(
    config: dict[str, Any] | None = None,
    *,
    extensions: tuple[str, ...] | list[str] | set[str] | None = None,
) -> list[Path]:
    app_config = config if isinstance(config, dict) else load_app_config()
    allowed_extensions = _normalize_extensions(extensions)
    paths: list[Path] = []
    seen: set[str] = set()

    for key_path in (
        ("render", "subtitlePath"),
        ("subtitles", "path"),
    ):
        _append_unique(paths, seen, _existing_subtitle_path(nested(app_config, *key_path), allowed_extensions))

    report = transcript_report(app_config)
    _append_unique(paths, seen, _existing_subtitle_path(report.get("primarySrt"), allowed_extensions))
    transcripts = report.get("transcripts", [])
    if isinstance(transcripts, list):
        for item in transcripts:
            if isinstance(item, dict):
                _append_unique(paths, seen, _existing_subtitle_path(item.get("srt"), allowed_extensions))

    return paths


def selected_subtitle_path(
    config: dict[str, Any] | None = None,
    *,
    extensions: tuple[str, ...] | list[str] | set[str] | None = None,
) -> Path | None:
    candidates = subtitle_candidates(config, extensions=extensions)
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


VIDEO_ENCODER_PRESETS = {
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
}


def video_encoder_preset(config: dict[str, Any], *keys: str, default: str = "veryfast") -> str:
    fallback = str(default or "veryfast").strip().lower()
    if fallback not in VIDEO_ENCODER_PRESETS:
        fallback = "veryfast"
    value = str(nested(config, *keys, default=fallback) or fallback).strip().lower()
    return value if value in VIDEO_ENCODER_PRESETS else fallback


def video_encoder_crf(
    config: dict[str, Any],
    *keys: str,
    default: int = 18,
    minimum: int = 0,
    maximum: int = 51,
) -> int:
    return max(minimum, min(maximum, int_value(config, *keys, default=default)))


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
