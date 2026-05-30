# Video Edit Common Workflow

This project should operate from the selected media, project state, and runtime app config snapshot, not from fixed historical source files.

## Source Of Truth

- Editable project state: `projects/<project-id>/project_state.json`
- Runtime config snapshot: `projects/<project-id>/output/app/video_edit_app_config.runtime.json` through `VIDEO_EDIT_APP_CONFIG`; if that env var is unset, scripts read the active project's `project_state.json`
- Media manifest: `assets.mediaManifest` or `assets.mediaManifestPath`
- Normalized edit timeline: `projects/<project-id>/output/timelines/current.timeline.json`, validated against `config/timeline.schema.json`
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
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
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

## Timeline Contract

The AI/operator editing contract is moving from renderer commands to a normalized JSON timeline:

- AI-editable decisions should be expressed as timeline JSON or as project-state settings that deterministically build timeline JSON.
- `scripts/build_edit_timeline.py` converts the current project config, media manifest, sync offsets, transcript selection, camera plan reports, face-center crop reports, color reports, and selected style inputs into `output/timelines/current.timeline.json`.
- `scripts/timeline_validate.py` validates strict schema conformance, source existence, media in/out bounds, non-overlapping tracks, transition references/ranges, preview range bounds, timeline duration bounds, and numeric bounded sync offsets before any renderer adapter runs.
- `scripts/timeline_changed_regions.py` compares the validated timeline with a previous/baseline timeline, writes `output/reports/timeline_changed_regions.json`, and can generate or execute per-region FFmpeg commands, optionally with Remotion and Blender overlay rendering first.
- `scripts/timeline_otio_adapter.py` exports the validated timeline as OpenTimelineIO-style JSON and imports embedded video-edit timelines for interoperability.
- Renderer adapters consume the validated timeline and generate technical commands. `scripts/ffmpeg_timeline_adapter.py` exports FFmpeg argv/filter-graph audit artifacts for the core timeline tracks, supports optional execution with render logs, has full-target plus preview/proxy export modes, and can composite validated Remotion or Blender PNG-sequence overlay artifacts. `scripts/timeline_graphics_adapter.py` exports Remotion/HyperFrames layer manifests and Blender job manifests plus audited renderer argv reports; matching workflow actions execute those adapters when dependencies are present. The combined workflow actions run Remotion/Blender first, then FFmpeg, using range-specific overlay artifacts for preview renders. `remotion/index.tsx` is the current Remotion overlay composition scaffold. `scripts/render_app_interview.py` remains the production FFmpeg-backed renderer until adapter parity is complete.
- Audit artifacts should remain traceable: analysis reports, timeline JSON, validation report, renderer commands/filter graphs, and render logs.

Current FFmpeg adapter scope:

- Implemented: `video.main` clip trimming/concat, `audio.main` trimming/concat plus denoise/mastering, image overlays on `overlay.graphics`, rich PNG subtitle overlay via generated or reused precomposed transparent video when the timeline references a PNG manifest, FFmpeg-filter subtitle fallback for ASS/SRT/VTT subtitle clips, optional Remotion/Blender PNG-sequence overlay composition, clip-level scale/crop-center and color filter chains embedded by the timeline builder, music-bed mixing when the timeline references an existing audio source, partial timeline-range export, low-resolution proxy export, changed-region command generation/execution, optional execution, and render-log capture.
- Explicitly reported as unsupported in the FFmpeg adapter: full person-edit-plan crop parity and natural-cut parity currently embedded in `render_app_interview.py`. HyperFrames/Blender export is handled separately by `scripts/timeline_graphics_adapter.py`.

Current graphics adapter scope:

- Implemented: Remotion and HyperFrames JSON layer manifests for video/audio references, subtitles, image overlays, generated overlay clips, partial timeline ranges, and audited external renderer argv reports. Remotion also has a bundled overlay composition scaffold in `remotion/index.tsx`; the adapter copies subtitle/logo PNGs into ignored `public/adapter-assets`, renders transparent PNG-sequence overlay artifacts, and writes overlay handoff metadata for FFmpeg composition. Blender job manifests are generated for clips explicitly marked with `metadata.renderer = "blender"`, `style.renderer = "blender"`, `style.engine = "blender"`, or Blender-specific effect types; the adapter also writes a Blender Python script for transparent PNG-sequence 3D text layers and handoff metadata for FFmpeg composition.
- Explicitly reported as not ready: full source media playback inside Remotion, single-file alpha video overlay export, a bundled HyperFrames renderer project/executable, and automatic Blender selection for normal 2D overlays.

Partial preview command example:

```powershell
$env:VIDEO_EDIT_PROJECT = "client-a-interview"
python .\scripts\ffmpeg_timeline_adapter.py --range-start 1612 --range-end 1912 --proxy
```

## Render Contract

`scripts/render_app_interview.py` is the common renderer. It reads cameras, audio, logo, still images, subtitle mode, title text, style, sync offsets, and output path from the runtime config.

Camera/audio sync is controlled by `scripts/auto_sync_app_sources.py`. It reads the current media manifest, finds coarse offsets against the master camera, then performs local fine waveform refinement and writes both coarse and refined values to `output/reports/app_sync_offsets.json`. `scripts/compare_manifest_transcripts.py` also writes transcript-derived offsets; the renderer uses those only as a current-project fallback for missing or low-score waveform sync and records the selected source in `output/reports/sync_offset_usage.json`.

When the final audio is an external WAV, do not trust one global source offset for every multicam cut. `scripts/render_app_interview.py` must run the external-audio cut sync guard after camera planning, natural dialogue cuts, onscreen-speaker masking, and source-coverage clipping. The guard compares each non-master camera segment's embedded audio against the selected external WAV at the exact rendered timeline position, using short local RMS-envelope waveform probes. It writes `output/reports/external_audio_cut_sync_report.json`.

Default guard behavior is conservative: keep the sub camera only when the local waveform score is high enough and the best local shift stays inside the configured tolerance. Otherwise replace that segment with the long master camera. Current config keys are `render.externalAudioCutSyncGuard`, `render.externalAudioCutSyncMinScore`, `render.externalAudioCutSyncMaxShift`, `render.externalAudioCutSyncProbeDuration`, `render.externalAudioCutSyncSearchRadius`, and `render.externalAudioCutSyncMaxProbes`. For this project, the first audit showed `camera2` and `camera3` are not reliable enough for the full render; `camera4` and `camera5` are the safer close-up sources.

Long-form sync QA must include user-reported bad-cut regions before a full rerender is accepted. For the current project, render and inspect a five-minute test centered around 31:52, and reuse existing transcript outputs if the user says not to re-transcribe.

Multicam planning is controlled by `render.multicamMode`. `master-first` keeps a simple master/close-up rotation. `speaker-aware` reads current subtitle overlay speaker roles, keeps interviewer ranges on the master camera, and rotates onscreen answer ranges through close-up cameras. `dynamic-cuts` replaces the old fixed `--dynamic-cuts` path with current-project short rhythmic camera segments and generic punch-in reframes. After planning, `scripts/render_app_interview.py` constrains segments to each selected camera's synced source coverage and writes `output/reports/source_coverage_usage.json`, so short or partial alternate-camera clips are not used outside their valid timeline range. `manual-plan` reads `render.cameraPlan` or `output/reports/manual_camera_plan.json`; segment rows use reusable fields such as `role`, `start`, and `end`, not fixed source filenames.

Close-up sub cameras must be gated by speaker role even when `render.multicamMode = manual-plan`. Enable `render.closeupsOnlyWhenOnscreenSpeaker = true` so `scripts/render_app_interview.py` reads the selected SRT plus `subtitleSpeakers.outputPath`, builds onscreen-speaker speech ranges, and replaces close-up camera segments with the master camera whenever the visible interviewee is not speaking. This pass runs after manual/dynamic camera planning and natural dialogue cut adjustment, then writes `output/reports/onscreen_closeup_camera_mask.json`. In the current project, `subtitleSpeakers.outputPath` should point to `output/reports/full_transcript_speaker_roles_audio_lr.json`, because the audio LR classifier is the stronger source for interviewer vs visible interviewee.

Natural dialogue camera cuts are controlled by `render.naturalDialogueCuts`. When enabled, `scripts/render_app_interview.py` analyzes the selected project audio around each generated camera boundary, moves the boundary to a nearby low-energy speech gap, writes `output/reports/natural_dialogue_cuts.json`, and leaves audio timing unchanged.

Silence shortening is controlled by `render.shortenSilence`. For normal interview renders, keep it enabled with `render.minSilence = 3.0`, `render.keepSilence = 2.0`, and `render.silenceNoise = "-30dB"`. This means any no-speech/silent region of 3 seconds or longer is reduced to 2 seconds by cutting the middle of the silent region. Silences shorter than 3 seconds are left untouched. The cut is applied after the base render, so both video and audio are shortened together and sync is preserved. The renderer writes `<output>.silence_shortening.json` with detected silences, removed ranges, and kept ranges. The current `projects/new-folder-2/project_state.json` default is enabled for the next normal render. Do not use this for debugging exact source/video sync unless the user explicitly asks for silence-shortened timing.

Silence shortening must be treated as a final-delivery timing pass, not a multicam sync tool. If a later pass generates PNG/ASS subtitle overlays separately from the base render, generate or shift the subtitle timing against the shortened output, or run the subtitle overlay before this pass so the subtitles are cut with the video.

Camera color matching is controlled by `render.colorMatchCameras`. When enabled for multicam projects, the renderer samples the selected camera files, uses the first/master camera as the reference, applies per-camera white-balance channel gains plus brightness/contrast/saturation correction in FFmpeg, and writes `output/reports/camera_color_match.json`. Sampling must happen after the final camera plan is known. Do not sample every camera at generic preview timestamps; sample only the timeline ranges where that camera is actually used, and compare each sub-camera sample against the master camera at the same synced timeline moment. The report should show `sampleBasis: actual camera plan`.

Brightness matching must not rely on skin samples alone: close-up sub cameras can have matching skin values while the whole shot and background are still too dark. The renderer therefore blends skin brightness, global frame brightness, and neutral non-skin/background brightness before deciding the FFmpeg `eq=brightness` value.

For background brightness matching, do not treat black clothing or dark foreground areas as the background. The current renderer uses a conservative neutral-background sample: non-skin pixels with low saturation and mid/high value (`hsv.s < 90`, `80 < hsv.v < 245`), with the detected face/person neighborhood excluded when possible. This aims to compare wall/room/background brightness against the long master camera instead of letting dark clothes force an excessive lift.

For white balance, prioritize low-saturation wall/background and neutral pixels. Skin is useful for exposure and subtitle-facing QA, but it should not drive channel gains; using skin for channel gains made the pale interview background drift green/cyan. Current channel-gain weighting is background-first (`backgroundBgr` 80%, `neutralBgr` 20%). For saturation, use more global/background weight and less skin weight, because the visible mismatch across camera cuts is usually the wall/background density rather than only skin.

Color temperature matching is separate from exposure and saturation, but do not judge it from `R/B` alone. For pale wall/background shots, also compare the wall `R/G` ratio; if `R/G` is below the master, the shot will read cyan/green/blue even when `R/B` looks plausible. Enable `render.colorMatchTemperature = true` for the automatic baseline, then verify rendered wall/background pixels with a bright low-saturation mask. For the current `camera5` audit, the rendered problematic close-ups were `R/G ~= 0.99, R/B ~= 1.17`, while the good close-up/master background target was about `R/G ~= 1.05, R/B ~= 1.23`; the fix is to raise red relative to green and reduce the blunt saturation-only override, not to add more blue.

If the whole edit should be slightly whiter/cooler, apply it as a shared final camera look with `render.outputLookFilter`, not as `cameraExtraFilters.master`. The current preferred adjustment is subtle and applies to every camera after per-camera matching: `colorchannelmixer=rr=0.99000:gg=1.00000:bb=1.01200,eq=brightness=0.0140:contrast=0.9850:saturation=0.9600`. This keeps the master from moving away from the sub cameras after matching.

Global camera push-in is controlled by `render.globalVideoZoom`. The current preferred full-analysis style is a 20% push-in on all camera video segments, applied in the FFmpeg visual filter graph before subtitles, title, and logo overlays.

Face-centered framing is required for multicam tests and final renders when push-in is enabled, but the default is horizontal-only centering. Before rendering, sample the actual timeline ranges for each selected camera, detect the visible face/person position with OpenCV or the app person-analysis metadata, and write a framing report under `output/reports`. The timeline builder embeds the detected crop center into each `scaleCrop` effect when `render.faceCenterCrop` is enabled; the FFmpeg adapter consumes that renderer-agnostic crop intent as crop-center expressions. Keep the original vertical center crop unless `render.faceCenterCropAxis` is explicitly `xy`, and keep the zoom amount at `render.globalVideoZoom` instead of increasing zoom to force exact centering.

For the long wide master camera, do not force the person to exact center. The current preferred framing leaves the person slightly to the right, while close-up sub cameras remain centered. Configure this with `render.faceCenterSubjectXByRole.master = 0.54`; the renderer shifts the crop window left so the detected master subject lands around 54% of the screen width. Keep sub-camera roles at the default `0.50` unless a specific shot needs a separate composition.

Close-up sub cameras can remain visually too dense, too dark, or too saturated/desaturated even after automatic master matching. Check `brightnessComponents` and `saturationComponents` in `camera_color_match.json`; if global/background deltas are positive, the sub camera should be lifted toward the master even when skin brightness is already close. Do not solve this with a one-off saturation-only override. The renderer should compare face/skin, neutral background, and global frame statistics, trim outlier pixels before averaging, and then emit one FFmpeg color match filter. Prefer this over frame-by-frame Python processing. If a manual `cameraExtraFilters` override is still needed, make it ratio-aware and verify the wall mask before full render. Current `camera5` correction is `colorchannelmixer=rr=1.06500:gg=0.98500:bb=1.00000,eq=brightness=-0.0140:contrast=1.0000:saturation=1.1200`, selected because it moves the problematic wall background from `R/G ~= 0.99, R/B ~= 1.17` to about `R/G ~= 1.07, R/B ~= 1.23`, close to the good close-up target.

Audio mastering is controlled by `render.audioMastering`. It applies the shared online-video chain from the old one-off render: high-pass, optional denoise, dynamic normalization, compression, and loudness normalization on the currently selected project audio.

Render encoding is controlled by `render.encoderPreset` and `render.crf`. These settings are the app-level replacement for the old one-off `--preset` / `--crf` flags and are used by both the common renderer and silence-shortening re-encode.

GPU encoding is controlled by `render.videoEncoder`. Use `h264_nvenc` when an NVIDIA GPU is available and quick iteration matters; use `render.nvencPreset` and `render.cq` for NVENC quality/speed tuning. Keep `libx264` with `render.encoderPreset` and `render.crf` when CPU encoding quality/size tradeoffs are preferred. Benchmark short samples before full renders because low CQ NVENC values can create much larger files.

For interview deliverables, prefer `render.outputFps = "30000/1001"` unless the user explicitly needs 60fps. The renderer must apply this as one shared FPS conversion after all camera segments have been concatenated, before title/logo/subtitle overlays. Do not only add a final output `-r`; that drops frames after the expensive filters and does not define the timeline used by overlays.

Important sync correction: do not apply `fps=30000/1001` independently inside every camera segment before `concat`. Segment-local FPS conversion accumulates frame rounding errors over many cuts; the audio remains continuous, so the rendered video gradually lags behind the external WAV and the audio appears early. In the 2026-05-29 investigation, external WAV sync stayed stable within roughly `-0.025s`, while the video-only comparison against source frames showed about `0.4s` lag near 17 minutes and about `0.8s` lag later in the render. The renderer should trim and style camera segments at source timing, `concat` the segments first, then apply one shared `fps=<render.outputFps>` to the concatenated base video before overlays. If drift is suspected, verify with visual frame matching against source frames at several timeline points, not only audio waveform correlation.

Background music is app-level shared behavior. `scripts/generate_music_bed.py` reads `music.prompt`, `music.mood`, `music.outputPath`, and the active project output root, then writes a project-local WAV plus a JSON sidecar. The common renderer reads `music.enabled`, `music.scope`, `music.rangeSource`, `music.volume`, and `music.rangesText`; `scope=full` mixes the bed through the whole render, while `scope=omission` raises the music only inside auto-detected omission/interviewer overlay ranges plus explicit ranges such as `00:12-00:18`.

Audio replacement is app-level shared behavior. `scripts/replace_video_audio.py` reads `workflow.inputVideoPath`, `replaceAudio.audioPath` or the selected external audio, `render.outputPath`, and `render.syncOffsetsPath`, then copies the input video stream while replacing audio from the current project external source. It does not use old `sound2` paths and can run the same silence-shortening pass as renders.

Omission-card replacement is also app-level shared behavior. `scripts/generate_omission_card.py` creates a project-local summary card from `omissionCard.text`, `omissionCard.label`, `omissionCard.duration`, and `omissionCard.rangesText`. When enabled, `scripts/render_app_interview.py` removes those source ranges from the camera/audio timeline, inserts the generated card for the configured duration, shifts later subtitle/glossary overlays, and maps omission-scope BGM to the card's output range.

Thumbnail and subtitle review behavior is app-level shared behavior. `scripts/generate_project_thumbnail.py` reads `thumbnail.*`, the current project video selection, style title/color/logo fields, and writes `output/images/thumbnail.png`. `scripts/generate_thumbnail_candidates.py` writes multiple project-driven thumbnail candidates and a contact sheet without relying on old fixed source images; `thumbnail.debugFaces` can draw detected face boxes on candidates for layout QA. `scripts/review_subtitles.py` reads only the current project transcript manifest and writes subtitle QA reports under `output/reports`, including optional operator-entered suspicious patterns, flagged-caption WAV clips, and clip re-transcription under `output/diagnostics/subtitle_review`. `scripts/apply_subtitle_corrections.py` applies operator-entered correction rows to the current project transcript manifest and redirects later overlay generation to the corrected SRT. `scripts/classify_subtitle_speakers.py` writes `full_transcript_speaker_roles.json` from operator-entered interviewer ranges/patterns/manual roles, and can include mouth-motion, MediaPipe mouth-opening, audio RMS, and mouth/audio correlation diagnostics from the current project timeline, so full subtitle overlays and omission-range BGM detection can use current project speaker roles. `scripts/classify_speakers_audio_features.py` is the preferred automatic splitter when the project audio is stereo: it classifies each SRT caption from active-speech LR channel balance plus light acoustic diagnostics, and writes a role JSON compatible with the PNG overlay generator. `scripts/compare_manifest_transcripts.py` replaces the old fixed-video transcript comparison diagnostics with a manifest-driven report that compares every current source transcript against the primary transcript, writes `output/reports/transcript_comparison.json` plus Markdown, and can feed render sync fallback when `render.useTranscriptComparisonSync` is enabled.

Full subtitle overlays use only the selected/parsed project transcript. If no current transcript exists, generation should fail instead of using older subtitles.

The preferred full-subtitle visual baseline is the pre-app PNG overlay style from `scripts/generate_full_transcript_png_overlays.py` / `scripts/subtitle_png_style.py`. Plain ASS is only an implementation fallback for very long renders and must visually approximate that baseline. For five-minute or longer QA clips, do not pass every PNG subtitle as an individual FFmpeg input on Windows; precompose the PNG subtitle manifest into one transparent overlay video, then overlay that video onto the rendered base clip. For long multicam plans, also write the FFmpeg filter graph to `output/reports/filtergraphs/<output>.ffgraph` and use `-filter_complex_script`, because the filter graph itself can exceed the Windows command-line length even after subtitle precomposition.

Full subtitle line breaking must preserve readable phrase boundaries. `scripts/generate_full_transcript_png_overlays.py` should measure text at the actual rendered font size and choose line breaks by layout width plus Japanese phrase penalties, not by raw character count. Do not break inside protected terms or phrase-like units such as Latin/number tokens, katakana technical terms, `FDE`, `PDM`, `SaaS`, `SIer`, `Claude Code`, `プロダクトマネージャー`, `ジョブディスクリプション`, `リバースエンジニアリング`, or common Japanese chunks such as `難しい`, `働き方`, `考え方`, `ということ`, `みたいな`, and `している`. Also avoid splitting Japanese okurigana words between kanji and following hiragana, such as `務|まらない`, `受|け入れ`, or `限|られている`. Avoid second lines that start with particles, suffix fragments, or weak continuations such as `いう`, `って`, `こと`, `ところ`, `もの`, `ので`, `けど`, `とか`, `たり`, `です`, `ます`, `は`, `が`, `を`, `に`, `で`, `と`, `も`, and `の`. If a natural two-line break would split a word or phrase, allow the caption to become a later timed chunk instead of forcing an ugly two-line split.

After changing subtitle text or wrap rules, regenerate full PNG overlays and inspect the layout diagnostics. For the current project, the latest audit wrote `projects/new-folder-2/output/reports/subtitle_line_break_layout_review_20260529.json` and confirmed `highPenaltyBreaks = 0` before regenerating `output/overlays/full_transcript_png_overlays/manifest.json`.

### Chapter Title Overlay

The top-left title should not stay as a fixed generic label for interview renders. Treat `style.titleText` as a fallback only. For normal analysis renders, read the full transcript, split the interview into topic chapters, and write a chapter title file such as `projects/<project-id>/output/reports/chapter_titles_from_full_transcript.json`.

Enable chapter-aware titles in project state:

```json
{
  "style": {
    "chapterTitlesEnabled": true,
    "chapterTitlesPath": "projects/<project-id>/output/reports/chapter_titles_from_full_transcript.json",
    "titleX": 18,
    "titleY": 18
  }
}
```

`scripts/generate_chapter_title_png_overlays.py` converts that chapter JSON into timed PNG title overlays and a manifest under `output/overlays/chapter_title_png_overlays`. `scripts/render_app_interview.py` reads the manifest and overlays the matching title only during its chapter time range. The title style should reuse the rich top-left PNG title look, but be positioned close to the top-left corner; the current project uses `18:18`.

Chapter titles must be created from the actual transcript topic shifts, not from a hardcoded project name. Keep each title short enough to read quickly, for example `日本企業でワークするか`, and regenerate the chapter PNG manifest after changing the chapter file.

When filler words such as `あー`, `えー`, `えっと`, `まあ`, or `なんか` are removed from the displayed subtitle text, do not leave strongly early subtitles at the filler audio. However, do not make every caption appear only at the exact first word either. That creates rapid blinking, overly short one-line captions, and unnatural reading rhythm. Use a readability-first hybrid pass: match displayed SRT text against `faster-whisper` word timestamps, shift only captions that are clearly early, keep a small lead-in before the matched content word, merge close same-speaker captions when the combined text still reads naturally, and enforce a minimum display duration plus a short tail hold. Never shift captions earlier.

For short QA clips, the reusable script is `scripts/retime_subtitles_readable.py`. It reads an SRT, a word-timestamp JSON from the subtitle-free base audio, and optionally the speaker-role JSON. It writes a retimed SRT plus a report with timing adjustments, merges, and remapped output roles for the PNG overlay generator.

```powershell
python .\scripts\retime_subtitles_readable.py `
  --srt "projects/new-folder-2/output/transcripts/manifest_sources/<clip-local>.srt" `
  --words "projects/new-folder-2/output/transcripts/manifest_sources/<clip-word-timestamps>.json" `
  --roles "projects/new-folder-2/output/reports/<clip-speaker-roles>.json" `
  --output-srt "projects/new-folder-2/output/transcripts/manifest_sources/<clip-readable-retimed>.srt" `
  --output-report "projects/new-folder-2/output/reports/<clip-readable-retime-report>.json" `
  --lead-in 0.35 `
  --strong-delay 0.70 `
  --min-duration 1.35 `
  --tail-hold 0.25
```

After this pass, point `render.subtitlePath` at the retimed SRT and point `subtitleSpeakers.outputPath` at the report's remapped `outputRoles` JSON, then regenerate the rich PNG subtitles. In the 2026-05-29 Semiogo 90s QA sample, the readable pass changed only five strongly early captions, merged five adjacent captions, and reduced overlay churn while preserving the rich purple/black speaker subtitle style.

Speaker-role color must not rely only on punctuation or short text. For stereo external recordings, run `classify-subtitle-speakers-audio` first and inspect `lrDb`: in the current project, left-channel dominant speech is the offscreen interviewer and right-channel dominant speech is the visible interviewee. Treat weak LR separation as ambiguous, not automatically interviewer; use transcript meaning, neighboring strong-LR captions, and mouth-motion checks as tie-breakers. If the visible interviewee is quoting a question or asking a rhetorical question as part of their answer, keep it `onscreen`. If the offscreen interviewer is reacting, summarizing, or confirming from outside the frame, mark it `interviewer` so the full PNG subtitle uses the semi-transparent black box.

### Speaker Role From Audio

For this project, text-only speaker classification is not reliable enough. The preferred automatic route is stereo audio analysis:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
```

The reusable script is `scripts/classify_speakers_audio_features.py`. It reads the selected SRT and a stereo audio/video source, measures active-speech channel balance per subtitle segment, and writes a role JSON that `scripts/generate_full_transcript_png_overlays.py` can use directly.

Set `subtitleSpeakers.outputPath` to the audio LR output before rendering:

```json
{
  "subtitleSpeakers": {
    "outputPath": "projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr.json"
  }
}
```

Key fields in the output JSON:

- `audioFeatures.lrDb`: left-channel RMS minus right-channel RMS in dB.
- `role=interviewer`: offscreen interviewer, rendered with the semi-transparent black subtitle box.
- `role=onscreen`: visible interviewee, rendered with the semi-transparent purple subtitle box.
- `confidence`: lower values need manual review; weak LR separation should not be treated as interviewer by default.

Current project calibration:

- `lrDb >= +1.5`: usually interviewer / left-channel dominant.
- `lrDb <= -1.5`: usually visible interviewee / right-channel dominant.
- `-1.5 < lrDb < +1.5`: ambiguous. Use surrounding strong-LR captions, transcript meaning, and mouth-motion checks.

Observed examples from the five-minute QA range:

- `確かに`, `そのあたりはしっかりと考えてきてあるなという感じがします`, `PDMもFDも同じビルダーでしょ` are left-channel dominant and should be `interviewer`.
- `コアの仕事って何なの?` is a visible-speaker rhetorical question and is right-channel dominant, so it should stay `onscreen`.
- `そうですね` in the tested range is right-channel dominant, so it should be `onscreen` unless visual/mouth evidence later contradicts it.

Useful explicit commands for QA clips:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
python .\scripts\classify_speakers_audio_features.py `
  --srt "projects/new-folder-2/output/transcripts/manifest_sources/<timeline-local>.srt" `
  --audio "projects/new-folder-2/output/videos/<base-render-with-final-audio>.mp4" `
  --output "projects/new-folder-2/output/reports/<clip>_speaker_roles_audio_lr.json" `
  --report "projects/new-folder-2/output/reports/<clip>_speaker_roles_audio_lr_report.json"
```

After generating the audio-LR role JSON, point the runtime config at it:

```json
{
  "render": {
    "subtitlePath": "projects/new-folder-2/output/transcripts/manifest_sources/<timeline-local>.srt"
  },
  "subtitleSpeakers": {
    "outputPath": "projects/new-folder-2/output/reports/<clip>_speaker_roles_audio_lr.json"
  }
}
```

Then regenerate full PNG subtitles. For five-minute or longer QA clips, precompose the PNG manifest to a transparent overlay video before compositing, otherwise Windows command length can force an ASS fallback and lose the rich subtitle style. When the generated filter graph is long, pass it via `-filter_complex_script` rather than inline `-filter_complex`.

Punchline overlays use only `style.punchlineText` from the runtime config. If it is empty, the generated manifest is empty.

## High Quality Full Analysis Render

This is the canonical Codex-side procedure for a full analysis, edit, subtitle review, and render when Codex should operate the scripts directly from project files. It uses the current app project model, not old root-level `source/` or `output/` folders.

### Goal

Produce a full edited render from the active project with:

- highest-accuracy transcription using `large-v3`;
- all selected video/audio sources transcribed and compared;
- speaker classification for onscreen speaker vs interviewer;
- role-aware full subtitles;
- manual subtitle review and correction after subtitle generation;
- noise reduction and online-video audio mastering;
- multicam color matching, including skin-tone/background matching when possible;
- a consistent 20% push-in zoom on all camera video segments;
- the specified right-top logo;
- fast sample/full renders using `h264_nvenc` when available.

### Required Project Context

Always run from the repo root:

```powershell
cd C:\Users\yurin\Desktop\video_edit
```

Set one of these before running project actions:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
```

or, for an explicit project root:

```powershell
$env:VIDEO_EDIT_PROJECT_ROOT = "C:\Users\yurin\Desktop\video_edit\projects\new-folder-2"
```

The source of truth remains `projects\<project-id>\project_state.json`, the project media manifest, and `projects\<project-id>\output\...`.

### Fixed Style Inputs

Use this image for the right-top logo:

```text
C:\Users\yurin\Documents\Codex\2026-05-25\files-mentioned-by-the-user-chatgpt\chatgpt-image-2026-05-25-203219-transparent-cropped.png
```

Copy it into the active project, for example:

```text
projects\<project-id>\source\images\right_logo_pre_fb05.png
```

Set both `assets.logo` and `assets.logoPath` to the copied project-local path. Use the pre-`fb05cf02153a6511da1204d9ff43890c1bad473b` logo size as the default reference; in the current project that means `style.logoHeight = 48`.

### Highest Accuracy Transcription

Preferred backend is `faster-whisper` on CUDA/CTranslate2 because the system Python can have CPU-only PyTorch even when the machine has an NVIDIA GPU. Do not use CPU `openai-whisper large-v3` for full-project transcription unless explicitly approved.

If a CPU transcription job is already running, stop it before starting the CUDA job. It competes for disk/CPU and can overwrite the same transcript outputs.

Use this project-local environment:

```powershell
$venv = "C:\Users\yurin\Desktop\video_edit\.video-edit\venvs\whisper-cu128"
if (!(Test-Path $venv)) { python -m venv $venv }
& "$venv\Scripts\python.exe" -m pip install -U pip setuptools wheel
& "$venv\Scripts\python.exe" -m pip install --index-url https://download.pytorch.org/whl/cu128 torch torchvision torchaudio
& "$venv\Scripts\python.exe" -m pip install -U openai-whisper faster-whisper
```

Known-good setup:

```text
Python venv: .video-edit\venvs\whisper-cu128
Backend: faster-whisper / CTranslate2 CUDA
Model: large-v3
Device: cuda
Compute type: float16
Beam size: 5
```

Verify CUDA before a full run:

```powershell
.\.video-edit\venvs\whisper-cu128\Scripts\python.exe -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
.\.video-edit\venvs\whisper-cu128\Scripts\python.exe -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

Expected result is `True`, the NVIDIA GPU name, and at least one CTranslate2 CUDA device.

Project settings should include:

```json
{
  "analysis": {
    "transcribeModel": "large-v3",
    "transcribeDevice": "cuda",
    "fasterWhisperComputeType": "float16",
    "transcribeBeamSize": 5,
    "transcribeTemperature": 0.0,
    "conditionOnPreviousText": false
  }
}
```

Run transcription for all manifest audio-bearing sources:

```powershell
.\.video-edit\venvs\whisper-cu128\Scripts\python.exe .\scripts\video_edit_run.py --action transcribe-dropped-faster
```

Expected outputs:

```text
projects\<project-id>\output\transcripts\manifest_sources\primary.srt
projects\<project-id>\output\transcripts\manifest_sources\primary.json
projects\<project-id>\output\transcripts\manifest_sources\manifest_transcripts.json
```

If CUDA is unavailable, do not silently accept slow CPU `large-v3` for a full run. Fix the CUDA environment first or run a short benchmark only.

### Sync And Comparison

After transcription, run waveform sync and transcript comparison:

```powershell
python .\scripts\video_edit_run.py --action auto-sync-dropped
python .\scripts\video_edit_run.py --action compare-transcripts
```

Expected reports:

```text
projects\<project-id>\output\reports\app_sync_offsets.json
projects\<project-id>\output\reports\transcript_comparison.json
```

Waveform sync is the primary source for audio/video alignment. Transcript comparison is a fallback and sanity check, not the final fine sync mechanism.

For external-audio renders, the final sync reference is the selected external WAV, not the camera video's AAC audio. Before accepting a multicam render, run or rely on the renderer's external-audio cut sync guard, which writes:

```text
projects\<project-id>\output\reports\external_audio_cut_sync_report.json
```

Sub-camera segments should be used only when the local score passes threshold and the detected local shift is within tolerance. Low-score, short, or shifted segments must fall back to the long master camera. In the current project, `camera2` and `camera3` failed this stricter audit, while `camera4` and `camera5` are the safer close-up candidates.

For long-form multicam renders, QA must include explicit checks around any user-reported bad cut. For the current long render, inspect the 31:52 area first with a surrounding five-minute render before accepting any full rerender.

When existing transcript data is available and the user says not to re-transcribe, do not run `transcribe-dropped`, `transcribe-dropped-faster`, or clip re-transcription. Reuse `primary.srt`, `primary.json`, `manifest_transcripts.json`, and existing speaker-role reports.

If audio and video content diverge at a sub-camera cut, do not hide it with subtitle timing changes. Check the camera segment role, source coverage, selected sync offset, source timestamp mapping, and whether the segment should fall back to the long master camera.

### Subtitle Review And Correction

After generating transcription, Codex must review subtitles before final render:

```powershell
python .\scripts\video_edit_run.py --action review-subtitles
```

Read the SRT/JSON and correct unnatural Whisper errors before rendering. Do not paraphrase full subtitles; full subtitles must stay faithful to the actual utterance except for explicit user-approved terminology fixes.

Apply corrections through the project correction workflow:

```powershell
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
```

Use the corrected project-local SRT for later subtitle generation. Avoid editing generated final ASS as the only correction source because it is easy to lose those edits on regeneration.

### Speaker Classification And Subtitles

Classify captions into at least:

- `onscreen`: person visible in the frame is speaking;
- `interviewer`: offscreen interviewer or questioner is speaking.

Run:

```powershell
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
```

Expected role outputs live under:

```text
projects\<project-id>\output\reports\full_transcript_speaker_roles*.json
```

For stereo external recordings, prefer `scripts/classify_speakers_audio_features.py`: it measures active-speech LR channel balance (`lrDb`) plus lightweight acoustic features and writes a role JSON compatible with the PNG overlay generator. In the current project, positive `lrDb` / left-channel dominant speech maps to the offscreen interviewer, while negative `lrDb` / right-channel dominant speech maps to the visible interviewee.

Before rendering, point `subtitleSpeakers.outputPath` at the audio LR classifier output:

```json
{
  "subtitleSpeakers": {
    "outputPath": "projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr.json"
  }
}
```

Practical current-project thresholds:

- `lrDb >= +1.5`: interviewer candidate.
- `lrDb <= -1.5`: onscreen interviewee candidate.
- between `-1.5` and `+1.5`: ambiguous; inspect context and neighboring strong-LR captions.

Do not classify a caption as interviewer only because it is short or ends in a question mark. If the visible speaker is quoting a question or using a rhetorical question inside their own answer, keep it `onscreen`; if the offscreen interviewer is reacting, summarizing, or confirming from outside the frame, mark it `interviewer`.

Current five-minute QA regression checks:

- `source_index=464` / `確かに`: interviewer, black subtitle.
- `source_index=465` / `そのあたりはしっかりと考えてきてあるなという感じがします`: interviewer, black subtitle.
- `source_index=496` / `コアの仕事って何なの?`: onscreen, purple subtitle, despite the question mark.
- `source_index=525-529`: interviewer, black subtitle.
- `source_index=538` / `そうですね`: onscreen by audio LR in the tested clip, not interviewer.

For full-timeline stereo classification against the external WAV:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
python .\scripts\classify_speakers_audio_features.py `
  --srt "projects/new-folder-2/output/transcripts/manifest_sources/primary.srt" `
  --audio "C:\Users\yurin\Downloads\New folder (2)\140101-003.WAV" `
  --output "projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr.json" `
  --report "projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr_report.json"
```

Generate role-aware ASS only when needed:

```powershell
python .\scripts\video_edit_run.py --action generate-role-aware-ass
```

The preferred visual baseline is the rich PNG subtitle style from `scripts/generate_full_transcript_png_overlays.py` and `scripts/subtitle_png_style.py`: large Yu Gothic Bold text, tracked lettering, dynamic-width rounded boxes, semi-transparent purple for onscreen speaker, and semi-transparent black for interviewer. If ASS is required, it must visually approximate that PNG baseline, not the simplified fallback.

Line breaks in full PNG subtitles are part of subtitle quality. Use rendered-width measurement plus Japanese phrase-boundary penalties. Protect domain terms and common chunks such as `FDE`, `PDM`, `SaaS`, `SIer`, `Claude Code`, `プロダクトマネージャー`, `ジョブディスクリプション`, `リバースエンジニアリング`, `難しい`, `働き方`, `考え方`, `ということ`, `みたいな`, and `している`. Avoid splitting okurigana words such as `務|まらない`, `受|け入れ`, or `限|られている`, and avoid second lines that start with weak continuations or particles such as `いう`, `って`, `こと`, `ので`, `です`, `ます`, `は`, `が`, `を`, `に`, `で`, `と`, `も`, or `の`.

After subtitle correction or wrap-rule changes, regenerate the PNG subtitle manifest and run a whole-SRT layout audit. For the current project, the reference audit is `projects/new-folder-2/output/reports/subtitle_line_break_layout_review_20260529.json`; it should report `highPenaltyBreaks = 0` before using `output/overlays/full_transcript_png_overlays/manifest.json` in a production render.

### Chapter Titles And Subtitle Timing

For interview renders, the left-top title is a chapter title derived from the transcript, not a fixed generic label. Read the full corrected SRT, identify topic changes, and create:

```text
projects\<project-id>\output\reports\chapter_titles_from_full_transcript.json
```

Each item should include `start`, `end`, and `title`. Titles should be short, topic-specific, and faithful to the discussion. In the current Semiogo project, an example chapter title is `日本企業でワークするか`.

Enable chapter titles:

```json
{
  "style": {
    "chapterTitlesEnabled": true,
    "chapterTitlesPath": "projects/new-folder-2/output/reports/chapter_titles_from_full_transcript.json",
    "titleX": 18,
    "titleY": 18
  }
}
```

Generate the timed title PNG overlays:

```powershell
python .\scripts\generate_chapter_title_png_overlays.py `
  --project-root "projects\<project-id>" `
  --chapters "projects\<project-id>\output\reports\chapter_titles_from_full_transcript.json"
```

If visible subtitle text has had filler words removed, the SRT start time must not remain strongly early at `あー`, `えー`, `えっと`, `まあ`, `なんか`, or similar filler audio. Use the readability-first hybrid pass in `scripts/retime_subtitles_readable.py`: match displayed SRT text against word timestamps, shift only captions that are clearly early, keep a small lead-in before matched content words, merge close same-speaker captions when natural, enforce minimum display duration and tail hold, and never shift captions earlier.

### Audio, Color, And Camera Defaults

Enable denoise and mastering for normal full-analysis renders:

```json
{
  "render": {
    "audioDenoise": true,
    "audioDenoiseStrength": 16,
    "audioMastering": true
  }
}
```

Enable multicam color matching:

```json
{
  "render": {
    "colorMatchCameras": true,
    "colorMatchWhiteBalance": true,
    "colorMatchTemperature": true,
    "colorMatchTemperatureStrength": 0.65
  }
}
```

The color target is the long main camera `ST7_7550.MP4`. Sub-camera samples must be taken at `timeline timestamp + sync offset`, from ranges where the camera is actually used, after manual/dynamic planning, speaker masking, natural cuts, and source coverage constraints. Do not sample every camera at the same generic preview timestamps; that pulls the match toward unused source ranges and creates visible jumps in later close-up cuts. Check `projects\<project-id>\output\reports\camera_color_match.json`; it should show `sampleBasis: actual camera plan`.

Brightness matching must blend skin, global frame brightness, and conservative neutral non-skin/background pixels. White balance should be background-first (`backgroundBgr` 80%, `neutralBgr` 20%) with skin excluded from channel gains. Skin can help exposure and saturation QA, but it must not drive `colorchannelmixer` gains; in the 2026-05-29 audit, face/skin-driven gains raised green/blue on `camera2` and `camera4`, making the pale wall look green. Temperature matching should verify both wall `R/G` and `R/B` ratios.

The shared white/clean look must be a final common pass, not a master-only pass. If the main camera is whitened after sub-camera matching but sub cameras were matched against the pre-whitened main, the reference itself is inconsistent. Put this look in `render.outputLookFilter`, apply it after per-camera matching to every camera, and do final QA against rendered post-look frames:

```json
{
  "render": {
    "outputLookFilter": "colorchannelmixer=rr=0.99000:gg=1.00000:bb=1.01200,eq=brightness=0.0140:contrast=0.9850:saturation=0.9600"
  }
}
```

For current `camera5` close-up audits, avoid a blunt saturation-only override. If manual correction is still needed after automatic matching, use the ratio-aware override and verify with a contact sheet:

```text
colorchannelmixer=rr=1.06500:gg=0.98500:bb=1.00000,eq=brightness=-0.0140:contrast=1.0000:saturation=1.1200
```

When changing the color matching implementation, render a short switching test before a production render. The current useful gate is a 95-second clip from the start because it includes the long master plus sub-camera cuts such as `camera2` and `camera4`. After the test, inspect `camera_color_match.json` for per-role `sampleTimelineSeconds`, `referenceSourceSeconds`, `backgroundBgr`, `neutralBgr`, `skinBgr`, channel gains, and emitted filters. If a close-up wall is still green/cyan, adjust the background/neutral white-balance basis; do not add a saturation-only fix.

Close-up cameras should be used only while the visible interviewee is speaking, even when a manual camera plan exists:

```json
{
  "render": {
    "closeupsOnlyWhenOnscreenSpeaker": true,
    "closeupSpeechPadding": 0.18,
    "closeupSpeechGapMerge": 0.8
  }
}
```

For normal interview deliverables, keep silence shortening enabled unless the render is specifically a sync/debug sample:

```json
{
  "render": {
    "shortenSilence": true,
    "minSilence": 3.0,
    "keepSilence": 2.0,
    "silenceNoise": "-30dB"
  }
}
```

Always inspect the generated `<output>.silence_shortening.json` report. Do not use silence-shortened outputs when validating exact raw source sync.

Apply the 20% push-in to camera video only, before subtitles, title graphics, right-top logo, glossary overlays, or omission cards:

```json
{
  "render": {
    "globalVideoZoom": 1.2,
    "faceCenterCrop": true,
    "faceCenterCropAxis": "x",
    "faceCenterSubjectXByRole": {
      "master": 0.54
    }
  }
}
```

Treat the 20% zoom as the minimum push-in. Do not double-zoom tight face crops so far that the speaker's head, hands, or important context are cut unnaturally. Check `output/reports/person_crop_usage.json` or `output/reports/face_center_crop_usage.json` and sample frames after render.

### Encoder Choice

For speed on NVIDIA systems:

```json
{
  "render": {
    "videoEncoder": "h264_nvenc",
    "nvencPreset": "p4",
    "cq": 19
  }
}
```

Benchmark with a short sample before a full render. `cq=19` is high quality but can create large files; if file size is too large, test `cq=23` or `cq=25`.

For interview videos, default long renders to 30fps unless 60fps is specifically required:

```json
{
  "render": {
    "outputFps": "30000/1001",
    "precomposeOverlayFps": "30000/1001"
  }
}
```

Do not apply `fps=30000/1001` independently inside every camera segment before `concat`. Segment-local FPS conversion caused cumulative visual drift in the 2026-05-29 sync investigation: the external WAV stayed aligned, but the video gradually lagged behind source frames. The correct graph is: trim and style camera segments at source timing, concatenate the segments, then apply one global `fps=<render.outputFps>` to the concatenated base before title/logo/subtitle overlays. `scripts/shorten_silences.py` must preserve this fixed timeline and can re-encode the final silence-shortened output with `h264_nvenc` when `render.videoEncoder = "h264_nvenc"`.

Use CPU x264 only when size/quality consistency matters more than render time:

```json
{
  "render": {
    "videoEncoder": "libx264",
    "encoderPreset": "veryfast",
    "crf": 18
  }
}
```

### Full Render Order

Recommended full pipeline:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"

.\.video-edit\venvs\whisper-cu128\Scripts\python.exe .\scripts\video_edit_run.py --action transcribe-dropped-faster
python .\scripts\video_edit_run.py --action auto-sync-dropped
python .\scripts\video_edit_run.py --action compare-transcripts
python .\scripts\video_edit_run.py --action review-subtitles
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
python .\scripts\video_edit_run.py --action generate-role-aware-ass
python .\scripts\video_edit_run.py --action render-selected
```

After render, verify:

```powershell
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<final-video>"
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels -of json "<final-video>"
```

Also inspect sample frames from early, interviewer, onscreen, multicam switch, bad-cut, and late sections. Confirm:

- logo is the specified image and size;
- speaker subtitles use purple/black correctly;
- subtitle style matches the PNG-style baseline, not simplified ASS;
- subtitle line breaks do not split words, technical terms, or weak Japanese continuations;
- corrected subtitle terms are present;
- audio remains synced after cuts or silence shortening;
- the 31:52 area and its surrounding five-minute QA render do not contain audio/video content mismatch;
- camera color is consistent, especially skin tone and pale wall/background temperature;
- every camera video segment has the intended 20% push-in without over-cropping faces or hands;
- denoise/mastering did not create pumping or clipped speech.

Important full-analysis rules:

- Full subtitles are literal utterance subtitles, not summaries.
- Interviewer omission mode may summarize questions, but normal full-subtitle mode must not.
- After subtitle generation, Codex must review and correct obvious unnatural transcription errors before final render.
- Do not use weak transcript matches for multicam sync decisions.
- Do not process full renders frame-by-frame in Python/OpenCV unless no FFmpeg equivalent exists.

## Script Guidelines

- Script names should describe reusable behavior, not a specific clip, person, source camera, or date.
- Defaults must be generic. Project-specific values belong in the runtime config, media manifest, or project files.
- AI/operator option changes should go through `project_state.json`; runtime config is generated for a specific run.
- Root-level `source/` and `output/` are not valid app data sources; they are ignored legacy workspace names.
- Project context is required. Use the Electron app, `VIDEO_EDIT_APP_CONFIG`, or `VIDEO_EDIT_PROJECT`; do not rely on `.video-edit` fallback state.
- When a script cannot run without current project data, fail with a clear message rather than silently using older project files.
