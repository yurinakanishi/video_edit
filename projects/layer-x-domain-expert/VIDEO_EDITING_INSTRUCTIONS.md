# LayerX Domain Expert Editing Methodology

This project should be edited through validated editing decisions, not by asking an AI model to write FFmpeg commands directly.

The stable architecture is:

```text
1. Analysis JSON
   Media probes, transcript, speaker diarization, face/person tracks,
   framing, camera quality, audio levels, and named entities.

2. Semantic JSON
   Highlight candidates, topics, strong quotes, entity explainers,
   subtitle candidates, and editorial intent.

3. Edit Decision JSON
   The actual timeline: which time ranges to use, which camera/layout to show,
   where captions and overlays appear, and how audio should behave.
```

The most important artifact is `edit_plan.json`. It is the complete blueprint for the video. Renderers should compile this plan into FFmpeg/OpenCV/overlay operations after validation.

## Core Pipeline

```text
Source media
-> ffprobe media inspection
-> speech transcription
-> speaker diarization
-> face/person/framing analysis
-> optional human identity mapping
-> LLM semantic and edit decisions
-> edit_plan.json generation
-> JSON Schema / Pydantic validation
-> Python compiler creates FFmpeg/OpenCV render instructions
-> 720p preview
-> user review
-> corrected preview iterations
-> final render only after approval
```

Do not let the AI produce a final `filter_complex` as the source of truth. The AI should describe what to show. Python should produce the rendering commands.

Bad:

```json
{
  "ffmpeg_filter": "[0:v]scale=..."
}
```

Good:

```json
{
  "layout": {
    "type": "person_with_bio",
    "person_id": "person_01",
    "person_position": "left"
  }
}
```

## JSON Artifacts

Use separate artifacts for separate responsibilities.

| Artifact | Purpose | Producer |
| --- | --- | --- |
| `project_manifest.json` | Source media, camera roles, sync offsets, output targets | Human + Python |
| `media_probe.json` | Duration, fps, resolution, codecs, streams | ffprobe |
| `transcript.json` | Utterances, word timestamps, confidence | STT |
| `speaker_diarization.json` | Which audio speaker speaks when | Diarization model |
| `vision_tracks.json` | Face/person tracks, locations, quality, mouth activity | OpenCV or vision model |
| `people_map.json` | Mapping between speakers, faces, and real people | Human confirmation |
| `semantic_marks.json` | Highlights, topics, strong captions, entity explainers | LLM |
| `style_guide.json` | Visual tokens and overlay component definitions | Human + AI |
| `edit_plan.json` | Final video timeline and editorial decisions | LLM + validation |
| `render_jobs.json` | Preview/final/master output profiles | Python |

Keep these identities separate:

```text
speaker_id     = a diarized audio speaker
face_track_id  = a tracked face in video
person_id      = a confirmed real person
```

Speaker diarization alone does not prove a real name. Face tracking alone does not prove identity. For interviews, panels, customer stories, internal films, or any multi-person video, use `people_map.json` before rendering name tags, departments, titles, or biography cards.

## Project Manifest Example

This structure supports any number of people and any number of cameras. Do not assume a fixed three-person setup.

```json
{
  "schema_version": "project_manifest.v1",
  "project_id": "layer-x-domain-expert",
  "time_unit": "seconds",
  "master_canvas": {
    "width": 3840,
    "height": 2160,
    "fps": 30
  },
  "media": [
    {
      "media_id": "group_wide",
      "path": "source/video/group_wide.mp4",
      "role": "group_wide",
      "camera_index": 1,
      "sync_offset": 0.0
    },
    {
      "media_id": "cam_person_01",
      "path": "source/video/cam_person_01.mp4",
      "role": "single_person",
      "camera_index": 2,
      "sync_offset": 0.12
    },
    {
      "media_id": "cam_person_02",
      "path": "source/video/cam_person_02.mp4",
      "role": "single_person",
      "camera_index": 3,
      "sync_offset": -0.04
    }
  ],
  "outputs": [
    {
      "name": "preview_720p",
      "width": 1280,
      "height": 720,
      "codec": "h264",
      "preset": "veryfast",
      "crf": 28
    },
    {
      "name": "final_1080p",
      "width": 1920,
      "height": 1080,
      "codec": "h264",
      "preset": "medium",
      "crf": 20
    },
    {
      "name": "master_4k",
      "width": 3840,
      "height": 2160,
      "codec": "h265",
      "preset": "slow",
      "crf": 20
    }
  ]
}
```

Store edit coordinates against the highest practical base canvas, usually the source or master canvas. Lower-resolution preview outputs should be scaled from the same edit plan so preview and final renders do not drift.

## Transcript Example

The transcript is source material for edit decisions. It is not automatically the subtitle file.

```json
{
  "schema_version": "transcript.v1",
  "source_audio_media_id": "group_wide",
  "language": "ja",
  "segments": [
    {
      "segment_id": "seg_000123",
      "start": 182.42,
      "end": 193.8,
      "speaker_id": "spk_01",
      "text": "Customer understanding is the starting point of business growth.",
      "confidence": 0.94,
      "words": [
        {
          "text": "Customer",
          "start": 182.42,
          "end": 182.88,
          "confidence": 0.91
        }
      ]
    }
  ]
}
```

Use seconds for time values. Avoid frame-only timelines because 29.97 fps, 30 fps, and variable-frame-rate sources can create off-by-one behavior.

## Vision Tracks Example

Do not dump every frame into JSON unless required. Prefer sampled observations, track IDs, and normalized coordinates.

```json
{
  "schema_version": "vision_tracks.v1",
  "media_id": "group_wide",
  "coordinate_system": "normalized_0_1",
  "sample_interval": 0.5,
  "tracks": [
    {
      "face_track_id": "face_001",
      "candidate_person_id": "person_01",
      "confidence": 0.88,
      "observations": [
        {
          "t": 182.5,
          "bbox": {
            "x": 0.12,
            "y": 0.18,
            "w": 0.18,
            "h": 0.32
          },
          "mouth_activity": 0.76,
          "gaze": "towards_person_02",
          "shot_quality": 0.91,
          "occluded": false
        }
      ]
    }
  ]
}
```

Use normalized coordinates from `0` to `1`. Convert them to preview, final, or master pixels during rendering.

## People Map Example

`people_map.json` is the identity authority. Any visible name, title, company, department, or biography overlay must come from this file or be marked as placeholder text.

```json
{
  "schema_version": "people_map.v1",
  "people": [
    {
      "person_id": "person_01",
      "display_name": "Person 1",
      "company": "LayerX",
      "department": "Domain Expert Team",
      "role_title": "Domain Expert",
      "speaker_ids": ["spk_01"],
      "face_track_ids": ["face_001", "face_014"],
      "bio_bullets": [
        "LayerX Domain Expert Team",
        "Leads domain research with customers",
        "Connects product decisions to real workflows"
      ]
    }
  ]
}
```

The `people` array can contain one person or many people. The edit logic must iterate over the array instead of hard-coding a participant count.

## Semantic Marks Example

`semantic_marks.json` is where the AI can create editorial meaning.

```json
{
  "schema_version": "semantic_marks.v1",
  "highlight_candidates": [
    {
      "id": "hl_001",
      "source_start": 182.42,
      "source_end": 193.8,
      "speaker_id": "spk_01",
      "score": 0.94,
      "reason": "The speaker states a clear relationship between domain expertise and customer value.",
      "digest_caption": "Domain expertise turns customer reality into product decisions.",
      "recommended_duration": 11.38
    }
  ],
  "topics": [
    {
      "topic_id": "topic_001",
      "start": 0.0,
      "end": 612.0,
      "title": "What Domain Experts Do at LayerX",
      "summary": "The participants explain how domain understanding informs product development."
    }
  ],
  "entity_explainers": [
    {
      "entity": "Bakuraku",
      "first_mentioned_at": 423.2,
      "explanation": "LayerX's business workflow product family for areas such as invoice processing and expense management.",
      "display_duration": 6.0
    }
  ],
  "punchline_subtitles": [
    {
      "start": 182.42,
      "end": 188.5,
      "speaker_id": "spk_01",
      "text": "Domain expertise turns customer reality into product decisions.",
      "style": "strong_caption",
      "priority": 0.92
    }
  ]
}
```

These captions are not full subtitles. They are strong, editorial captions selected for emphasis.

## Edit Plan Example

The renderer should be able to read `edit_plan.json` and generate the render without asking the LLM for FFmpeg syntax.

```json
{
  "schema_version": "edit_plan.v1",
  "project_id": "layer-x-domain-expert",
  "canvas": {
    "base_width": 3840,
    "base_height": 2160,
    "fps": 30
  },
  "global_style_ref": "style_guide.v1",
  "timeline": [
    {
      "event_id": "digest_001",
      "timeline_start": 0.0,
      "timeline_end": 10.8,
      "type": "source_clip",
      "section": "digest",
      "source": {
        "media_id": "cam_person_01",
        "in": 182.4,
        "out": 193.2
      },
      "layout": {
        "type": "single",
        "crop_mode": "person_centered",
        "target_person_id": "person_01"
      },
      "audio": {
        "mode": "source",
        "fade_in": 0.1,
        "fade_out": 0.2
      },
      "overlays": [
        {
          "type": "caption",
          "start": 0.4,
          "end": 6.8,
          "text": "Domain expertise turns customer reality into product decisions.",
          "style_id": "digest_caption_large"
        }
      ],
      "reason": "Strong opening statement for the digest."
    },
    {
      "event_id": "main_intro_group",
      "timeline_start": 10.8,
      "timeline_end": 23.5,
      "type": "source_clip",
      "section": "main",
      "source": {
        "media_id": "group_wide",
        "in": 0.0,
        "out": 12.7
      },
      "layout": {
        "type": "wide_group",
        "ensure_people_visible": ["person_01", "person_02"],
        "safe_margin": 0.06
      },
      "overlays": [
        {
          "type": "lower_third_people",
          "people_source": "people_map",
          "anchor": "below_face",
          "style_id": "name_tag_reference_style"
        }
      ]
    },
    {
      "event_id": "self_intro_person_01",
      "timeline_start": 23.5,
      "timeline_end": 53.5,
      "type": "source_clip",
      "section": "main",
      "source": {
        "media_id": "cam_person_01",
        "in": 12.7,
        "out": 42.7
      },
      "layout": {
        "type": "person_with_bio",
        "person_id": "person_01",
        "person_position": "left",
        "bio_position": "right"
      },
      "overlays": [
        {
          "type": "bio_card",
          "person_id": "person_01",
          "style_id": "bio_card_reference_style",
          "bullets_source": "people_map"
        }
      ]
    },
    {
      "event_id": "main_multicam_001",
      "timeline_start": 53.5,
      "timeline_end": 69.5,
      "type": "multicam_segment",
      "section": "main",
      "source_time": {
        "in": 42.7,
        "out": 58.7
      },
      "layout": {
        "type": "single",
        "selected_media_id": "cam_person_02",
        "target_person_id": "person_02",
        "selection_reason": "The target person is the primary speaker and has clear expression and mouth activity."
      },
      "overlays": [
        {
          "type": "topic_title",
          "position": "top_right",
          "text": "What Domain Experts Do at LayerX",
          "style_id": "topic_title_top_right"
        },
        {
          "type": "caption",
          "start": 3.2,
          "end": 8.7,
          "text": "The job is to turn complex operations into usable products.",
          "style_id": "main_punchline_caption"
        }
      ]
    },
    {
      "event_id": "main_grid_001",
      "timeline_start": 69.5,
      "timeline_end": 83.5,
      "type": "multicam_segment",
      "section": "main",
      "source_time": {
        "in": 58.7,
        "out": 72.7
      },
      "layout": {
        "type": "split_grid",
        "media_ids": ["group_wide", "cam_person_01", "cam_person_02"],
        "grid_strategy": "auto_by_media_count",
        "divider": {
          "color": "#B7E6C1",
          "width_px_at_base": 6
        }
      },
      "overlays": [
        {
          "type": "entity_explainer",
          "start": 2.0,
          "end": 8.0,
          "entity": "Bakuraku",
          "text": "LayerX's business workflow product family for areas such as invoice processing and expense management.",
          "position": "bottom",
          "style_id": "entity_explainer_bottom"
        }
      ]
    }
  ],
  "validation_rules": {
    "no_unintended_gaps": true,
    "no_unintended_overlaps": true,
    "all_source_ranges_must_exist": true,
    "captions_must_not_overlap_entity_explainers": true,
    "person_labels_require_people_map": true,
    "all_person_ids_must_exist": true,
    "all_media_ids_must_exist": true,
    "all_style_ids_must_exist": true
  }
}
```

Use participant-aware layout names:

- `wide_group` for a camera that includes the group.
- `single` for one selected person or one selected media source.
- `person_with_bio` for an introduction layout.
- `speaker_reaction_pair` for speaker plus listener/reaction.
- `split_grid` for any count of camera feeds.
- `auto_by_media_count` when the renderer should choose a grid from the number of media inputs.

Avoid count-specific names such as `wide_3shot`, `all_three_people`, or `split_4` unless the layout truly requires that exact number.

## Style Guide Example

Use style tokens instead of embedding rendering details in the edit plan.

```json
{
  "schema_version": "style_guide.v1",
  "colors": {
    "background_dark": "#10251C",
    "accent_green": "#B7E6C1",
    "text_primary": "#FFFFFF",
    "text_secondary": "#DDEFE5"
  },
  "typography": {
    "font_family": "Noto Sans CJK JP",
    "caption_large_px_at_base": 92,
    "caption_medium_px_at_base": 64,
    "topic_title_px_at_base": 48,
    "name_tag_px_at_base": 44
  },
  "layout": {
    "safe_margin_x": 0.055,
    "safe_margin_y": 0.06,
    "lower_third_padding_px_at_base": 32,
    "bio_card_width_ratio": 0.38
  },
  "components": {
    "name_tag_reference_style": {
      "background": "semi_transparent_dark",
      "border": "accent_green",
      "border_radius_px_at_base": 18
    },
    "main_punchline_caption": {
      "position": "bottom_center",
      "max_lines": 2,
      "background": "none",
      "stroke": true
    },
    "entity_explainer_bottom": {
      "position": "bottom",
      "background": "semi_transparent_dark",
      "max_lines": 2
    }
  }
}
```

For complex text cards, lower thirds, rounded boxes, multi-line layouts, and branded components, prefer generating transparent PNG/SVG overlays with Python and then compositing them with FFmpeg. Use FFmpeg `drawtext` only when the typography and layout are simple enough to validate reliably.

## LLM Prompt Shape

When generating `edit_plan.json`, provide the LLM with validated inputs and require schema-conformant output only.

```text
You are the editorial director for a business interview video.

Inputs:
- project_manifest.json
- media_probe.json
- transcript.json
- speaker_diarization.json
- vision_tracks.json
- people_map.json
- semantic_marks.json
- style_guide.json

Goals:
- Create an opening digest from the strongest moments.
- Transition from the digest into the main section.
- Use a group view when introducing the conversation.
- Render person labels only from people_map.json.
- During self-introductions, show the person and a short biography card.
- Do not create full subtitles; show only strong editorial captions.
- Show topic titles and entity explainers when they add clarity.
- Use camera selection based on speaker, reactions, visual quality, and variety.
- Support any number of participants and cameras.

Output:
- edit_plan.json only.
- Strictly follow the JSON Schema.
- Do not invent media_id, person_id, style_id, speaker_id, or face_track_id.
- Keep all source in/out values within media duration.
- Avoid unintended timeline gaps and overlaps.
- Do not render names, titles, or departments unless they exist in people_map.json.
```

Use Structured Outputs or another JSON Schema constrained generation method when available. Always run local validation before rendering.

## OTIO Export

Keep `edit_plan.json` as the project renderer source of truth, but preserve a path to OpenTimelineIO export where practical.

```text
edit_plan.json
-> internal FFmpeg/OpenCV renderer
-> optional OTIO export
-> possible later handoff to Premiere, Resolve, or another NLE
```

FFmpeg-only timelines are harder for humans to adjust later. OTIO export gives the project an escape hatch for manual finishing.

## Required Rules

1. Store times in seconds.
2. Store geometry in normalized coordinates unless a style token explicitly uses base-canvas pixels.
3. Keep `speaker_id`, `face_track_id`, and `person_id` separate.
4. Do not let AI infer real names or titles without `people_map.json`.
5. Keep full transcripts separate from editorial captions.
6. Make the LLM output edit intent, not renderer syntax.
7. Validate all IDs, source ranges, timeline continuity, caption collisions, and overlay dependencies before rendering.
8. Always create a lightweight preview first.
9. Render final production output only after the preview is reviewed and accepted.

In one sentence: AI should create a validated edit timeline, and Python should safely compile that timeline into FFmpeg/OpenCV/OTIO outputs.
