from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
EDIT_PLAN = REPORTS / "edit_plan.json"
REPORT = REPORTS / "audio_mix_plan.json"

INTERVIEW_MAIN_AUDIO_MEDIA_ID = "cam_person_02"
MEDIA_TO_ROLE = {
    "group_wide": "master",
    "cam_person_01": "camera2",
    "cam_person_02": "camera3",
    "cam_person_03": "camera4",
}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def duration(event: dict[str, Any]) -> float:
    return max(0.01, float(event.get("timeline_end") or 0.0) - float(event.get("timeline_start") or 0.0))


def mapped_time(source_media_id: str, source_time: float, target_media_id: str, offsets: dict[str, float]) -> float:
    source_role = MEDIA_TO_ROLE.get(source_media_id, "master")
    target_role = MEDIA_TO_ROLE.get(target_media_id, "master")
    shared_clock = float(source_time) - float(offsets.get(source_role, 0.0))
    return max(0.0, shared_clock + float(offsets.get(target_role, 0.0)))


def main() -> None:
    plan = read_json(EDIT_PLAN, {})
    offsets_payload = read_json(REPORTS / "app_sync_offsets.json", {"offsets": {"master": 0.0}})
    offsets = offsets_payload.get("offsets") if isinstance(offsets_payload.get("offsets"), dict) else {"master": 0.0}
    audit = read_json(REPORTS / "audio_source_quality_audit.json", {})
    events = plan["timeline"]["events"] if isinstance(plan.get("timeline"), dict) else plan.get("timeline", [])
    changed = []
    skipped = []
    for event in events:
        if not isinstance(event, dict):
            continue
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        if event.get("section") == "bridge" or source.get("media_id") == "company_movie":
            skipped.append({"event_id": event.get("event_id"), "reason": "company_movie_keeps_own_audio"})
            continue
        if event.get("section") not in {"digest", "main"}:
            continue
        reference = event.get("reference_source") if isinstance(event.get("reference_source"), dict) else source
        reference_media_id = str(reference.get("media_id") or source.get("media_id") or "group_wide")
        reference_in = float(reference.get("in") or source.get("in") or 0.0)
        audio_in = mapped_time(reference_media_id, reference_in, INTERVIEW_MAIN_AUDIO_MEDIA_ID, offsets)
        event["audio"] = {
            "mode": "single_interview_source",
            "source_media_id": INTERVIEW_MAIN_AUDIO_MEDIA_ID,
            "in": round(audio_in, 3),
            "out": round(audio_in + duration(event), 3),
            "timing_reference_media_id": reference_media_id,
            "timing_reference_in": round(reference_in, 3),
            "timing_reference_out": round(reference_in + duration(event), 3),
            "reason": "Use one continuous interview audio source through digest, main interview, and closing; do not switch audio source mid-video.",
        }
        changed.append(
            {
                "event_id": event.get("event_id"),
                "section": event.get("section"),
                "audio_media_id": INTERVIEW_MAIN_AUDIO_MEDIA_ID,
                "audio_in": round(audio_in, 3),
                "audio_out": round(audio_in + duration(event), 3),
                "timing_reference_media_id": reference_media_id,
            }
        )
    plan["audio_policy"] = {
        "schema_version": "audio_policy.v1",
        "interview_main_audio_media_id": INTERVIEW_MAIN_AUDIO_MEDIA_ID,
        "single_audio_source_for_interview": True,
        "no_mid_video_audio_source_switching": True,
        "company_movie_audio_policy": "company_movie_keeps_own_embedded_audio",
        "quality_audit_source": str(REPORTS / "audio_source_quality_audit.json"),
        "reason": "group_wide is the best transcript/reference source but does not include the separate final thanks take; cam_person_02 covers the synced main interview and closing with the best measured noise floor/SNR among continuous sources.",
    }
    write_json(EDIT_PLAN, plan)
    report = {
        "schema_version": "audio_mix_plan.v1",
        "project_id": "layer-x-domain-expert",
        "policy": plan["audio_policy"],
        "sync_offsets": offsets,
        "quality_recommendation": audit.get("recommendation"),
        "changed_event_count": len(changed),
        "skipped_event_count": len(skipped),
        "changed_events": changed,
        "skipped_events": skipped,
    }
    write_json(REPORT, report)
    print(json.dumps({"edit_plan": str(EDIT_PLAN), "report": str(REPORT), "changed_event_count": len(changed)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
