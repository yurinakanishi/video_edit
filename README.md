# Video Edit Project

## Layout

```text
app/                      Electron UI source
scripts/                  Shared Python render, analysis, transcript, and FFmpeg tools
projects/<project-id>/    User projects, selected media manifests, and rendered outputs
.video-edit/              Local app runtime state and logs
release/                  Packaged Electron builds
config/                   App-level defaults and portable config files
docs/                     App architecture and workflow notes
```

Root-level `source/` and `output/` belonged to the old single-video workflow and are not part of the app runtime contract. Large media, generated outputs, `.video-edit/`, `projects/`, and packaged builds are ignored by Git.

## Current Render Entry Points

Electron direct actions and command-line automation can also use the shared runtime-config runner:

```powershell
$env:VIDEO_EDIT_PROJECT = "client-a-interview"
python .\scripts\video_edit_run.py --action transcribe-dropped
python .\scripts\video_edit_run.py --action generate-music-bed
python .\scripts\video_edit_run.py --action replace-audio
python .\scripts\video_edit_run.py --action generate-thumbnail
python .\scripts\video_edit_run.py --action generate-thumbnail-candidates
python .\scripts\video_edit_run.py --action review-subtitles
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action compare-transcripts
python .\scripts\video_edit_run.py --action build-timeline
python .\scripts\video_edit_run.py --action validate-timeline
python .\scripts\video_edit_run.py --action detect-changed-regions
python .\scripts\video_edit_run.py --action export-otio
python .\scripts\video_edit_run.py --action import-otio
python .\scripts\video_edit_run.py --action export-changed-region-commands
python .\scripts\video_edit_run.py --action export-changed-region-remotion-and-blender-commands
python .\scripts\video_edit_run.py --action render-changed-regions-with-remotion-and-blender
python .\scripts\video_edit_run.py --action export-ffmpeg-command
python .\scripts\video_edit_run.py --action export-ffmpeg-preview-command
python .\scripts\video_edit_run.py --action render-timeline-ffmpeg
python .\scripts\video_edit_run.py --action export-remotion-command
python .\scripts\video_edit_run.py --action render-remotion-layers
python .\scripts\video_edit_run.py --action export-ffmpeg-preview-with-remotion-overlays
python .\scripts\video_edit_run.py --action render-preview-with-remotion-overlays
python .\scripts\video_edit_run.py --action export-ffmpeg-with-remotion-overlays
python .\scripts\video_edit_run.py --action render-final-with-remotion-overlays
python .\scripts\video_edit_run.py --action export-hyperframes-command
python .\scripts\video_edit_run.py --action render-hyperframes-layers
python .\scripts\video_edit_run.py --action export-blender-command
python .\scripts\video_edit_run.py --action render-blender-elements
python .\scripts\video_edit_run.py --action export-ffmpeg-preview-with-remotion-and-blender
python .\scripts\video_edit_run.py --action render-preview-with-remotion-and-blender
python .\scripts\video_edit_run.py --action export-ffmpeg-with-remotion-and-blender
python .\scripts\video_edit_run.py --action render-final-with-remotion-and-blender
python .\scripts\video_edit_run.py --action render-selected
```

The Electron app writes a project-local runtime config under `projects\<project-id>\output\app\video_edit_app_config.runtime.json` and passes it through `VIDEO_EDIT_APP_CONFIG`. The runner delegates to common render, analysis, FFmpeg, and ffprobe commands. It requires project context and does not fall back to old root `source/` or `output/` files, nor to stale `.video-edit` runtime config.

The operator and AI-editable project settings live in `projects\<project-id>\project_state.json`. The Electron UI keeps this file synchronized with current selections and reloads it while the project is active, so an AI agent can change options such as subtitle color, render mode, music, thumbnail, review, and analysis settings without using the human UI. Runtime config remains an execution snapshot generated from that project state. Command-line runs also read `project_state.json` when `VIDEO_EDIT_PROJECT` or `VIDEO_EDIT_PROJECT_ROOT` is set and `VIDEO_EDIT_APP_CONFIG` is not.

Renderer-agnostic edit decisions now have a first-class timeline contract. `build-timeline` writes `projects\<project-id>\output\timelines\current.timeline.json` using `config\timeline.schema.json`, then validates it with `timeline_validate.py` and writes `output\reports\timeline_validation.json`. AI edits should target this timeline JSON or the project settings that generate it; renderer adapters are responsible for FFmpeg, Remotion, HyperFrames, Blender, or OTIO command/data generation. `detect-changed-regions` compares the validated timeline with `previous.timeline.json`, writes `output\reports\timeline_changed_regions.json`, and the changed-region render actions can export or execute only those merged time ranges, including staged Remotion + Blender overlay handoff. `export-otio` writes an OpenTimelineIO-style JSON file at `output\timelines\current.otio`, and `import-otio` can restore embedded video-edit timelines. `export-ffmpeg-command` reads the validated timeline and writes audited FFmpeg argv/filter-graph artifacts under `output\reports\renderer_commands` and `output\reports\filtergraphs`. It consumes timeline clip scale/crop-center intent, uses or generates precomposed rich PNG subtitle overlays when the timeline references a PNG manifest, with ASS/SRT/VTT subtitle filters as fallback. `export-ffmpeg-preview-command` exports the timeline preview range as a proxy command without rendering by default. `render-timeline-ffmpeg` executes the validated FFmpeg adapter command and writes a render log under `output\reports\render_logs`. `export-remotion-command`, `export-hyperframes-command`, and `export-blender-command` use `scripts\timeline_graphics_adapter.py` to write validated layer/job manifests plus audited renderer argv reports; the matching render actions execute those external adapters when dependencies are present. `render-remotion-layers` executes the Remotion overlay adapter explicitly as a transparent PNG sequence. Remotion and Blender overlay artifacts can be composed into FFmpeg via preview/final actions, including `export-ffmpeg-preview-with-remotion-and-blender` / `render-preview-with-remotion-and-blender` and `export-ffmpeg-with-remotion-and-blender` / `render-final-with-remotion-and-blender`. The Remotion scaffold in `remotion\index.tsx` renders overlay layers from the manifest and materializes subtitle/logo assets under ignored `public\adapter-assets`; base camera/audio assembly remains FFmpeg's job.

Background music is controlled by the runtime `music` config. The app can generate a reusable project music bed at `output/audio/music_bed.wav` and mix it either across the whole render or only inside omission/title-card ranges. Those ranges are auto-detected from current overlay manifests when possible, and operator-entered ranges such as `00:12-00:18` can be added as overrides.

Audio replacement is app-level shared behavior. `replace-audio` copies the selected input video's video stream, replaces its audio with the selected current-project external audio, applies the current `app_sync_offsets.json` offset when available, and can run the same silence-shortening pass as renders.

The common renderer can also replace configured omission/interviewer ranges with a project-local summary card generated by `scripts/generate_omission_card.py`. This is driven by `omissionCard.*` in the runtime config, shifts later subtitle/glossary timing forward, and can reuse the same omission ranges used for BGM.

The old one-off render's natural dialogue cut and audio mastering behavior is now generic app behavior. `render.naturalDialogueCuts` moves selected camera boundaries to nearby low-energy speech gaps without changing audio timing, and `render.audioMastering` applies the common high-pass, denoise, dynamics, and loudness chain to the selected project audio.

Render encoding is also runtime-config driven. `render.encoderPreset` and `render.crf` replace the old one-off `--preset` / `--crf` flags, and the same settings are reused when silence-shortening re-encodes the final output.

Camera/audio sync is generic app behavior. `auto-sync-dropped` writes `output/reports/app_sync_offsets.json` from selected project media and now includes local fine waveform refinement after the coarse match, replacing the old fixed-source `refine_*` sync scripts. The renderer can also use the current `compare-transcripts` report as a fallback for missing or low-score waveform sync, but only when the report's manifest fingerprint matches the active project.

Thumbnail generation and subtitle QA are also app-level actions now. `generate-thumbnail` writes `output/images/thumbnail.png` from the current project video and style fields; `generate-thumbnail-candidates` writes multiple project-driven candidates plus `output/images/thumbnail_candidates/thumbnail_candidates_contact_sheet.jpg`, with optional detected-face debug boxes for layout QA; `review-subtitles` reads the current project transcription manifest and writes `output/reports/subtitle_review.json` plus Markdown, with optional flagged-caption WAV clips and clip re-transcription under `output/diagnostics/subtitle_review`; `apply-subtitle-corrections` applies operator-entered subtitle fixes to a project-local corrected transcript so later overlay generation uses the corrected subtitle only; `classify-subtitle-speakers` writes `output/reports/full_transcript_speaker_roles.json` from operator-entered interviewer ranges/patterns/manual roles and can include current-project mouth-motion, mouth-opening, audio RMS, and mouth/audio correlation diagnostics; `compare-transcripts` compares current project source transcripts against the primary transcript and writes `output/reports/transcript_comparison.json` plus Markdown with match classes and suggested offsets. These actions fail when current project inputs are missing instead of using historical single-video files.

## Source Video Person Analysis

Generate per-video person bbox metadata before editing:

```powershell
python .\scripts\analyze_person_edit_metadata.py --fps-sample 1
```

Or run the two steps separately:

```powershell
python .\scripts\analyze_person_bboxes.py --fps-sample 1
python .\scripts\build_person_edit_plan.py
```

`analyze_person_bboxes.py` writes frame-level YOLO person detections to the active project output under `reports/person_bboxes`, including eye-vs-face direction evidence, optional MediaPipe iris-based gaze evidence, optional mouth-opening landmarks, and a fixed/moving camera-motion flag.
`build_person_edit_plan.py` converts those detections into segment-level guidance for crop, zoom, cut, and wide-shot decisions under the active project output `reports/person_edit_plans`; fixed-camera shots use the dominant face direction for stable look-space placement.
The Electron interview renderer uses those plans by default for per-camera segment crops, and writes `reports/person_crop_usage.json` with the matched plans and rendered segments. The timeline path also supports face-center crop reports through `render.faceCenterCrop`, embedding detected crop centers in clip `scaleCrop` effects for the FFmpeg adapter. Full person-edit-plan parity remains a renderer-adapter follow-up. Composition guidance uses shared mathematical anchors from `scripts/composition_rules.py`: golden-ratio lines, thirds, silver-ratio lines, and outer-golden anchors for stronger side placement. The generated analysis includes target subject x/y ratios and anchor names so renderers can use the same placement rules.

The detector uses Ultralytics YOLO. Install it in the project Python environment if needed:

```powershell
python -m pip install ultralytics
```

For more precise gaze and mouth-opening metrics, install MediaPipe in the same Python environment:

```powershell
python -m pip install mediapipe
```

For a short style reference video, keep the video under 60 seconds and generate a reference profile:

```powershell
python .\scripts\analyze_person_edit_metadata.py `
  --input .\projects\client-a-interview\source\video\reference.mp4 `
  --fps-sample 1 `
  --max-duration 60 `
  --output-dir .\projects\client-a-interview\output\reports\reference_person_bboxes `
  --plan-output-dir .\projects\client-a-interview\output\reports\reference_edit_plans `
  --reference-profile-output .\projects\client-a-interview\output\reports\reference_edit_profile.json
```

The reference profile is used by the Electron dropped-file interview renderer as a target for person size, crop placement, and simple visual tone.

For multicam renders, the app can also match close-up camera white balance, brightness, contrast, and saturation to the master camera before applying the reference profile. The renderer writes the sampled channel gains and adjustments to `output/reports/camera_color_match.json`.

`Speaker-aware interview cuts` use the current subtitle overlay speaker roles: interviewer ranges stay on the master camera, while onscreen answer ranges rotate through close-up cameras. `Rhythmic punch-in cuts` is the app-level replacement for the old fixed `--dynamic-cuts` render path: it builds short current-project camera segments from captions when available, falls back to a reusable rhythmic schedule, and applies generic punch-in reframes. The renderer also constrains camera plans to each source file's synced timeline coverage, replacing out-of-coverage camera segments with a covered fallback and writing `output/reports/source_coverage_usage.json`. `Use saved manual plan` reads `render.cameraPlan` or `output/reports/manual_camera_plan.json`, using generic segment rows with `role`, `start`, and `end`.

Electron dropped-file interview renders can also accept multiple still-image inserts. Text/diagram images are shown static near matching transcript text when possible; photo-like images are analyzed for faces or visual focus and get subtle person-, landscape-, or object-appropriate pan/zoom with fade in/out.

For the detailed workflow, see `docs/video_edit_method.md`.
