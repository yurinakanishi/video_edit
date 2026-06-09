from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = PROJECT_ROOT / "reference"
REPORTS = PROJECT_ROOT / "output" / "reports"
ANALYSIS_DIR = REPORTS / "reference_image_analysis"
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


def rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("/", "\\")


REFERENCE_ANALYSIS: dict[str, dict[str, Any]] = {
    "annotation-sample.png": {
        "reference_image_id": "annotation_sample",
        "layout_types": ["speaker_reaction_pair", "entity_explainer"],
        "intended_sections": ["main_interview_topic_explainer", "two_person_exchange"],
        "framing": {
            "composition": "two_person_split_with_logo_topic_and_explainer",
            "subject_crop": "medium close-up to medium shot; shoulders and upper torso visible",
            "face_position": "left subject face centered near x=0.23,y=0.28; right subject face centered near x=0.74,y=0.30",
            "panel_order_rule": "preserve conversation-role order; interviewer left when included",
            "divider": {"orientation": "vertical", "x_norm": 0.5, "color": "#8EC6FF", "width_norm": 0.006},
            "safe_margins_norm": {"x": 0.035, "top": 0.07, "bottom": 0.18},
        },
        "overlay_style": {
            "logo": {"position": "top_left", "x_norm": 0.03, "y_norm": 0.035, "width_norm": 0.18},
            "topic_title": {"position": "top_right", "background": "#5F5AF5", "text": "white bold", "height_norm": 0.09},
            "entity_explainer": {
                "position": "lower_third",
                "label_tab": "#5F5AF5",
                "body": "white card with dense black Japanese text",
                "avoid_caption_overlap": True,
            },
        },
        "render_directives": [
            "Use for short term/entity explanations during a focused two-person exchange.",
            "Keep faces above the explainer card and outside the top logo/title band.",
            "Crop each panel so eyes sit in the upper third and microphones/hands remain visible when context matters.",
        ],
    },
    "annotation-sample2.png": {
        "reference_image_id": "annotation_sample_review_meeting",
        "layout_types": ["wide_group", "entity_explainer", "review_context"],
        "intended_sections": ["opening_digest", "main_interview_contextual_explainer"],
        "framing": {
            "composition": "wide_three_person_review_meeting_with_explainer",
            "subject_crop": "wide group crop; table, laptop, microphones, and all visible participants retained",
            "face_position": "group faces distributed across upper-middle band, roughly y=0.25-0.42",
            "safe_margins_norm": {"x": 0.04, "top": 0.09, "bottom": 0.23},
            "context_priority": "retain table and object context when explaining meeting format or process",
        },
        "overlay_style": {
            "logo": {"position": "top_left", "x_norm": 0.03, "y_norm": 0.04, "width_norm": 0.17},
            "topic_title": {"position": "top_right", "background": "#5F5AF5", "text": "white bold"},
            "entity_explainer": {"position": "bottom", "body": "white wide card", "label_tab": "#5F5AF5"},
        },
        "render_directives": [
            "Use when the edit needs a contextual group view rather than a tight speaker crop.",
            "Do not crop out laptops, microphones, mugs, or table context if they support the topic.",
            "Place captions above or separate from the explainer card; never stack readable text blocks directly on top of each other.",
        ],
    },
    "left-person-with-name-plate-sample.png": {
        "reference_image_id": "single_person_nameplate",
        "layout_types": ["single", "lower_third_person"],
        "intended_sections": ["participant_identification"],
        "framing": {
            "composition": "single_person_medium_closeup_with_large_nameplate",
            "subject_crop": "upper torso crop with breathing room above head and shoulders visible",
            "face_position": "face centered around x=0.48,y=0.28; eyes near upper third",
            "safe_margins_norm": {"x": 0.06, "top": 0.09, "bottom": 0.22},
            "background": "office context kept softly visible, not cropped to a plain backdrop",
        },
        "overlay_style": {
            "logo": {"position": "top_left", "x_norm": 0.03, "y_norm": 0.04, "width_norm": 0.18},
            "topic_title": {"position": "top_right", "background": "#5F5AF5", "text": "white bold"},
            "nameplate": {
                "position": "lower_center",
                "role_line": "white bold with blue-purple outline/shadow above plate",
                "name_box": "#5F5AF5 solid rectangle with very large white name",
                "width_norm": 0.56,
            },
        },
        "render_directives": [
            "Use this only for participant introduction or first clear identification cuts.",
            "Keep the subject large enough that facial expression reads clearly; avoid cutting off the microphone.",
            "Name, title, and role text must come from people_map.json.",
            "Do not render caption subtitles during the interval where the nameplate is visible.",
        ],
    },
    "middle-and-right-people-with-name-plate-divided-sample.png": {
        "reference_image_id": "two_person_nameplate_split",
        "layout_types": ["split_grid", "speaker_reaction_pair"],
        "intended_sections": ["two_person_exchange"],
        "framing": {
            "composition": "two_equal_vertical_panels_with_nameplates",
            "subject_crop": "each person medium close-up; shoulders and microphone visible",
            "face_position": "left panel face around x=0.27,y=0.30; right panel face around x=0.74,y=0.28",
            "divider": {"orientation": "vertical", "x_norm": 0.5, "color": "#8EC6FF", "width_norm": 0.006},
            "panel_order_rule": "if interviewer is included, interviewer panel stays left; if middle/right only, middle stays left and right stays right",
        },
        "overlay_style": {
            "logo": {"position": "top_left", "x_norm": 0.03, "y_norm": 0.04, "width_norm": 0.18},
            "topic_title": {"position": "top_right", "background": "#5F5AF5", "text": "white bold"},
            "nameplate": {"current_project_policy": "do_not_render_nameplates_in_split_layouts"},
        },
        "render_directives": [
            "Use for important exchanges where both faces should remain readable.",
            "Keep panel order stable; do not swap panels to chase the active speaker.",
            "Do not show nameplates in split layouts for this project; reserve large nameplates for single-person introduction cuts.",
        ],
    },
    "person-introduction-sample.png": {
        "reference_image_id": "person_introduction_bio_card",
        "layout_types": ["person_with_bio", "bio_card"],
        "intended_sections": ["participant_self_introduction", "main_interview_intro"],
        "framing": {
            "composition": "large biography panel plus person crop",
            "subject_crop": "person side medium close-up with head and upper torso visible",
            "face_position": "person face around x=0.73,y=0.31 when bio card is left; mirror when person is left",
            "bio_panel": {"width_norm": 0.48, "x_norm": 0.03, "y_norm": 0.05, "height_norm": 0.89},
            "safe_margins_norm": {"x": 0.035, "top": 0.05, "bottom": 0.05},
        },
        "overlay_style": {
            "bio_card": {
                "background": "#5F5AF5",
                "title": "white centered bold with horizontal separator",
                "bullets": "large white text, generous line spacing",
                "source": "people_map.bio_bullets",
            }
        },
        "render_directives": [
            "Use for self-introduction ranges where a participant's background is being established.",
            "Place the biography card on the side opposite the visible person.",
            "Do not hard-code biographies; use people_map.bio_bullets only.",
        ],
    },
    "three-people-divided-sample.png": {
        "reference_image_id": "three_person_divided",
        "layout_types": ["split_grid", "wide_group", "three_person_divided"],
        "intended_sections": ["main_intro_group", "group_reaction", "multi_participant_moment"],
        "framing": {
            "composition": "three_equal_vertical_panels",
            "subject_crop": "each participant fills their column with face and upper torso visible",
            "face_position": "faces centered in each column around y=0.28-0.34",
            "divider": {"orientation": "vertical", "color": "#8EC6FF", "width_norm": 0.006},
            "panel_order_rule": "left participant, middle participant, right participant in physical seating order",
            "safe_margins_norm": {"x": 0.025, "top": 0.08, "bottom": 0.08},
        },
        "overlay_style": {
            "logo": {"position": "top_left", "x_norm": 0.03, "y_norm": 0.04, "width_norm": 0.18},
            "topic_title": {"position": "top_right", "background": "#5F5AF5", "text": "white bold"},
        },
        "render_directives": [
            "Use when all three participants or the group dynamic should be visible.",
            "Keep all faces at comparable size and vertical position.",
            "Use thin blue/light-green dividers and avoid large lower text blocks unless needed.",
        ],
    },
}


def image_meta(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "width": image.width,
            "height": image.height,
            "aspect_ratio": round(image.width / image.height, 6) if image.height else None,
            "mode": image.mode,
        }


def build_payload(path: Path, analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "reference_image_analysis.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "source_image": rel(path),
        "image": image_meta(path),
        "analysis_basis": "manual visual analysis of project reference still",
        **analysis,
        "application_policy": {
            "adapt_to_video_context": True,
            "do_not_render_reference_image_directly": True,
            "match_framing_crop_face_position_and_visual_style": True,
            "allow_mirroring_when_layout_requires_opposite_bio_side": True,
        },
    }


def update_style_guide(manifest: dict[str, Any]) -> None:
    path = REPORTS / "style_guide.json"
    style = read_json(path, {})
    style.setdefault("style_sources", {})
    style["style_sources"]["reference_image_analysis_manifest"] = str(ANALYSIS_DIR / "manifest.json")
    style["style_sources"]["reference_image_analysis"] = {
        item["reference_image_id"]: item["analysis_path"] for item in manifest["references"]
    }
    style.setdefault("reference_alignment", {})
    style["reference_alignment"].update(
        {
            "opening_digest": {
                "reference_image_id": "annotation_sample_review_meeting",
                "analysis_path": str(ANALYSIS_DIR / "annotation-sample2.json"),
                "alignment_goal": "wide group context with branded logo/title and digest caption space",
            },
            "company_movie_bridge": {
                "reference_image_id": None,
                "alignment_goal": "fit the source movie cleanly; no interview reference crop applied",
            },
            "main_intro_group": {
                "reference_image_id": "three_person_divided",
                "analysis_path": str(ANALYSIS_DIR / "three-people-divided-sample.json"),
                "alignment_goal": "all participants visible with balanced face size and stable physical order",
            },
            "main_single_speaker": {
                "reference_image_id": "single_person_nameplate",
                "analysis_path": str(ANALYSIS_DIR / "left-person-with-name-plate-sample.json"),
                "alignment_goal": "medium close-up, face in upper third, name/caption-safe lower area",
            },
            "self_introduction": {
                "reference_image_id": "person_introduction_bio_card",
                "analysis_path": str(ANALYSIS_DIR / "person-introduction-sample.json"),
                "alignment_goal": "large person crop paired with opposite-side biography panel",
            },
            "two_person_exchange": {
                "reference_image_id": "two_person_nameplate_split",
                "analysis_path": str(ANALYSIS_DIR / "middle-and-right-people-with-name-plate-divided-sample.json"),
                "alignment_goal": "stable panel order and comparable face positions",
            },
            "entity_explainer": {
                "reference_image_id": "annotation_sample",
                "analysis_path": str(ANALYSIS_DIR / "annotation-sample.json"),
                "alignment_goal": "white lower explainer card with blue-purple label tab, no caption collision",
            },
        }
    )
    write_json(path, style)


def update_edit_plan() -> None:
    path = REPORTS / "edit_plan.json"
    plan = read_json(path, {})
    if not isinstance(plan.get("timeline"), list):
        return
    plan["reference_image_analysis_source"] = str(ANALYSIS_DIR / "manifest.json")
    for event in plan["timeline"]:
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
                "analysis_path": str(ANALYSIS_DIR / "annotation-sample2.json"),
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
                "analysis_path": str(ANALYSIS_DIR / "three-people-divided-sample.json"),
                "apply": ["balanced_three_person_face_positions", "physical_order", "topic_title_safe_area"],
            }
        elif layout_type == "single":
            layout["reference_alignment"] = {
                "reference_image_id": "single_person_nameplate",
                "analysis_path": str(ANALYSIS_DIR / "left-person-with-name-plate-sample.json"),
                "apply": ["medium_closeup", "eyes_upper_third", "lower_nameplate_caption_safe_area"],
            }
        elif layout_type == "person_with_bio":
            layout["reference_alignment"] = {
                "reference_image_id": "person_introduction_bio_card",
                "analysis_path": str(ANALYSIS_DIR / "person-introduction-sample.json"),
                "apply": ["opposite_side_bio_card", "large_person_crop", "bio_text_from_people_map"],
            }
        elif layout_type in {"split_grid", "speaker_reaction_pair"}:
            layout["reference_alignment"] = {
                "reference_image_id": "two_person_nameplate_split",
                "analysis_path": str(ANALYSIS_DIR / "middle-and-right-people-with-name-plate-divided-sample.json"),
                "fallback_reference_image_id": "three_person_divided",
                "fallback_analysis_path": str(ANALYSIS_DIR / "three-people-divided-sample.json"),
                "apply": ["stable_panel_order", "matched_face_scale", "thin_dividers"],
            }
        for overlay in event.get("overlays", []):
            if isinstance(overlay, dict) and overlay.get("type") == "entity_explainer":
                overlay["reference_alignment"] = {
                    "reference_image_id": "annotation_sample",
                    "analysis_path": str(ANALYSIS_DIR / "annotation-sample.json"),
                    "apply": ["white_lower_card", "blue_label_tab", "caption_collision_avoidance"],
                }
    write_json(path, plan)


def main() -> None:
    references = []
    for filename, analysis in sorted(REFERENCE_ANALYSIS.items()):
        source = REFERENCE_ROOT / filename
        if not source.exists():
            raise SystemExit(f"Reference image missing: {source}")
        payload = build_payload(source, analysis)
        output = ANALYSIS_DIR / f"{source.stem}.json"
        write_json(output, payload)
        references.append(
            {
                "reference_image_id": analysis["reference_image_id"],
                "source_image": rel(source),
                "analysis_path": str(output),
                "layout_types": analysis["layout_types"],
                "intended_sections": analysis["intended_sections"],
            }
        )

    manifest = {
        "schema_version": "reference_image_analysis_manifest.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "references": references,
        "rules": {
            "section_layouts_must_reference_analysis": True,
            "match_framing_crop_face_position_and_visual_style": True,
            "adapt_reference_to_video_context": True,
        },
    }
    write_json(ANALYSIS_DIR / "manifest.json", manifest)
    update_style_guide(manifest)
    update_edit_plan()
    print(json.dumps({"manifest": str(ANALYSIS_DIR / "manifest.json"), "references": len(references)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
