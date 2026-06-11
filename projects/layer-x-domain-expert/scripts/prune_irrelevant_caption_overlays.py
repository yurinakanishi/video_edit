from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
DIGEST_QA_PATH = REPORTS_DIR / "digest_qa_selection.json"
REPORT_PATH = REPORTS_DIR / "caption_relevance_prune_report.json"


EXACT_REMOVE = {
    "めっちゃ大事です",
    "感覚があって",
    "自分が調べるよりも全然",
    "探し出してきてくれるんですけど",
    "そこに対して",
    "メッセージじゃないですけどお二人から",
    "おすすめしてくださいって",
    "言うわけじゃないんですけど",
    "本当に細かいところですけど",
    "さっきちょっとお話した",
    "自分が",
    "タイミングが来るとか",
    "よろしくお願いします",
    "根元がすみませんさっき根元が中途半端だったんで",
    "こういうとここうできたらいいのになとか",
    "結構いっぱいあったんですけど",
    "これ気をつけてますとか",
    "提供できたなみたいなこともあるので",
    "実際付加価値のある仕事をやるって",
    "こういうものを",
    "よ",
    "キャリア",
    "話もあると思うんですけど",
    "限定的に考えていると",
    "それはいきなり何もなしだと難しいと思うんですけれどもちょっと",
}

EDITORIAL_REWRITES = {
    "なんでそうするんですかって聞かれた時に": "なんでそうするんですかと聞かれた時に",
    "この辺へのハードルの高さというか": "この辺へのハードルの高さ",
    "正直全然僕より詳しいということもある": "正直僕より詳しいこともある",
    "自分たちに求められることは結構研ぎ澄まされてきているなという": "自分たちに求められることは結構研ぎ澄まされてきている",
    "自分たちに求められることは結構研ぎ澄まされてきているなという感覚があって": "自分たちに求められることは結構研ぎ澄まされてきている",
    "どういうことを実現していきたいのかとか": "どういうことを実現したいのか",
}

SETUP_OR_FILLER_PATTERNS = (
    "よろしくお願いします",
    "すみません",
    "中途半端",
    "この辺ちょっと",
    "さっき",
    "みたいなところ",
    "というところで",
    "という感じ",
)

FRAGMENT_ENDINGS = (
    "ですけど",
    "なんですけど",
    "なんですけれども",
    "ですけれども",
    "という",
    "って",
    "とか",
    "みたいな",
    "に対して",
    "として",
    "すると",
    "で",
    "が",
    "を",
    "に",
    "は",
)

KEEP_KEYWORDS = (
    "AI",
    "PDM",
    "PdM",
    "プロダクト",
    "ドメイン",
    "エキスパート",
    "バックオフィス",
    "開発",
    "言語化",
    "当たり前",
    "暗黙知",
    "慣行",
    "労務",
    "経理",
    "実務",
    "ユーザー",
    "価値",
    "機能",
    "キャリア",
    "おすすめ",
    "視野",
    "不安",
    "調べ",
    "リサーチ",
    "法律",
    "仕様",
    "体験",
    "判断",
    "課題",
    "成長",
    "自動化",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalized_text(text: str) -> str:
    return (
        text.replace("\n", "")
        .replace(" ", "")
        .replace("　", "")
        .replace("、", "")
        .replace("。", "")
        .strip()
    )


def has_keep_keyword(text: str) -> bool:
    return any(keyword in text for keyword in KEEP_KEYWORDS)


def removal_reason(text: str) -> str | None:
    text = normalized_text(text)
    if not text:
        return "empty_text"
    if text in EXACT_REMOVE:
        return "explicit_filler_or_fragment"
    if any(pattern in text for pattern in SETUP_OR_FILLER_PATTERNS):
        return "setup_or_filler"
    if len(text) <= 8 and not has_keep_keyword(text):
        return "too_short_without_editorial_value"
    if len(text) <= 16 and text.endswith(FRAGMENT_ENDINGS) and not has_keep_keyword(text):
        return "sentence_fragment"
    if text.endswith(("ですけど", "なんですけど", "ですけれども", "なんですけれども")) and not (
        "なぜ" in text or "なんで" in text
    ):
        return "dangling_clause"
    return None


def overlay_text(overlay: dict[str, Any]) -> str:
    return str(overlay.get("text") or overlay.get("label") or "")


def rewrite_caption_text(text: str) -> str | None:
    return EDITORIAL_REWRITES.get(normalized_text(text))


def prune_event_overlays(plan: dict[str, Any]) -> dict[str, Any]:
    removed: list[dict[str, Any]] = []
    rewritten: list[dict[str, Any]] = []
    digest_events_trimmed: list[dict[str, Any]] = []
    events = plan.get("timeline", [])
    if not isinstance(events, list):
        events = plan.get("events", [])
    if not isinstance(events, list):
        raise TypeError("edit_plan.json must contain a timeline or events list")

    for event in events:
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue

        kept_overlays = []
        removed_from_event = []
        for overlay in overlays:
            if overlay.get("type") != "caption":
                kept_overlays.append(overlay)
                continue
            text = overlay_text(overlay)
            rewritten_text = rewrite_caption_text(text)
            if rewritten_text is not None and rewritten_text != text:
                rewritten.append(
                    {
                        "event_id": event.get("event_id") or event.get("id"),
                        "section": event.get("section"),
                        "overlay_id": overlay.get("id"),
                        "start": overlay.get("start"),
                        "end": overlay.get("end"),
                        "before": text,
                        "after": rewritten_text,
                    }
                )
                overlay["text"] = rewritten_text
                text = rewritten_text
            reason = None
            if "start" in overlay and "end" in overlay:
                duration = float(overlay.get("end", 0.0)) - float(overlay.get("start", 0.0))
                if duration < 0.75:
                    reason = "too_short_to_read"
            reason = reason or removal_reason(text)
            if reason:
                item = {
                    "event_id": event.get("event_id") or event.get("id"),
                    "section": event.get("section"),
                    "overlay_id": overlay.get("id"),
                    "start": overlay.get("start"),
                    "end": overlay.get("end"),
                    "text": text,
                    "reason": reason,
                }
                removed.append(item)
                removed_from_event.append(item)
            else:
                kept_overlays.append(overlay)

        event["overlays"] = kept_overlays

        if event.get("section") == "digest" and removed_from_event:
            caption_overlays = [o for o in kept_overlays if o.get("type") == "caption"]
            if not caption_overlays:
                event["_remove_digest_event_after_caption_prune"] = True
                digest_events_trimmed.append(
                    {
                        "event_id": event.get("event_id") or event.get("id"),
                        "action": "remove_event",
                        "reason": "no_remaining_digest_captions",
                    }
                )
                continue

            first_caption = min(float(o.get("start", 0.0)) for o in caption_overlays)
            last_caption = max(float(o.get("end", o.get("start", 0.0))) for o in caption_overlays)
            if first_caption > 0.001 or last_caption < float(event.get("duration", 0.0)) - 0.001:
                trim_digest_event(event, first_caption, last_caption, digest_events_trimmed)

    pruned_events = [e for e in events if not e.pop("_remove_digest_event_after_caption_prune", False)]
    if isinstance(plan.get("timeline"), list):
        plan["timeline"] = pruned_events
    else:
        plan["events"] = pruned_events

    if plan.get("events") == [] and isinstance(plan.get("timeline"), list):
        plan.pop("events", None)
    if plan.get("duration_sec") == 0.0 and isinstance(plan.get("timeline"), list):
        plan.pop("duration_sec", None)

    ripple_timeline(plan)

    return {
        "removed": removed,
        "rewritten": rewritten,
        "digest_events_trimmed": digest_events_trimmed,
        "removed_count": len(removed),
        "rewritten_count": len(rewritten),
        "digest_trim_count": len(digest_events_trimmed),
    }


def trim_digest_event(
    event: dict[str, Any],
    first_caption: float,
    last_caption: float,
    digest_events_trimmed: list[dict[str, Any]],
) -> None:
    original_duration = float(event.get("duration", 0.0))
    trim_in = max(0.0, first_caption)
    trim_out = min(original_duration, last_caption)
    new_duration = max(0.001, trim_out - trim_in)

    source = event.get("source")
    if isinstance(source, dict):
        old_in = float(source.get("in", 0.0))
        if "in" in source:
            source["in"] = round(old_in + trim_in, 3)
        if "out" in source:
            source["out"] = round(old_in + trim_in + new_duration, 3)

    reference_source = event.get("reference_source")
    if isinstance(reference_source, dict):
        old_in = float(reference_source.get("in", 0.0))
        if "in" in reference_source:
            reference_source["in"] = round(old_in + trim_in, 3)
        if "out" in reference_source:
            reference_source["out"] = round(old_in + trim_in + new_duration, 3)

    for overlay in event.get("overlays", []):
        if "start" in overlay:
            overlay["start"] = round(max(0.0, float(overlay["start"]) - trim_in), 3)
        if "end" in overlay:
            overlay["end"] = round(max(float(overlay.get("start", 0.0)), float(overlay["end"]) - trim_in), 3)

    event["duration"] = round(new_duration, 3)
    digest_events_trimmed.append(
        {
            "event_id": event.get("event_id") or event.get("id"),
            "action": "trim_to_remaining_captions",
            "trim_in": round(trim_in, 3),
            "trim_out": round(trim_out, 3),
            "old_duration": round(original_duration, 3),
            "new_duration": round(new_duration, 3),
        }
    )


def ripple_timeline(plan: dict[str, Any]) -> None:
    events = plan.get("timeline", [])
    if not isinstance(events, list):
        events = plan.get("events", [])
    if not isinstance(events, list):
        return
    cursor = 0.0
    for event in events:
        duration = float(event.get("duration") or 0.0)
        if duration <= 0.0:
            start = float(event.get("timeline_start", cursor))
            end = float(event.get("timeline_end", start))
            duration = max(0.001, end - start)
        event["timeline_start"] = round(cursor, 3)
        cursor += duration
        event["timeline_end"] = round(cursor, 3)


def prune_digest_selection() -> dict[str, Any]:
    if not DIGEST_QA_PATH.exists():
        return {"status": "missing", "path": str(DIGEST_QA_PATH)}

    data = load_json(DIGEST_QA_PATH)
    rewritten: list[dict[str, Any]] = []
    removed = prune_caption_lists(data.get("clips", []), rewritten)
    data.setdefault("caption_relevance", {})["pruned_irrelevant_fragments"] = True
    data["caption_relevance"]["removed_count"] = len(removed)
    data["caption_relevance"]["rewritten_count"] = len(rewritten)
    dump_json(DIGEST_QA_PATH, data)
    return {
        "status": "updated",
        "removed_count": len(removed),
        "rewritten_count": len(rewritten),
        "removed": removed,
        "rewritten": rewritten,
    }


def prune_caption_lists(node: Any, rewritten: list[dict[str, Any]], clip_id: str | None = None) -> list[dict[str, Any]]:
    removed: list[dict[str, Any]] = []
    if isinstance(node, dict):
        current_clip_id = str(node.get("id") or node.get("clip_id") or clip_id or "")
        if node.get("type") == "caption" and "text" in node:
            text = str(node.get("text") or "")
            rewritten_text = rewrite_caption_text(text)
            if rewritten_text is not None and rewritten_text != text:
                rewritten.append(
                    {
                        "clip_id": current_clip_id,
                        "caption_id": node.get("id"),
                        "before": text,
                        "after": rewritten_text,
                    }
                )
                node["text"] = rewritten_text
                text = rewritten_text
            reason = removal_reason(text)
            if reason:
                return [
                    {
                        "clip_id": current_clip_id,
                        "caption_id": node.get("id"),
                        "text": text,
                        "reason": reason,
                    }
                ]
        captions = node.get("captions")
        if isinstance(captions, list):
            kept = []
            for caption in captions:
                if not isinstance(caption, dict):
                    kept.append(caption)
                    continue
                text = str(caption.get("text") or "")
                rewritten_text = rewrite_caption_text(text)
                if rewritten_text is not None and rewritten_text != text:
                    rewritten.append(
                        {
                            "clip_id": current_clip_id,
                            "caption_id": caption.get("id"),
                            "before": text,
                            "after": rewritten_text,
                        }
                    )
                    caption["text"] = rewritten_text
                    text = rewritten_text
                reason = removal_reason(text)
                if reason:
                    removed.append(
                        {
                            "clip_id": current_clip_id,
                            "caption_id": caption.get("id"),
                            "text": text,
                            "reason": reason,
                        }
                    )
                else:
                    kept.append(caption)
            node["captions"] = kept
        for value in node.values():
            removed.extend(prune_caption_lists(value, rewritten, current_clip_id))
    elif isinstance(node, list):
        kept_items = []
        for item in node:
            item_removed = prune_caption_lists(item, rewritten, clip_id)
            if isinstance(item, dict) and item.get("type") == "caption" and item_removed:
                removed.extend(item_removed)
                continue
            removed.extend(item_removed)
            kept_items.append(item)
        node[:] = kept_items
    return removed


def main() -> None:
    plan = load_json(EDIT_PLAN_PATH)
    before = deepcopy(plan)
    edit_plan_report = prune_event_overlays(plan)
    plan.setdefault("metadata", {})["caption_relevance_prune"] = {
        "enabled": True,
        "policy": "remove filler, greetings, dangling fragments, and non-editorial short captions",
        "removed_count": edit_plan_report["removed_count"],
        "rewritten_count": edit_plan_report["rewritten_count"],
    }
    dump_json(EDIT_PLAN_PATH, plan)

    digest_report = prune_digest_selection()
    report = {
        "edit_plan": edit_plan_report,
        "digest_qa_selection": digest_report,
        "before_event_count": len(before.get("timeline") or before.get("events") or []),
        "after_event_count": len(plan.get("timeline") or plan.get("events") or []),
    }
    dump_json(REPORT_PATH, report)
    print(
        f"removed={edit_plan_report['removed_count']} "
        f"rewritten={edit_plan_report['rewritten_count']} "
        f"digest_trims={edit_plan_report['digest_trim_count']} "
        f"events={report['before_event_count']}->{report['after_event_count']}"
    )


if __name__ == "__main__":
    main()
