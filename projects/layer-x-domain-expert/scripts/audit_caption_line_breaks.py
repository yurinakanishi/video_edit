from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "caption_line_break_audit.json"
REVIEW_SCRIPT = PROJECT_ROOT / "scripts" / "export_caption_review_md.py"
JST = timezone(timedelta(hours=9))


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def caption_overlays(plan: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    events = plan["timeline"]["events"] if isinstance(plan.get("timeline"), dict) else plan.get("timeline", [])
    rows = []
    for event in events:
        overlays = event.get("overlays") if isinstance(event.get("overlays"), list) else []
        for overlay in overlays:
            if isinstance(overlay, dict) and overlay.get("type") == "caption" and overlay.get("text"):
                rows.append((event, overlay))
    return rows


def line_break_indexes(lines: list[str]) -> list[int]:
    indexes = []
    cursor = 0
    for line in lines[:-1]:
        cursor += len(line)
        indexes.append(cursor)
    return indexes


def audit_caption(event: dict[str, Any], overlay: dict[str, Any], review: Any) -> list[dict[str, Any]]:
    text = review.clean_caption_text(str(overlay.get("text") or "")) if hasattr(review, "clean_caption_text") else " ".join(str(overlay.get("text") or "").split())
    lines = review.wrap_caption_text(text)
    issues = []
    if len(lines) > 2:
        issues.append({"reason": "more_than_two_lines", "lines": lines})
    for line in lines:
        line_fits = review.caption_line_fits(line)
        if not line_fits and len(lines) == 1 and hasattr(review, "caption_single_line_font_size"):
            line_fits = review.caption_single_line_font_size(line) is not None
        if not line_fits:
            issues.append({"reason": "line_does_not_fit_caption_box", "line": line})
    spans = review.protected_spans(text)
    for index in line_break_indexes(lines):
        left = text[:index]
        right = text[index:]
        if hasattr(review, "invalid_caption_cut") and review.invalid_caption_cut(text, index, spans):
            issues.append({"reason": "line_break_inside_protected_or_word_span", "left": left, "right": right, "lines": lines})
        elif not review.natural_caption_boundary(left, right):
            issues.append({"reason": "unnatural_line_boundary", "left": left, "right": right, "lines": lines})
    return [
        {
            "event_id": event.get("event_id"),
            "section": event.get("section"),
            "caption_id": overlay.get("caption_id"),
            "caption_no": overlay.get("caption_no"),
            "text": text,
            **issue,
        }
        for issue in issues
    ]


def main() -> None:
    review = load_review_module()
    plan = read_json(EDIT_PLAN)
    rows = caption_overlays(plan)
    issues = []
    for event, overlay in rows:
        issues.extend(audit_caption(event, overlay, review))
    payload = {
        "schema_version": "caption_line_break_audit.v2",
        "project_id": "layer-x-domain-expert",
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "policy": "Rendered caption lines must be one or two lines, fit the caption box, and must not break inside protected terms, katakana words, latin tokens, or suffix fragments.",
        "checked_caption_overlays": len(rows),
        "issue_count": len(issues),
        "issues": issues,
    }
    write_json(REPORT, payload)
    print(json.dumps({"output": str(REPORT), "checked_caption_overlays": len(rows), "issue_count": len(issues)}, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
