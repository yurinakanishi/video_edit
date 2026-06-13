from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import render_test_project1_style_preview as renderer


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
VIDEOS_DIR = PROJECT_DIR / "output" / "videos"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
REPORT_PATH = REPORTS_DIR / "render_segment_cache_audit.json"
SEGMENT_DIR = VIDEOS_DIR / "preview_test_project1_style_segments"

JST = timezone(timedelta(hours=9))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the LayerX segment render cache.")
    parser.add_argument("--no-write", action="store_true", help="Print the audit summary without updating the saved report JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = read_json(EDIT_PLAN_PATH)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    statuses: dict[str, int] = {}
    items = []

    for index, event in enumerate(events, start=1):
        segment_id = f"segment_{index:03d}_{event.get('event_id', 'event')}"
        segment_path = SEGMENT_DIR / f"{segment_id}.mp4"
        reusable, reason = renderer.segment_cache_status(segment_path, event)
        statuses[reason] = statuses.get(reason, 0) + 1
        item = {
            "index": index,
            "event_id": event.get("event_id"),
            "segment": str(segment_path),
            "manifest": str(renderer.segment_manifest_path(segment_path)),
            "reusable": reusable,
            "status": reason,
        }
        if segment_path.exists():
            item["segment_file"] = renderer.file_signature(segment_path)
        manifest_path = renderer.segment_manifest_path(segment_path)
        if manifest_path.exists():
            item["manifest_file"] = renderer.file_signature(manifest_path)
        items.append(item)

    orphan_manifests = []
    manifest_dir = renderer.cache_manifest_dir(SEGMENT_DIR)
    if manifest_dir.exists():
        expected = {Path(item["manifest"]) for item in items}
        for manifest_path in sorted(manifest_dir.glob("*.json")):
            if manifest_path not in expected:
                orphan_manifests.append(str(manifest_path))

    orphan_segments = []
    expected_segments = {Path(item["segment"]) for item in items}
    if SEGMENT_DIR.exists():
        for segment_path in sorted(SEGMENT_DIR.glob("*.mp4")):
            if segment_path not in expected_segments:
                orphan_segments.append(str(segment_path))

    report = {
        "schema_version": "render_segment_cache_audit.v1",
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "cache_version": renderer.RENDER_CACHE_VERSION,
        "edit_plan": str(EDIT_PLAN_PATH),
        "segment_dir": str(SEGMENT_DIR),
        "manifest_dir": str(manifest_dir),
        "event_count": len(events),
        "reusable_count": statuses.get("reusable", 0),
        "invalid_count": len(events) - statuses.get("reusable", 0),
        "status_counts": statuses,
        "orphan_segment_count": len(orphan_segments),
        "orphan_segments": orphan_segments,
        "orphan_manifest_count": len(orphan_manifests),
        "orphan_manifests": orphan_manifests,
        "ready_for_resume_reuse": statuses.get("reusable", 0) == len(events),
        "items": items,
    }
    if not args.no_write:
        write_json(REPORT_PATH, report)
    print(
        json.dumps(
            {
                "report": str(REPORT_PATH),
                "written": not args.no_write,
                "event_count": report["event_count"],
                "reusable_count": report["reusable_count"],
                "invalid_count": report["invalid_count"],
                "status_counts": report["status_counts"],
                "orphan_segment_count": report["orphan_segment_count"],
                "orphan_manifest_count": report["orphan_manifest_count"],
                "ready_for_resume_reuse": report["ready_for_resume_reuse"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
