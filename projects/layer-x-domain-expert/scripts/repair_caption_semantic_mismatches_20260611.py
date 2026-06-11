from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "caption_semantic_mismatch_repair_20260611.json"
JST = timezone(timedelta(hours=9))


TEXT_REPAIRS = {
    "main_caption_004": {
        "text": "経理の生産性に問題意識があった",
        "reason": "Source speech says 経理の生産性, not generic バックオフィス.",
    },
    "main_caption_005": {
        "text": "決算期は終電帰りが当たり前だった",
        "reason": "Keep the caption on the concrete source statement and avoid combining it with another speaker's evaluation.",
    },
    "main_caption_007": {
        "text": "開発と言われたことが転職のきっかけだった",
        "reason": "Source speech is about being told '開発' after enjoying the previous job.",
    },
    "main_caption_014": {
        "text": "何が作れるのかに興味を持ってLayerXに来た",
        "reason": "Source speech says どんなものができるんだろうと興味を持った.",
    },
    "main_caption_021": {
        "text": "仕様の検討にも深く関わっている",
        "reason": "Source speech supports 仕様検討に関わる; 労務を主務 is contextual but not in the caption source window.",
    },
    "main_caption_034": {
        "text": "エンジニアはドメインをものすごく調べている",
        "reason": "Source speech says 皆さんドメインの方めっちゃ調べてる; avoid over-specific LayerX wording.",
    },
    "main_caption_050": {
        "text": "AIはリサーチがすごく優秀",
        "reason": "Source speech directly says AIのリサーチがすごい優秀; previous text over-interpreted the point.",
    },
    "main_caption_065": {
        "text": "経理の伸ばし方が難しかった",
        "reason": "Source speech says 経理としてどう伸ばしていくのか and めちゃくちゃ難しい; previous startup phrasing was too broad.",
    },
    "main_caption_073": {
        "text": "知識を活かして挑戦できる",
        "reason": "Source speech says 自分の知識を活かしていろんなことをやればいい; previous code wording was outside this source window.",
    },
    "main_caption_091": {
        "text": "バックオフィス経験者にはめちゃめちゃおすすめ",
        "reason": "Source answer lands on おすすめ and めちゃめちゃおすすめ; make the caption answer-oriented, not question-title-like.",
    },
    "main_caption_auto_033": {
        "text": "役所は「やらなくていい」とは答えない",
        "source_start_sec": 1955.94,
        "source_end_sec": 1961.66,
        "reason": "Previous source window stopped before the actual '答え返ってこない' phrase.",
    },
}

REMOVE_ROOT_IDS = {
    "main_caption_068": "Duplicate/over-interpreted HR-tech caption over the same source as main_caption_014.",
    "main_caption_070": "Interviewer question-derived caption; main captions should emphasize answers.",
    "main_caption_auto_039": "Source speech is incomplete/unclear and the caption over-interprets it.",
    "main_caption_087": "Interviewer question-derived caption; remove from displayed main captions.",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def caption_root_id(event: dict[str, Any], overlay: dict[str, Any], index: int) -> str:
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    return str(metadata.get("caption_cut_continuation_root_id") or overlay.get("caption_id") or f"{event.get('event_id')}_caption_{index}")


def patch_source_window(overlay: dict[str, Any], start: float, end: float) -> None:
    metadata = overlay.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["source_start_sec"] = round(start, 3)
        metadata["source_end_sec"] = round(end, 3)
        metadata["caption_start_sec"] = round(start, 3)
        metadata["caption_end_sec"] = round(end, 3)
    alignment = overlay.setdefault("audio_alignment", {})
    if isinstance(alignment, dict):
        alignment["source_window_sec"] = [round(start, 3), round(end, 3)]
        alignment["speech_window_sec"] = [round(start, 3), round(end, 3)]
        diagnostics = alignment.setdefault("diagnostics", {})
        if isinstance(diagnostics, dict):
            diagnostics["semantic_source_window_repaired"] = True


def main() -> None:
    plan = read_json(EDIT_PLAN)
    events = [event for event in plan.get("timeline", []) if isinstance(event, dict)]
    repaired = []
    removed = []
    embedded_repaired = []
    embedded_removed = []

    for event in events:
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue
        next_overlays = []
        for index, overlay in enumerate(overlays):
            if not (isinstance(overlay, dict) and overlay.get("type") == "caption"):
                next_overlays.append(overlay)
                continue
            root_id = caption_root_id(event, overlay, index)
            if root_id in REMOVE_ROOT_IDS:
                removed.append(
                    {
                        "event_id": event.get("event_id"),
                        "caption_id": overlay.get("caption_id"),
                        "root_id": root_id,
                        "text": overlay.get("text"),
                        "reason": REMOVE_ROOT_IDS[root_id],
                    }
                )
                continue
            if root_id in TEXT_REPAIRS:
                repair = TEXT_REPAIRS[root_id]
                old_text = overlay.get("text")
                overlay["text"] = repair["text"]
                metadata = overlay.setdefault("metadata", {})
                if isinstance(metadata, dict):
                    metadata["semantic_review_fixed"] = True
                    metadata["semantic_review_fixed_at"] = datetime.now(JST).isoformat(timespec="seconds")
                    metadata["semantic_review_reason"] = repair["reason"]
                    if old_text != repair["text"]:
                        metadata["display_text_semantically_repaired_from"] = old_text
                if repair.get("source_start_sec") is not None and repair.get("source_end_sec") is not None:
                    patch_source_window(overlay, float(repair["source_start_sec"]), float(repair["source_end_sec"]))
                repaired.append(
                    {
                        "event_id": event.get("event_id"),
                        "caption_id": overlay.get("caption_id"),
                        "root_id": root_id,
                        "old_text": old_text,
                        "new_text": repair["text"],
                        "reason": repair["reason"],
                    }
                )
            next_overlays.append(overlay)
        event["overlays"] = next_overlays
        embedded_items = event.get("main_caption_plan_items")
        if isinstance(embedded_items, list):
            next_items = []
            for item in embedded_items:
                if not isinstance(item, dict):
                    next_items.append(item)
                    continue
                caption_id = str(item.get("caption_id") or "")
                if caption_id in REMOVE_ROOT_IDS:
                    embedded_removed.append(
                        {
                            "event_id": event.get("event_id"),
                            "caption_id": caption_id,
                            "display_text": item.get("display_text"),
                            "reason": REMOVE_ROOT_IDS[caption_id],
                        }
                    )
                    continue
                if caption_id in TEXT_REPAIRS:
                    repair = TEXT_REPAIRS[caption_id]
                    old_display = item.get("display_text")
                    item["display_text"] = repair["text"]
                    item["semantic_review_fixed"] = True
                    item["semantic_review_reason"] = repair["reason"]
                    if repair.get("source_start_sec") is not None and repair.get("source_end_sec") is not None:
                        item["source_start_sec"] = round(float(repair["source_start_sec"]), 3)
                        item["source_end_sec"] = round(float(repair["source_end_sec"]), 3)
                        item["caption_start_sec"] = round(float(repair["source_start_sec"]), 3)
                        item["caption_end_sec"] = round(float(repair["source_end_sec"]), 3)
                    embedded_repaired.append(
                        {
                            "event_id": event.get("event_id"),
                            "caption_id": caption_id,
                            "old_display_text": old_display,
                            "new_display_text": repair["text"],
                            "reason": repair["reason"],
                        }
                    )
                next_items.append(item)
            event["main_caption_plan_items"] = next_items

    plan.setdefault("metadata", {})["caption_semantic_mismatch_repair_20260611"] = {
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "repaired_count": len(repaired),
        "removed_count": len(removed),
        "embedded_repaired_count": len(embedded_repaired),
        "embedded_removed_count": len(embedded_removed),
        "source": "manual full-caption semantic review against voice_speaker_attribution.json",
    }
    write_json(EDIT_PLAN, plan)
    report = {
        "schema_version": "caption_semantic_mismatch_repair_20260611.v1",
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "repaired_count": len(repaired),
        "removed_count": len(removed),
        "embedded_repaired_count": len(embedded_repaired),
        "embedded_removed_count": len(embedded_removed),
        "repaired": repaired,
        "removed": removed,
        "embedded_repaired": embedded_repaired,
        "embedded_removed": embedded_removed,
    }
    write_json(REPORT, report)
    print(json.dumps({k: report[k] for k in ("repaired_count", "removed_count")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
