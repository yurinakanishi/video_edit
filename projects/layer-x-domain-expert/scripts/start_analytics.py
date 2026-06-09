from __future__ import annotations

import argparse
import json
import struct
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "source"
OUTPUT_ROOT = PROJECT_ROOT / "output"
REPORTS = OUTPUT_ROOT / "reports"
CONFIG = PROJECT_ROOT / "config"
STATE_PATH = PROJECT_ROOT / "project_state.json"
TRANSCRIPT_MANIFEST_DIR = OUTPUT_ROOT / "transcripts" / "manifest_sources"
FFPROBE_DEFAULT = Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe")
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


def require(path: Path) -> Path:
    if not path.exists():
        raise SystemExit(f"Required project source is missing: {path}")
    return path


def ffprobe_path(state: dict[str, Any]) -> str:
    configured = (((state.get("tools") or {}).get("ffprobe")) or "").strip()
    if configured and Path(configured).exists():
        return configured
    if FFPROBE_DEFAULT.exists():
        return str(FFPROBE_DEFAULT)
    return "ffprobe"


def probe_video(path: Path, ffprobe: str) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    raw = json.loads(result.stdout)
    streams = raw.get("streams", [])
    fmt = raw.get("format", {})
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    fps = fps_from_rate(str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"))
    return {
        "duration": round(float(fmt.get("duration") or 0.0), 3),
        "hasVideo": bool(video),
        "hasAudio": bool(audio),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fps,
        "videoCodec": video.get("codec_name"),
        "avgFrameRate": video.get("avg_frame_rate"),
        "audioCodec": audio.get("codec_name"),
        "sampleRate": int(audio.get("sample_rate") or 0) if audio else None,
        "channels": int(audio.get("channels") or 0) if audio else None,
        "storage": "project-source",
    }


def fps_from_rate(rate: str) -> float:
    if "/" in rate:
        numerator, denominator = rate.split("/", 1)
        try:
            den = float(denominator)
            return round(float(numerator) / den, 6) if den else 0.0
        except ValueError:
            return 0.0
    try:
        return round(float(rate), 6)
    except ValueError:
        return 0.0


def png_dimensions(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return {"codec": path.suffix.lower().lstrip("."), "storage": "project-source"}
    width, height = struct.unpack(">II", header[16:24])
    return {"width": width, "height": height, "codec": "png", "storage": "project-source"}


def project_media() -> list[dict[str, Any]]:
    return [
        {
            "media_id": "group_wide",
            "app_id": "group-wide",
            "label": "Group wide",
            "path": require(SOURCE_ROOT / "video" / "three people.mp4"),
            "kind": "video",
            "project_role": "group_wide",
            "app_role": "master",
            "camera_index": 1,
            "sync_offset": 0.0,
            "screen_position": "wide",
            "originalPath": r"C:\Users\yurin\Downloads\C0007-007.MP4",
        },
        {
            "media_id": "cam_person_01",
            "app_id": "cam-person-01",
            "label": "Left participant camera",
            "path": require(SOURCE_ROOT / "video" / "person-left.mp4"),
            "kind": "video",
            "project_role": "single_person",
            "app_role": "camera2",
            "camera_index": 2,
            "sync_offset": 0.0,
            "screen_position": "left",
            "person_id_hint": "person_01",
            "originalPath": r"C:\Users\yurin\Downloads\C0011-002.MP4",
        },
        {
            "media_id": "cam_person_02",
            "app_id": "cam-person-02",
            "label": "Middle participant camera",
            "path": require(SOURCE_ROOT / "video" / "person-middle.mp4"),
            "kind": "video",
            "project_role": "single_person",
            "app_role": "camera3",
            "camera_index": 3,
            "sync_offset": 0.0,
            "screen_position": "middle",
            "person_id_hint": "person_02",
            "originalPath": r"C:\Users\yurin\Downloads\C0484-003.MP4",
        },
        {
            "media_id": "cam_person_03",
            "app_id": "cam-person-03",
            "label": "Right participant camera",
            "path": require(SOURCE_ROOT / "video" / "person-right.mp4"),
            "kind": "video",
            "project_role": "single_person",
            "app_role": "camera4",
            "camera_index": 4,
            "sync_offset": 0.0,
            "screen_position": "right",
            "person_id_hint": "person_03",
            "originalPath": r"C:\Users\yurin\Downloads\C0487-005.MP4",
        },
        {
            "media_id": "company_movie",
            "app_id": "company-movie",
            "label": "Company movie",
            "path": require(SOURCE_ROOT / "video" / "company-movie.mp4"),
            "kind": "video",
            "project_role": "company_movie",
            "app_role": "company_movie",
            "sync_offset": 0.0,
            "originalPath": r"C:\Users\yurin\Downloads\layerX_15sec_0920_2.mp4",
        },
        {
            "media_id": "layerx_logo",
            "app_id": "layerx-logo-horizontal-rgb-color",
            "label": "LayerX Logo Horizontal RGB Color",
            "path": require(SOURCE_ROOT / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"),
            "kind": "image",
            "project_role": "logo",
            "app_role": "logo",
            "originalPath": r"C:\Users\yurin\Downloads\LayerX_Logo_Horizontal_RGB_Color.png",
        },
    ]


def build_project_manifest(media: list[dict[str, Any]], probes: dict[str, Any]) -> dict[str, Any]:
    videos = [item for item in media if item["kind"] == "video"]
    fps_values = [probes[item["media_id"]]["fps"] for item in videos if probes[item["media_id"]].get("fps")]
    fps = fps_values[0] if fps_values else 30.0
    return {
        "schema_version": "project_manifest.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "time_unit": "seconds",
        "coordinate_system": "normalized_0_1",
        "master_canvas": {"width": 1920, "height": 1080, "fps": fps},
        "media": [
            {
                "media_id": item["media_id"],
                "path": rel(item["path"]),
                "kind": item["kind"],
                "role": item["project_role"],
                **({"camera_index": item["camera_index"]} if "camera_index" in item else {}),
                **({"screen_position": item["screen_position"]} if "screen_position" in item else {}),
                **({"person_id_hint": item["person_id_hint"]} if "person_id_hint" in item else {}),
                "sync_offset": item.get("sync_offset", 0.0),
                "duration": probes[item["media_id"]].get("duration"),
            }
            for item in media
        ],
        "outputs": [
            {"name": "preview_720p", "width": 1280, "height": 720, "codec": "h264", "preset": "veryfast", "crf": 28},
            {"name": "final_1080p", "width": 1920, "height": 1080, "codec": "h264", "preset": "medium", "crf": 20},
        ],
        "rules": {
            "final_render_requires_user_approval": True,
            "person_labels_require_people_map": True,
            "full_transcript_subtitles_allowed": False,
        },
        "transcription": {
            "policy": "single_reference_source_only",
            "source_audio_media_id": "group_wide",
            "reason": "interview cameras were recorded at the same time; synced timeline can share one transcript",
        },
        "sync": {
            "policy": "priority_order_timecode_audio_clap_visual_transcript_manual",
            "reference_media_id": "group_wide",
            "offset_report": str(REPORTS / "app_sync_offsets.json"),
            "sync_map": str(REPORTS / "sync_map.json"),
            "audio_track_analysis": str(REPORTS / "audio_track_analysis.json"),
            "analysis_report": str(REPORTS / "audio_sync_clap_analysis.json"),
            "precision_target": "millisecond",
        },
    }


def build_media_probe(media: list[dict[str, Any]], probes: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "media_probe.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "media": [
            {
                "media_id": item["media_id"],
                "path": rel(item["path"]),
                "kind": item["kind"],
                "role": item["project_role"],
                "probe": probes[item["media_id"]],
            }
            for item in media
        ],
    }


def build_app_manifest(media: list[dict[str, Any]], probes: dict[str, Any]) -> dict[str, Any]:
    files = []
    for item in media:
        path = item["path"]
        metadata = dict(probes[item["media_id"]])
        stat = path.stat()
        files.append(
            {
                "id": item["app_id"],
                "kind": item["kind"],
                "role": item["app_role"],
                "label": item["label"],
                "path": str(path),
                "originalPath": item.get("originalPath", ""),
                "relativePath": rel(path).replace("source\\", "", 1),
                "name": path.name,
                "extension": path.suffix,
                "sizeBytes": stat.st_size,
                "confidence": 1,
                "reason": "generated from current project source files by project-local analytics bootstrap",
                "metadata": metadata,
            }
        )
    return {
        "version": 1,
        "sourceDirectory": str(SOURCE_ROOT),
        "sourcePaths": [str(item["path"]) for item in media],
        "generatedAt": now_iso(),
        "files": files,
        "audio": [],
        "images": [item for item in files if item["kind"] == "image"],
        "subtitles": [],
        "other": [],
        "selected": {
            "masterVideo": str(SOURCE_ROOT / "video" / "three people.mp4"),
            "rightCloseVideo": str(SOURCE_ROOT / "video" / "person-right.mp4"),
            "leftCloseVideo": str(SOURCE_ROOT / "video" / "person-left.mp4"),
            "companyMovie": str(SOURCE_ROOT / "video" / "company-movie.mp4"),
            "externalAudio": "",
            "logo": str(SOURCE_ROOT / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"),
            "stillImages": [str(SOURCE_ROOT / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png")],
        },
        "manifestPath": str(REPORTS / "media_manifest.json"),
    }


def build_people_map() -> dict[str, Any]:
    people = []
    for person_id, position, role in (
        ("person_01", "left", "interviewer"),
        ("person_02", "middle", "interviewee"),
        ("person_03", "right", "interviewee"),
    ):
        people.append(
            {
                "person_id": person_id,
                "display_name": f"Placeholder {position.title()} Participant",
                "company": "LayerX",
                "department": "TBD",
                "role_title": "TBD",
                "conversation_role": role,
                "screen_position": position,
                "speaker_ids": [],
                "face_track_ids": [],
                "source_camera_media_ids": [f"cam_person_0{int(person_id[-1])}"],
                "identity_status": "placeholder_unverified",
                "bio_bullets": ["LayerX", "Department TBD", "Role TBD", "Domain expertise TBD"],
            }
        )
    return {
        "schema_version": "people_map.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "identity_policy": {
            "visible_names_are_placeholders": True,
            "requires_human_confirmation_before_final_render": True,
        },
        "people": people,
    }


def bbox_to_norm(box: dict[str, Any], width: float, height: float) -> dict[str, float]:
    x1 = float(box.get("x1", 0.0))
    y1 = float(box.get("y1", 0.0))
    x2 = float(box.get("x2", 0.0))
    y2 = float(box.get("y2", 0.0))
    return {
        "x": round(max(0.0, min(1.0, x1 / width)), 4) if width else 0.0,
        "y": round(max(0.0, min(1.0, y1 / height)), 4) if height else 0.0,
        "w": round(max(0.0, min(1.0, (x2 - x1) / width)), 4) if width else 0.0,
        "h": round(max(0.0, min(1.0, (y2 - y1) / height)), 4) if height else 0.0,
    }


def media_id_for_bbox_path(path: Path) -> str | None:
    stem = path.name.replace("_person_bboxes.json", "")
    return {
        "three_people": "group_wide",
        "person-left": "cam_person_01",
        "person-middle": "cam_person_02",
        "person-right": "cam_person_03",
        "company-movie": "company_movie",
    }.get(stem)


def build_vision_tracks() -> dict[str, Any]:
    tracks: list[dict[str, Any]] = []
    bbox_dir = REPORTS / "person_bboxes"
    for bbox_path in sorted(bbox_dir.glob("*_person_bboxes.json")):
        media_id = media_id_for_bbox_path(bbox_path)
        if not media_id:
            continue
        payload = read_json(bbox_path, {})
        width = float(payload.get("width") or 0)
        height = float(payload.get("height") or 0)
        track_observations: dict[str, list[dict[str, Any]]] = {}
        for frame in payload.get("frames", []):
            for person in frame.get("persons", []):
                track_id = str(person.get("track_id") or person.get("id") or "untracked")
                obs = {
                    "t": float(frame.get("time") or 0.0),
                    "bbox": bbox_to_norm(person.get("bbox") or {}, width, height),
                    "confidence": person.get("confidence"),
                    "screen_position": person.get("position"),
                    "shot_size": person.get("shot_size"),
                    "face_direction": person.get("face_direction"),
                }
                track_observations.setdefault(track_id, []).append(obs)
        for track_id, observations in sorted(track_observations.items()):
            tracks.append(
                {
                    "face_track_id": f"{media_id}_track_{track_id}",
                    "media_id": media_id,
                    "candidate_person_id": None,
                    "confidence": "analysis_track_not_identity",
                    "observations": observations,
                }
            )
    status = "sampled" if tracks else "pending_person_bbox_analysis"
    return {
        "schema_version": "vision_tracks.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "coordinate_system": "normalized_0_1",
        "sample_interval": "see source person_bboxes fps_sample",
        "status": status,
        "source_reports": [str(path) for path in sorted(bbox_dir.glob("*_person_bboxes.json"))],
        "tracks": tracks,
    }


def build_style_guide() -> dict[str, Any]:
    opening_style = read_json(CONFIG / "opening_digest_style.json", {})
    existing = read_json(REPORTS / "style_guide.json", {})
    style_guide = {
        "schema_version": "style_guide.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "style_sources": {
            "opening_digest_style": str(CONFIG / "opening_digest_style.json"),
            "reference_images": [str(path) for path in sorted((PROJECT_ROOT / "reference").glob("*.png"))],
        },
        "styles": {
            "opening_digest_sample_caption": (opening_style.get("captionStyle") or {}),
            "opening_digest_top_right_title": (opening_style.get("topRightTitle") or {}),
            "opening_digest_sample_frame": (opening_style.get("frameTreatment") or {}),
            "name_tag_reference_style": {
                "reference": str(PROJECT_ROOT / "reference" / "left-person-with-name-plate-sample.png"),
                "text_source": "people_map",
                "anchor": "below_face",
            },
            "bio_card_reference_style": {
                "reference": str(PROJECT_ROOT / "reference" / "person-introduction-sample.png"),
                "bullets_source": "people_map",
            },
            "main_punchline_caption": {
                "inherits": "opening_digest_sample_caption",
                "mode": "editorial_caption_subtitles_only",
            },
            "entity_explainer_bottom": {
                "position": "bottom",
                "max_lines": 2,
                "text_source": "semantic_marks.entity_explainers",
            },
        },
    }
    existing_sources = existing.get("style_sources") if isinstance(existing.get("style_sources"), dict) else {}
    for key in ("reference_image_analysis_manifest", "reference_image_analysis"):
        if key in existing_sources:
            style_guide["style_sources"][key] = existing_sources[key]
    if isinstance(existing.get("reference_alignment"), dict):
        style_guide["reference_alignment"] = existing["reference_alignment"]
    return style_guide


def transcript_confidence(segment: dict[str, Any]) -> float | None:
    avg_logprob = segment.get("avg_logprob")
    try:
        value = float(avg_logprob)
    except (TypeError, ValueError):
        return None
    # Map Whisper avg_logprob into a conservative 0-1 editorial confidence.
    return round(max(0.0, min(1.0, 1.0 + value)), 4)


def build_transcript() -> dict[str, Any]:
    manifest = read_json(TRANSCRIPT_MANIFEST_DIR / "manifest_transcripts.json", {})
    primary_path = manifest.get("primarySrt")
    primary_json = TRANSCRIPT_MANIFEST_DIR / "primary.json"
    if not primary_json.exists():
        return build_pending_transcript()

    payload = read_json(primary_json, {})
    segments = []
    for index, segment in enumerate(payload.get("segments", []), start=1):
        if not isinstance(segment, dict):
            continue
        segments.append(
            {
                "segment_id": f"seg_{index:06d}",
                "start": float(segment.get("start") or 0.0),
                "end": float(segment.get("end") or 0.0),
                "speaker_id": None,
                "text": str(segment.get("text") or "").strip(),
                "confidence": transcript_confidence(segment),
                "words": segment.get("words") if isinstance(segment.get("words"), list) else [],
            }
        )
    return {
        "schema_version": "transcript.v1",
        "project_id": "layer-x-domain-expert",
        "source_audio_media_id": "group_wide",
        "language": payload.get("language") or manifest.get("language") or "ja",
        "status": "transcribed_pending_diarization",
        "generated_at": now_iso(),
        "source_manifest": str(TRANSCRIPT_MANIFEST_DIR / "manifest_transcripts.json"),
        "source_primary_json": str(primary_json),
        "source_primary_srt": primary_path or str(TRANSCRIPT_MANIFEST_DIR / "primary.srt"),
        "segments": segments,
    }


def build_pending_transcript() -> dict[str, Any]:
    return {
        "schema_version": "transcript.v1",
        "project_id": "layer-x-domain-expert",
        "source_audio_media_id": "group_wide",
        "language": "ja",
        "status": "pending_transcription",
        "segments": [],
    }


def build_pending_diarization() -> dict[str, Any]:
    return {
        "schema_version": "speaker_diarization.v1",
        "project_id": "layer-x-domain-expert",
        "source_audio_media_id": "group_wide",
        "status": "pending_diarization",
        "speakers": [],
        "segments": [],
    }


def build_audio_sync() -> dict[str, Any]:
    path = REPORTS / "audio_sync_clap_analysis.json"
    if path.exists():
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("schema_version"):
            return payload
    return {
        "schema_version": "audio_sync_clap_analysis.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "status": "pending_clap_waveform_analysis",
        "reference_role": "master",
        "reference_media_id": "group_wide",
        "method": {
            "clap_detection": "pending",
            "waveform_check": "pending",
            "precision": "millisecond target",
        },
        "offsets": {"master": 0.0},
        "blockers": ["run projects/layer-x-domain-expert/scripts/analyze_clap_sync.py"],
    }


def build_audio_track_analysis() -> dict[str, Any]:
    path = REPORTS / "audio_track_analysis.json"
    if path.exists():
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("schema_version"):
            return payload
    return {
        "schema_version": "audio_track_analysis.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "status": "pending_audio_track_inspection",
        "blockers": ["run projects/layer-x-domain-expert/scripts/inspect_audio_tracks.py"],
    }


def build_sync_map() -> dict[str, Any]:
    path = REPORTS / "sync_map.json"
    if path.exists():
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("schema_version"):
            return payload
    return {
        "schema_version": "sync_map.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "master_clock": {"media_id": "group_wide", "role": "master"},
        "media_sync": [
            {
                "media_id": "group_wide",
                "role": "master",
                "sync_status": "master",
                "sync_model": "identity",
                "offset_sec": 0.0,
                "rate": 1.0,
                "confidence": 1.0,
            }
        ],
        "rules": {
            "do_not_use_failed_audio_correlation": True,
            "require_two_anchors_for_clips_longer_than_20_minutes": True,
            "manual_review_if_confidence_below": 0.9,
        },
    }


def build_pending_semantic(transcript: dict[str, Any]) -> dict[str, Any]:
    has_segments = bool(transcript.get("segments"))
    status = "pending_semantic_analysis" if has_segments else "pending_transcript"
    blockers = ["semantic highlight selection has not run yet"] if has_segments else ["transcript.json has no speech segments yet"]
    return {
        "schema_version": "semantic_marks.v1",
        "project_id": "layer-x-domain-expert",
        "status": status,
        "highlight_candidates": [],
        "topics": [],
        "entity_explainers": [],
        "punchline_subtitles": [],
        "blockers": blockers,
    }


def build_semantic_artifact(transcript: dict[str, Any]) -> dict[str, Any]:
    path = REPORTS / "semantic_marks.json"
    if path.exists():
        payload = read_json(path, {})
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") == "semantic_marks.v1"
            and payload.get("status") != "pending_transcript"
            and isinstance(payload.get("highlight_candidates"), list)
            and payload.get("highlight_candidates")
        ):
            return payload
    return build_pending_semantic(transcript)


def build_pending_edit_plan() -> dict[str, Any]:
    return {
        "schema_version": "edit_plan.v1",
        "project_id": "layer-x-domain-expert",
        "canvas": {"base_width": 1920, "base_height": 1080, "fps": 30},
        "global_style_ref": "style_guide.v1",
        "status": "not_ready_for_render",
        "timeline": [],
        "validation": {
            "ready_for_preview": False,
            "blockers": [
                "transcript.json is pending",
                "semantic_marks.json is pending",
                "camera sync offsets are still provisional",
            ],
        },
        "required_sequence": ["opening_digest", "company_movie_bridge", "main_interview"],
    }


def build_edit_plan_artifact() -> dict[str, Any]:
    path = REPORTS / "edit_plan.json"
    if path.exists():
        payload = read_json(path, {})
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") == "edit_plan.v1"
            and isinstance(payload.get("timeline"), list)
            and payload.get("timeline")
        ):
            return payload
    return build_pending_edit_plan()


def build_render_jobs() -> dict[str, Any]:
    return {
        "schema_version": "render_jobs.v1",
        "project_id": "layer-x-domain-expert",
        "generated_at": now_iso(),
        "jobs": [
            {
                "name": "preview_720p",
                "purpose": "fast user review preview",
                "width": 1280,
                "height": 720,
                "codec": "h264",
                "preset": "veryfast",
                "crf": 28,
                "allowed_before_user_approval": True,
            },
            {
                "name": "final_1080p",
                "purpose": "production-quality review render",
                "width": 1920,
                "height": 1080,
                "codec": "h264",
                "preset": "medium",
                "crf": 20,
                "allowed_before_user_approval": False,
            },
        ],
    }


def update_state(state: dict[str, Any], app_manifest: dict[str, Any]) -> dict[str, Any]:
    transcript_artifact = read_json(REPORTS / "transcript.json", {})
    semantic_artifact = read_json(REPORTS / "semantic_marks.json", {})
    edit_plan_artifact = read_json(REPORTS / "edit_plan.json", {})
    state = dict(state)
    state["revision"] = int(state.get("revision") or 0) + 1
    state["updatedAt"] = now_iso()
    state.setdefault("project", {})
    state["project"].update(
        {
            "id": "layer-x-domain-expert",
            "name": "Layer X Domain Expert",
            "root": str(PROJECT_ROOT),
            "sourceRoot": str(SOURCE_ROOT),
            "outputRoot": str(OUTPUT_ROOT),
        }
    )
    state.setdefault("assets", {})
    state["assets"].update(
        {
            "mediaDirectory": str(SOURCE_ROOT),
            "materialPaths": app_manifest["sourcePaths"],
            "mediaManifestPath": str(REPORTS / "media_manifest.json"),
            "mediaManifest": app_manifest,
            "masterVideo": str(SOURCE_ROOT / "video" / "three people.mp4"),
            "rightCloseVideo": str(SOURCE_ROOT / "video" / "person-right.mp4"),
            "leftCloseVideo": str(SOURCE_ROOT / "video" / "person-left.mp4"),
            "referenceVideo": "",
            "externalAudio": "",
            "logo": str(SOURCE_ROOT / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png"),
            "stillImages": [str(SOURCE_ROOT / "assets" / "LayerX_Logo_Horizontal_RGB_Color.png")],
            "sourceRoot": str(SOURCE_ROOT / "video"),
        }
    )
    state.setdefault("analysis", {})
    state["analysis"].update(
        {
            "artifactPaths": {
                "projectManifest": str(REPORTS / "project_manifest.json"),
                "mediaProbe": str(REPORTS / "media_probe.json"),
                "transcript": str(REPORTS / "transcript.json"),
                "speakerDiarization": str(REPORTS / "speaker_diarization.json"),
                "visionTracks": str(REPORTS / "vision_tracks.json"),
                "peopleMap": str(REPORTS / "people_map.json"),
                "semanticMarks": str(REPORTS / "semantic_marks.json"),
                "styleGuide": str(REPORTS / "style_guide.json"),
                "editPlan": str(REPORTS / "edit_plan.json"),
                "renderJobs": str(REPORTS / "render_jobs.json"),
                "audioSync": str(REPORTS / "audio_sync_clap_analysis.json"),
                "audioTrackAnalysis": str(REPORTS / "audio_track_analysis.json"),
                "syncMap": str(REPORTS / "sync_map.json"),
                "referenceImageAnalysis": str(REPORTS / "reference_image_analysis" / "manifest.json"),
            },
            "transcriptionPolicy": {
                "mode": "single_reference_source_only",
                "sourceMediaId": "group_wide",
                "sourceRole": "master",
                "script": str(PROJECT_ROOT / "scripts" / "transcribe_reference_only.py"),
            },
            "syncPolicy": {
                "mode": "timecode_audio_clap_visual_transcript_manual",
                "script": str(PROJECT_ROOT / "scripts" / "analyze_clap_sync.py"),
                "analysisPath": str(REPORTS / "audio_sync_clap_analysis.json"),
                "offsetsPath": str(REPORTS / "app_sync_offsets.json"),
                "syncMapPath": str(REPORTS / "sync_map.json"),
            },
            "personBboxesDir": str(REPORTS / "person_bboxes"),
            "personEditPlansDir": str(REPORTS / "person_edit_plans"),
            "personModel": str(PROJECT_ROOT.parents[1] / ".video-edit" / "models" / "yolov8n.pt"),
            "personFpsSample": 0.5,
            "personMaxSeconds": 90,
        }
    )
    state.setdefault("render", {})
    state["render"]["syncOffsetsPath"] = str(REPORTS / "app_sync_offsets.json")
    state.setdefault("codexWork", {})
    state["codexWork"]["analyticsBootstrap"] = {
        "updatedAt": now_iso(),
        "status": "foundation_json_created",
        "transcriptStatus": transcript_artifact.get("status") or "pending_transcription",
        "semanticStatus": semantic_artifact.get("status") or "pending_semantic_analysis",
        "editPlanStatus": edit_plan_artifact.get("status") or "not_ready_for_render",
        "visionStatus": "sampled" if (REPORTS / "person_bboxes").exists() else "pending_person_bbox_analysis",
    }
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Create LayerX analytics foundation JSON artifacts.")
    parser.add_argument("--skip-state", action="store_true")
    args = parser.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    state = read_json(STATE_PATH, {})
    media = project_media()
    ffprobe = ffprobe_path(state)
    probes: dict[str, Any] = {}
    for item in media:
        if item["kind"] == "video":
            probes[item["media_id"]] = probe_video(item["path"], ffprobe)
        else:
            probes[item["media_id"]] = png_dimensions(item["path"])

    project_manifest = build_project_manifest(media, probes)
    media_probe = build_media_probe(media, probes)
    app_manifest = build_app_manifest(media, probes)
    transcript = build_transcript()
    artifacts = {
        "project_manifest.json": project_manifest,
        "media_probe.json": media_probe,
        "media_manifest.json": app_manifest,
        "people_map.json": build_people_map(),
        "speaker_diarization.json": build_pending_diarization(),
        "transcript.json": transcript,
        "vision_tracks.json": build_vision_tracks(),
        "audio_track_analysis.json": build_audio_track_analysis(),
        "audio_sync_clap_analysis.json": build_audio_sync(),
        "sync_map.json": build_sync_map(),
        "semantic_marks.json": build_semantic_artifact(transcript),
        "style_guide.json": build_style_guide(),
        "edit_plan.json": build_edit_plan_artifact(),
        "render_jobs.json": build_render_jobs(),
    }
    for name, payload in artifacts.items():
        write_json(REPORTS / name, payload)

    if not args.skip_state:
        write_json(STATE_PATH, update_state(state, app_manifest))

    summary = {
        "project": "layer-x-domain-expert",
        "artifacts": [str(REPORTS / name) for name in artifacts],
        "videos": [item["media_id"] for item in media if item["kind"] == "video"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
