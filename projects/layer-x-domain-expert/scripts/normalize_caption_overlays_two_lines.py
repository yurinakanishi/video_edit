import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REVIEW_SCRIPT = PROJECT_ROOT / "scripts" / "export_caption_review_md.py"


def load_review_module() -> Any:
    spec = importlib.util.spec_from_file_location("caption_review_tools", REVIEW_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {REVIEW_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def clean_text(text: str) -> str:
    return " ".join(str(text).replace("、", "").split()).strip()


def unit_fits(review: Any, text: str) -> bool:
    lines = review.wrap_caption_text(text)
    return 1 <= len(lines) <= 2 and all(review.caption_line_fits(line) for line in lines)


def bad_unit(text: str) -> bool:
    text = clean_text(text)
    if len(text) < 6 and not text.endswith(("です", "ます", "こと", "ため", "価値", "役割")):
        return True
    return text.endswith(("という", "として", "ではなく", "だけで", "ことも", "ものでは", "感じを", "実", "経", "判", "こ", "とい"))


UNIT_SPLIT_OVERRIDES = {
    "ドメインエキスパートの役割というか重要性みたいなもので": ["ドメインエキスパートの役割というか", "重要性みたいなもので"],
    "足すだけでなく「なくていい」と言えることも価値": ["足すだけでなく", "「なくていい」と言えることも価値"],
    "実務家のプライドを無視していないかを気にしている": ["実務家のプライドを無視していないか", "気にしている"],
    "ドメインがない領域でも活躍できるスキルを身につけたい": ["ドメインがない領域でも", "活躍できるスキルを身につけたい"],
    "AIで作業者が分析できるようになる変化を支援したい": ["AIで作業者が分析できるようになる", "変化を支援したい"],
    "AIで専門家の経験を多くの人が得られるかもしれない": ["AIで専門家の経験を", "多くの人が得られるかもしれない"],
}


def split_text_units(review: Any, text: str) -> list[str]:
    remaining = clean_text(text)
    if hasattr(review, "split_caption_units"):
        return review.split_caption_units(remaining)
    if remaining in UNIT_SPLIT_OVERRIDES:
        return UNIT_SPLIT_OVERRIDES[remaining]
    units: list[str] = []
    while remaining:
        if unit_fits(review, remaining):
            units.append(remaining)
            break

        spans = review.protected_spans(remaining)
        semantic_cuts = set(review.caption_cut_candidates(remaining, spans))
        candidates = []
        for index in range(1, len(remaining)):
            if review.inside_protected_span(index, spans):
                continue
            prefix = remaining[:index].strip(" 、。！？")
            rest = remaining[index:].strip(" 、。！？")
            if not prefix or not rest or not unit_fits(review, prefix):
                continue
            bad_break = review.bad_caption_break(prefix)
            bad_start = review.bad_caption_start(rest)
            natural_boundary = getattr(review, "natural_caption_boundary", lambda left, right: not bad_break and not bad_start)
            if not natural_boundary(prefix, rest):
                continue
            bad_unit_penalty = 30 if bad_unit(prefix) or bad_unit(rest) else 0
            semantic_bonus = 12 if index in semantic_cuts else 0
            length_score = min(index, 40)
            penalty = (20 if bad_break else 0) + (20 if bad_start else 0) + bad_unit_penalty
            candidates.append((length_score + semantic_bonus - penalty, index, prefix, rest))

        if not candidates:
            semantic_candidates = []
            for index in semantic_cuts:
                prefix = remaining[:index].strip(" 、。！？")
                rest = remaining[index:].strip(" 、。！？")
                natural_boundary = getattr(review, "natural_caption_boundary", lambda left, right: True)
                if prefix and rest and unit_fits(review, prefix) and natural_boundary(prefix, rest):
                    semantic_candidates.append((len(prefix), index, prefix, rest))
            if semantic_candidates:
                _, _, prefix, rest = max(semantic_candidates, key=lambda item: item[0])
            else:
                cut = review.best_caption_cut(remaining, 2, spans)
                prefix = remaining[:cut].strip(" 、。！？")
                rest = remaining[cut:].strip(" 、。！？")
        else:
            _, _, prefix, rest = max(candidates, key=lambda item: (item[0], item[1]))

        if not prefix:
            units.append(remaining)
            break
        units.append(prefix)
        remaining = rest

    return units


def split_overlay(review: Any, overlay: dict[str, Any]) -> list[dict[str, Any]]:
    text = clean_text(str(overlay.get("text") or ""))
    if not text:
        return [overlay]
    units = split_text_units(review, text)
    if len(units) <= 1:
        overlay["text"] = units[0] if units else text
        return [overlay]

    start = float(overlay.get("start") or 0.0)
    end = float(overlay.get("end") or start)
    duration = max(0.0, end - start)
    gap = 0.1 if duration >= len(units) * 0.9 else 0.04
    slot = duration / len(units) if units else duration
    result = []
    base_caption_id = str(overlay.get("caption_id") or overlay.get("source_srt_index") or "caption")
    for index, unit in enumerate(units):
        next_overlay = deepcopy(overlay)
        part_start = start + slot * index
        part_end = start + slot * (index + 1)
        if index < len(units) - 1:
            part_end = max(part_start + 0.2, part_end - gap)
        next_overlay["start"] = round(part_start, 3)
        next_overlay["end"] = round(part_end, 3)
        next_overlay["text"] = unit
        next_overlay["caption_part"] = {
            "part_index": index + 1,
            "part_count": len(units),
            "original_text": text,
            "policy": "max_two_lines_per_caption",
        }
        if overlay.get("caption_id"):
            next_overlay["caption_id"] = f"{base_caption_id}_part{index + 1:02d}"
        result.append(next_overlay)
    return result


def caption_part_group_key(overlay: dict[str, Any]) -> tuple[str, str] | None:
    caption_part = overlay.get("caption_part") if isinstance(overlay.get("caption_part"), dict) else None
    if not caption_part or not caption_part.get("original_text"):
        return None
    caption_id = str(overlay.get("caption_id") or overlay.get("source_srt_index") or "caption")
    base_caption_id = caption_id.rsplit("_part", 1)[0]
    return base_caption_id, clean_text(str(caption_part.get("original_text") or ""))


def rebuild_split_part_group(review: Any, group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first = deepcopy(group[0])
    caption_part = first.get("caption_part") if isinstance(first.get("caption_part"), dict) else {}
    original_text = clean_text(str(caption_part.get("original_text") or first.get("text") or ""))
    if not original_text:
        return group
    start = min(float(item.get("start") or 0.0) for item in group)
    end = max(float(item.get("end") or start) for item in group)
    first["start"] = round(start, 3)
    first["end"] = round(max(end, start + 0.01), 3)
    first["text"] = original_text
    first.pop("caption_part", None)
    caption_id = str(first.get("caption_id") or "")
    if "_part" in caption_id:
        first["caption_id"] = caption_id.rsplit("_part", 1)[0]
    return split_overlay(review, first)


def normalize_plan(plan: dict[str, Any], review: Any) -> dict[str, Any]:
    events = plan["timeline"]["events"] if isinstance(plan.get("timeline"), dict) else plan.get("timeline", [])
    split_count = 0
    added_count = 0
    rebuilt_group_count = 0
    for event in events:
        overlays = event.get("overlays")
        if not isinstance(overlays, list):
            continue
        normalized = []
        index = 0
        while index < len(overlays):
            overlay = overlays[index]
            if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("text"):
                group_key = caption_part_group_key(overlay)
                if group_key:
                    group = [overlay]
                    index += 1
                    while index < len(overlays):
                        next_overlay = overlays[index]
                        if not isinstance(next_overlay, dict) or caption_part_group_key(next_overlay) != group_key:
                            break
                        group.append(next_overlay)
                        index += 1
                    split = rebuild_split_part_group(review, group)
                    rebuilt_group_count += 1
                else:
                    split = split_overlay(review, overlay)
                    index += 1
                if len(split) > 1:
                    split_count += 1
                    added_count += len(split) - 1
                normalized.extend(split)
            else:
                normalized.append(overlay)
                index += 1
        event["overlays"] = normalized

    existing_split_parts = 0
    split_source_keys = set()
    for event in events:
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        for overlay in overlays:
            if not isinstance(overlay, dict):
                continue
            caption_part = overlay.get("caption_part") if isinstance(overlay.get("caption_part"), dict) else None
            if not caption_part:
                continue
            existing_split_parts += 1
            split_source_keys.add(str(caption_part.get("original_text") or overlay.get("text") or ""))

    plan["caption_overlay_normalization"] = {
        "policy": "max_two_lines_per_caption",
        "split_long_caption_overlays": True,
        "newly_split_original_overlay_count": split_count,
        "newly_added_overlay_count": added_count,
        "rebuilt_existing_split_group_count": rebuilt_group_count,
        "current_split_source_count": len(split_source_keys),
        "current_split_part_overlay_count": existing_split_parts,
        "note": "Long captions are split into sequential 1-2 line overlays instead of rendering 3+ lines or shrinking text.",
    }
    return plan


def main() -> None:
    review = load_review_module()
    plan = read_json(EDIT_PLAN)
    plan = normalize_plan(plan, review)
    write_json(EDIT_PLAN, plan)
    print(json.dumps({"output": str(EDIT_PLAN), **plan["caption_overlay_normalization"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
