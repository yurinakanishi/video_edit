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
-> clap plus waveform audio sync analysis
-> speech transcription from one synced reference source
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
| `audio_sync_clap_analysis.json` | Clap candidates, waveform correlation, and camera sync offsets | Python |
| `sync_map.json` | Evidence-backed master/camera time mapping, anchors, confidence, and drift model | Python + manual review |
| `vision_tracks.json` | Face/person tracks, locations, quality, mouth activity | OpenCV or vision model |
| `people_map.json` | Mapping between speakers, faces, and real people | Human confirmation |
| `semantic_marks.json` | Highlights, topics, strong captions, entity explainers | LLM |
| `style_guide.json` | Visual tokens and overlay component definitions | Human + AI |
| `reference_image_analysis/*.json` | Per-reference framing, subject crop, face position, overlay zones, and section alignment rules | Human + Python |
| `edit_plan.json` | Final video timeline and editorial decisions | LLM + validation |
| `render_jobs.json` | Preview/final/master output profiles | Python |

Keep these identities separate:

```text
speaker_id     = a diarized audio speaker
face_track_id  = a tracked face in video
person_id      = a confirmed real person
```

Speaker diarization alone does not prove a real name. Face tracking alone does not prove identity. For interviews, panels, customer stories, internal films, or any multi-person video, use `people_map.json` before rendering name tags, departments, titles, or biography cards.

## Transcription And Sync Policy

The interview cameras were recorded at the same time, so do not transcribe every camera by default.

Use one audio-bearing interview source as the transcript authority:

- `source_audio_media_id`: `group_wide`
- app/render role: `master`
- source file: `source/video/three people.mp4`

The transcript from this source is shared across the synced multicam timeline. Other camera audio should be used for sync confirmation and fallback audio diagnostics, not duplicate transcription.

Use this sync evidence priority order:

1. Timecode, LTC, or metadata timecode
2. Usable scratch audio / waveform correlation
3. Clap or slate point, using audio or visual contact frame
4. Visual sync from mouth movement, hand motion, or scene events
5. Transcript-based rough sync
6. Manual anchor points plus drift correction

Camera audio near `-85` / `-90` dBFS is not reliable for waveform sync unless there is a recoverable transient such as a clap, table hit, laugh burst, or camera beep. Inspect the tracks first with `ffprobe`, `volumedetect`, and/or `astats`; then try one rescued waveform pass with gain and filtering. If the correlation peak is weak, record the failure and do not force an offset from it.

Before generating semantic marks or edit decisions, run project-local audio sync analysis:

```text
projects/layer-x-domain-expert/scripts/analyze_clap_sync.py
```

The sync analysis must combine:

- clap-like transient detection, if a clap exists near the start of the recording;
- broad waveform/transient-envelope correlation across the scanned audio range;
- millisecond-level cross-correlation around the clap candidate to confirm the final offset.

Store the detailed evidence in:

```text
output/reports/audio_sync_clap_analysis.json
```

Store renderer-compatible offsets in:

```text
output/reports/app_sync_offsets.json
```

Store the evidence-backed sync model and anchors in:

```text
output/reports/sync_map.json
```

`sync_map.json` uses this timing convention:

```text
master_time = camera_time * rate + offset_sec
```

Renderer/app offsets may also be stored separately when a renderer expects:

```text
source_time = master_timeline_time + app_offset_sec
```

For long clips, prefer at least two anchors, one near the beginning and one near the end, and fit a linear model when drift is measurable:

```json
{
  "media_id": "cam_person_02",
  "sync_model": "linear",
  "offset_sec": -2.3334,
  "rate": 0.999982,
  "drift_ppm": -18.0,
  "anchors": [
    {
      "camera_time": 12.4167,
      "master_time": 10.0833,
      "method": "visual_clap_frame",
      "confidence": 0.95
    },
    {
      "camera_time": 3612.5,
      "master_time": 3610.1,
      "method": "mouth_movement_phrase_match",
      "confidence": 0.87
    }
  ],
  "manual_review_required": true
}
```

Required sync rules:

- Do not use failed or weak audio correlation as if it were a confirmed offset.
- Mark low-confidence entries with `manual_review_required: true`.
- Require two anchors for clips longer than 20 minutes when practical.
- For silent or nearly silent cameras, prefer visual clap, mouth movement, hand gesture, scene event, or manual anchor evidence.
- Render a 4-way sync-check grid before treating provisional cameras as trusted edit coverage.

`project_manifest.json` and `edit_plan.json` source timing should use these sync offsets. If clap and waveform evidence conflict, mark sync as requiring manual review instead of guessing. Do not use a transcript comparison between all camera transcripts as the primary sync method for this project.

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
    },
    {
      "media_id": "company_movie",
      "path": "source/video/company-movie.mp4",
      "role": "company_movie",
      "sync_offset": 0.0
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
      "conversation_role": "interviewer",
      "screen_position": "left",
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

For this project, preserve the participant roles and physical screen positions in `people_map.json`:

- The left-side participant is the interviewer: `conversation_role: "interviewer"`, `screen_position: "left"`.
- The middle and right participants are interviewees: `conversation_role: "interviewee"`, `screen_position: "middle"` / `"right"`.
- When rendering any two-person divided layout that includes the interviewer, the interviewer must appear on the left side of the split, regardless of who is speaking.
- When rendering a two-person divided layout between only the middle and right interviewees, keep their natural order: middle participant on the left panel, right participant on the right panel.

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

These captions are not full transcript subtitles. They are editorial caption subtitles selected for emphasis. Slightly longer lines may use one caption swap within the same speech segment.

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
      "event_id": "digest_to_main_company_movie",
      "timeline_start": 10.8,
      "timeline_end": 18.8,
      "type": "source_clip",
      "section": "bridge",
      "source": {
        "media_id": "company_movie",
        "in": 0.0,
        "out": 8.0
      },
      "layout": {
        "type": "single",
        "crop_mode": "fit"
      },
      "audio": {
        "mode": "source"
      },
      "overlays": [],
      "reason": "Company movie bridge between Opening Digest and main section."
    },
    {
      "event_id": "main_intro_group",
      "timeline_start": 18.8,
      "timeline_end": 31.5,
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
      "timeline_start": 31.5,
      "timeline_end": 61.5,
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
      "timeline_start": 61.5,
      "timeline_end": 77.5,
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
      "timeline_start": 77.5,
      "timeline_end": 91.5,
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
- audio_sync_clap_analysis.json
- sync_map.json
- vision_tracks.json
- people_map.json
- semantic_marks.json
- style_guide.json
- reference_image_analysis/manifest.json

Goals:
- Create an opening digest from the strongest moments.
- After the digest, insert source/video/company-movie.mp4 as a bridge before the main section.
- Use a group view when introducing the conversation.
- Render person labels only from people_map.json.
- During self-introductions, show the person and a short biography card.
- Do not create full transcript subtitles in either section; use editorial caption subtitles only.
- Prefer short emphasized phrases; allow one caption swap within a speech segment when the line is slightly longer.
- Show topic titles and entity explainers when they add clarity.
- Use camera selection based on speaker, reactions, visual quality, and variety.
- Support any number of participants and cameras.

Output:
- edit_plan.json only.
- Strictly follow the JSON Schema.
- Do not invent media_id, person_id, style_id, speaker_id, or face_track_id.
- Keep all source in/out values within media duration.
- Apply sync offsets from audio_sync_clap_analysis.json / app_sync_offsets.json.
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

---

## Editorial Requirements

The following are project-specific creative, caption, and cutting rules for this interview. Use them together with the JSON pipeline and `edit_plan.json` design above.

### Deliverables

| Output | Purpose | Settings |
| --- | --- | --- |
| `preview_720p` | Preview | 1280×720, fast encode, optimized for review iterations |
| `final_1080p` | Client review | 1920×1080, production-quality review render |

Do not treat `final_1080p` as the final delivery until the preview is approved. `master_4k` is not a required output for this specification.

### Overall Editorial Direction

Edit this video as a polished business interview, not as raw event footage. The goal is to keep viewers engaged through the end.

Priorities:

- Hook viewers with a 45-second opening digest
- Establish all three participants and their titles near the start of the main section
- Make each person's background clear during self-introductions
- Use editorial caption subtitles in both digest and main section; never full transcript subtitles
- Emphasize only the most important words as on-screen captions; allow one caption swap when a line is slightly longer
- Show the current topic in the upper-right corner as the conversation moves
- Add short explainers for proper nouns when needed
- Use all four camera sources to keep the edit visually varied
- Match the clean, professional business-interview look shown in the reference images

### Opening Digest (First 45 Seconds)

- Pull the strongest statements and reactions from the main interview into a digest of about 45 seconds
- After the digest ends, insert `source/video/company-movie.mp4` as a bridge clip before the main section begins
- Select digest captions from `highlight_candidates` / `digest_caption` in `semantic_marks.json`
- Use fewer captions than in the main section
- Prefer short, strong emphasized phrases; if a line is slightly longer, one caption swap within the same speech segment is acceptable

**Opening Digest visual style**

Opening Digest must use the same visual treatment as the styled sample from `projects/test-project-1`:

- Style specification: `config/opening_digest_style.json`
- Reference source video: `projects/test-project-1/source/video/Interview_with_Michael_Eisen_on_Open_Access_middle_1min.mp4`
- Reference styled preview: `projects/test-project-1/output/videos/preview_sample1_catchphrase_collection_styled.mp4`
- Reference frame profile: `projects/test-project-1/output/subtitles/sample11_frame_design_profile.json`
- Reference subtitle profile: `projects/test-project-1/output/subtitles/sample1_catchphrase_collection_styled_profile.json`

For all Opening Digest clips, keep these elements consistent with the sample:

- Top blue-purple band with the white slanted LayerX logo panel
- LayerX logo placement and size inside the left panel
- Upper-right title banner using the same blue-purple family, white bold text, and slanted banner feel
- Continuous thin bottom blue-purple band
- Large lower digest captions in rounded blue-purple boxes with white bold text
- Horizontal reveal animation for caption entry, staggered reveal for second caption lines, and quick fade out
- Content video shifted down by the same sample-derived offset so faces avoid the header and lower captions

During the Opening Digest, the upper-right title is the **overall title for this video**. It is not a chapter title.

Do not render full transcript subtitles in the Opening Digest. Render only editorial caption subtitles from `semantic_marks.json`, using `style_id: opening_digest_sample_caption`.

Digest caption length:

- Default: one short emphasized phrase per clip
- Allowed: a slightly longer line that needs one caption swap within the same speech segment (show caption A, then replace it once with caption B before the clip ends)
- Not allowed: full transcript subtitles or continuous line-by-line subtitle coverage

### Digest-to-Main Bridge (`company-movie.mp4`)

Between the Opening Digest and the main section, insert the company movie clip:

- Source: `projects/layer-x-domain-expert/source/video/company-movie.mp4`
- Manifest `media_id`: `company_movie`
- Timeline `section`: `bridge`
- Use the clip as a visual and narrative bridge from the digest hook into the interview main section
- Trim `in` / `out` to the editorially appropriate portion of the company movie; use the full clip only if that length fits the pacing goal
- Do not add digest captions, topic titles, or interview overlays to this bridge clip unless a future style rule explicitly requires them
- Place this event after the last digest event and before the first main-section event in `edit_plan.json`

### Main Section Visual Difference From Digest

The main section uses the same basic visual language as the digest, but it is not identical.

Keep these consistent with the digest/sample style:

- Editorial caption placement and style
- LayerX logo placement and scale
- Upper-right title placement
- Upper-right title blue-purple box background
- Caption colors, rounded boxes, reveal animation, and quick fade timing

Remove these digest-only frame elements from the main section:

- The full-width thick purple top band background
- The thin purple bottom band line

Important: the upper-right title's own purple box background remains in the main section. Only the digest-style full-width top band and bottom line are removed.

In the main section, the upper-right title is the **chapter/topic title** for the current segment. Derive chapter titles from transcript analysis and store them in `semantic_marks.json` `topics`, then reference them from `edit_plan.json` as `overlays.type: topic_title`, `position: top_right`.

The main section also uses editorial caption subtitles only. Do not switch to full transcript subtitles after the digest.

### Participant Introduction at the Start of the Main Section

Participant introduction belongs to the **main section**, not to the digest. Treat it as the early part of the main section.

Do not assume the introduction begins at a fixed timestamp. Determine the participant introduction and each self-introduction range from the transcript/transcribed subtitles, speaker turns, and semantic content.

Near the start of the main section, when the transcript indicates participant introduction, use a **wide shot that includes all three participants** (`layout.type: wide_group`).

In that shot, place provisional title/name labels below each person's face.

Examples:

- LayerX ○○ Division — Yamada-san
- LayerX △△ Division — Sato-san
- LayerX □□ Division — Suzuki-san

**Text management**

- Placeholder titles and names are acceptable for now
- Centralize editable text in `people_map.json` (`display_name`, `company`, `department`, `role_title`)
- `edit_plan.json` overlays must reference `people_source: "people_map"` instead of hard-coding text
- Overlay type: `lower_third_people`, `anchor: below_face`

**Display style**

- Follow the reference image design (`style_guide.json` → `name_tag_reference_style`)
- Place labels naturally below each face so ownership is obvious at a glance
- Keep a clean, professional business-interview look

### Self-Introduction Layout

When each person introduces themselves, place that person **large on the left or right side of the frame** (`layout.type: person_with_bio`).

On the opposite side, show their background, role, and focus area as **large bullet points**.

Examples:

- LayerX ○○ Division
- Product Manager
- Leads the launch of SaaS businesses
- Previously owned the ○○ domain

**Text management**

- Placeholder biography text is acceptable for now
- Store bullet points in the `bio_bullets` array in `people_map.json`
- `edit_plan.json` `bio_card` overlays must use `bullets_source: "people_map"`
- Create one `person_with_bio` event per person and sync it to that person's self-introduction speech range

**Display style**

- Match the reference image layout, type size, spacing, color usage, and information hierarchy (`style_guide.json` → `bio_card_reference_style`)
- Respect existing layout tokens such as `bio_card_width_ratio`

### Caption Policy

Do **not** display the full transcript as subtitles in either the Opening Digest or the main section. Use **editorial caption subtitles** only: strong phrases, memorable lines, and points the viewer should take away.

| Item | Policy |
| --- | --- |
| Display mode | Caption subtitles only. Never render continuous full-transcript subtitles. |
| Digest source | `semantic_marks.json` → `highlight_candidates` / `digest_caption` |
| Main source | `transcript.json` is source material only. Display text flows through `punchline_subtitles` in `semantic_marks.json` into `edit_plan.json` |
| Frequency | Main section: much higher than in the digest. Target roughly one caption every 30 seconds on average |
| Back-to-back captions | Allowed when important lines continue in sequence; do not wait 30 seconds in those cases |
| Gaps | Allowed when there is no strong line worth emphasizing; gaps longer than 30 seconds are fine |
| Length | Prefer short, strong, readable catchphrases. If a line is slightly longer, one caption swap within the same speech segment is acceptable |
| Caption swap | Replace the on-screen caption once with the next caption phrase for the same speech segment. Do not chain multiple swaps to approximate full subtitles |

Bad example:

> Um, well, for us, when we think about business growth, customer understanding is really important, and...

Good example:

> The starting point of business growth is customer understanding.

Slightly longer but still acceptable (one swap within the segment):

> Caption 1: Customer understanding is the starting point of business growth.
> Caption 2: That understanding has to come before product decisions.

Summarize and polish for readability without changing the speaker's meaning. Use `style_id: main_punchline_caption` in the main section and `style_id: opening_digest_sample_caption` in the digest.

### Topic Title in the Upper Right

During the main section, show a **topic title in the upper-right corner** for each conversation segment (`overlays.type: topic_title`, `position: top_right`).

- Digest: use the overall video title in the upper-right title box.
- Main section: use the current chapter/topic title in the upper-right title box.
- Expect a topic change roughly once every 10 minutes across the full interview
- Analyze subtitles and transcript segments, then assign appropriate titles to `topics` in `semantic_marks.json`
- Keep the topic title visible continuously or for a defined duration, and change it naturally at topic boundaries

Examples:

- What It Means to Work at LayerX
- The Reality of Building a Business
- Behind Product Development
- Delivering Results as a Team
- What We Want to Take On Next

### Proper-Noun Explainer Lower Thirds

Analyze subtitles and transcript text. When a proper noun appears in conversation, add a short explainer lower third at the **bottom of the screen** when it helps comprehension (`overlays.type: entity_explainer`).

Examples of targets:

- Company names, service names, business names
- Technical terms and industry terms
- Personal names and project names

Keep explanations short enough for context, not long definitions. Store them in `entity_explainers` in `semantic_marks.json`.

Examples:

**LayerX**
A SaaS and fintech company with the mission to digitize all economic activity.

**Bakuraku**
LayerX's suite of workflow services for invoice processing, expense management, and related operations.

**Placement rules**

- Display at the bottom of the screen (`position: bottom`)
- Adjust position, background, and spacing so regular captions do not overlap
- Follow `validation_rules.captions_must_not_overlap_entity_explainers`

### Four-Camera Cutting

This interview has **three participants and four camera sources**. Cut based on conversational flow, not on a fixed timer.

**Example shot usage**

| Situation | Layout |
| --- | --- |
| Overall group energy | `wide_group` |
| Active speaker close-up | `single` (select the speaker's `media_id`) |
| Listener reaction | `single` or `speaker_reaction_pair` |
| Important two-person exchange | `speaker_reaction_pair` or 2-up split |
| Everyone talking at once / lively moment | `split_grid` (4-up allowed) |
| 2-up when needed | `split_grid` (2 feeds) |

**4-up rules**

- A 4-up split is allowed when everyone is speaking together
- Separate panels with a **thin light-green line** (`divider.color: #B7E6C1`)
- Do not stay in 4-up all the time; switch layouts based on conversation needs

**2-up divided layout rules**

- The left-side participant is the interviewer. Whenever a 2-up / two-person divided layout includes this interviewer, place the interviewer in the left panel.
- The middle and right participants are interviewees. When the 2-up layout includes only these two interviewees, place the middle participant in the left panel and the right participant in the right panel.
- Do not swap panel order just because the active speaker changes. Use visual emphasis, captions, or camera selection to indicate the current speaker while preserving the role/order rule.
- Encode the selected panel order in `edit_plan.json`, for example `layout.panel_order: ["interviewer", "interviewee_middle"]` or person IDs from `people_map.json`.

**Cut-selection rules**

- When someone makes an important statement, prioritize their close-up
- When a two-person exchange matters, center those two participants
- When group atmosphere matters, use the wide 3-person shot
- When reactions are strong, include the listener's expression
- Avoid staying on one angle too long; vary cuts throughout the interview

Describe camera choices in `multicam_segment` events using `speaker_id`, mouth activity (`mouth_activity`), shot quality (`shot_quality`), gaze, and topic boundaries together.

### Reference Images

Use the project's **reference images** as the baseline for design, layout, caption style, participant name tags, and self-introduction information panels.

Do not copy them exactly. Adapt them to this interview footage. Reflect extracted tokens in `style_guide.json` (colors, font sizes, spacing, component definitions).

Elements to carry over from the reference images:

- How participant names and titles are shown
- Participant placement during self-introductions
- Biography panel layout
- Type size and spacing
- Lower-third color usage
- Information density balance
- Clean business-interview presentation

Store reference images under `projects/layer-x-domain-expert/reference/`. The renderer should read the optional `reference_image` field in `style_guide.json` when present.

#### Project Reference Image Inventory

Use these project-local sample images as visual references. They are design references only; do not render them directly into the final video.

| Reference image | Use for | Relevant plan/style IDs |
| --- | --- | --- |
| `reference/person-introduction-sample.png` | Self-introduction biography layout with one large person crop and a large opposite-side career/background panel | `layout.type: person_with_bio`, `bio_card_reference_style` |
| `reference/annotation-sample.png` | Proper-noun explainer card, two-person split composition, upper-right topic title, and top-left LayerX logo placement | `entity_explainer_bottom`, `speaker_reaction_pair`, `topic_title_top_right` |
| `reference/three-people-divided-sample.png` | Three-person divided layout with vertical separators and a persistent upper-right topic title | `split_grid`, `auto_by_media_count`, `topic_title_top_right` |
| `reference/middle-and-right-people-with-name-plate-divided-sample.png` | Two-person split layout with large name plates for both participants | `split_grid`, `lower_third_people`, `name_tag_reference_style` |
| `reference/left-person-with-name-plate-sample.png` | Single-person close-up with a large centered lower-third name plate and role/title text above it | `single`, `lower_third_people`, `name_tag_reference_style` |

#### Extracted Reference Design Notes

Carry these observations into `style_guide.json` component definitions and renderer layout logic:

- Brand color: use a saturated LayerX blue-purple as the primary overlay color, approximately `#5F5AF5` to `#6258F7`.
- Split dividers: use thin light-blue or light-green vertical rules, approximately `#8EC6FF` or `#B7E6C1`, with enough contrast against interview footage.
- Logo: place the LayerX logo at the upper-left safe area when a branded topic or split layout is shown. Keep it clear of faces and topic bars.
- Topic title: use a blue-purple upper-right banner with white bold Japanese text. The banner can have angled/slanted ends and subtle translucent geometric texture, but text readability is more important than decoration.
- Name plates: use a two-tier treatment. Put role/title text above or near the plate in bold white with blue-purple outline or shadow, then place the display name in a solid blue-purple rectangle with very large white type.
- Explainer card: use a white rectangular card at the lower third with black bold Japanese text, paired with a blue-purple label tab above or attached to the card. Keep the card below faces and above the bottom safe edge.
- Biography card: use a large blue-purple panel on the side opposite the person. Use a centered section title, a thin horizontal separator line, and large white bullet text with generous line spacing.
- Person framing: for `person_with_bio`, keep the person large on one side and crop around head/torso while preserving breathing room. For split layouts, keep each face centered within its panel and avoid cutting off microphones or name plates.
- Information density: the reference images allow dense Japanese text, but only in explicit explanation or biography cards. Strong captions should remain shorter and more readable than the bio/explainer text.

#### Reference-Specific Application Rules

- For `person-introduction-sample.png`, use the person side plus biography-panel structure when rendering each person's self-introduction. The panel should use `people_map.bio_bullets`, not hard-coded text.
- For `annotation-sample.png`, use the lower white explainer card for terms such as LayerX, Bakuraku, FDE, CPO, CTO, and CISO when they help viewer comprehension. Validate that this card does not overlap regular captions.
- For `three-people-divided-sample.png`, use the three-column divided look when all participants or the group dynamic should be visible. Keep the topic banner in the upper-right and preserve the top-left logo.
- For `middle-and-right-people-with-name-plate-divided-sample.png`, use the two-up divided look for important exchanges between two participants. Each participant's name plate must be anchored to that participant's panel and sourced from `people_map.json`. If the interviewer is one of the two participants, keep the interviewer in the left panel; if the split is between the middle and right interviewees only, keep the middle participant left and the right participant right.
- For `left-person-with-name-plate-sample.png`, use the single-person lower-third style when one speaker is the clear focus. The role/title line and display name must both come from `people_map.json`; placeholders are allowed only until confirmed identity data is available.
