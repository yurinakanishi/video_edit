from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT_JSON = REPORTS / "long_caption_speech_unit_polish_report.json"
REPORT_MD = REPORTS / "long_caption_speech_unit_polish_report.md"
JST = timezone(timedelta(hours=9))

PERSON_NAMES = {
    "person_01": "矢野",
    "person_02": "根本",
    "person_03": "村田",
}

MANUAL_UNITS: dict[str, list[dict[str, Any]]] = {
    "main_caption_004": [
        {"start": 873.240, "end": 880.120, "text": "働く中で経理の生産性に\n問題意識があった", "speaker_person_id": "person_02"},
        {"start": 880.120, "end": 883.540, "text": "課題を感じることが多かった", "speaker_person_id": "person_02"},
    ],
    "main_caption_011": [
        {"start": 1054.280, "end": 1061.280, "text": "LayerXのカルチャーが\n好きだった", "speaker_person_id": "person_03"},
        {"start": 1061.280, "end": 1070.280, "text": "人事企画として\nベンチマークしていた", "speaker_person_id": "person_03"},
    ],
    "main_caption_014": [
        {"start": 1115.280, "end": 1123.280, "text": "何が作れるのかに\n一気に興味を持った", "speaker_person_id": "person_03"},
        {"start": 1123.280, "end": 1126.280, "text": "勤怠を作る話に惹かれた", "speaker_person_id": "person_03"},
    ],
    "main_caption_015": [
        {"start": 1143.280, "end": 1148.280, "text": "開発に参画できる\n壁打ち相手として関われる", "speaker_person_id": "person_03"},
        {"start": 1153.280, "end": 1155.280, "text": "面白い状況だと思った", "speaker_person_id": "person_03"},
    ],
    "main_caption_022": [
        {"start": 1368.920, "end": 1377.920, "text": "実務のモヤモヤを\nプロダクトに落とし込める", "speaker_person_id": "person_03"},
    ],
    "main_caption_031": [
        {"start": 1571.120, "end": 1581.620, "text": "当たり前の業務にも\n法律や理由の背景がある", "speaker_person_id": "person_03"},
        {"start": 1581.620, "end": 1588.620, "text": "会社ルールの裏側にも\n事情がある", "speaker_person_id": "person_03"},
    ],
    "main_caption_032": [
        {"start": 1595.620, "end": 1601.220, "text": "ドメインエキスパートは\n何でも知ってそうに見える", "speaker_person_id": "person_01"},
        {"start": 1601.220, "end": 1604.100, "text": "期待の高さが\nハードルになる", "speaker_person_id": "person_01"},
        {"start": 1604.100, "end": 1611.940, "text": "知らないことまで\n期待される難しさがある", "speaker_person_id": "person_01"},
    ],
    "main_caption_047": [
        {"start": 1848.540, "end": 1853.760, "text": "ルールを調べるだけなら\nエンジニアにもできる", "speaker_person_id": "person_02"},
        {"start": 1855.460, "end": 1866.460, "text": "何を実現したいかという\nビジョンが必要になる", "speaker_person_id": "person_01"},
    ],
    "main_caption_049": [
        {"start": 1903.860, "end": 1907.860, "text": "いらないものを\nちゃんと言うことも価値", "speaker_person_id": "person_02"},
        {"start": 1907.860, "end": 1916.360, "text": "必要に見えるものを\n足しすぎてしまう", "speaker_person_id": "person_02"},
        {"start": 1916.360, "end": 1922.100, "text": "なくていいと\n止められることが価値", "speaker_person_id": "person_02"},
    ],
    "main_caption_065": [
        {"start": 993.220, "end": 998.580, "text": "経理としてどう伸ばすかが\n難しかった", "speaker_person_id": "person_02"},
        {"start": 998.580, "end": 1002.620, "text": "大手ではマネジメントに\n寄りがちだった", "speaker_person_id": "person_02"},
    ],
    "main_caption_076": [
        {"start": 2314.040, "end": 2319.000, "text": "人事労務領域なら\nやれる気がする", "speaker_person_id": "person_02"},
        {"start": 2319.000, "end": 2324.040, "text": "ドメインの貯金がなくなった時が\n怖い", "speaker_person_id": "person_02"},
    ],
    "main_caption_078": [
        {"start": 2395.780, "end": 2403.320, "text": "月次申告などの作業を\n減らしたい", "speaker_person_id": "person_03"},
        {"start": 2403.320, "end": 2409.380, "text": "バクラクで貢献できることを\n増やしたい", "speaker_person_id": "person_03"},
    ],
    "main_caption_080": [
        {"start": 2465.200, "end": 2473.700, "text": "作業量を減らし\n確認時間を短縮する", "speaker_person_id": "person_03"},
        {"start": 2473.700, "end": 2482.200, "text": "やりたいことを\n一つの機能に込める", "speaker_person_id": "person_03"},
    ],
    "main_caption_081": [
        {"start": 2523.200, "end": 2529.000, "text": "実務家としての話が\nプロダクトに活きる", "speaker_person_id": "person_03"},
        {"start": 2529.000, "end": 2534.200, "text": "自分の経験が活かされる瞬間が\nやりがい", "speaker_person_id": "person_03"},
    ],
    "main_caption_085": [
        {"start": 2716.680, "end": 2724.000, "text": "バックオフィス経験を\n多くの人が得られる", "speaker_person_id": "person_03"},
        {"start": 2724.000, "end": 2730.680, "text": "経理や労務を経験して\n活躍できる", "speaker_person_id": "person_03"},
    ],
    "main_caption_088": [
        {"start": 2832.860, "end": 2840.580, "text": "不安があると\n結局人に聞きに来る", "speaker_person_id": "person_03"},
    ],
    "main_caption_089": [
        {"start": 2869.760, "end": 2876.040, "text": "AIで経理が\nなくなるわけではない", "speaker_person_id": "person_02"},
        {"start": 2876.040, "end": 2881.320, "text": "経理の役割が\n変わっていく", "speaker_person_id": "person_02"},
    ],
    "main_caption_093": [
        {"start": 2960.040, "end": 2966.040, "text": "AIの活用や向き合い方も\n変わる", "speaker_person_id": "person_03"},
    ],
    "main_caption_auto_004": [
        {"start": 1433.380, "end": 1438.300, "text": "やりたいことを\n普通に言える", "speaker_person_id": "person_01"},
        {"start": 1438.300, "end": 1443.260, "text": "違和感も\n普通に言える", "speaker_person_id": "person_01"},
    ],
    "main_caption_auto_009": [
        {"start": 1973.100, "end": 1977.000, "text": "AIが普及してきている", "speaker_person_id": "person_01"},
        {"start": 1977.000, "end": 1983.100, "text": "エンジニアの生産性も\n上がっている", "speaker_person_id": "person_01"},
    ],
    "main_caption_auto_016": [
        {"start": 2203.740, "end": 2212.000, "text": "AIが普及していくのは\n間違いない", "speaker_person_id": "person_02"},
        {"start": 2212.000, "end": 2222.740, "text": "AIから逃げない姿勢が\nキャリアに必要", "speaker_person_id": "person_02"},
    ],
    "main_caption_auto_018": [
        {"start": 2267.040, "end": 2272.500, "text": "PDMがだめなら\n経理に戻ればいい", "speaker_person_id": "person_02"},
        {"start": 2272.500, "end": 2276.040, "text": "そう言われていた", "speaker_person_id": "person_02"},
    ],
    "main_caption_auto_038": [
        {"start": 2297.040, "end": 2302.000, "text": "今はドメインの\nアドバンテージがある", "speaker_person_id": "person_02"},
        {"start": 2302.000, "end": 2307.040, "text": "ドメインがない領域でも\n活躍できる力を身につけたい", "speaker_person_id": "person_02"},
    ],
    "main_caption_auto_041": [
        {"start": 2514.200, "end": 2523.200, "text": "開発に関わる\nやりがいがある", "speaker_person_id": "person_03"},
    ],
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_root(value: Any) -> str:
    text = str(value or "")
    if "__unit_" in text:
        return text.split("__unit_", 1)[0]
    if "__cont__" in text:
        return text.split("__cont__", 1)[0]
    return text


def root_for_overlay(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    for key in ("speech_unit_split_root_id", "main_caption_id", "caption_cut_continuation_root_id", "caption_continuation_root_id"):
        if metadata.get(key):
            return normalize_root(metadata[key])
    if overlay.get("caption_id"):
        return normalize_root(overlay.get("caption_id"))
    return f"{event.get('event_id')}_caption_{index}"


def root_for_item(item: dict[str, Any]) -> str:
    if item.get("speech_unit_split_root_id"):
        return normalize_root(item.get("speech_unit_split_root_id"))
    return normalize_root(item.get("caption_id"))


def event_ref_window(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else event.get("source")
    if not isinstance(source, dict) or source.get("in") is None or source.get("out") is None:
        return None
    if source.get("media_id") != "group_wide":
        return None
    return float(source["in"]), float(source["out"])


def event_duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def base_style_for_root(events: list[dict[str, Any]], root: str) -> dict[str, Any]:
    for event in events:
        for index, overlay in enumerate(event.get("overlays", []) or []):
            if isinstance(overlay, dict) and overlay.get("type") == "caption" and root_for_overlay(event, overlay, index) == root:
                return overlay
    return {
        "type": "caption",
        "style_id": "main_punchline_caption",
        "caption_no": None,
        "speaker_person_id": None,
        "metadata": {},
    }


def remove_existing(events: list[dict[str, Any]], roots: set[str]) -> dict[str, int]:
    removed_overlays = 0
    removed_items = 0
    for event in events:
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        kept_overlays = []
        for index, overlay in enumerate(overlays):
            if isinstance(overlay, dict) and overlay.get("type") == "caption" and root_for_overlay(event, overlay, index) in roots:
                removed_overlays += 1
                continue
            kept_overlays.append(overlay)
        event["overlays"] = kept_overlays

        items = event.get("main_caption_plan_items") if isinstance(event.get("main_caption_plan_items"), list) else []
        kept_items = []
        for item in items:
            if isinstance(item, dict) and root_for_item(item) in roots:
                removed_items += 1
                continue
            kept_items.append(item)
        event["main_caption_plan_items"] = kept_items
    return {"overlays": removed_overlays, "plan_items": removed_items}


def add_units(events: list[dict[str, Any]], root: str, base: dict[str, Any], units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    added = []
    for unit_index, unit in enumerate(units, start=1):
        source_start = float(unit["start"])
        source_end = float(unit["end"])
        full_window = [round(source_start, 3), round(source_end, 3)]
        for event in events:
            if event.get("section") != "main":
                continue
            ref = event_ref_window(event)
            if not ref:
                continue
            overlap_start = max(source_start, ref[0])
            overlap_end = min(source_end, ref[1])
            if overlap_end - overlap_start < 0.18:
                continue
            local_start = overlap_start - ref[0]
            local_end = min(event_duration(event), overlap_end - ref[0])
            speaker_id = str(unit.get("speaker_person_id") or base.get("speaker_person_id") or "")
            metadata = dict(base.get("metadata") or {})
            metadata.update(
                {
                    "main_caption_id": root,
                    "speech_unit_split_root_id": root,
                    "speech_unit_polished": True,
                    "caption_source_of_truth": "edit_plan.json",
                    "source_start_sec": round(overlap_start, 3),
                    "source_end_sec": round(overlap_end, 3),
                    "caption_start_sec": round(overlap_start, 3),
                    "caption_end_sec": round(overlap_end, 3),
                    "caption_source_full_window_sec": full_window,
                    "caption_handoff_end_sec": round(source_end, 3),
                }
            )
            if speaker_id:
                metadata["speaker_person_id"] = speaker_id
                metadata["speaker_name"] = PERSON_NAMES.get(speaker_id, speaker_id)
            continuation = overlap_start > source_start + 0.001
            if continuation:
                metadata["caption_cut_continuation"] = True
                metadata["caption_continues_from_event_id"] = root
            else:
                metadata.pop("caption_cut_continuation", None)
                metadata.pop("caption_continues_from_event_id", None)
            caption_id = f"{root}__unit_{unit_index:02d}"
            if continuation:
                caption_id = f"{caption_id}__cont__{event.get('event_id')}"
            overlay = {
                "type": "caption",
                "start": round(local_start, 3),
                "end": round(local_end, 3),
                "text": unit["text"],
                "style_id": base.get("style_id") or "main_punchline_caption",
                "caption_id": caption_id,
                "caption_no": base.get("caption_no"),
                "speaker_person_id": speaker_id or base.get("speaker_person_id"),
                "metadata": metadata,
                "audio_alignment": {
                    "method": "speech_unit_caption_manual_polish",
                    "source_audio_media_id": "group_wide",
                    "source_window_sec": [round(overlap_start, 3), round(overlap_end, 3)],
                    "speech_window_sec": [round(overlap_start, 3), round(overlap_end, 3)],
                    "diagnostics": {
                        "root_caption_id": root,
                        "full_unit_source_window_sec": full_window,
                        "event_reference_window_sec": [round(ref[0], 3), round(ref[1], 3)],
                    },
                },
            }
            event.setdefault("overlays", []).append(overlay)
            event.setdefault("main_caption_plan_items", []).append(
                {
                    "caption_id": caption_id,
                    "caption_no": base.get("caption_no"),
                    "source": "speech_unit_caption_manual_polish",
                    "source_start_sec": round(overlap_start, 3),
                    "source_end_sec": round(overlap_end, 3),
                    "caption_start_sec": round(overlap_start, 3),
                    "caption_end_sec": round(overlap_end, 3),
                    "display_text": unit["text"],
                    "speaker_person_id": speaker_id or base.get("speaker_person_id"),
                    "speaker_name": metadata.get("speaker_name"),
                    "caption_source_of_truth": "edit_plan.json",
                    "speech_unit_split_root_id": root,
                    "speech_unit_polished": True,
                }
            )
            added.append(
                {
                    "event_id": event.get("event_id"),
                    "caption_id": caption_id,
                    "timeline_window_sec": [
                        round(float(event.get("timeline_start") or 0.0) + local_start, 3),
                        round(float(event.get("timeline_start") or 0.0) + local_end, 3),
                    ],
                    "source_window_sec": [round(overlap_start, 3), round(overlap_end, 3)],
                    "full_unit_source_window_sec": full_window,
                    "text": unit["text"],
                    "speaker_person_id": speaker_id,
                }
            )
    return added


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    roots = set(MANUAL_UNITS)
    base_by_root = {root: base_style_for_root(events, root) for root in roots}
    removed = remove_existing(events, roots)
    repairs = []
    for root in sorted(roots):
        added = add_units(events, root, base_by_root[root], MANUAL_UNITS[root])
        repairs.append(
            {
                "root_caption_id": root,
                "new_unit_count": len(MANUAL_UNITS[root]),
                "new_units": [
                    {
                        "source_window_sec": [unit["start"], unit["end"]],
                        "duration_sec": round(float(unit["end"]) - float(unit["start"]), 3),
                        "text": unit["text"],
                        "speaker_person_id": unit.get("speaker_person_id"),
                    }
                    for unit in MANUAL_UNITS[root]
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
            "summary": f"Polished {len(repairs)} long caption split roots with natural speech-matched caption units.",
            "report": str(REPORT_JSON),
        }
    )
    write_json(EDIT_PLAN, plan)
    report = {
        "schema_version": "long_caption_speech_unit_polish_report.v1",
        "generated_at": now,
        "single_source_of_truth": "edit_plan.json",
        "removed": removed,
        "repair_count": len(repairs),
        "repairs": repairs,
    }
    write_json(REPORT_JSON, report)
    lines = [
        "# Long Caption Speech Unit Polish Report",
        "",
        f"- Generated: {now}",
        f"- Repair count: {len(repairs)}",
        f"- Removed old overlays: {removed['overlays']}",
        f"- Removed old plan items: {removed['plan_items']}",
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
