from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
MAIN_CAPTION_PLAN_PATH = REPORTS_DIR / "main_caption_plan.json"
REPORT_PATH = REPORTS_DIR / "main_interviewer_question_caption_removal_report.json"


INTERVIEWER_PERSON_ID = "person_01"
INTERVIEWER_NAME = "矢野"

QUESTION_MARKERS = (
    "?",
    "？",
    "ですか",
    "ますか",
    "でしょうか",
    "じゃないですか",
    "ありますか",
    "あったりされますか",
    "感じるところがあったりしますか",
    "どう考え",
    "お二人",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize(text: str) -> str:
    return (
        str(text or "")
        .replace("\n", "")
        .replace("<br>", "")
        .replace(" ", "")
        .replace("　", "")
        .replace("、", "")
        .replace("。", "")
        .strip()
    )


def is_interviewer_caption(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return (
        item.get("speaker_person_id") == INTERVIEWER_PERSON_ID
        or metadata.get("speaker_person_id") == INTERVIEWER_PERSON_ID
        or item.get("speaker_name") == INTERVIEWER_NAME
        or metadata.get("speaker_name") == INTERVIEWER_NAME
    )


def question_reason(text: str) -> str | None:
    compact = normalize(text)
    if not compact:
        return None
    for marker in QUESTION_MARKERS:
        if marker in compact:
            return f"interviewer_question_marker:{marker}"
    return None


def overlay_question_text(overlay: dict[str, Any]) -> str:
    parts = [
        overlay.get("text", ""),
        overlay.get("caption_part", {}).get("original_text", "")
        if isinstance(overlay.get("caption_part"), dict)
        else "",
    ]
    metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
    parts.extend(
        [
            metadata.get("display_text", ""),
            metadata.get("full_reference_text", ""),
        ]
    )
    return " ".join(str(part or "") for part in parts)


def plan_caption_question_text(caption: dict[str, Any]) -> str:
    return " ".join(
        str(caption.get(key) or "")
        for key in ("display_text", "full_reference_text", "source_text", "question", "answer_summary")
    )


def collect_question_group_ids(plan: dict[str, Any]) -> tuple[set[str], list[dict[str, Any]]]:
    question_group_ids: set[str] = set()
    seeds: list[dict[str, Any]] = []
    for event in plan.get("timeline", []):
        if event.get("section") != "main":
            continue
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue
        for overlay in overlays:
            if overlay.get("type") != "caption" or not is_interviewer_caption(overlay):
                continue
            reason = question_reason(overlay_question_text(overlay))
            if not reason:
                continue
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            group_id = metadata.get("main_caption_id") or overlay.get("caption_id")
            if not group_id:
                continue
            question_group_ids.add(str(group_id))
            seeds.append(
                {
                    "event_id": event.get("event_id"),
                    "caption_id": overlay.get("caption_id"),
                    "main_caption_id": group_id,
                    "text": overlay.get("text"),
                    "original_text": overlay.get("caption_part", {}).get("original_text")
                    if isinstance(overlay.get("caption_part"), dict)
                    else None,
                    "reason": reason,
                }
            )
    return question_group_ids, seeds


def prune_edit_plan(plan: dict[str, Any], question_group_ids: set[str]) -> list[dict[str, Any]]:
    removed: list[dict[str, Any]] = []
    for event in plan.get("timeline", []):
        if event.get("section") != "main":
            continue
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue

        kept: list[dict[str, Any]] = []
        for overlay in overlays:
            if overlay.get("type") != "caption":
                kept.append(overlay)
                continue
            metadata = overlay.get("metadata") if isinstance(overlay.get("metadata"), dict) else {}
            group_id = metadata.get("main_caption_id") or overlay.get("caption_id")
            if is_interviewer_caption(overlay) and group_id and str(group_id) in question_group_ids:
                removed.append(
                    {
                        "event_id": event.get("event_id"),
                        "timeline_start": event.get("timeline_start"),
                        "timeline_end": event.get("timeline_end"),
                        "caption_id": overlay.get("caption_id"),
                        "main_caption_id": group_id,
                        "text": overlay.get("text"),
                        "speaker_person_id": overlay.get("speaker_person_id"),
                        "speaker_name": metadata.get("speaker_name"),
                    }
                )
            else:
                kept.append(overlay)
        event["overlays"] = kept
    return removed


def prune_main_caption_plan(caption_plan: dict[str, Any]) -> list[dict[str, Any]]:
    captions = caption_plan.get("captions")
    if not isinstance(captions, list):
        return []

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for caption in captions:
        if is_interviewer_caption(caption):
            reason = question_reason(plan_caption_question_text(caption))
            if reason:
                removed.append(
                    {
                        "caption_id": caption.get("caption_id"),
                        "caption_no": caption.get("caption_no"),
                        "caption_start_sec": caption.get("caption_start_sec"),
                        "caption_end_sec": caption.get("caption_end_sec"),
                        "display_text": caption.get("display_text"),
                        "full_reference_text": caption.get("full_reference_text"),
                        "speaker_person_id": caption.get("speaker_person_id"),
                        "speaker_name": caption.get("speaker_name"),
                        "reason": reason,
                    }
                )
                continue
        kept.append(caption)

    caption_plan["captions"] = kept
    caption_plan.setdefault("policy", {})["exclude_main_interviewer_questions"] = True
    caption_plan["updated_at"] = now_iso()
    return removed


def main() -> None:
    plan = load_json(EDIT_PLAN_PATH)
    caption_plan = load_json(MAIN_CAPTION_PLAN_PATH) if MAIN_CAPTION_PLAN_PATH.exists() else None

    question_group_ids, seeds = collect_question_group_ids(plan)
    removed_overlays = prune_edit_plan(plan, question_group_ids)
    dump_json(EDIT_PLAN_PATH, plan)

    removed_plan_captions: list[dict[str, Any]] = []
    if isinstance(caption_plan, dict):
        removed_plan_captions = prune_main_caption_plan(caption_plan)
        dump_json(MAIN_CAPTION_PLAN_PATH, caption_plan)

    report = {
        "generated_at": now_iso(),
        "policy": {
            "scope": "main section only",
            "digest_questions_allowed": True,
            "interviewer_person_id": INTERVIEWER_PERSON_ID,
            "interviewer_name": INTERVIEWER_NAME,
            "question_markers": QUESTION_MARKERS,
            "remove_whole_split_group": True,
        },
        "question_group_ids": sorted(question_group_ids),
        "question_seeds": seeds,
        "removed_overlay_count": len(removed_overlays),
        "removed_overlays": removed_overlays,
        "removed_main_caption_plan_count": len(removed_plan_captions),
        "removed_main_caption_plan_items": removed_plan_captions,
    }
    dump_json(REPORT_PATH, report)
    print(
        f"Removed {len(removed_overlays)} main interviewer question caption overlays "
        f"across {len(question_group_ids)} split groups."
    )
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
