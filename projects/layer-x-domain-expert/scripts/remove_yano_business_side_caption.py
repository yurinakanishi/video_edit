from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
MAIN_CAPTION_PLAN = REPORTS / "main_caption_plan.json"
REPORT = REPORTS / "removed_yano_business_side_caption.json"

REMOVE_TEXT = "矢野さんはLayerXで初めて事業側の仕事に関わった"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    payload = read_json(MAIN_CAPTION_PLAN)
    captions = payload.get("captions") if isinstance(payload, dict) else []
    kept = []
    removed = []
    for caption in captions:
        if isinstance(caption, dict) and str(caption.get("display_text") or "") == REMOVE_TEXT:
            removed.append(caption)
        else:
            kept.append(caption)
    payload["captions"] = kept
    write_json(MAIN_CAPTION_PLAN, payload)
    write_json(
        REPORT,
        {
            "schema_version": "removed_yano_business_side_caption.v1",
            "project_id": "layer-x-domain-expert",
            "removed_text": REMOVE_TEXT,
            "removed_count": len(removed),
            "removed_items": removed,
        },
    )
    print(json.dumps({"removed_count": len(removed), "report": str(REPORT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
