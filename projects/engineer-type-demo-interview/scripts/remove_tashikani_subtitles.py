from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_DIR / "project_state.json"
REPORT_PATH = PROJECT_DIR / "output" / "reports" / "remove_tashikani_subtitles_report.json"
TARGET_PATTERN = "確かに"

PUNCTUATION = "、。，．,.!?！？"
LEADING_PUNCT_RE = re.compile(rf"^[\s{re.escape(PUNCTUATION)}]+")
TRAILING_PUNCT_RE = re.compile(rf"[\s{re.escape(PUNCTUATION)}]+$")


@dataclass
class Cue:
    index: str
    timing: str
    lines: list[str]


def load_default_srt() -> Path:
    if not STATE_PATH.exists():
        raise FileNotFoundError(f"Project state is missing: {STATE_PATH}")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    subtitle_path = state.get("render", {}).get("subtitlePath")
    if not subtitle_path:
        raise ValueError("render.subtitlePath is not set in project_state.json")
    return Path(subtitle_path)


def parse_srt(text: str) -> list[Cue]:
    cues: list[Cue] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return cues

    for block in re.split(r"\n{2,}", normalized):
        rows = block.split("\n")
        if len(rows) < 3:
            continue
        cues.append(Cue(index=rows[0].strip(), timing=rows[1].strip(), lines=rows[2:]))
    return cues


def trim_punctuation(text: str) -> str:
    previous = None
    current = text
    while previous != current:
        previous = current
        current = LEADING_PUNCT_RE.sub("", current)
        current = TRAILING_PUNCT_RE.sub("", current)
    return current.strip()


def clean_line(line: str) -> str:
    text = line.strip()
    if TARGET_PATTERN not in text:
        return text

    # Remove filler prefixes such as "確かに。", "確かにな", and "なるほど確かに".
    text = re.sub(
        rf"^(?:なるほど)?\s*確かに(?:な)?(?:\s*[{re.escape(PUNCTUATION)}]\s*)*",
        "",
        text,
    )

    # Remove any remaining exact filler phrase without touching unrelated words like
    # "明確に" or "確立".
    text = re.sub(r"確かに(?:な)?", "", text)

    text = trim_punctuation(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def serialize_srt(cues: list[Cue]) -> str:
    blocks: list[str] = []
    for cue in cues:
        blocks.append("\n".join([cue.index, cue.timing, *cue.lines]))
    return "\n\n".join(blocks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove '確かに' phrases from the active project SRT subtitles.")
    parser.add_argument("--srt", type=Path, default=None, help="Override subtitle SRT path.")
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help="JSON report path.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a timestamped backup.")
    args = parser.parse_args()

    srt_path = args.srt or load_default_srt()
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT is missing: {srt_path}")

    original_text = srt_path.read_text(encoding="utf-8")
    cues = parse_srt(original_text)
    updated_cues: list[Cue] = []
    changes: list[dict[str, object]] = []

    for cue in cues:
        before_text = "\n".join(cue.lines)
        cleaned_lines = [clean_line(line) for line in cue.lines]
        cleaned_lines = [line for line in cleaned_lines if line.strip()]
        after_text = "\n".join(cleaned_lines)

        if after_text != before_text:
            action = "deleted" if not cleaned_lines else "updated"
            changes.append(
                {
                    "index": cue.index,
                    "timing": cue.timing,
                    "action": action,
                    "before": before_text,
                    "after": after_text,
                }
            )

        if cleaned_lines:
            updated_cues.append(Cue(index=cue.index, timing=cue.timing, lines=cleaned_lines))

    updated_text = serialize_srt(updated_cues)
    backup_path = None
    if updated_text != original_text:
        if not args.no_backup:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = srt_path.with_name(f"{srt_path.stem}.before_tashikani_removal_{stamp}{srt_path.suffix}")
            shutil.copy2(srt_path, backup_path)
        srt_path.write_text(updated_text, encoding="utf-8", newline="\n")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "srtPath": str(srt_path),
        "backupPath": str(backup_path) if backup_path else None,
        "totalCuesBefore": len(cues),
        "totalCuesAfter": len(updated_cues),
        "changedCues": len(changes),
        "deletedCues": sum(1 for item in changes if item["action"] == "deleted"),
        "updatedCues": sum(1 for item in changes if item["action"] == "updated"),
        "changes": changes,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("changedCues", "deletedCues", "updatedCues")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
