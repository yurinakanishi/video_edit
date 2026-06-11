from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "output" / "reports"
EDIT_PLAN_PATH = REPORTS_DIR / "edit_plan.json"
MAIN_CAPTION_PLAN_PATH = REPORTS_DIR / "main_caption_plan.json"
REPORT_PATH = REPORTS_DIR / "caption_condense_report.json"
WRAP_RULES_PATH = PROJECT_DIR / "scripts" / "caption_wrap_rules.py"


CONDENSE_TEXT: dict[str, str] = {
    "ドメインエキスパートチームがあるわけではなく労務やPDMなどそれぞれの立場から開発に関与している": "それぞれの立場から開発に関与している",
    "思いっきりキャリアチェンジみたいなのが頭の中にあったわけでもなかった": "大きなキャリアチェンジは考えていなかった",
    "もうこれやりたいですとかちょっと違和感ありますとかそういうのを結構普通に言いますよね": "やりたいことや違和感を普通に言える",
    "いわゆるAIが普及してきてエンジニアの人たちもすごい効率生産性も上がってるみたいな話もあると思うんですけど": "AIでエンジニアの生産性も上がっている",
    "開発とかそういうものにも関与する中で今後のキャリアって結構僕らも聞かれることってある": "開発に関わる中で今後のキャリアを考える",
    "大事だなとは思いますがそれが大前提としてAIが普及していくのは間違いないのでAIに逃げないみたいなところはバックオフィスでキャリアを築く上では絶対に必要だなと思います": "AIから逃げない姿勢はキャリアに必要",
    "その環境に自分を受けているというのは 今のところキャリア的な意味で間違いなく選んでいないなとは思います": "その環境を選んでよかったと思う",
    "よく言われるのが入った時にPDMにダメだったらまた経理に戻ればいいですよって言われてたんですよ": "PDMが合わなければ経理に戻ればいいと言われた",
    "今は結構ドメインのアドバンテージがあるっていいですけどそれがないところでも一定活躍できる": "ドメインがなくても活躍できる力を身につけたい",
    "もちろんエンジニアさんはプロだったんですけれどもそのあたりは思いを込めて作業量をチェック時間をすごく短縮するやりたいことをなるべく一つの機能の中に持ち込んであげるみたいなのは意識して作れた機能なんじゃないかなと思いますね": "作業量とチェック時間を短縮する機能を作れた",
    "そういう時に結構何だろう開発に関わっているやりがいみたいな感じのシーンもあったりしますね": "開発に関わるやりがいがある",
    "ある種それに乗っかってればいつの間にかそういう分析とかができるようになってたりとか": "AIに乗るだけで分析できるようになる",
    "こういうものをジョブローテーションの中に組み込んでみんなが経理とか労務とかバックオフィスの仕事を経験した上でそれぞれ活躍するみたいなそういうのができるとそれはそれで面白そうなんですよ": "バックオフィス経験を広く活かせると面白い",
    "よくある仕事なんですけどこれやっても結局本当にって言って聞きに来るみたいなのがめちゃめちゃあったりするんですよ": "不安があると結局人に聞きに来る",
    "なんでなんですかを絶対に逃がしてくれない": "「なんで？」を絶対に逃がしてくれない",
    "結構やっぱりバックオフィスの仕事って前提ミスが許されませんっていう通説としてあるじゃないですか": "バックオフィスの仕事は前提ミスが許されない通説がある",
    "ドメインがなくても活躍できる力を身につけたい": "ドメインがなくても活躍できる力を身につけたい",
    "ドメインの貯金がなくなったときの怖さがある": "ドメインの貯金がなくなる怖さがある",
    "AIに乗るだけで分析できるようになる": "AIに乗るだけで分析できるようになる",
    "属人化は今後大きく変わっていく可能性がある": "属人化は今後大きく変わる可能性がある",
    "過去の処理とかどういう風にやってたかを確認して": "過去の処理を確認する",
    "過去の処理をどうしていたか確認する": "過去の処理を確認する",
    "バックオフィス経験を広く活かせると面白い": "バックオフィス経験を広く活かせると面白い",
    "そうなんですよ。それ実務なんで自分取り換えればそういう": "実務経験は入れ替えがきく",
}


def load_wrap_rules() -> Any:
    spec = importlib.util.spec_from_file_location("caption_wrap_rules", WRAP_RULES_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {WRAP_RULES_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean_text(text: str) -> str:
    return " ".join(str(text or "").replace("、", "").split()).strip()


def source_text_for_overlay(overlay: dict[str, Any]) -> str:
    caption_part = overlay.get("caption_part") if isinstance(overlay.get("caption_part"), dict) else {}
    return clean_text(str(caption_part.get("original_text") or overlay.get("text") or ""))


def caption_line_count(wrap_rules: Any, text: str) -> int:
    return len(wrap_rules.wrap_caption_text(text))


def replacement_for(text: str) -> str | None:
    cleaned = clean_text(text)
    return CONDENSE_TEXT.get(cleaned)


def condense_overlay_group(
    wrap_rules: Any,
    group: list[dict[str, Any]],
    event: dict[str, Any],
    source_text: str,
    replacement: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    first = deepcopy(group[0])
    start = min(float(item.get("start") or 0.0) for item in group)
    end = max(float(item.get("end") or start) for item in group)
    first["start"] = round(start, 3)
    first["end"] = round(max(end, start + 0.01), 3)
    first["text"] = replacement
    first.pop("caption_part", None)
    first.setdefault("metadata", {})
    if isinstance(first["metadata"], dict):
        first["metadata"]["caption_condensed"] = True
        first["metadata"]["condensed_from"] = source_text
        first["metadata"]["condense_policy"] = "editorial_two_line_unit"
    caption_id = str(first.get("caption_id") or "")
    if "_part" in caption_id:
        first["caption_id"] = caption_id.rsplit("_part", 1)[0]

    report_item = {
        "event_id": event.get("event_id"),
        "section": event.get("section"),
        "caption_id": first.get("caption_id"),
        "source_text": source_text,
        "replacement": replacement,
        "source_overlay_count": len(group),
        "replacement_line_count": caption_line_count(wrap_rules, replacement),
        "replacement_lines": wrap_rules.wrap_caption_text(replacement),
    }
    return [first], report_item


def condense_edit_plan(plan: dict[str, Any], wrap_rules: Any) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    events = plan["timeline"]["events"] if isinstance(plan.get("timeline"), dict) else plan.get("timeline", [])
    for event in events:
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue
        next_overlays: list[dict[str, Any]] = []
        index = 0
        while index < len(overlays):
            overlay = overlays[index]
            if not isinstance(overlay, dict) or overlay.get("type") != "caption":
                next_overlays.append(overlay)
                index += 1
                continue

            source_text = source_text_for_overlay(overlay)
            replacement = replacement_for(source_text)
            if not replacement:
                next_overlays.append(overlay)
                index += 1
                continue

            group = [overlay]
            group_key = None
            caption_part = overlay.get("caption_part") if isinstance(overlay.get("caption_part"), dict) else None
            if caption_part and caption_part.get("original_text"):
                caption_id = str(overlay.get("caption_id") or "")
                group_key = (caption_id.rsplit("_part", 1)[0], source_text)
            index += 1
            if group_key:
                while index < len(overlays):
                    next_overlay = overlays[index]
                    if not isinstance(next_overlay, dict) or next_overlay.get("type") != "caption":
                        break
                    next_caption_part = (
                        next_overlay.get("caption_part")
                        if isinstance(next_overlay.get("caption_part"), dict)
                        else None
                    )
                    next_caption_id = str(next_overlay.get("caption_id") or "")
                    next_key = (
                        next_caption_id.rsplit("_part", 1)[0],
                        clean_text(str(next_caption_part.get("original_text") or ""))
                        if next_caption_part
                        else "",
                    )
                    if next_key != group_key:
                        break
                    group.append(next_overlay)
                    index += 1

            condensed, report_item = condense_overlay_group(wrap_rules, group, event, source_text, replacement)
            next_overlays.extend(condensed)
            changed.append(report_item)
        event["overlays"] = next_overlays
    return changed


def condense_main_caption_plan(caption_plan: dict[str, Any], wrap_rules: Any) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    captions = caption_plan.get("captions")
    if not isinstance(captions, list):
        return changed
    for caption in captions:
        source_text = clean_text(
            str(caption.get("full_reference_text") or caption.get("display_text") or "")
        )
        replacement = replacement_for(source_text) or replacement_for(str(caption.get("display_text") or ""))
        if not replacement:
            continue
        before = caption.get("display_text")
        caption["display_text"] = replacement
        caption["display_text_condensed"] = True
        caption["display_text_condensed_from"] = source_text
        changed.append(
            {
                "caption_id": caption.get("caption_id"),
                "caption_no": caption.get("caption_no"),
                "before": before,
                "replacement": replacement,
                "replacement_line_count": caption_line_count(wrap_rules, replacement),
                "replacement_lines": wrap_rules.wrap_caption_text(replacement),
            }
        )
    if changed:
        caption_plan["updated_at"] = now_iso()
        caption_plan.setdefault("policy", {})["condense_long_captions_to_two_line_units"] = True
    return changed


def main() -> None:
    wrap_rules = load_wrap_rules()
    plan = load_json(EDIT_PLAN_PATH)
    changed_overlays = condense_edit_plan(plan, wrap_rules)
    dump_json(EDIT_PLAN_PATH, plan)

    changed_plan_items: list[dict[str, Any]] = []
    if MAIN_CAPTION_PLAN_PATH.exists():
        caption_plan = load_json(MAIN_CAPTION_PLAN_PATH)
        changed_plan_items = condense_main_caption_plan(caption_plan, wrap_rules)
        dump_json(MAIN_CAPTION_PLAN_PATH, caption_plan)

    report = {
        "generated_at": now_iso(),
        "policy": {
            "goal": "Condense captions that would become 3+ lines or awkward sequential parts into editorial 1-2 line units.",
            "font_measured": True,
            "max_visual_lines": 2,
        },
        "changed_overlay_count": len(changed_overlays),
        "changed_overlays": changed_overlays,
        "changed_main_caption_plan_count": len(changed_plan_items),
        "changed_main_caption_plan_items": changed_plan_items,
    }
    dump_json(REPORT_PATH, report)
    print(
        json.dumps(
            {
                "changed_overlay_count": len(changed_overlays),
                "changed_main_caption_plan_count": len(changed_plan_items),
                "report": str(REPORT_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
