from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
MAIN_CAPTION_PLAN_PATH = REPORTS_DIR / "main_caption_plan.json"
REPORT_PATH = REPORTS_DIR / "strong_caption_additions_report.json"


PEOPLE = {
    "person_01": {"name": "矢野", "screen_position": "left", "role": "interviewer"},
    "person_02": {"name": "根本", "screen_position": "middle", "role": "interviewee"},
    "person_03": {"name": "村田", "screen_position": "right", "role": "interviewee"},
}


STRONG_ADDITIONS = [
    {
        "caption_id": "main_caption_strong_001",
        "source_start_sec": 1757.50,
        "source_end_sec": 1761.50,
        "display_text": "実務経験者が開発に入る意味がある",
        "full_reference_text": "これをとにかく避けるためにドメインエキスパートの実務の経験者",
        "speaker_person_id": "person_03",
        "reason": "実務者が開発に入る理由を端的に言っている強い発言。",
    },
    {
        "caption_id": "main_caption_strong_002",
        "source_start_sec": 1907.86,
        "source_end_sec": 1916.36,
        "display_text": "必要に見えるものを足しすぎてしまう",
        "full_reference_text": "経理とか労務のドメインを知っているからこれなくて大丈夫かなとか必要なものをどんどんやっちゃう",
        "speaker_person_id": "person_02",
        "reason": "機能を足しすぎるリスクを説明しており、後続の「なくていい」と言える価値につながる。",
    },
    {
        "caption_id": "main_caption_strong_003",
        "source_start_sec": 2403.32,
        "source_end_sec": 2409.38,
        "display_text": "バクラクのプロダクトで貢献したい",
        "full_reference_text": "バクラクのプロダクトで貢献できることがあればいいなみたいなのはずっと思っていますね。",
        "speaker_person_id": "person_02",
        "reason": "開発に関わる動機として強い。",
    },
    {
        "caption_id": "main_caption_strong_004",
        "source_start_sec": 2571.66,
        "source_end_sec": 2578.86,
        "display_text": "余った時間で付加価値のある仕事をする",
        "full_reference_text": "余った時間で付加価値のあることをやりましょう。実際付加価値のある仕事をやるって",
        "speaker_person_id": "person_03",
        "reason": "AI・自動化によって生まれる時間の使い方を明確に言っている。",
    },
    {
        "caption_id": "main_caption_strong_005",
        "source_start_sec": 2604.58,
        "source_end_sec": 2608.34,
        "display_text": "AIの力で分析できるようになる",
        "full_reference_text": "AIの力を借りて分析できるようになりましたとか",
        "speaker_person_id": "person_02",
        "reason": "AIによる実務変化が具体的で強い。",
    },
    {
        "caption_id": "main_caption_strong_006",
        "source_start_sec": 2658.00,
        "source_end_sec": 2662.32,
        "display_text": "新しい働き方を定義していく",
        "full_reference_text": "その新しい働き方をある種の定義していきながら",
        "speaker_person_id": "person_03",
        "reason": "AI時代の働き方のテーマとして強い。",
    },
    {
        "caption_id": "main_caption_strong_007",
        "source_start_sec": 2674.02,
        "source_end_sec": 2679.32,
        "display_text": "経理や労務は専門性が高い",
        "full_reference_text": "経理とか労務の領域ってすごい専門性が高くて",
        "speaker_person_id": "person_03",
        "reason": "バックオフィス領域の専門性を明確に言っている。",
    },
    {
        "caption_id": "main_caption_strong_008",
        "source_start_sec": 2694.16,
        "source_end_sec": 2701.32,
        "display_text": "労務や経理の経験は新しい働き方に必要",
        "full_reference_text": "1年2年労務とか経理とか経験するって結構必要だと思うんですよ。そういうのを新しい働き方でできるという",
        "speaker_person_id": "person_03",
        "reason": "経験と新しい働き方をつなげる強いまとめ。",
    },
    {
        "caption_id": "main_caption_strong_009",
        "source_start_sec": 2755.44,
        "source_end_sec": 2757.64,
        "display_text": "今後数年で大きく変わってくる",
        "full_reference_text": "その辺は今後数年でだいぶ変わってくる",
        "speaker_person_id": "person_03",
        "reason": "変化の大きさを端的に表す。",
    },
    {
        "caption_id": "main_caption_strong_010",
        "source_start_sec": 2853.68,
        "source_end_sec": 2862.44,
        "display_text": "経理は効率化が早く進みやすい",
        "full_reference_text": "経理でいうと労務よりは効率化が早いんじゃないかなとは思いますね",
        "speaker_person_id": "person_03",
        "reason": "領域ごとのAI・効率化の差を説明している。",
    },
    {
        "caption_id": "main_caption_strong_011",
        "source_start_sec": 2966.04,
        "source_end_sec": 2973.70,
        "display_text": "専門家として尖るキャリアも良い",
        "full_reference_text": "その後もちろん専門家としてすごく一個に尖っていくっていうのもいいキャリアだと思うんですけれども",
        "speaker_person_id": "person_02",
        "reason": "キャリア論の締めとして使える。",
    },
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def event_source_range(event: dict[str, Any]) -> tuple[float, float] | None:
    source = event.get("reference_source") or event.get("source") or {}
    if source.get("in") is None or source.get("out") is None:
        return None
    return float(source["in"]), float(source["out"])


def existing_caption_ids(plan: dict[str, Any]) -> set[str]:
    ids = set()
    for event in plan.get("timeline", []):
        for overlay in event.get("overlays", []) if isinstance(event.get("overlays"), list) else []:
            if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("caption_id"):
                ids.add(str(overlay["caption_id"]))
    return ids


def find_event(plan: dict[str, Any], start: float) -> dict[str, Any] | None:
    for event in plan.get("timeline", []):
        if event.get("section") != "main":
            continue
        source_range = event_source_range(event)
        if not source_range:
            continue
        source_in, source_out = source_range
        if source_in <= start < source_out:
            return event
    return None


def add_to_edit_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    added: list[dict[str, Any]] = []
    ids = existing_caption_ids(plan)
    for item in STRONG_ADDITIONS:
        if item["caption_id"] in ids:
            continue
        event = find_event(plan, float(item["source_start_sec"]))
        if not event:
            added.append({**item, "status": "skipped", "reason": "no_matching_main_event"})
            continue
        source_in, source_out = event_source_range(event) or (0.0, 0.0)
        start = max(0.0, float(item["source_start_sec"]) - source_in)
        end = min(source_out - source_in, max(float(item["source_end_sec"]) - source_in, start + 2.2))
        person = PEOPLE[item["speaker_person_id"]]
        overlay = {
            "type": "caption",
            "start": round(start, 3),
            "end": round(end, 3),
            "text": item["display_text"],
            "style_id": "main_punchline_caption",
            "caption_id": item["caption_id"],
            "caption_no": item["caption_id"].replace("main_caption_", ""),
            "speaker_person_id": item["speaker_person_id"],
            "metadata": {
                "main_caption_id": item["caption_id"],
                "source": "strong_caption_additions",
                "caption_start_sec": round(float(item["source_start_sec"]), 3),
                "caption_end_sec": round(float(item["source_end_sec"]), 3),
                "source_start_sec": round(float(item["source_start_sec"]), 3),
                "source_end_sec": round(float(item["source_end_sec"]), 3),
                "speaker_name": person["name"],
                "selection_reason": item["reason"],
                "full_reference_text": item["full_reference_text"],
            },
        }
        event.setdefault("overlays", []).append(overlay)
        event["overlays"].sort(key=lambda overlay: float(overlay.get("start", 0.0)) if isinstance(overlay, dict) else 0.0)
        added.append({**item, "status": "added", "event_id": event.get("event_id")})
    return added


def add_to_main_caption_plan() -> list[dict[str, Any]]:
    if not MAIN_CAPTION_PLAN_PATH.exists():
        return []
    plan = load_json(MAIN_CAPTION_PLAN_PATH)
    captions = plan.get("captions") if isinstance(plan.get("captions"), list) else []
    existing = {str(caption.get("caption_id")) for caption in captions}
    added: list[dict[str, Any]] = []
    for item in STRONG_ADDITIONS:
        if item["caption_id"] in existing:
            continue
        person = PEOPLE[item["speaker_person_id"]]
        captions.append(
            {
                "caption_id": item["caption_id"],
                "caption_no": item["caption_id"].replace("main_caption_", ""),
                "source": "strong_caption_additions",
                "source_match_method": "manual_semantic_review",
                "source_match_confidence": 0.82,
                "source_segment_id": None,
                "source_start_sec": round(float(item["source_start_sec"]), 3),
                "source_end_sec": round(float(item["source_end_sec"]), 3),
                "caption_start_sec": round(float(item["source_start_sec"]), 3),
                "caption_end_sec": round(float(item["source_end_sec"]), 3),
                "display_text": item["display_text"],
                "full_reference_text": item["full_reference_text"],
                "search_keys": [],
                "speaker_person_id": item["speaker_person_id"],
                "speaker_name": person["name"],
                "speaker_screen_position": person["screen_position"],
                "speaker_role": person["role"],
                "speaker_attribution_method": "manual_semantic_review",
                "speaker_attribution_confidence": 0.82,
                "selection_reason": item["reason"],
            }
        )
        added.append(item)
    if added:
        captions.sort(key=lambda caption: (float(caption.get("caption_start_sec") or 0.0), str(caption.get("caption_id"))))
        plan["captions"] = captions
        plan["updated_at"] = now_iso()
        plan.setdefault("policy", {})["strong_caption_additions"] = True
        dump_json(MAIN_CAPTION_PLAN_PATH, plan)
    return added


def main() -> None:
    edit_plan = load_json(EDIT_PLAN_PATH)
    edit_added = add_to_edit_plan(edit_plan)
    dump_json(EDIT_PLAN_PATH, edit_plan)
    main_plan_added = add_to_main_caption_plan()
    report = {
        "generated_at": now_iso(),
        "policy": "Add any remaining strong interviewee statements that are not already represented by existing captions.",
        "candidate_count": len(STRONG_ADDITIONS),
        "edit_plan_added_count": sum(1 for item in edit_added if item.get("status") == "added"),
        "edit_plan_results": edit_added,
        "main_caption_plan_added_count": len(main_plan_added),
        "main_caption_plan_added": main_plan_added,
    }
    dump_json(REPORT_PATH, report)
    print(json.dumps({"report": str(REPORT_PATH), "added": report["edit_plan_added_count"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
