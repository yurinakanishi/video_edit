from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
MAIN_CAPTION_PLAN_PATH = REPORTS_DIR / "main_caption_plan.json"
DIGEST_QA_PATH = REPORTS_DIR / "digest_qa_selection.json"
REPORT_PATH = REPORTS_DIR / "caption_display_polish_report.json"


TEXT_REWRITES = {
    "何でも知ってそうな感じがあると思ってて": "何でも知ってそうに見える",
    "この辺へのハードルの高さ": "期待の高さがハードルになる",
    "すごい皆さんドメインの方めっちゃ調べてるんですよ": "ドメインをめっちゃ調べている",
    "それこそ労務だって役所とかに聞いたら": "役所は「やらなくていい」とは言えない",
    "実務家のプライドを無視していないかを気にしている": "現場のプライドを無視しない",
    "実務家じゃできないなっていうのは感じますね": "実務経験があるから判断できる",
    "開発は自分とは関係ないものだと思っていた": "開発は自分とは関係ないものだった",
    "勤怠を作るなら面白そうだと思ってLayerXに来た": "勤怠づくりに興味を持ってLayerXに来た",
    "足元何か重要性が上がっていると思うかというと": "ドメインエキスパートの重要性が上がっている",
    "AIって一瞬でできると思うんですよね": "AIなら一瞬でできるように見える",
    "その環境を選んでよかったと思う": "その環境を選んでよかった",
    "そこのある意味健全なプレッシャーというのが来た": "健全なプレッシャーがある",
    "自分たちに求められることは結構研ぎ澄まされてきている": "求められることが研ぎ澄まされている",
    "ちゃんと伝えるには背景まで整理して": "ちゃんと伝えるには背景まで整理する",
    "仕様をゴリゴリ書いていくというよりは": "仕様を書くより目的を考える",
    "はっきりさせるっていうのは結構こだわってやらなきゃいけない": "はっきりさせることにこだわる",
    "そういう思いとかその道筋を考えていくっていう": "そういう思いとかその道筋を考えていく",
    "ちょっと使いづらい機能になってしまうので": "使いづらい機能になってしまう",
    "実務知識を活かせるなら挑戦できると思った": "実務知識を活かせるなら挑戦できる",
    "コードを書けなくても開発に関われると思えた": "コードを書けなくても開発に関われる",
    "AIで専門家の経験を多くの人が得られるかもしれない": "AIで専門家の経験を多くの人が得られる",
}

REMOVE_TEXTS = {
    "ドメインエキスパートって言うと",
    "おすすめするんですよ",
    "めちゃめちゃおすすめですよ",
    "二人が開発に関わった背景が対談のテーマ",
    "ちょっと使いづらい機能になってしまうので",
    "使いづらい機能になってしまう",
    "最初はヒアリングから始まった",
    "製品をどう伝えるかを中心に担当した",
    "最初は製品をどう伝えるかを中心に担当した",
    "入口は採用体験や人事の勉強だった",
    "ドメインエキスパートの指揮官のようなやつとして期待している",
    "必要な情報を一つの画面で確認できるようにした",
    "PDMの仕事は日によって違う",
    "PDMはフェーズによって仕事内容が変わる",
    "開発に関わることは少し違うキャリアへの一歩",
    "家族には経理系の仕事だと説明していた",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(text: str) -> str:
    return " ".join(str(text or "").replace("、", "").split()).strip()


def rewrite_text(text: str) -> str | None:
    return TEXT_REWRITES.get(clean(text))


def polish_edit_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for event in plan.get("timeline", []):
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        kept_overlays = []
        for overlay in overlays:
            if not isinstance(overlay, dict) or overlay.get("type") != "caption":
                kept_overlays.append(overlay)
                continue
            before = str(overlay.get("text") or "")
            if clean(before) in REMOVE_TEXTS:
                changed.append(
                    {
                        "event_id": event.get("event_id"),
                        "section": event.get("section"),
                        "caption_id": overlay.get("caption_id"),
                        "before": before,
                        "after": None,
                        "action": "removed_weak_caption",
                    }
                )
                continue
            after = rewrite_text(before)
            if not after or after == before:
                kept_overlays.append(overlay)
                continue
            overlay["text"] = after
            metadata = overlay.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["display_text_polished"] = True
                metadata["display_text_polished_from"] = before
            changed.append(
                {
                    "event_id": event.get("event_id"),
                    "section": event.get("section"),
                    "caption_id": overlay.get("caption_id"),
                    "before": before,
                    "after": after,
                    "action": "rewritten",
                }
            )
            kept_overlays.append(overlay)
        event["overlays"] = kept_overlays
    return changed


def polish_caption_plan(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = load_json(path)
    changed: list[dict[str, Any]] = []
    captions = data.get("captions") if isinstance(data.get("captions"), list) else []
    kept_captions = []
    for caption in captions:
        before = str(caption.get("display_text") or "")
        if clean(before) in REMOVE_TEXTS:
            changed.append(
                {
                    "caption_id": caption.get("caption_id"),
                    "caption_no": caption.get("caption_no"),
                    "before": before,
                    "after": None,
                    "action": "removed_weak_caption",
                }
            )
            continue
        after = rewrite_text(before)
        if not after or after == before:
            kept_captions.append(caption)
            continue
        caption["display_text"] = after
        caption["display_text_polished"] = True
        caption["display_text_polished_from"] = before
        changed.append(
            {
                "caption_id": caption.get("caption_id"),
                "caption_no": caption.get("caption_no"),
                "before": before,
                "after": after,
                "action": "rewritten",
            }
        )
        kept_captions.append(caption)
    if changed:
        data["captions"] = kept_captions
        data["updated_at"] = now_iso()
        data.setdefault("policy", {})["polish_display_text_fragments"] = True
        data.setdefault("policy", {})["remove_weak_caption_fragments"] = True
        dump_json(path, data)
    return changed


def polish_digest_selection(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = load_json(path)
    changed: list[dict[str, Any]] = []

    def walk(node: Any, path_bits: list[str]) -> None:
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key in {"display_text", "caption", "text", "subtitle"} and isinstance(value, str):
                    if clean(value) in REMOVE_TEXTS:
                        node[key] = ""
                        changed.append({"path": ".".join(path_bits + [key]), "before": value, "after": "", "action": "removed_weak_caption"})
                        continue
                    after = rewrite_text(value)
                    if after and after != value:
                        node[key] = after
                        changed.append({"path": ".".join(path_bits + [key]), "before": value, "after": after, "action": "rewritten"})
                else:
                    walk(value, path_bits + [str(key)])
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, path_bits + [str(index)])

    walk(data, [])
    if changed:
        data["updated_at"] = now_iso()
        dump_json(path, data)
    return changed


def main() -> None:
    plan = load_json(EDIT_PLAN_PATH)
    changed_overlays = polish_edit_plan(plan)
    dump_json(EDIT_PLAN_PATH, plan)
    changed_main_plan = polish_caption_plan(MAIN_CAPTION_PLAN_PATH)
    changed_digest_selection = polish_digest_selection(DIGEST_QA_PATH)
    report = {
        "generated_at": now_iso(),
        "policy": "Replace unclear fragments and casual transcript wording with concise editorial display captions.",
        "rewrites": TEXT_REWRITES,
        "changed_overlay_count": len(changed_overlays),
        "changed_overlays": changed_overlays,
        "changed_main_caption_plan_count": len(changed_main_plan),
        "changed_main_caption_plan": changed_main_plan,
        "changed_digest_selection_count": len(changed_digest_selection),
        "changed_digest_selection": changed_digest_selection,
    }
    dump_json(REPORT_PATH, report)
    print(json.dumps({"report": str(REPORT_PATH), "changed_overlay_count": len(changed_overlays)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
