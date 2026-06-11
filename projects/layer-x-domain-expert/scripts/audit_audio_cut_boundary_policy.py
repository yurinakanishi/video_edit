from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
RENDER_SCRIPT = PROJECT_ROOT / "scripts" / "render_test_project1_style_preview.py"
REPORT = REPORTS / "audio_cut_boundary_policy_report.json"


def main() -> None:
    text = RENDER_SCRIPT.read_text(encoding="utf-8")
    segment_fn_start = text.index("def segment_audio_filter_chain")
    segment_fn_end = text.index("\n\ndef final_audio_filter_chain", segment_fn_start)
    segment_fn = text[segment_fn_start:segment_fn_end]
    final_fn_start = text.index("def final_audio_filter_chain")
    final_fn_end = text.index("\n\ndef single_person_crop_filter", final_fn_start)
    final_fn = text[final_fn_start:final_fn_end]

    stateful_filters = ["afftdn", "anlmdn", "acompressor", "dynaudnorm", "loudnorm"]
    stateful_in_segment = [name for name in stateful_filters if name in segment_fn]
    stateful_in_final = [name for name in stateful_filters if name in final_fn]
    payload = {
        "schema_version": "audio_cut_boundary_policy_report.v1",
        "project_id": "layer-x-domain-expert",
        "problem_found": "Previous render path applied denoise/compression/dynaudnorm inside every segment, causing filter state and loudness to reset at video cuts.",
        "fix_applied": "segment_audio_filter_chain now only resamples to 48 kHz; final_audio_filter_chain performs denoise/compression/dynaudnorm/loudnorm once on the concatenated timeline.",
        "segment_audio_filter_policy": "aresample_only",
        "stateful_filters_in_segment_audio": stateful_in_segment,
        "stateful_filters_in_final_audio": stateful_in_final,
        "ready": len(stateful_in_segment) == 0 and {"afftdn", "acompressor", "dynaudnorm", "loudnorm"}.issubset(set(stateful_in_final)),
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
