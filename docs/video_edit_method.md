# Video Edit Common Workflow

This project should operate from the selected media, project state, and runtime app config snapshot, not from fixed historical source files.

## Source Of Truth

- Editable project state: `projects/<project-id>/project_state.json`
- Runtime config snapshot: `projects/<project-id>/output/app/video_edit_app_config.runtime.json` through `VIDEO_EDIT_APP_CONFIG`; if that env var is unset, scripts read the active project's `project_state.json`
- Media manifest: `assets.mediaManifest` or `assets.mediaManifestPath`
- Project roots: `project.sourceRoot` and `project.outputRoot`
- Transcript overlays: generated from the current project transcript under `projects/<project-id>/output/transcripts/manifest_sources`

Render and overlay scripts must not fall back to hardcoded subtitles, fixed camera filenames, or previous project output.

## Common Commands

```powershell
$env:VIDEO_EDIT_PROJECT = "client-a-interview"
python .\scripts\video_edit_run.py --action transcribe-dropped
python .\scripts\video_edit_run.py --action transcribe-dropped-faster
python .\scripts\video_edit_run.py --action auto-sync-dropped
python .\scripts\video_edit_run.py --action analyze-person-edit-metadata
python .\scripts\video_edit_run.py --action analyze-blocking
python .\scripts\video_edit_run.py --action generate-music-bed
python .\scripts\video_edit_run.py --action replace-audio
python .\scripts\video_edit_run.py --action generate-thumbnail
python .\scripts\video_edit_run.py --action generate-thumbnail-candidates
python .\scripts\video_edit_run.py --action review-subtitles
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action compare-transcripts
python .\scripts\video_edit_run.py --action render-selected
```

## Render Contract

`scripts/render_app_interview.py` is the common renderer. It reads cameras, audio, logo, still images, subtitle mode, title text, style, sync offsets, and output path from the runtime config.

Camera/audio sync is controlled by `scripts/auto_sync_app_sources.py`. It reads the current media manifest, finds coarse offsets against the master camera, then performs local fine waveform refinement and writes both coarse and refined values to `output/reports/app_sync_offsets.json`. `scripts/compare_manifest_transcripts.py` also writes transcript-derived offsets; the renderer uses those only as a current-project fallback for missing or low-score waveform sync and records the selected source in `output/reports/sync_offset_usage.json`.

Long-form sync QA must include user-reported bad-cut regions before a full rerender is accepted. For the current project, render and inspect a five-minute test centered around 31:52, and reuse existing transcript outputs if the user says not to re-transcribe.

Multicam planning is controlled by `render.multicamMode`. `master-first` keeps a simple master/close-up rotation. `speaker-aware` reads current subtitle overlay speaker roles, keeps interviewer ranges on the master camera, and rotates onscreen answer ranges through close-up cameras. `dynamic-cuts` replaces the old fixed `--dynamic-cuts` path with current-project short rhythmic camera segments and generic punch-in reframes. After planning, `scripts/render_app_interview.py` constrains segments to each selected camera's synced source coverage and writes `output/reports/source_coverage_usage.json`, so short or partial alternate-camera clips are not used outside their valid timeline range. `manual-plan` reads `render.cameraPlan` or `output/reports/manual_camera_plan.json`; segment rows use reusable fields such as `role`, `start`, and `end`, not fixed source filenames.

Natural dialogue camera cuts are controlled by `render.naturalDialogueCuts`. When enabled, `scripts/render_app_interview.py` analyzes the selected project audio around each generated camera boundary, moves the boundary to a nearby low-energy speech gap, writes `output/reports/natural_dialogue_cuts.json`, and leaves audio timing unchanged.

Camera color matching is controlled by `render.colorMatchCameras`. When enabled for multicam projects, the renderer samples the selected camera files, uses the first/master camera as the reference, applies per-camera white-balance channel gains plus brightness/contrast/saturation correction in FFmpeg, and writes `output/reports/camera_color_match.json`.

Global camera push-in is controlled by `render.globalVideoZoom`. The current preferred full-analysis style is a 20% push-in on all camera video segments, applied in the FFmpeg visual filter graph before subtitles, title, and logo overlays.

Audio mastering is controlled by `render.audioMastering`. It applies the shared online-video chain from the old one-off render: high-pass, optional denoise, dynamic normalization, compression, and loudness normalization on the currently selected project audio.

Render encoding is controlled by `render.encoderPreset` and `render.crf`. These settings are the app-level replacement for the old one-off `--preset` / `--crf` flags and are used by both the common renderer and silence-shortening re-encode.

GPU encoding is controlled by `render.videoEncoder`. Use `h264_nvenc` when an NVIDIA GPU is available and quick iteration matters; use `render.nvencPreset` and `render.cq` for NVENC quality/speed tuning. Keep `libx264` with `render.encoderPreset` and `render.crf` when CPU encoding quality/size tradeoffs are preferred. Benchmark short samples before full renders because low CQ NVENC values can create much larger files.

Background music is app-level shared behavior. `scripts/generate_music_bed.py` reads `music.prompt`, `music.mood`, `music.outputPath`, and the active project output root, then writes a project-local WAV plus a JSON sidecar. The common renderer reads `music.enabled`, `music.scope`, `music.rangeSource`, `music.volume`, and `music.rangesText`; `scope=full` mixes the bed through the whole render, while `scope=omission` raises the music only inside auto-detected omission/interviewer overlay ranges plus explicit ranges such as `00:12-00:18`.

Audio replacement is app-level shared behavior. `scripts/replace_video_audio.py` reads `workflow.inputVideoPath`, `replaceAudio.audioPath` or the selected external audio, `render.outputPath`, and `render.syncOffsetsPath`, then copies the input video stream while replacing audio from the current project external source. It does not use old `sound2` paths and can run the same silence-shortening pass as renders.

Omission-card replacement is also app-level shared behavior. `scripts/generate_omission_card.py` creates a project-local summary card from `omissionCard.text`, `omissionCard.label`, `omissionCard.duration`, and `omissionCard.rangesText`. When enabled, `scripts/render_app_interview.py` removes those source ranges from the camera/audio timeline, inserts the generated card for the configured duration, shifts later subtitle/glossary overlays, and maps omission-scope BGM to the card's output range.

Thumbnail and subtitle review behavior is app-level shared behavior. `scripts/generate_project_thumbnail.py` reads `thumbnail.*`, the current project video selection, style title/color/logo fields, and writes `output/images/thumbnail.png`. `scripts/generate_thumbnail_candidates.py` writes multiple project-driven thumbnail candidates and a contact sheet without relying on old fixed source images; `thumbnail.debugFaces` can draw detected face boxes on candidates for layout QA. `scripts/review_subtitles.py` reads only the current project transcript manifest and writes subtitle QA reports under `output/reports`, including optional operator-entered suspicious patterns, flagged-caption WAV clips, and clip re-transcription under `output/diagnostics/subtitle_review`. `scripts/apply_subtitle_corrections.py` applies operator-entered correction rows to the current project transcript manifest and redirects later overlay generation to the corrected SRT. `scripts/classify_subtitle_speakers.py` writes `full_transcript_speaker_roles.json` from operator-entered interviewer ranges/patterns/manual roles, and can include mouth-motion, MediaPipe mouth-opening, audio RMS, and mouth/audio correlation diagnostics from the current project timeline, so full subtitle overlays and omission-range BGM detection can use current project speaker roles. `scripts/compare_manifest_transcripts.py` replaces the old fixed-video transcript comparison diagnostics with a manifest-driven report that compares every current source transcript against the primary transcript, writes `output/reports/transcript_comparison.json` plus Markdown, and can feed render sync fallback when `render.useTranscriptComparisonSync` is enabled.

Full subtitle overlays use only the selected/parsed project transcript. If no current transcript exists, generation should fail instead of using older subtitles.

The preferred full-subtitle visual baseline is the pre-app PNG overlay style from `scripts/generate_full_transcript_png_overlays.py` / `scripts/subtitle_png_style.py`. Plain ASS is only an implementation fallback for very long renders and must visually approximate that baseline.

Punchline overlays use only `style.punchlineText` from the runtime config. If it is empty, the generated manifest is empty.

## High Quality Full Analysis Render

For the reusable Codex-side full-analysis workflow, see `docs/codex_full_analysis_render_method.md`. That document records the current preferred setup: `large-v3` transcription through `faster-whisper` / CTranslate2 CUDA in `.video-edit\venvs\whisper-cu128`, all-source transcription/comparison, speaker-role subtitles, strict subtitle review/correction, skin-tone-based multicam color matching, 20% global camera push-in, online-video audio denoise/mastering, the specified right-logo asset, and optional `h264_nvenc` acceleration.

## Script Guidelines

- Script names should describe reusable behavior, not a specific clip, person, source camera, or date.
- Defaults must be generic. Project-specific values belong in the runtime config, media manifest, or project files.
- AI/operator option changes should go through `project_state.json`; runtime config is generated for a specific run.
- Root-level `source/` and `output/` are not valid app data sources; they are ignored legacy workspace names.
- Project context is required. Use the Electron app, `VIDEO_EDIT_APP_CONFIG`, or `VIDEO_EDIT_PROJECT`; do not rely on `.video-edit` fallback state.
- When a script cannot run without current project data, fail with a clear message rather than silently using older project files.
