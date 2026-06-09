from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "output" / "reports"
REFERENCE_ANALYSIS = REPORTS / "reference_image_analysis"
JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_transcript_artifact(text: str) -> bool:
    text = clean_text(text)
    artifacts = (
        "音声に忠実に文字起こしないでください",
    )
    return any(artifact in text for artifact in artifacts)


def load_content_window() -> dict[str, Any]:
    path = REPORTS / "content_window.json"
    payload = read_json(path, {})
    if isinstance(payload, dict) and payload.get("schema_version") == "content_window.v1":
        return payload
    return {
        "usable_master_range": {"start_sec": 0.0, "end_sec": None},
        "rules": {"exclude_before_start": False, "exclude_after_end_marker": False},
    }


def segment_in_content_window(segment: dict[str, Any], content_window: dict[str, Any]) -> bool:
    usable = content_window.get("usable_master_range") if isinstance(content_window.get("usable_master_range"), dict) else {}
    start_bound = float(usable.get("start_sec") or 0.0)
    end_bound_raw = usable.get("end_sec")
    end_bound = float(end_bound_raw) if end_bound_raw is not None else None
    start = float(segment.get("start") or 0.0)
    end = float(segment.get("end") or start)
    if start < start_bound:
        return False
    if end_bound is not None and end > end_bound:
        return False
    return True


def caption_text(text: str, *, max_chars: int = 34) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    punctuation = "。！？、,. "
    cut = max((text.rfind(mark, 0, max_chars + 1) for mark in punctuation), default=-1)
    if cut >= 10:
        return text[:cut].strip(" 、,.。")
    return text[:max_chars].strip()


def score_segment(segment: dict[str, Any]) -> float:
    text = clean_text(str(segment.get("text") or ""))
    duration = max(0.01, float(segment.get("end") or 0.0) - float(segment.get("start") or 0.0))
    length_score = min(1.0, len(text) / 80.0)
    density = min(1.0, len(text) / max(duration * 14.0, 1.0))
    keyword_bonus = 0.0
    for keyword in ("ドメイン", "専門", "顧客", "業務", "価値", "課題", "LayerX", "プロダクト", "事業", "現場"):
        if keyword in text:
            keyword_bonus += 0.08
    return round(min(1.0, 0.2 + length_score * 0.35 + density * 0.25 + keyword_bonus), 4)


def segment_id(segment: dict[str, Any], index: int) -> str:
    value = str(segment.get("segment_id") or "").strip()
    return value or f"seg_{index:06d}"


def topic_title(text: str, fallback_index: int) -> str:
    if "ドメイン" in text or "専門" in text:
        return "ドメインエキスパートの役割"
    if "顧客" in text or "課題" in text:
        return "顧客理解と課題発見"
    if "プロダクト" in text or "開発" in text:
        return "プロダクトへの接続"
    if "LayerX" in text or "事業" in text:
        return "LayerXで生きる専門性"
    return f"トピック {fallback_index}"


def build_topics(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []
    start = float(segments[0].get("start") or 0.0)
    end = float(segments[-1].get("end") or start)
    target_topic_seconds = 420.0
    topics = []
    cursor = start
    topic_index = 1
    while cursor < end:
        topic_end = min(end, cursor + target_topic_seconds)
        text = " ".join(
            clean_text(str(segment.get("text") or ""))
            for segment in segments
            if cursor <= float(segment.get("start") or 0.0) < topic_end
        )
        topics.append(
            {
                "topic_id": f"topic_{topic_index:03d}",
                "start": round(cursor, 3),
                "end": round(topic_end, 3),
                "title": topic_title(text, topic_index),
                "summary": caption_text(text, max_chars=90) if text else "Transcript topic pending review.",
            }
        )
        cursor = topic_end
        topic_index += 1
    return topics


def find_topic_id(topics: list[dict[str, Any]], time_value: float) -> str | None:
    for topic in topics:
        if float(topic.get("start") or 0.0) <= time_value < float(topic.get("end") or 0.0):
            return str(topic.get("topic_id"))
    return topics[-1]["topic_id"] if topics else None


def build_semantic_marks(transcript: dict[str, Any], content_window: dict[str, Any]) -> dict[str, Any]:
    segments = [
        segment
        for segment in transcript.get("segments", [])
        if clean_text(str(segment.get("text") or ""))
        and not is_transcript_artifact(str(segment.get("text") or ""))
        and segment_in_content_window(segment, content_window)
    ]
    topics = build_topics(segments)
    ranked = sorted(
        (
            {
                "segment": segment,
                "index": index,
                "score": score_segment(segment),
            }
            for index, segment in enumerate(segments, start=1)
        ),
        key=lambda item: item["score"],
        reverse=True,
    )
    highlights = []
    for order, item in enumerate(ranked[:12], start=1):
        segment = item["segment"]
        start = float(segment.get("start") or 0.0)
        end = float(segment.get("end") or start)
        text = clean_text(str(segment.get("text") or ""))
        highlights.append(
            {
                "id": f"hl_{order:03d}",
                "segment_id": segment_id(segment, item["index"]),
                "source_start": round(start, 3),
                "source_end": round(end, 3),
                "speaker_id": segment.get("speaker_id"),
                "score": item["score"],
                "reason": "Keyword density, segment length, and editorial phrase strength suggest this as a digest/main caption candidate.",
                "digest_caption": caption_text(text, max_chars=30),
                "recommended_duration": round(max(4.0, min(10.0, end - start)), 3),
                "topic_id": find_topic_id(topics, start),
            }
        )

    punchlines = []
    used_windows: list[float] = []
    for item in ranked:
        segment = item["segment"]
        start = float(segment.get("start") or 0.0)
        if any(abs(start - used) < 25.0 for used in used_windows):
            continue
        end = float(segment.get("end") or start)
        text = caption_text(str(segment.get("text") or ""), max_chars=34)
        if not text:
            continue
        used_windows.append(start)
        punchlines.append(
            {
                "start": round(start, 3),
                "end": round(min(end, start + 7.0), 3),
                "segment_id": segment_id(segment, item["index"]),
                "speaker_id": segment.get("speaker_id"),
                "text": text,
                "style": "strong_caption",
                "priority": item["score"],
                "topic_id": find_topic_id(topics, start),
            }
        )
        if len(punchlines) >= 40:
            break

    entity_terms = []
    full_text = "\n".join(clean_text(str(segment.get("text") or "")) for segment in segments)
    for entity, explanation in (
        ("LayerX", "Business workflow and AI software company."),
        ("ドメインエキスパート", "業務領域の深い知識をプロダクトや顧客価値に接続する役割。"),
        ("Bakuraku", "LayerXのバックオフィス業務支援プロダクト群。"),
    ):
        if entity in full_text:
            first = next((float(s.get("start") or 0.0) for s in segments if entity in str(s.get("text") or "")), 0.0)
            entity_terms.append(
                {
                    "entity": entity,
                    "first_mentioned_at": round(first, 3),
                    "explanation": explanation,
                    "display_duration": 6.0,
                }
            )

    return {
        "schema_version": "semantic_marks.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "status": "draft_from_transcript",
        "analysis_method": "project-local heuristic draft; requires editorial review before final render",
        "content_window_source": str(REPORTS / "content_window.json"),
        "highlight_candidates": highlights,
        "topics": topics,
        "entity_explainers": entity_terms,
        "punchline_subtitles": punchlines,
    }


def safe_source_out(media_duration: float, start: float, duration: float) -> float:
    return round(min(media_duration, start + duration), 3)


def media_duration(manifest: dict[str, Any], media_id: str) -> float:
    for item in manifest.get("media", []):
        if item.get("media_id") == media_id:
            try:
                return float(item.get("duration") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def sync_review_items(sync_map: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in sync_map.get("media_sync", []):
        if not isinstance(item, dict) or item.get("role") == "master":
            continue
        if item.get("manual_review_required") or float(item.get("confidence") or 0.0) < 0.9:
            items.append(item)
    return items


def trusted_camera_roles(sync_map: dict[str, Any]) -> list[dict[str, str]]:
    role_to_media = {
        "camera2": {"media_id": "cam_person_01", "person_id": "person_01"},
        "camera3": {"media_id": "cam_person_02", "person_id": "person_02"},
        "camera4": {"media_id": "cam_person_03", "person_id": "person_03"},
    }
    trusted: list[dict[str, str]] = []
    for item in sync_map.get("media_sync", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if role not in role_to_media:
            continue
        try:
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if item.get("sync_status") == "synced" and not item.get("manual_review_required") and confidence >= 0.9:
            trusted.append({"role": role, **role_to_media[role]})
    return trusted


def apply_reference_alignment(plan: dict[str, Any]) -> dict[str, Any]:
    plan["reference_image_analysis_source"] = str(REFERENCE_ANALYSIS / "manifest.json")
    for event in plan.get("timeline", []):
        if not isinstance(event, dict):
            continue
        layout = event.get("layout")
        if not isinstance(layout, dict):
            continue
        section = str(event.get("section") or "")
        layout_type = str(layout.get("type") or "")
        if section == "digest":
            layout["reference_alignment"] = {
                "reference_image_id": "annotation_sample_review_meeting",
                "analysis_path": str(REFERENCE_ANALYSIS / "annotation-sample2.json"),
                "apply": ["wide_group_context", "logo_title_style", "caption_safe_lower_zone"],
            }
        elif section == "bridge":
            layout["reference_alignment"] = {
                "reference_image_id": None,
                "apply": ["preserve_source_aspect", "no_interview_crop"],
            }
        elif event.get("event_id") == "main_intro_group":
            layout["reference_alignment"] = {
                "reference_image_id": "three_person_divided",
                "analysis_path": str(REFERENCE_ANALYSIS / "three-people-divided-sample.json"),
                "apply": ["balanced_three_person_face_positions", "physical_order", "topic_title_safe_area"],
            }
        elif layout_type == "single":
            layout["reference_alignment"] = {
                "reference_image_id": "single_person_nameplate",
                "analysis_path": str(REFERENCE_ANALYSIS / "left-person-with-name-plate-sample.json"),
                "apply": ["medium_closeup", "eyes_upper_third", "lower_nameplate_caption_safe_area"],
            }
        elif layout_type == "person_with_bio":
            layout["reference_alignment"] = {
                "reference_image_id": "person_introduction_bio_card",
                "analysis_path": str(REFERENCE_ANALYSIS / "person-introduction-sample.json"),
                "apply": ["opposite_side_bio_card", "large_person_crop", "bio_text_from_people_map"],
            }
        elif layout_type in {"split_grid", "speaker_reaction_pair"}:
            layout["reference_alignment"] = {
                "reference_image_id": "two_person_nameplate_split",
                "analysis_path": str(REFERENCE_ANALYSIS / "middle-and-right-people-with-name-plate-divided-sample.json"),
                "fallback_reference_image_id": "three_person_divided",
                "fallback_analysis_path": str(REFERENCE_ANALYSIS / "three-people-divided-sample.json"),
                "apply": ["stable_panel_order", "matched_face_scale", "thin_dividers"],
            }
        for overlay in event.get("overlays", []):
            if isinstance(overlay, dict) and overlay.get("type") == "entity_explainer":
                overlay["reference_alignment"] = {
                    "reference_image_id": "annotation_sample",
                    "analysis_path": str(REFERENCE_ANALYSIS / "annotation-sample.json"),
                    "apply": ["white_lower_card", "blue_label_tab", "caption_collision_avoidance"],
                }
    return plan


def build_edit_plan(
    manifest: dict[str, Any],
    semantic: dict[str, Any],
    sync: dict[str, Any],
    sync_map: dict[str, Any],
    content_window: dict[str, Any],
) -> dict[str, Any]:
    timeline = []
    cursor = 0.0
    offsets = sync.get("offsets") if isinstance(sync.get("offsets"), dict) else {}
    trusted_roles = trusted_camera_roles(sync_map)
    digest_highlights = semantic.get("highlight_candidates", [])[:5]
    for index, highlight in enumerate(digest_highlights, start=1):
        source_start = float(highlight.get("source_start") or 0.0)
        source_end = float(highlight.get("source_end") or source_start + 6.0)
        duration = min(9.0, max(4.0, source_end - source_start))
        timeline.append(
            {
                "event_id": f"digest_{index:03d}",
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "type": "source_clip",
                "section": "digest",
                "source": {"media_id": "group_wide", "in": round(source_start, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), source_start, duration)},
                "reference_source": {"media_id": "group_wide", "in": round(source_start, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), source_start, duration)},
                "layout": {"type": "wide_group", "crop_mode": "speaker_aware_pending"},
                "audio": {"mode": "source", "source_media_id": "group_wide", "fade_in": 0.08, "fade_out": 0.12},
                "overlays": [
                    {
                        "type": "topic_title",
                        "position": "top_right",
                        "text": "Domain Expert Digest",
                        "style_id": "opening_digest_top_right_title",
                    },
                    {
                        "type": "caption",
                        "start": 0.35,
                        "end": min(duration - 0.25, 6.5),
                        "text": highlight.get("digest_caption"),
                        "style_id": "opening_digest_sample_caption",
                    },
                ],
                "reason": highlight.get("reason"),
            }
        )
        cursor += duration

    company_duration = min(10.0, media_duration(manifest, "company_movie") or 10.0)
    timeline.append(
        {
            "event_id": "digest_to_main_company_movie",
            "timeline_start": round(cursor, 3),
            "timeline_end": round(cursor + company_duration, 3),
            "type": "source_clip",
            "section": "bridge",
            "source": {"media_id": "company_movie", "in": 0.0, "out": round(company_duration, 3)},
            "reference_source": {"media_id": "company_movie", "in": 0.0, "out": round(company_duration, 3)},
            "layout": {"type": "single", "crop_mode": "fit"},
            "audio": {"mode": "source"},
            "overlays": [],
            "reason": "Company movie bridge between the opening digest and main interview.",
        }
    )
    cursor += company_duration

    topics = semantic.get("topics", [])
    main_start = float(topics[0].get("start") or 0.0) if topics else 0.0
    intro_duration = 18.0
    timeline.append(
        {
            "event_id": "main_intro_group",
            "timeline_start": round(cursor, 3),
            "timeline_end": round(cursor + intro_duration, 3),
            "type": "source_clip",
            "section": "main",
            "source": {"media_id": "group_wide", "in": round(main_start, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), main_start, intro_duration)},
            "reference_source": {"media_id": "group_wide", "in": round(main_start, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), main_start, intro_duration)},
            "layout": {"type": "wide_group", "ensure_people_visible": ["person_01", "person_02", "person_03"], "safe_margin": 0.06},
            "audio": {"mode": "source", "source_media_id": "group_wide"},
            "overlays": [
                {"type": "lower_third_people", "people_source": "people_map", "anchor": "below_face", "style_id": "name_tag_reference_style"},
                {"type": "topic_title", "position": "top_right", "topic_id": topics[0]["topic_id"] if topics else None, "style_id": "opening_digest_top_right_title"},
            ],
            "reason": "Establish all participants at the start of the main section.",
        }
    )
    cursor += intro_duration

    for index, punchline in enumerate(semantic.get("punchline_subtitles", [])[:12], start=1):
        source_start = float(punchline.get("start") or 0.0)
        duration = 18.0
        selected = trusted_roles[(index - 1) % len(trusted_roles)] if trusted_roles else None
        if selected:
            selected_media = selected["media_id"]
            selected_role = selected["role"]
            selected_source_start = max(0.0, source_start + float(offsets.get(selected_role, 0.0)))
            layout = {
                "type": "single",
                "selected_media_id": selected_media,
                "target_person_id": selected["person_id"],
                "selection_reason": f"{selected_role} is sync-confirmed and usable for visual variety",
            }
        else:
            selected_media = "group_wide"
            selected_source_start = source_start
            layout = {"type": "wide_group", "selection_reason": "wide shot is the only fully trusted sync source"}
        timeline.append(
            {
                "event_id": f"main_segment_{index:03d}",
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "type": "source_clip",
                "section": "main",
                "source": {"media_id": selected_media, "in": round(selected_source_start, 3), "out": safe_source_out(media_duration(manifest, selected_media), selected_source_start, duration)},
                "reference_source": {"media_id": "group_wide", "in": round(source_start, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), source_start, duration)},
                "layout": layout,
                "audio": {"mode": "source", "source_media_id": "group_wide"},
                "overlays": [
                    {"type": "topic_title", "position": "top_right", "topic_id": punchline.get("topic_id"), "style_id": "opening_digest_top_right_title"},
                    {"type": "caption", "start": 1.0, "end": min(8.0, duration - 1.0), "text": punchline.get("text"), "style_id": "main_punchline_caption"},
                ],
                "reason": "Draft main-section beat from transcript-derived punchline candidate.",
            }
        )
        cursor += duration

    unresolved = [role for role in ("camera2", "camera3", "camera4") if role not in (sync.get("offsets") or {})]
    review_required = sync_review_items(sync_map)
    blockers = []
    if unresolved:
        blockers.append(f"sync offsets are missing for {', '.join(unresolved)}")
    if review_required:
        blockers.append(
            "manual sync review required for "
            + ", ".join(f"{item.get('role')} ({item.get('method')}, confidence {item.get('confidence')})" for item in review_required)
        )
    if not semantic.get("highlight_candidates"):
        blockers.append("semantic marks contain no highlight candidates")
    return apply_reference_alignment({
        "schema_version": "edit_plan.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "canvas": manifest.get("master_canvas") or {"width": 1920, "height": 1080, "fps": 30},
        "global_style_ref": "style_guide.v1",
        "status": "draft_ready_for_limited_preview" if not blockers else "draft_needs_sync_review",
        "sync_source": str(REPORTS / "app_sync_offsets.json"),
        "sync_map_source": str(REPORTS / "sync_map.json"),
        "content_window_source": str(REPORTS / "content_window.json"),
        "content_window": content_window.get("usable_master_range"),
        "timeline": timeline,
        "validation": {
            "ready_for_preview": bool(timeline and semantic.get("highlight_candidates")),
            "preview_scope": "sync_review_required" if review_required else "all_confirmed_sources",
            "blockers": blockers,
            "warnings": ["Draft generated from transcript heuristics; editorial review required before final render."],
        },
        "required_sequence": ["opening_digest", "company_movie_bridge", "main_interview"],
    })


def main() -> None:
    transcript = read_json(REPORTS / "transcript.json", {})
    if not transcript.get("segments"):
        raise SystemExit("transcript.json has no segments. Run transcribe_reference_only.py and start_analytics.py first.")
    manifest = read_json(REPORTS / "project_manifest.json", {})
    sync = read_json(REPORTS / "app_sync_offsets.json", {"offsets": {"master": 0.0}})
    sync_map = read_json(REPORTS / "sync_map.json", {})
    content_window = load_content_window()
    semantic = build_semantic_marks(transcript, content_window)
    edit_plan = build_edit_plan(manifest, semantic, sync, sync_map, content_window)
    write_json(REPORTS / "semantic_marks.json", semantic)
    write_json(REPORTS / "edit_plan.json", edit_plan)
    print(json.dumps({"semantic_marks": str(REPORTS / "semantic_marks.json"), "edit_plan": str(REPORTS / "edit_plan.json"), "edit_status": edit_plan["status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
