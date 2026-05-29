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
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
python .\scripts\video_edit_run.py --action compare-transcripts
python .\scripts\video_edit_run.py --action render-selected
```

## Render Contract

`scripts/render_app_interview.py` is the common renderer. It reads cameras, audio, logo, still images, subtitle mode, title text, style, sync offsets, and output path from the runtime config.

Camera/audio sync is controlled by `scripts/auto_sync_app_sources.py`. It reads the current media manifest, finds coarse offsets against the master camera, then performs local fine waveform refinement and writes both coarse and refined values to `output/reports/app_sync_offsets.json`. `scripts/compare_manifest_transcripts.py` also writes transcript-derived offsets; the renderer uses those only as a current-project fallback for missing or low-score waveform sync and records the selected source in `output/reports/sync_offset_usage.json`.

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

If the whole edit should be slightly whiter/cooler, apply it as a shared final camera look with `render.outputLookFilter`, not as `cameraExtraFilters.master`. The current preferred adjustment is subtle and applies to every camera after per-camera matching: `colorchannelmixer=rr=0.99000:gg=1.00000:bb=1.01200,eq=brightness=0.0140:contrast=0.9850:saturation=0.9600`. This keeps the master from moving away from the sub cameras after matching.

Global camera push-in is controlled by `render.globalVideoZoom`. The current preferred full-analysis style is a 20% push-in on all camera video segments, applied in the FFmpeg visual filter graph before subtitles, title, and logo overlays.

Face-centered framing is required for multicam tests and final renders when push-in is enabled, but the default is horizontal-only centering. Before rendering, sample the actual timeline ranges for each selected camera, detect the visible face/person position with OpenCV or the app person-analysis metadata, and write a framing report under `output/reports`. The renderer should use the detected face center for the crop x-position, keep the original vertical center crop unless `render.faceCenterCropAxis` is explicitly `xy`, and keep the zoom amount at `render.globalVideoZoom` instead of increasing zoom to force exact centering.

For the long wide master camera, do not force the person to exact center. The current preferred framing leaves the person slightly to the right, while close-up sub cameras remain centered. Configure this with `render.faceCenterSubjectXByRole.master = 0.54`; the renderer shifts the crop window left so the detected master subject lands around 54% of the screen width. Keep sub-camera roles at the default `0.50` unless a specific shot needs a separate composition.

Close-up sub cameras can remain visually too dense, too dark, or too saturated/desaturated even after automatic master matching. Check `brightnessComponents` and `saturationComponents` in `camera_color_match.json`; if global/background deltas are positive, the sub camera should be lifted toward the master even when skin brightness is already close. Do not solve this with a one-off saturation override. The renderer should compare face/skin, neutral background, and global frame statistics, trim outlier pixels before averaging, and then emit one FFmpeg color match filter. Prefer this over frame-by-frame Python processing or manual `cameraExtraFilters`. For the 2026-05-29 Semiogo 90s sample, the corrected approach removed the manual `camera5` saturation override and generated `saturation=0.8478` from the weighted face/background/global comparison; measured close-up output saturation moved from the over-saturated `0.26045` back to `0.20203`, close to the master range `0.20295`.

Audio mastering is controlled by `render.audioMastering`. It applies the shared online-video chain from the old one-off render: high-pass, optional denoise, dynamic normalization, compression, and loudness normalization on the currently selected project audio.

Render encoding is controlled by `render.encoderPreset` and `render.crf`. These settings are the app-level replacement for the old one-off `--preset` / `--crf` flags and are used by both the common renderer and silence-shortening re-encode.

GPU encoding is controlled by `render.videoEncoder`. Use `h264_nvenc` when an NVIDIA GPU is available and quick iteration matters; use `render.nvencPreset` and `render.cq` for NVENC quality/speed tuning. Keep `libx264` with `render.encoderPreset` and `render.crf` when CPU encoding quality/size tradeoffs are preferred. Benchmark short samples before full renders because low CQ NVENC values can create much larger files.

For interview deliverables, prefer `render.outputFps = "30000/1001"` unless the user explicitly needs 60fps. The renderer applies this immediately after each camera segment trim, before color matching, global zoom, and overlays, so downstream filters process about half as many frames. Do not only add a final output `-r`; that drops frames after the expensive filters and gives little speed benefit.

Background music is app-level shared behavior. `scripts/generate_music_bed.py` reads `music.prompt`, `music.mood`, `music.outputPath`, and the active project output root, then writes a project-local WAV plus a JSON sidecar. The common renderer reads `music.enabled`, `music.scope`, `music.rangeSource`, `music.volume`, and `music.rangesText`; `scope=full` mixes the bed through the whole render, while `scope=omission` raises the music only inside auto-detected omission/interviewer overlay ranges plus explicit ranges such as `00:12-00:18`.

Audio replacement is app-level shared behavior. `scripts/replace_video_audio.py` reads `workflow.inputVideoPath`, `replaceAudio.audioPath` or the selected external audio, `render.outputPath`, and `render.syncOffsetsPath`, then copies the input video stream while replacing audio from the current project external source. It does not use old `sound2` paths and can run the same silence-shortening pass as renders.

Omission-card replacement is also app-level shared behavior. `scripts/generate_omission_card.py` creates a project-local summary card from `omissionCard.text`, `omissionCard.label`, `omissionCard.duration`, and `omissionCard.rangesText`. When enabled, `scripts/render_app_interview.py` removes those source ranges from the camera/audio timeline, inserts the generated card for the configured duration, shifts later subtitle/glossary overlays, and maps omission-scope BGM to the card's output range.

Thumbnail and subtitle review behavior is app-level shared behavior. `scripts/generate_project_thumbnail.py` reads `thumbnail.*`, the current project video selection, style title/color/logo fields, and writes `output/images/thumbnail.png`. `scripts/generate_thumbnail_candidates.py` writes multiple project-driven thumbnail candidates and a contact sheet without relying on old fixed source images; `thumbnail.debugFaces` can draw detected face boxes on candidates for layout QA. `scripts/review_subtitles.py` reads only the current project transcript manifest and writes subtitle QA reports under `output/reports`, including optional operator-entered suspicious patterns, flagged-caption WAV clips, and clip re-transcription under `output/diagnostics/subtitle_review`. `scripts/apply_subtitle_corrections.py` applies operator-entered correction rows to the current project transcript manifest and redirects later overlay generation to the corrected SRT. `scripts/classify_subtitle_speakers.py` writes `full_transcript_speaker_roles.json` from operator-entered interviewer ranges/patterns/manual roles, and can include mouth-motion, MediaPipe mouth-opening, audio RMS, and mouth/audio correlation diagnostics from the current project timeline, so full subtitle overlays and omission-range BGM detection can use current project speaker roles. `scripts/classify_speakers_audio_features.py` is the preferred automatic splitter when the project audio is stereo: it classifies each SRT caption from active-speech LR channel balance plus light acoustic diagnostics, and writes a role JSON compatible with the PNG overlay generator. `scripts/compare_manifest_transcripts.py` replaces the old fixed-video transcript comparison diagnostics with a manifest-driven report that compares every current source transcript against the primary transcript, writes `output/reports/transcript_comparison.json` plus Markdown, and can feed render sync fallback when `render.useTranscriptComparisonSync` is enabled.

Full subtitle overlays use only the selected/parsed project transcript. If no current transcript exists, generation should fail instead of using older subtitles.

The preferred full-subtitle visual baseline is the pre-app PNG overlay style from `scripts/generate_full_transcript_png_overlays.py` / `scripts/subtitle_png_style.py`. Plain ASS is only an implementation fallback for very long renders and must visually approximate that baseline. For five-minute or longer QA clips, do not pass every PNG subtitle as an individual FFmpeg input on Windows; precompose the PNG subtitle manifest into one transparent overlay video, then overlay that video onto the rendered base clip. For long multicam plans, also write the FFmpeg filter graph to `output/reports/filtergraphs/<output>.ffgraph` and use `-filter_complex_script`, because the filter graph itself can exceed the Windows command-line length even after subtitle precomposition.

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

For the reusable Codex-side full-analysis workflow, see `docs/codex_full_analysis_render_method.md`. That document records the current preferred setup: `large-v3` transcription through `faster-whisper` / CTranslate2 CUDA in `.video-edit\venvs\whisper-cu128`, all-source transcription/comparison, speaker-role subtitles, strict subtitle review/correction, skin-tone-based multicam color matching, 20% global camera push-in, online-video audio denoise/mastering, the specified right-logo asset, and optional `h264_nvenc` acceleration.

## Script Guidelines

- Script names should describe reusable behavior, not a specific clip, person, source camera, or date.
- Defaults must be generic. Project-specific values belong in the runtime config, media manifest, or project files.
- AI/operator option changes should go through `project_state.json`; runtime config is generated for a specific run.
- Root-level `source/` and `output/` are not valid app data sources; they are ignored legacy workspace names.
- Project context is required. Use the Electron app, `VIDEO_EDIT_APP_CONFIG`, or `VIDEO_EDIT_PROJECT`; do not rely on `.video-edit` fallback state.
- When a script cannot run without current project data, fail with a clear message rather than silently using older project files.
