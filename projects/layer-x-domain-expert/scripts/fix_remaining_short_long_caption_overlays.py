from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "scripts"
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT_JSON = REPORTS / "remaining_short_long_caption_fix_report.json"
REPORT_MD = REPORTS / "remaining_short_long_caption_fix_report.md"
JST = timezone(timedelta(hours=9))

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import polish_long_caption_speech_unit_splits as polish  # noqa: E402


REPLACE_UNITS = {
    "main_caption_022": [
        {"start": 1368.920, "end": 1373.800, "text": "実務のモヤモヤを\n言える", "speaker_person_id": "person_03"},
        {"start": 1373.800, "end": 1377.920, "text": "プロダクトに\n落とし込める", "speaker_person_id": "person_03"},
    ],
    "main_caption_046": [
        {"start": 1803.760, "end": 1807.900, "text": "コア以外は\n落とす", "speaker_person_id": "person_02"},
        {"start": 1807.900, "end": 1811.940, "text": "判断も必要", "speaker_person_id": "person_02"},
    ],
    "main_caption_049": [
        {"start": 1903.860, "end": 1907.860, "text": "いらないものを\nちゃんと言うことも価値", "speaker_person_id": "person_02"},
        {"start": 1907.860, "end": 1912.200, "text": "必要に見えるものを\n足しすぎる", "speaker_person_id": "person_02"},
        {"start": 1912.200, "end": 1916.360, "text": "ドメイン知識があるから\n迷いが出る", "speaker_person_id": "person_02"},
        {"start": 1916.360, "end": 1922.100, "text": "なくていいと\n止められることが価値", "speaker_person_id": "person_02"},
    ],
    "main_caption_auto_016": [
        {"start": 2203.740, "end": 2212.000, "text": "AIが普及していくのは\n間違いない", "speaker_person_id": "person_02"},
        {"start": 2212.000, "end": 2217.000, "text": "AIから逃げない姿勢が", "speaker_person_id": "person_02"},
        {"start": 2217.000, "end": 2222.740, "text": "キャリアを築く上で\n必要", "speaker_person_id": "person_02"},
    ],
    "main_caption_080": [
        {"start": 2465.200, "end": 2469.200, "text": "作業量を減らし", "speaker_person_id": "person_03"},
        {"start": 2469.200, "end": 2473.700, "text": "確認時間を\n短縮する", "speaker_person_id": "person_03"},
        {"start": 2473.700, "end": 2478.000, "text": "やりたいことを", "speaker_person_id": "person_03"},
        {"start": 2478.000, "end": 2482.200, "text": "一つの機能に\n込める", "speaker_person_id": "person_03"},
    ],
    "main_caption_auto_041": [
        {"start": 2514.200, "end": 2518.600, "text": "開発に関わる", "speaker_person_id": "person_03"},
        {"start": 2518.600, "end": 2523.200, "text": "やりがいがある", "speaker_person_id": "person_03"},
    ],
    "main_caption_strong_010": [
        {"start": 2853.680, "end": 2858.000, "text": "経理は効率化が", "speaker_person_id": "person_03"},
        {"start": 2858.000, "end": 2862.440, "text": "早く進みやすい", "speaker_person_id": "person_03"},
    ],
    "main_caption_090": [
        {"start": 2888.680, "end": 2893.000, "text": "人や現場に\n向き合う時間が", "speaker_person_id": "person_03"},
        {"start": 2893.000, "end": 2897.280, "text": "増えていく", "speaker_person_id": "person_03"},
    ],
}

REMOVE_ONLY_ROOTS = {
    # Duplicate of main_caption_049 after speech-unit splitting.
    "main_caption_strong_002",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    roots = set(REPLACE_UNITS) | REMOVE_ONLY_ROOTS
    base_by_root = {root: polish.base_style_for_root(events, root) for root in roots}
    removed = polish.remove_existing(events, roots)
    repairs = []
    for root in sorted(REPLACE_UNITS):
        added = polish.add_units(events, root, base_by_root[root], REPLACE_UNITS[root])
        repairs.append(
            {
                "root_caption_id": root,
                "new_unit_count": len(REPLACE_UNITS[root]),
                "new_units": [
                    {
                        "source_window_sec": [unit["start"], unit["end"]],
                        "duration_sec": round(float(unit["end"]) - float(unit["start"]), 3),
                        "text": unit["text"],
                        "speaker_person_id": unit.get("speaker_person_id"),
                    }
                    for unit in REPLACE_UNITS[root]
                ],
                "added_overlays": added,
            }
        )

    for event in events:
        overlays = event.get("overlays")
        if isinstance(overlays, list):
            overlays.sort(key=lambda overlay: (float(overlay.get("start") or 0.0), str(overlay.get("type") or ""), str(overlay.get("caption_id") or "")) if isinstance(overlay, dict) else (0.0, "", ""))
        items = event.get("main_caption_plan_items")
        if isinstance(items, list):
            items.sort(key=lambda item: (float(item.get("caption_start_sec") or item.get("source_start_sec") or 0.0), str(item.get("caption_id") or "")) if isinstance(item, dict) else (0.0, ""))

    now = datetime.now(JST).isoformat(timespec="seconds")
    plan["updated_at"] = now
    plan.setdefault("revision_notes", []).append(
        {
            "updated_at": now,
            "script": Path(__file__).name,
            "summary": "Fixed remaining short captions displayed longer than 8 seconds and removed one duplicate caption root.",
            "report": str(REPORT_JSON),
        }
    )
    write_json(EDIT_PLAN, plan)

    report = {
        "schema_version": "remaining_short_long_caption_fix_report.v1",
        "generated_at": now,
        "removed": removed,
        "removed_only_roots": sorted(REMOVE_ONLY_ROOTS),
        "repair_count": len(repairs),
        "repairs": repairs,
    }
    write_json(REPORT_JSON, report)
    lines = [
        "# Remaining Short-Long Caption Fix Report",
        "",
        f"- Generated: {now}",
        f"- Repaired roots: {len(repairs)}",
        f"- Removed duplicate roots: {', '.join(sorted(REMOVE_ONLY_ROOTS))}",
        f"- Removed overlays: {removed['overlays']}",
        f"- Removed plan items: {removed['plan_items']}",
        "",
    ]
    for repair in repairs:
        lines.append(f"## {repair['root_caption_id']}")
        lines.append("")
        for unit in repair["new_units"]:
            text = str(unit["text"]).replace("\n", "<br>")
            lines.append(
                f"- `{unit['source_window_sec'][0]:.3f} - {unit['source_window_sec'][1]:.3f}` "
                f"({unit['duration_sec']:.3f}s): {text}"
            )
        lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({"repair_count": len(repairs), "removed": removed, "report_json": str(REPORT_JSON), "report_md": str(REPORT_MD)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
