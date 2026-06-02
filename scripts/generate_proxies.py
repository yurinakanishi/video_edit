from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from video_edit_core.paths import OUTPUT
from video_edit_core.app_config import load_app_config, media_manifest, nested, optional_path


APP_CONFIG = load_app_config()
FFMPEG = optional_path(APP_CONFIG, "tools", "ffmpeg", default=Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"))
FFPROBE = optional_path(APP_CONFIG, "tools", "ffprobe", default=Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))
PROXY_PROFILE = "h264-960p-ultrafast-crf28"
CAMERA_ROLES = {"master", "camera2", "camera3", "camera4", "camera5", "camera6"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_signature(path: Path) -> str:
    stat = path.stat()
    payload = json.dumps(
        {
            "path": str(path.resolve()).lower(),
            "size": stat.st_size,
            "mtimeNs": stat.st_mtime_ns,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_stem(item: dict[str, Any], index: int) -> str:
    raw = str(item.get("id") or item.get("name") or Path(str(item.get("path") or "")).stem or f"video_{index:03d}")
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._") or f"video_{index:03d}"


def proxy_output_dir() -> Path:
    configured = nested(APP_CONFIG, "proxy", "outputDir", default="")
    if configured:
        return Path(str(configured))
    return OUTPUT / "proxy"


def manifest_path(payload: dict[str, Any]) -> Path:
    configured = nested(APP_CONFIG, "assets", "mediaManifestPath", default="")
    if configured:
        return Path(str(configured))
    existing = payload.get("manifestPath")
    if existing:
        return Path(str(existing))
    return OUTPUT / "reports" / "media_manifest.json"


def manifest_file_lists(payload: dict[str, Any]) -> list[list[dict[str, Any]]]:
    lists: list[list[dict[str, Any]]] = []
    for key in ("files", "items", "cameras", "audio", "images", "subtitles", "other"):
        value = payload.get(key)
        if isinstance(value, list):
            lists.append([item for item in value if isinstance(item, dict)])
    return lists


def video_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = payload.get("files")
    if not isinstance(files, list):
        files = payload.get("items")
    if not isinstance(files, list):
        return []
    items: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "video":
            continue
        if item.get("role") not in CAMERA_ROLES:
            continue
        metadata = item.get("metadata", {})
        if isinstance(metadata, dict) and metadata.get("hasVideo") is False:
            continue
        if item.get("path"):
            items.append(item)
    return items


def update_manifest_item(payload: dict[str, Any], source_item: dict[str, Any], proxy: dict[str, Any]) -> None:
    keys = {
        "id": str(source_item.get("id") or ""),
        "path": str(source_item.get("path") or ""),
        "role": str(source_item.get("role") or ""),
    }
    for items in manifest_file_lists(payload):
        for item in items:
            if keys["id"] and str(item.get("id") or "") == keys["id"]:
                item["proxy"] = proxy
            elif keys["path"] and str(item.get("path") or "") == keys["path"] and str(item.get("role") or "") == keys["role"]:
                item["proxy"] = proxy


def run_ffmpeg(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        "scale=960:-2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True)


def probe_metadata(path: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                str(FFPROBE),
                "-v",
                "error",
                "-show_entries",
                "format=duration,size",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return {}
    metadata: dict[str, Any] = {}
    fmt = payload.get("format", {}) if isinstance(payload, dict) else {}
    if isinstance(fmt, dict):
        for key in ("duration", "size"):
            try:
                metadata[key] = float(fmt[key]) if key == "duration" else int(fmt[key])
            except (KeyError, TypeError, ValueError):
                pass
    streams = payload.get("streams", []) if isinstance(payload, dict) else []
    if isinstance(streams, list):
        video = next((stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"), {})
        if isinstance(video, dict):
            for key in ("width", "height", "codec_name", "avg_frame_rate"):
                if key in video:
                    metadata[key] = video[key]
    return metadata


def main() -> None:
    payload = media_manifest(APP_CONFIG)
    if not isinstance(payload, dict) or not (payload.get("files") or payload.get("items")):
        raise SystemExit("No media manifest with video files was found.")

    out_dir = proxy_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = video_items(payload)
    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for index, item in enumerate(targets):
        source = Path(str(item.get("path") or ""))
        if not source.exists():
            errors.append({"id": item.get("id"), "path": str(source), "error": "source missing"})
            continue
        signature = source_signature(source)
        output = out_dir / f"{safe_stem(item, index)}_960p.mp4"
        existing_proxy = item.get("proxy") if isinstance(item.get("proxy"), dict) else {}
        existing_path = Path(str(existing_proxy.get("path") or output))
        if (
            existing_proxy.get("profile") == PROXY_PROFILE
            and existing_proxy.get("sourceSignature") == signature
            and existing_path.exists()
            and existing_path.stat().st_size > 0
        ):
            proxy = {
                **existing_proxy,
                "path": str(existing_path),
                "profile": PROXY_PROFILE,
                "sourceSignature": signature,
            }
            update_manifest_item(payload, item, proxy)
            skipped.append({"id": item.get("id"), "role": item.get("role"), "path": str(existing_path), "reason": "fresh"})
            continue

        try:
            run_ffmpeg(source, output)
            proxy = {
                "path": str(output),
                "profile": PROXY_PROFILE,
                "sourceSignature": signature,
                "generatedAt": utc_now(),
                "metadata": probe_metadata(output),
            }
            update_manifest_item(payload, item, proxy)
            generated.append({"id": item.get("id"), "role": item.get("role"), "source": str(source), "path": str(output)})
        except (OSError, subprocess.CalledProcessError) as error:
            errors.append({"id": item.get("id"), "role": item.get("role"), "source": str(source), "error": str(error)})

    target_path = manifest_path(payload)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload["manifestPath"] = str(target_path)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "manifestPath": str(target_path),
                "proxyDir": str(out_dir),
                "profile": PROXY_PROFILE,
                "generated": generated,
                "skipped": skipped,
                "errors": errors,
                "count": {"targets": len(targets), "generated": len(generated), "skipped": len(skipped), "errors": len(errors)},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors and not generated and not skipped:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
