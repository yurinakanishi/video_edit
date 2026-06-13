from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "render-segment-cache/v1"


def stable_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(payload: Any) -> str:
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def file_signature(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def ms(value: float) -> int:
    return int(round(value * 1000))


def segment_ranges(start: float, end: float, segment_duration: float) -> list[dict[str, Any]]:
    duration = max(0.1, float(segment_duration))
    ranges: list[dict[str, Any]] = []
    cursor = float(start)
    index = 1
    while cursor < end - 0.001:
        segment_end = min(float(end), cursor + duration)
        ranges.append(
            {
                "id": f"segment_{index:03d}_{ms(cursor):08d}_{ms(segment_end):08d}",
                "index": index,
                "start": round(cursor, 6),
                "end": round(segment_end, 6),
                "duration": round(segment_end - cursor, 6),
            }
        )
        cursor = segment_end
        index += 1
    return ranges


@dataclass(frozen=True)
class CacheStatus:
    reusable: bool
    reason: str


class SegmentCache:
    def __init__(self, segment_dir: Path, *, cache_version: str) -> None:
        self.segment_dir = segment_dir
        self.cache_version = cache_version
        self.manifest_dir = segment_dir / "_manifests"

    def segment_path(self, segment_id: str, suffix: str) -> Path:
        return self.segment_dir / f"{segment_id}{suffix}"

    def manifest_path(self, segment_id: str) -> Path:
        return self.manifest_dir / f"{segment_id}.json"

    def status(self, segment_id: str, segment_path: Path, payload: Any) -> CacheStatus:
        if not segment_path.exists() or segment_path.stat().st_size <= 0:
            return CacheStatus(False, "missing_or_empty_segment")
        manifest_path = self.manifest_path(segment_id)
        if not manifest_path.exists():
            return CacheStatus(False, "missing_manifest")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return CacheStatus(False, "unreadable_manifest")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            return CacheStatus(False, "schema_version_changed")
        if manifest.get("cache_version") != self.cache_version:
            return CacheStatus(False, "cache_version_changed")
        if manifest.get("fingerprint") != fingerprint(payload):
            return CacheStatus(False, "fingerprint_mismatch")
        return CacheStatus(True, "reusable")

    def write_manifest(self, segment_id: str, segment_path: Path, payload: Any, metadata: dict[str, Any] | None = None) -> None:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "cache_version": self.cache_version,
            "segment_id": segment_id,
            "fingerprint": fingerprint(payload),
            "payload": payload,
            "segment": file_signature(segment_path),
        }
        if metadata:
            manifest["metadata"] = metadata
        self.manifest_path(segment_id).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def remove(self, segment_id: str, segment_path: Path) -> None:
        for path in (segment_path, self.manifest_path(segment_id)):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass


def write_concat_list(path: Path, segments: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for segment in segments:
        escaped = segment.as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

