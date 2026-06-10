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

PERSON_CAMERA = {
    "person_01": {"media_id": "cam_person_01", "role": "camera2"},
    "person_02": {"media_id": "cam_person_02", "role": "camera3"},
    "person_03": {"media_id": "cam_person_03", "role": "camera4"},
}

INTRODUCTION_CUES = [
    {
        "event_id": "intro_person_02_nemoto",
        "person_id": "person_02",
        "master_in": 623.52,
        "duration": 14.0,
        "reason": "根本さんの自己紹介開始に合わせて、単独カメラで大きなネームプレートを表示。",
    },
    {
        "event_id": "intro_person_03_murata",
        "person_id": "person_03",
        "master_in": 675.06,
        "duration": 14.0,
        "reason": "村田さんの自己紹介開始に合わせて、単独カメラで大きなネームプレートを表示。",
    },
    {
        "event_id": "intro_person_01_yano",
        "person_id": "person_01",
        "master_in": 727.46,
        "duration": 14.0,
        "reason": "矢野さんの自己紹介開始に合わせて、単独カメラで大きなネームプレートを表示。",
    },
]


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


def load_speaker_activity() -> dict[str, dict[str, Any]]:
    payload = read_json(REPORTS / "speaker_activity_analysis.json", {})
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("segments", []):
        if isinstance(item, dict) and item.get("segment_id"):
            result[str(item["segment_id"])] = item
    return result


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


def editorial_caption(text: str, *, max_chars: int = 34) -> str:
    text = clean_text(text)
    rules = [
        (("ヒアリング",), "顧客の声を聞くところから始まる"),
        (("ドメイン", "アドバンテージ"), "ドメイン知識がプロダクトの強みになる"),
        (("バックオフィス", "プロダクト"), "現場理解をプロダクトの価値へつなげる"),
        (("ジョブローテーション",), "経験を循環させてドメイン理解を広げる"),
        (("プロダクトマネージャー", "コード"), "コードだけではないプロダクトづくり"),
        (("経理", "ローム", "ドメイン"), "実務の専門性が開発の前提になる"),
        (("専門家", "実務家"), "実務家のプライドをプロダクトに活かす"),
        (("顧客", "課題"), "顧客理解から課題を見つける"),
        (("AI", "活用"), "AI活用にもドメイン理解が効いてくる"),
        (("手で", "バックオフィス"), "手作業の業務をプロダクトで変えていく"),
        (("プロダクト", "興味がなかった"), "入社前はプロダクトに強い興味はなかった"),
        (("いきなり", "難しい"), "何もないところから専門性は育たない"),
        (("それぞれのプロダクト",), "プロダクトごとの思いを理解して作る"),
        (("共通点", "プロダクト開発", "ドメイン"), "ドメイン知識を開発に接続する"),
    ]
    for keywords, caption in rules:
        if all(keyword in text for keyword in keywords):
            return caption
    return caption_text(text, max_chars=max_chars)


def editorial_candidate_score(text: str) -> float:
    text = clean_text(text)
    if not text:
        return -1.0
    weak_markers = ("よろしくお願いします", "ありがとうございます", "大丈夫ですか", "緊張感", "休憩室", "QK", "3社目です")
    if any(marker in text for marker in weak_markers):
        return -0.5
    score = 0.0
    for keyword in ("ドメイン", "専門", "顧客", "業務", "価値", "課題", "プロダクト", "事業", "現場", "ヒアリング", "バックオフィス", "AI", "経理", "労務"):
        if keyword in text:
            score += 0.18
    concrete_markers = ("する", "できる", "つな", "始ま", "活用", "関与", "理解", "作")
    if any(marker in text for marker in concrete_markers):
        score += 0.2
    if 18 <= len(text) <= 90:
        score += 0.15
    return score


def score_segment(segment: dict[str, Any]) -> float:
    text = clean_text(str(segment.get("text") or ""))
    duration = max(0.01, float(segment.get("end") or 0.0) - float(segment.get("start") or 0.0))
    length_score = min(1.0, len(text) / 80.0)
    density = min(1.0, len(text) / max(duration * 14.0, 1.0))
    keyword_bonus = 0.0
    for keyword in ("ドメイン", "専門", "顧客", "業務", "価値", "課題", "LayerX", "プロダクト", "事業", "現場"):
        if keyword in text:
            keyword_bonus += 0.08
    return round(min(1.0, 0.2 + length_score * 0.25 + density * 0.2 + keyword_bonus + max(0.0, editorial_candidate_score(text)) * 0.35), 4)


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
    ranked_all = sorted(
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
    ranked = [item for item in ranked_all if editorial_candidate_score(str(item["segment"].get("text") or "")) > 0.35]
    if len(ranked) < 12:
        ranked = ranked + [item for item in ranked_all if item not in ranked]
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
                "digest_caption": editorial_caption(text, max_chars=30),
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
        text = editorial_caption(str(segment.get("text") or ""), max_chars=34)
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


def synced_source_start_for_person(person_id: str, master_time: float, offsets: dict[str, Any]) -> tuple[str, float]:
    camera = PERSON_CAMERA[person_id]
    role = camera["role"]
    try:
        offset = float(offsets.get(role, 0.0))
    except (TypeError, ValueError):
        offset = 0.0
    return camera["media_id"], max(0.0, master_time + offset)


def digest_speaker_activity(highlight: dict[str, Any], activity_by_segment: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    segment_id = str(highlight.get("segment_id") or "")
    activity = activity_by_segment.get(segment_id)
    if activity and activity.get("active_person_id") in {"person_02", "person_03"}:
        return activity
    return None


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


def ordered_people(left: str, right: str) -> list[str]:
    seating_order = ["person_01", "person_02", "person_03"]
    pair = [left, right]
    return [person_id for person_id in seating_order if person_id in pair]


def provisional_media_ids(person_ids: list[str], sync_map: dict[str, Any]) -> list[str]:
    media_to_item = {item.get("media_id"): item for item in sync_map.get("media_sync", []) if isinstance(item, dict)}
    result = []
    for person_id in person_ids:
        media_id = PERSON_CAMERA.get(person_id, {}).get("media_id")
        item = media_to_item.get(media_id)
        if media_id and (not item or item.get("manual_review_required") or float(item.get("confidence") or 0.0) < 0.9):
            result.append(media_id)
    return result


def choose_layout_from_activity(
    punchline: dict[str, Any],
    activity: dict[str, Any] | None,
    sync_map: dict[str, Any],
) -> tuple[str, float, dict[str, Any]]:
    source_start = float(punchline.get("start") or 0.0)
    text = str(punchline.get("text") or "")
    if not activity:
        return (
            "group_wide",
            source_start,
            {
                "type": "wide_group",
                "ensure_people_visible": ["person_01", "person_02", "person_03"],
                "selection_reason": "No speaker activity analysis available for this segment; use group-safe coverage.",
            },
        )

    active = str(activity.get("active_person_id") or "")
    reaction = str(activity.get("reaction_person_id") or "")
    confidence = float(activity.get("confidence") or 0.0)
    scores = activity.get("activity_scores") if isinstance(activity.get("activity_scores"), list) else []
    top = float((scores[0] or {}).get("score") or 0.0) if scores else 0.0
    second = float((scores[1] or {}).get("score") or 0.0) if len(scores) > 1 else 0.0
    third = float((scores[2] or {}).get("score") or 0.0) if len(scores) > 2 else 0.0

    if active not in PERSON_CAMERA:
        return (
            "group_wide",
            source_start,
            {
                "type": "wide_group",
                "ensure_people_visible": ["person_01", "person_02", "person_03"],
                "speaker_activity": activity,
                "selection_reason": "Speaker activity confidence is low, so a wide group shot is safer than a false speaker cut.",
            },
        )

    multi_person = second >= top * 0.82 and third >= top * 0.62
    if multi_person:
        people = ["person_01", "person_02", "person_03"]
        media_ids = [PERSON_CAMERA[person_id]["media_id"] for person_id in people]
        layout = {
            "type": "split_grid",
            "media_ids": media_ids,
            "grid_strategy": "three_person_vertical_split",
            "panel_order": people,
            "active_person_id": active,
            "reaction_person_ids": [person_id for person_id in people if person_id != active],
            "speaker_activity": activity,
            "divider": {"color": "#B7E6C1", "width_px_at_base": 6},
            "selection_reason": "Three visible participants show comparable activity, so use a three-way divided reference cut.",
        }
        provisional = provisional_media_ids(people, sync_map)
        if provisional:
            layout["uses_provisional_media_ids"] = provisional
        return "group_wide", source_start, layout

    if confidence < 0.48:
        return (
            "group_wide",
            source_start,
            {
                "type": "wide_group",
                "ensure_people_visible": ["person_01", "person_02", "person_03"],
                "speaker_activity": activity,
                "selection_reason": "Speaker activity confidence is low and not clearly multi-person, so a wide group shot is safer than a false speaker cut.",
            },
        )

    question_like = any(token in text for token in ("ですか", "ますか", "どう", "お二人", "?"))
    exchange_like = active == "person_01" or question_like or (reaction in PERSON_CAMERA and second >= top * 0.58)
    if exchange_like and reaction in PERSON_CAMERA:
        people = ordered_people(active, reaction)
        media_ids = [PERSON_CAMERA[person_id]["media_id"] for person_id in people]
        layout = {
            "type": "split_grid",
            "media_ids": media_ids,
            "grid_strategy": "two_person_vertical_split",
            "panel_order": people,
            "active_person_id": active,
            "reaction_person_ids": [person_id for person_id in people if person_id != active],
            "speaker_activity": activity,
            "divider": {"color": "#B7E6C1", "width_px_at_base": 6},
            "selection_reason": "Two-up selected because the active speaker and strongest reaction candidate form the conversational exchange.",
        }
        provisional = provisional_media_ids(people, sync_map)
        if provisional:
            layout["uses_provisional_media_ids"] = provisional
        return "group_wide", source_start, layout

    selected = PERSON_CAMERA[active]
    layout = {
        "type": "single",
        "selected_media_id": selected["media_id"],
        "target_person_id": active,
        "speaker_activity": activity,
        "selection_reason": "Single-speaker close-up selected because mouth-motion analysis identifies one dominant active speaker.",
    }
    return selected["media_id"], source_start, layout


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
                "reference_image_id": "single_person_fullscreen_intro_white_text",
                "analysis_path": str(REFERENCE_ANALYSIS / "single-person-introduction-name-subtitle-reference.json"),
                "apply": ["full_screen_left_person_closeup", "lower_left_white_role_name", "match_single_intro_reference"],
            }
        elif layout_type == "single":
            layout["reference_alignment"] = {
                "reference_image_id": "single_person_fullscreen_intro_white_text",
                "analysis_path": str(REFERENCE_ANALYSIS / "single-person-introduction-name-subtitle-reference.json"),
                "apply": ["medium_closeup", "eyes_upper_third", "lower_left_white_role_name"],
            }
        elif layout_type == "person_with_bio":
            layout["reference_alignment"] = {
                "reference_image_id": "person_introduction_bio_card",
                "analysis_path": str(REFERENCE_ANALYSIS / "person-introduction-sample.json"),
                "apply": ["opposite_side_bio_card", "large_person_crop", "bio_text_from_people_map"],
            }
        elif layout_type in {"split_grid", "speaker_reaction_pair"}:
            layout["reference_alignment"] = {
                "reference_image_id": "two_person_split_intro_white_names",
                "analysis_path": str(REFERENCE_ANALYSIS / "two-person-split-introduction-name-subtitle-reference.json"),
                "fallback_reference_image_id": "three_person_divided",
                "fallback_analysis_path": str(REFERENCE_ANALYSIS / "three-people-divided-sample.json"),
                "apply": ["stable_panel_order", "matched_face_scale", "per_panel_white_name_labels"],
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
    activity_by_segment = load_speaker_activity()
    middle_right_digest = [
        highlight
        for highlight in semantic.get("highlight_candidates", [])
        if digest_speaker_activity(highlight, activity_by_segment)
    ]
    digest_highlights = middle_right_digest[:5]
    if len(digest_highlights) < 5:
        digest_highlights.extend(
            highlight
            for highlight in semantic.get("highlight_candidates", [])
            if highlight not in digest_highlights and float(highlight.get("source_start") or 0.0) >= 620.0
        )
    digest_highlights = digest_highlights[:5]
    for index, highlight in enumerate(digest_highlights, start=1):
        source_start = float(highlight.get("source_start") or 0.0)
        source_end = float(highlight.get("source_end") or source_start + 6.0)
        duration = min(9.0, max(4.0, source_end - source_start))
        activity = digest_speaker_activity(highlight, activity_by_segment)
        target_person_id = str((activity or {}).get("active_person_id") or "person_02")
        if target_person_id not in {"person_02", "person_03"}:
            target_person_id = "person_02"
        selected_media, selected_source_start = synced_source_start_for_person(target_person_id, source_start, offsets)
        timeline.append(
            {
                "event_id": f"digest_{index:03d}",
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "type": "source_clip",
                "section": "digest",
                "source": {"media_id": selected_media, "in": round(selected_source_start, 3), "out": safe_source_out(media_duration(manifest, selected_media), selected_source_start, duration)},
                "reference_source": {"media_id": "group_wide", "in": round(source_start, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), source_start, duration)},
                "layout": {
                    "type": "single",
                    "crop_mode": "person_centered",
                    "selected_media_id": selected_media,
                    "target_person_id": target_person_id,
                    "speaker_activity": activity,
                    "selection_reason": "Opening digest excludes the left participant and uses the middle/right close-up when that participant is detected as speaking.",
                },
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

    company_duration = media_duration(manifest, "company_movie") or 8.0
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
            "reason": "Full company movie bridge between the opening digest and main interview; do not cut it midway.",
        }
    )
    cursor += company_duration

    topics = semantic.get("topics", [])
    main_start = float(topics[0].get("start") or 0.0) if topics else 0.0
    intro_topic = topics[0]["topic_id"] if topics else None

    def append_wide_intro(event_id: str, master_in: float, master_out: float, reason: str) -> None:
        nonlocal cursor
        duration = master_out - master_in
        timeline.append(
            {
                "event_id": event_id,
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "type": "source_clip",
                "section": "main",
                "source": {"media_id": "group_wide", "in": round(master_in, 3), "out": round(master_out, 3)},
                "reference_source": {"media_id": "group_wide", "in": round(master_in, 3), "out": round(master_out, 3)},
                "layout": {"type": "wide_group", "ensure_people_visible": ["person_01", "person_02", "person_03"], "safe_margin": 0.06},
                "audio": {"mode": "source", "source_media_id": "group_wide"},
                "overlays": [
                    {"type": "topic_title", "position": "top_right", "topic_id": intro_topic, "style_id": "opening_digest_top_right_title"},
                ],
                "reason": reason,
            }
        )
        cursor += duration

    def append_yano_intro(event_id: str, master_in: float, master_out: float, *, show_name: bool, reason: str) -> None:
        nonlocal cursor
        duration = master_out - master_in
        media_id, source_start = synced_source_start_for_person("person_01", master_in, offsets)
        overlays = [{"type": "topic_title", "position": "top_right", "topic_id": intro_topic, "style_id": "opening_digest_top_right_title"}]
        if show_name:
            overlays.append(
                {
                    "type": "lower_third_person",
                    "person_id": "person_01",
                    "people_source": "people_map",
                    "anchor": "lower_left",
                    "style_id": "single_intro_white_text_reference",
                    "start": 0.0,
                    "end": duration,
                }
            )
        timeline.append(
            {
                "event_id": event_id,
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "type": "source_clip",
                "section": "main",
                "source": {"media_id": media_id, "in": round(source_start, 3), "out": safe_source_out(media_duration(manifest, media_id), source_start, duration)},
                "reference_source": {"media_id": "group_wide", "in": round(master_in, 3), "out": round(master_out, 3)},
                "layout": {
                    "type": "single",
                    "selected_media_id": media_id,
                    "target_person_id": "person_01",
                    "crop_mode": "single_intro_reference_fullscreen",
                    "introduction_nameplate": show_name,
                    "selection_reason": "Show the speaking left participant close-up, matching the one-person introduction reference.",
                },
                "audio": {"mode": "continuous_reference", "source_media_id": "group_wide"},
                "overlays": overlays,
                "caption_policy": "no_caption_while_nameplate_visible" if show_name else "editorial_captions_allowed",
                "reason": reason,
            }
        )
        cursor += duration

    def append_two_person_intro(event_id: str, master_in: float, master_out: float, active_person_id: str, *, show_labels: bool, reason: str) -> None:
        nonlocal cursor
        duration = master_out - master_in
        people = ["person_02", "person_03"]
        media_ids = [PERSON_CAMERA[item]["media_id"] for item in people]
        overlays = [{"type": "topic_title", "position": "top_right", "topic_id": intro_topic, "style_id": "opening_digest_top_right_title"}]
        if show_labels:
            overlays.append(
                {
                    "type": "split_person_labels",
                    "person_ids": people,
                    "people_source": "people_map",
                    "style_id": "two_person_intro_white_names_reference",
                    "start": 0.0,
                    "end": duration,
                }
            )
        timeline.append(
            {
                "event_id": event_id,
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + duration, 3),
                "type": "source_clip",
                "section": "main",
                "source": {"media_id": "group_wide", "in": round(master_in, 3), "out": round(master_out, 3)},
                "reference_source": {"media_id": "group_wide", "in": round(master_in, 3), "out": round(master_out, 3)},
                "layout": {
                    "type": "split_grid",
                    "media_ids": media_ids,
                    "grid_strategy": "two_person_intro_vertical_split",
                    "panel_order": people,
                    "active_person_id": active_person_id,
                    "reaction_person_ids": [item for item in people if item != active_person_id],
                    "introduction_nameplate": show_labels,
                    "selection_reason": "Show the two interviewees in split view when they are introduced by name.",
                },
                "audio": {"mode": "source", "source_media_id": "group_wide"},
                "overlays": overlays,
                "caption_policy": "no_caption_while_nameplate_visible" if show_labels else "editorial_captions_allowed",
                "reason": reason,
            }
        )
        cursor += duration

    append_wide_intro("main_intro_group_greeting", 519.14, 524.94, "Initial greeting must show all three participants.")
    append_yano_intro("main_intro_yano_self", 524.94, 532.10, show_name=True, reason="Cut to Yano close-up exactly when he says he is Yano; keep his name visible throughout.")
    append_wide_intro("main_intro_wide_after_yano", 532.10, 535.54, "Briefly return to the three-person camera before introducing the two guests.")
    append_two_person_intro("main_intro_two_guests_named", 535.54, 546.54, "person_02", show_labels=True, reason="At '根本さんと…', cut to the two-person split and show both names.")
    append_yano_intro("main_intro_yano_explains_001", 546.54, 561.54, show_name=False, reason="Yano continues the setup; cut back to the speaking person.")
    append_wide_intro("main_intro_wide_context_001", 561.54, 576.54, "Wide context cut to keep pacing around 15 seconds.")
    append_yano_intro("main_intro_yano_explains_002", 576.54, 591.54, show_name=False, reason="Yano explains the domain expert role; show the speaker.")
    append_two_person_intro("main_intro_two_guest_reaction", 591.54, 606.54, "person_02", show_labels=False, reason="Reaction cut to the introduced guests while keeping the 15-second rhythm.")
    append_yano_intro("main_intro_yano_prompt_selfintro", 606.54, 623.52, show_name=False, reason="Yano asks the guests to introduce themselves; show the speaker.")

    intro_ranges = [
        {**INTRODUCTION_CUES[0], "duration": 47.54},
        {
            "event_id": "intro_between_nemoto_murata",
            "person_id": None,
            "master_in": 671.06,
            "duration": 4.0,
            "reason": "Keep the handoff to 村田さん without cutting the introduction.",
        },
        {**INTRODUCTION_CUES[1], "duration": 47.44},
    ]

    for cue in intro_ranges:
        if cue["person_id"] is None:
            master_in = float(cue["master_in"])
            cue_duration = float(cue["duration"])
            timeline.append(
                {
                    "event_id": cue["event_id"],
                    "timeline_start": round(cursor, 3),
                    "timeline_end": round(cursor + cue_duration, 3),
                    "type": "source_clip",
                    "section": "main",
                    "source": {"media_id": "group_wide", "in": round(master_in, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), master_in, cue_duration)},
                    "reference_source": {"media_id": "group_wide", "in": round(master_in, 3), "out": safe_source_out(media_duration(manifest, "group_wide"), master_in, cue_duration)},
                    "layout": {"type": "wide_group", "ensure_people_visible": ["person_01", "person_02", "person_03"], "safe_margin": 0.06},
                    "audio": {"mode": "source", "source_media_id": "group_wide"},
                    "overlays": [
                        {"type": "topic_title", "position": "top_right", "topic_id": topics[0]["topic_id"] if topics else None, "style_id": "opening_digest_top_right_title"},
                    ],
                    "reason": cue["reason"],
                }
            )
            cursor += cue_duration
            continue
        person_id = cue["person_id"]
        master_in = float(cue["master_in"])
        cue_duration = float(cue["duration"])
        if person_id in {"person_02", "person_03"}:
            people = ["person_02", "person_03"]
            media_ids = [PERSON_CAMERA[item]["media_id"] for item in people]
            timeline.append(
                {
                    "event_id": cue["event_id"],
                    "timeline_start": round(cursor, 3),
                    "timeline_end": round(cursor + cue_duration, 3),
                    "type": "source_clip",
                    "section": "main",
                    "source": {
                        "media_id": "group_wide",
                        "in": round(master_in, 3),
                        "out": safe_source_out(media_duration(manifest, "group_wide"), master_in, cue_duration),
                    },
                    "reference_source": {
                        "media_id": "group_wide",
                        "in": round(master_in, 3),
                        "out": safe_source_out(media_duration(manifest, "group_wide"), master_in, cue_duration),
                    },
                    "layout": {
                        "type": "split_grid",
                        "media_ids": media_ids,
                        "grid_strategy": "two_person_intro_vertical_split",
                        "panel_order": people,
                        "active_person_id": person_id,
                        "reaction_person_ids": [item for item in people if item != person_id],
                        "introduction_nameplate": True,
                        "selection_reason": "After the left-person self-introduction, identify the two interviewees together in a two-person split matching the new reference.",
                    },
                    "audio": {"mode": "continuous_reference", "source_media_id": "group_wide"},
                    "overlays": [
                        {"type": "topic_title", "position": "top_right", "topic_id": topics[0]["topic_id"] if topics else None, "style_id": "opening_digest_top_right_title"},
                        {
                            "type": "split_person_labels",
                            "person_ids": people,
                            "people_source": "people_map",
                            "style_id": "two_person_intro_white_names_reference",
                            "start": 0.25,
                            "end": cue_duration,
                        },
                    ],
                    "caption_policy": "no_caption_while_nameplate_visible",
                    "reason": cue["reason"],
                }
            )
            cursor += cue_duration
            continue
        selected_media, source_start = synced_source_start_for_person(person_id, master_in, offsets)
        timeline.append(
            {
                "event_id": cue["event_id"],
                "timeline_start": round(cursor, 3),
                "timeline_end": round(cursor + cue_duration, 3),
                "type": "source_clip",
                "section": "main",
                "source": {
                    "media_id": selected_media,
                    "in": round(source_start, 3),
                    "out": safe_source_out(media_duration(manifest, selected_media), source_start, cue_duration),
                },
                "reference_source": {
                    "media_id": "group_wide",
                    "in": round(master_in, 3),
                    "out": safe_source_out(media_duration(manifest, "group_wide"), master_in, cue_duration),
                },
                "layout": {
                    "type": "single",
                    "selected_media_id": selected_media,
                    "target_person_id": person_id,
                    "crop_mode": "person_centered",
                    "introduction_nameplate": True,
                    "selection_reason": "Introduction nameplate cuts must show one participant at a time, not a split layout.",
                },
                "audio": {"mode": "source", "source_media_id": "group_wide"},
                "overlays": [
                    {
                        "type": "lower_third_person",
                        "person_id": person_id,
                        "people_source": "people_map",
                        "anchor": "lower_center",
                        "style_id": "name_tag_reference_style",
                        "start": 0.25,
                        "end": min(cue_duration - 0.25, 8.5),
                    }
                ],
                "caption_policy": "no_caption_while_nameplate_visible",
                "reason": cue["reason"],
            }
        )
        cursor += cue_duration

    for index, punchline in enumerate(semantic.get("punchline_subtitles", [])[:12], start=1):
        source_start = float(punchline.get("start") or 0.0)
        duration = 15.0
        activity = activity_by_segment.get(str(punchline.get("segment_id") or ""))
        selected_media, selected_source_start, layout = choose_layout_from_activity(punchline, activity, sync_map)
        if selected_media in ("cam_person_01", "cam_person_02", "cam_person_03"):
            role = MEDIA_TO_ROLE = {"cam_person_01": "camera2", "cam_person_02": "camera3", "cam_person_03": "camera4"}[selected_media]
            selected_source_start = max(0.0, source_start + float(offsets.get(role, 0.0)))
        else:
            selected_source_start = source_start
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
        "speaker_activity_source": str(REPORTS / "speaker_activity_analysis.json"),
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
