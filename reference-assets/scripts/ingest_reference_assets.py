from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover - dependency is expected in this repo
    Image = None


LIBRARY_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = LIBRARY_ROOT / "config" / "analysis_settings.json"
ASSET_LIBRARY_ROOT = LIBRARY_ROOT / "library"
OUTPUT_ROOT = LIBRARY_ROOT / "output"
REPORTS_ROOT = OUTPUT_ROOT / "reports"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def kind_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    return "other"


def bucket_for_kind(kind: str) -> str:
    return "video" if kind == "video" else "images" if kind == "image" else "other"


def parse_rate(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            denominator = float(right)
            return float(left) / denominator if denominator else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def ffprobe_metadata(path: Path, ffprobe: str) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return {}

    metadata: dict[str, Any] = {}
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    if fmt.get("duration") is not None:
        metadata["duration"] = round(float(fmt["duration"]), 6)
    for stream in payload.get("streams", []):
        if not isinstance(stream, dict):
            continue
        if stream.get("codec_type") == "video":
            metadata.update(
                {
                    "hasVideo": True,
                    "width": int(stream.get("width") or 0) or None,
                    "height": int(stream.get("height") or 0) or None,
                    "fps": parse_rate(stream.get("avg_frame_rate")),
                    "videoCodec": stream.get("codec_name"),
                }
            )
            if stream.get("duration") is not None and "duration" not in metadata:
                metadata["duration"] = round(float(stream["duration"]), 6)
        elif stream.get("codec_type") == "audio":
            metadata.update(
                {
                    "hasAudio": True,
                    "audioCodec": stream.get("codec_name"),
                    "sampleRate": int(stream.get("sample_rate") or 0) or None,
                    "channels": int(stream.get("channels") or 0) or None,
                }
            )
    metadata.setdefault("hasVideo", False)
    metadata.setdefault("hasAudio", False)
    return {key: value for key, value in metadata.items() if value is not None}


def image_metadata(path: Path) -> dict[str, Any]:
    if Image is None:
        return {"hasVideo": False, "hasAudio": False}
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        return {"hasVideo": False, "hasAudio": False}
    return {"width": width, "height": height, "hasVideo": False, "hasAudio": False}


def media_metadata(path: Path, kind: str, ffprobe: str) -> dict[str, Any]:
    if kind == "video":
        return ffprobe_metadata(path, ffprobe)
    if kind == "image":
        return image_metadata(path)
    return {}


def collect_source_files(settings: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    collections = settings.get("collections") if isinstance(settings.get("collections"), list) else []
    for collection in collections:
        name = str(collection.get("collection") or "").strip()
        directory = Path(str(collection.get("sourceDirectory") or ""))
        if not name or not directory.exists():
            continue
        for path in sorted(directory.rglob("*"), key=lambda item: str(item).lower()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                items.append({"collection": name, "path": path})
                if limit is not None and len(items) >= limit:
                    return items
    return items


def build_manifests(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    settings = load_json(args.settings)
    source_items = collect_source_files(settings, args.limit)
    now = utc_now()
    assets: list[dict[str, Any]] = []
    media_files: list[dict[str, Any]] = []

    for index, source_item in enumerate(source_items, start=1):
        original = Path(source_item["path"])
        collection = str(source_item["collection"])
        kind = kind_for_path(original)
        digest = sha256_file(original)
        asset_id = f"sample-{index}"
        asset_dir = ASSET_LIBRARY_ROOT / "collections" / collection / bucket_for_kind(kind) / asset_id
        target = asset_dir / f"{asset_id}{original.suffix.lower()}"
        analysis_path = asset_dir / "analysis.json"
        metadata = media_metadata(original, kind, args.ffprobe)
        relative_path = target.relative_to(ASSET_LIBRARY_ROOT)
        asset = {
            "assetId": asset_id,
            "mediaId": f"media-{index:03d}",
            "collection": collection,
            "kind": kind,
            "sourcePath": str(target),
            "originalPath": str(original),
            "analysisPath": str(analysis_path),
            "sha256": digest,
            "sizeBytes": original.stat().st_size,
            "relativePath": str(relative_path),
            "name": original.name,
            "extension": original.suffix.lower(),
            "metadata": metadata,
        }
        media_item = {
            "id": asset["mediaId"],
            "kind": kind,
            "role": "reference-video" if kind == "video" else "still",
            "label": f"{collection} {kind}",
            "path": str(target),
            "originalPath": str(original),
            "relativePath": str(relative_path),
            "name": target.name,
            "extension": target.suffix.lower(),
            "sizeBytes": asset["sizeBytes"],
            "confidence": 1.0,
            "reason": "reference asset copied into library collection bundle",
            "metadata": {**metadata, "storage": "copied", "sha256": digest, "assetId": asset_id, "collection": collection},
        }
        assets.append(asset)
        media_files.append(media_item)

    source_collections = [
        {
            "collection": str(item.get("collection") or ""),
            "sourceDirectory": str(Path(str(item.get("sourceDirectory") or ""))),
        }
        for item in settings.get("collections", [])
    ]
    media_manifest = {
        "version": 1,
        "sourceDirectory": str(ASSET_LIBRARY_ROOT),
        "sourcePaths": [item["sourceDirectory"] for item in source_collections],
        "sourceCollections": source_collections,
        "generatedAt": now,
        "manifestPath": str(REPORTS_ROOT / "media_manifest.json"),
        "files": media_files,
        "cameras": [],
        "audio": [],
        "images": [item for item in media_files if item["kind"] == "image"],
        "subtitles": [],
        "other": [],
        "selected": {},
    }
    reference_manifest = {
        "schemaVersion": "reference-assets-manifest/v1",
        "libraryId": "reference-assets",
        "generatedAt": now,
        "libraryRoot": str(ASSET_LIBRARY_ROOT),
        "sourceRoot": str(ASSET_LIBRARY_ROOT),
        "outputRoot": str(OUTPUT_ROOT),
        "mediaManifestPath": str(REPORTS_ROOT / "media_manifest.json"),
        "sourceCollections": source_collections,
        "assets": assets,
    }
    return media_manifest, reference_manifest, assets


def copy_assets(assets: list[dict[str, Any]], *, dry_run: bool, force: bool) -> None:
    for asset in assets:
        source = Path(asset["originalPath"])
        target = Path(asset["sourcePath"])
        if dry_run:
            print(json.dumps({"copy": str(source), "to": str(target), "assetId": asset["assetId"]}, ensure_ascii=False))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            try:
                if sha256_file(target) == asset["sha256"]:
                    continue
            except OSError:
                pass
        shutil.copy2(source, target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy configured reference assets into the reference-assets project.")
    parser.add_argument("--settings", type=Path, default=SETTINGS_PATH)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    media_manifest, reference_manifest, assets = build_manifests(args)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "libraryRoot": str(LIBRARY_ROOT),
                    "assetCount": len(assets),
                    "assets": [
                        {
                            "assetId": item["assetId"],
                            "collection": item["collection"],
                            "kind": item["kind"],
                            "originalPath": item["originalPath"],
                            "sourcePath": item["sourcePath"],
                            "analysisPath": item["analysisPath"],
                        }
                        for item in assets
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        copy_assets(assets, dry_run=True, force=args.force)
        return

    copy_assets(assets, dry_run=False, force=args.force)
    write_json(REPORTS_ROOT / "media_manifest.json", media_manifest)
    write_json(REPORTS_ROOT / "reference_assets_manifest.json", reference_manifest)
    print(json.dumps({"assetCount": len(assets), "manifest": str(REPORTS_ROOT / "reference_assets_manifest.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
