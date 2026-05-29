# Codex Full Analysis Render Method

This is the reusable Codex-side procedure for full analysis, editing, subtitle review, and render. It is intended for cases where the Electron app can exist, but Codex should operate the scripts directly from project files.

## Goal

Produce a full edited render from the active project with:

- highest-accuracy transcription using `large-v3`;
- all selected video/audio sources transcribed and compared;
- speaker classification for onscreen speaker vs interviewer;
- role-aware full subtitles;
- manual subtitle review and correction after subtitle generation;
- noise reduction and YouTube-style audio mastering;
- multicam color matching, including skin-tone-based matching when possible;
- a consistent 20% push-in zoom on all camera video segments;
- the specified right-top logo;
- fast sample/full render using `h264_nvenc` when available.

## Required Project Context

Always run from the repo root:

```powershell
cd C:\Users\yurin\Desktop\video_edit
```

Set one of these before running actions:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
```

or, for an explicit project root:

```powershell
$env:VIDEO_EDIT_PROJECT_ROOT = "C:\Users\yurin\Desktop\video_edit\projects\new-folder-2"
```

Do not use old root-level `source/` or `output/` folders. Use `projects\<project-id>\project_state.json`, the project media manifest, and `projects\<project-id>\output\...`.

## Fixed Style Inputs

Use this image for the right-top logo:

```text
C:\Users\yurin\Documents\Codex\2026-05-25\files-mentioned-by-the-user-chatgpt\chatgpt-image-2026-05-25-203219-transparent-cropped.png
```

Copy it into the project, for example:

```text
projects\<project-id>\source\images\right_logo_pre_fb05.png
```

Set both `assets.logo` and `assets.logoPath` to the copied path. Use the pre-`fb05cf02153a6511da1204d9ff43890c1bad473b` logo size as the default reference. In the current project that means `style.logoHeight = 48`.

## Highest Accuracy Transcription

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

The current known-good setup is:

```text
Python venv: .video-edit\venvs\whisper-cu128
Torch: CUDA build, for example 2.11.0+cu128
Backend used for actual transcription: faster-whisper / CTranslate2 CUDA
Model: large-v3
Device: cuda
Compute type: float16
Beam size: 5
```

`openai-whisper large-v3` can detect CUDA, but on an RTX 3070 Laptop GPU it was observed to use nearly all 8GB VRAM and run close to CPU speed. `faster-whisper large-v3` used less VRAM and completed the same all-source transcription reliably, so the default full-run action is `transcribe-dropped-faster`.

Use the prepared CUDA environment when available:

```powershell
.\.video-edit\venvs\whisper-cu128\Scripts\python.exe -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
.\.video-edit\venvs\whisper-cu128\Scripts\python.exe -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
```

Expected result is `True`, the NVIDIA GPU name, and at least one CTranslate2 CUDA device.

Project settings should use:

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

This action runs `scripts/transcribe_manifest_sources_faster.py`, transcribes every audio-bearing media manifest source, chooses the primary source, and writes the same project-local SRT/JSON outputs expected by the rest of the workflow.

Expected outputs:

```text
projects\<project-id>\output\transcripts\manifest_sources\primary.srt
projects\<project-id>\output\transcripts\manifest_sources\primary.json
projects\<project-id>\output\transcripts\manifest_sources\manifest_transcripts.json
```

If CUDA is unavailable, do not silently accept slow CPU `large-v3` for a full run unless explicitly approved. Fix the CUDA environment first or run a short benchmark only.

## Sync And Comparison

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

For long-form multicam renders, QA must include explicit checks around any user-reported bad cut. For the current long render, always inspect the 31:52 area first. That point is near a master-to-sub-camera cut and must be tested with a surrounding five-minute render before any full rerender is accepted.

When the existing transcript data is already available and the user says not to re-transcribe, do not run `transcribe-dropped`, `transcribe-dropped-faster`, or any clip re-transcription. Reuse the existing `primary.srt`, `primary.json`, `manifest_transcripts.json`, and `full_transcript_speaker_roles.json`.

If audio and video content diverge at a sub-camera cut, do not hide it with subtitle timing changes. Check the camera segment role, source coverage, selected sync offset, source timestamp mapping, and whether the segment should fall back to the long master camera. A questionable sub-camera sync should be removed from the local camera plan or replaced with the master camera until a verified waveform offset is available.

## Subtitle Review And Correction

After generating transcription, Codex must review the subtitles before final render:

```powershell
python .\scripts\video_edit_run.py --action review-subtitles
```

Read the SRT/JSON and correct unnatural Whisper errors before rendering. Do not paraphrase full subtitles. Full subtitles must stay faithful to the actual utterance, except for explicit user-approved corrections such as terminology fixes.

Apply corrections through the project correction workflow:

```powershell
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
```

Use the corrected project-local SRT for later subtitle generation. Avoid editing generated final ASS as the only correction source because it is easy to lose those edits on regeneration.

## Speaker Classification

Classify captions into at least:

- `onscreen`: person visible in the frame is speaking;
- `interviewer`: offscreen interviewer or questioner is speaking.

Run:

```powershell
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
```

Expected output:

```text
projects\<project-id>\output\reports\full_transcript_speaker_roles.json
```

Use strict interviewer patterns and manual ranges when needed. Do not classify a caption as interviewer only because the sentence is short, and do not classify it as interviewer only because it ends in a question mark. For stereo external recordings, prefer `scripts/classify_speakers_audio_features.py`: it measures each subtitle segment's active-speech LR channel balance (`lrDb`) plus lightweight acoustic features and writes a role JSON compatible with the PNG overlay generator. In the current project, positive `lrDb` / left-channel dominant speech maps to the offscreen interviewer, while negative `lrDb` / right-channel dominant speech maps to the visible interviewee. Treat weak LR separation as ambiguous, not as interviewer by default; then use surrounding transcript meaning, neighboring strong-LR captions, and mouth-motion diagnostics as tie-breakers. If the visible speaker is quoting a question or using a rhetorical question inside their own answer, keep it `onscreen`; if the offscreen interviewer is reacting, summarizing, or confirming from outside the frame, mark it `interviewer`.

Before rendering, point `subtitleSpeakers.outputPath` at the audio LR classifier output. The current project should use:

```json
{
  "subtitleSpeakers": {
    "outputPath": "projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr.json"
  }
}
```

For the current project, use these practical thresholds first:

- `lrDb >= +1.5`: interviewer candidate.
- `lrDb <= -1.5`: onscreen interviewee candidate.
- between `-1.5` and `+1.5`: ambiguous; inspect context and neighboring strong-LR captions.

Current five-minute QA findings to keep as regression checks:

- `source_index=464` / `確かに`: interviewer, black subtitle.
- `source_index=465` / `そのあたりはしっかりと考えてきてあるなという感じがします`: interviewer, black subtitle.
- `source_index=496` / `コアの仕事って何なの?`: onscreen, purple subtitle, despite the question mark.
- `source_index=525-529`: interviewer, black subtitle.
- `source_index=538` / `そうですね`: onscreen by audio LR in the tested clip, not interviewer.

For a local QA clip, classify against the local timeline SRT and the already-rendered base clip containing the final audio:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
python .\scripts\classify_speakers_audio_features.py `
  --srt "projects/new-folder-2/output/transcripts/manifest_sources/<timeline-local>.srt" `
  --audio "projects/new-folder-2/output/videos/<base-render-with-final-audio>.mp4" `
  --output "projects/new-folder-2/output/reports/<clip>_speaker_roles_audio_lr.json" `
  --report "projects/new-folder-2/output/reports/<clip>_speaker_roles_audio_lr_report.json"
```

For the full timeline, classify against the primary SRT and external stereo WAV:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
python .\scripts\classify_speakers_audio_features.py `
  --srt "projects/new-folder-2/output/transcripts/manifest_sources/primary.srt" `
  --audio "C:\Users\yurin\Downloads\New folder (2)\140101-003.WAV" `
  --output "projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr.json" `
  --report "projects/new-folder-2/output/reports/full_transcript_speaker_roles_audio_lr_report.json"
```

Use the generated `*_speaker_roles_audio_lr.json` as `subtitleSpeakers.outputPath` before running `generate-full-overlays`. If the audio is mono, channel separation is not valid; fall back to mouth-motion diagnostics plus manual review.

Generate role-aware ASS subtitles:

```powershell
python .\scripts\video_edit_run.py --action generate-role-aware-ass
```

The role-aware style is:

- onscreen speaker: semi-transparent light purple box with white text;
- interviewer: semi-transparent black box with white text.

For visual style, the baseline is the pre-app PNG subtitle look, not the simplified ASS fallback. Use the PNG overlay style from `scripts/generate_full_transcript_png_overlays.py` and `scripts/subtitle_png_style.py` for QA clips and final renders: large Yu Gothic Bold text, tracked lettering, dynamic-width rounded boxes, semi-transparent purple for onscreen speaker, and semi-transparent black for interviewer. If a QA clip is long enough that individual PNG inputs exceed Windows command-line length, precompose the PNG manifest into one transparent overlay video and overlay that video onto the base render. For long multicam timelines, also write the FFmpeg filter graph to `output/reports/filtergraphs/<output>.ffgraph` and pass it with `-filter_complex_script`; the inline `-filter_complex` string can exceed Windows command-line length even after PNG subtitle precomposition. If the transcript is sourced from external audio, create a timeline-shifted SRT from the existing SRT and point `render.subtitlePath` at it; this is a timestamp conversion, not a new transcription. If ASS is absolutely required, it must be styled to visually match this PNG baseline as closely as possible, not as plain minimal ASS text.

## Chapter-Aware Top-Left Title

For interview renders, the left-top title is a chapter title derived from the transcript, not a fixed generic label. Read the full corrected SRT, identify topic changes, and create:

```text
projects\<project-id>\output\reports\chapter_titles_from_full_transcript.json
```

Each item should include `start`, `end`, and `title`. Titles should be short, topic-specific, and faithful to the discussion. Do not invent a marketing headline that is unrelated to the transcript. In the current Semiogo project, an example chapter title is `日本企業でワークするか`.

Enable it in `project_state.json`:

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

Run or let the renderer call:

```powershell
python .\scripts\generate_chapter_title_png_overlays.py `
  --project-root "projects\<project-id>" `
  --chapters "projects\<project-id>\output\reports\chapter_titles_from_full_transcript.json"
```

The script writes timed PNG overlays and `output\overlays\chapter_title_png_overlays\manifest.json`. `scripts/render_app_interview.py` consumes that manifest and overlays the appropriate title during each chapter. If `chapterTitlesEnabled` is false or no chapter items exist, the renderer falls back to the static `style.titleText` title.

The current placement requirement is close to the upper-left corner, not the older inset placement. Use `style.titleX = 18` and `style.titleY = 18` unless a specific frame check shows collision with faces, subtitles, or the right-top logo.

## Subtitle Timing After Filler Removal

If the visible subtitle text has had filler words removed, the SRT start time must be moved to the first displayed content word. Do not allow a caption to appear during `あー`, `えー`, `えっと`, `まあ`, `なんか`, or similar filler audio if those words are not shown in the subtitle.

For short QA renders, use this lightweight procedure:

1. Render or reuse the subtitle-free base clip with the final audio.
2. Run `faster-whisper` / `large-v3` on that base clip with `word_timestamps=True`. This is a local clip-level timing pass, not a full re-transcription replacement.
3. Match each displayed SRT caption to the first spoken content word in the word-timestamp output.
4. Shift only the caption start later to the matched word start. Never shift a caption earlier.
5. Save a local retimed SRT and a JSON report with `oldStart`, `newStart`, `delay`, and matched prefix.
6. Regenerate the PNG subtitle overlay from the retimed SRT and composite it over the same base video.

In the 2026-05-29 Semiogo 90s sample, this method corrected 8 captions, including `ちょっと事前...` from `16.90s` to `20.80s`, `今日はその話...` from `34.92s` to `37.10s`, and `みんな好きなんでしょうね` from `69.54s` to `74.24s`. Keep the original transcript text corrections intact; this step is only timing retime, not paraphrasing.

## Audio Denoise And Mastering

Enable:

```json
{
  "render": {
    "audioDenoise": true,
    "audioDenoiseStrength": 16,
    "audioMastering": true
  }
}
```

The renderer applies a lightweight online-video chain: high-pass, denoise, low-pass, dynamic normalization, compression, loudness normalization, and limiter. This is preferred over heavy external denoise passes unless the source is severely noisy.

## Multicam Color Matching

Enable:

```json
{
  "render": {
    "colorMatchCameras": true,
    "colorMatchWhiteBalance": true
  }
}
```

The renderer samples each selected camera and uses the long master/first camera as the reference. Sub-camera color samples must be taken at `timeline timestamp + sync offset`, not at the raw master timestamp, so the sampled frames represent the same interview moment. Sampling must be based on the final camera plan, after manual-plan, speaker masking, natural cut adjustment, and source coverage constraints. Do not use generic evenly spaced preview timestamps for all cameras; sample only ranges where the camera is actually used. The report should show `sampleBasis: actual camera plan`.

It should prefer detected skin-color samples when available, but brightness matching must also include global frame brightness and neutral non-skin/background brightness. Close-up cameras can match the master skin value while still looking too dark overall, so the renderer blends skin, global, and background deltas before emitting the FFmpeg brightness correction. The sub cameras must be adjusted toward the long master camera, not the other way around.

Background brightness sampling must avoid black clothing and dark foreground areas. Use conservative neutral-background pixels only: non-skin, low-saturation, mid/high-value pixels, with the face/person neighborhood excluded when possible. This keeps the comparison focused on wall/room/background brightness and prevents over-lifting a shot just because the visible person wears dark clothes.

The report must be checked after render:

```text
projects\<project-id>\output\reports\camera_color_match.json
```

If a camera is still too warm, too cool, too dark, or too saturated/desaturated after automatic matching, adjust the shared color-match algorithm or lightweight FFmpeg color filters rather than per-frame Python/OpenCV rawvideo processing for the full timeline. When judging darkness, inspect `brightnessComponents` in `camera_color_match.json`; a positive `globalDelta` or `backgroundDelta` means the sub camera is darker than the master outside skin-only areas and should be lifted. When judging saturation, inspect `saturationComponents` and compare rendered close-up output against the long master. The preferred algorithm compares face/skin, neutral background, and global frame statistics after trimming outlier pixels, then uses the weighted average to emit one FFmpeg filter. For the 2026-05-29 Semiogo 90s sample, the background/face-aware method matched the camera5 close-up output global saturation to the master range (`0.20203` vs `0.20295`) without a manual saturation boost.

For the current project, the color target is the long main camera `ST7_7550.MP4`. 2cam/sub-camera footage must be normalized toward that master camera so skin tone and overall warmth do not jump across multicam cuts.

For white balance, prioritize the wall/background and neutral pixels over skin. Skin should not drive channel gains because that can make pale background walls drift green/cyan. Current channel-gain weighting is background-first: `backgroundBgr` 80%, `neutralBgr` 20%, with skin excluded from channel gains. Saturation matching should weight global/background more than skin, because the obvious cut mismatch is often the wall/background density.

If the whole edit should feel slightly whiter/cooler, apply a shared output look after per-camera matching with `render.outputLookFilter`, not a master-only extra filter. The current light correction is:

```json
{
  "render": {
    "outputLookFilter": "colorchannelmixer=rr=0.99000:gg=1.00000:bb=1.01200,eq=brightness=0.0140:contrast=0.9850:saturation=0.9600"
  }
}
```

This is intentionally subtle: a small brightness lift, slightly lower contrast/saturation, and a little more blue. It is applied to every camera segment after matching, so the master does not move away from the sub cameras.

For close-up sub-camera shots, also check whether the image still feels too dense, too muted, or too colorful after the automatic match. Avoid piling manual `cameraExtraFilters` on top of the automatic match unless the user explicitly asks for a stylized look. In the current Semiogo sample, the previous `camera5` overrides `saturation=0.8000` and then `saturation=1.0200` were both too blunt; the current target is no manual extra filter, with the automatic report showing `saturationComponents` and an emitted `eq=...:saturation=0.8478` for camera5. Record any future manual adjustment in the render report so it is not confused with the automatic face/background/global match.

## Close-Up Camera Eligibility

Close-up cameras should only be used while the visible interviewee is speaking. This applies even when a manual camera plan exists; do not let a prebuilt close-up segment override speaker-role evidence.

Enable:

```json
{
  "render": {
    "closeupsOnlyWhenOnscreenSpeaker": true,
    "closeupSpeechPadding": 0.18,
    "closeupSpeechGapMerge": 0.8
  }
}
```

`scripts/render_app_interview.py` reads the selected SRT and `subtitleSpeakers.outputPath`, builds onscreen speech ranges, then replaces close-up camera segments with the master camera when the role is `interviewer` or there is no visible-speaker speech. It writes `output/reports/onscreen_closeup_camera_mask.json` with replaced ranges. For the latest current-project dry run, the manual plan had 62 input segments, became 116 output segments after masking, and replaced 50 inappropriate close-up gaps with the master camera.

## Silence Shortening

Enable silence shortening for normal interview deliverables unless the render is specifically a sync/debug sample:

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

The rule is: if nobody is speaking for 3 seconds or longer, reduce that silent region to 2 seconds by cutting the middle. Silences shorter than 3 seconds are not modified. The pass runs after the base render and cuts video/audio together, so subtitle/audio/video sync stays intact for the shortened output. The current `projects/new-folder-2/project_state.json` default is enabled for the next normal render.

Always inspect the generated `<output>.silence_shortening.json` report when reviewing a final render; it records detected silences, removed ranges, and kept ranges. Do not use silence-shortened outputs when validating exact raw source sync, because timeline positions after the first removal no longer match the original source time. If subtitle overlays are generated separately after the base render, either generate/shift the subtitle timings against the shortened output or burn/precompose the subtitles before silence shortening so they are cut with the video.

## Global 20% Video Zoom

Apply a consistent 20% push-in to every camera video segment. This is a video-only transform: do not zoom subtitles, title graphics, right-top logo, glossary overlays, or omission cards.

The intended visual result is a 1.2x scale centered on the source frame, then cropped back to the final 1920x1080 canvas. This shows roughly the central 83% of each source frame. If the requirement is an exact 80% visible crop instead, use `globalVideoZoom = 1.25`.

Preferred renderer behavior:

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

`scripts/render_app_interview.py` reads `render.globalVideoZoom` and composes this transform into the per-camera FFmpeg visual filter graph after source color matching and before overlays/subtitles are burned.

When person-aware crops are enabled, treat the 20% zoom as the minimum push-in. Do not double-zoom tight face crops so far that the speaker's head, hands, or important context are cut unnaturally. Check `output/reports/person_crop_usage.json` and sample frames after render.

For test renders with visible multicam cuts, analyze the selected timeline ranges before rendering and generate a face-centered crop plan. Use face/person detection on frames from the actual synced source time, average stable detections per segment, then use the detected face center for horizontal crop positioning while clamping inside 1920x1080. Keep the vertical crop at the original centered 20% zoom unless `render.faceCenterCropAxis` is explicitly `xy`. Do not increase beyond `render.globalVideoZoom` just to force exact centering; if 20% zoom is insufficient, move as far as that crop allows and record the limitation.

For the long wide master camera, the preferred composition is intentionally not exact center. Set `render.faceCenterSubjectXByRole.master = 0.54` so the detected person lands slightly right of center. This is implemented by shifting the crop window left from the detected face center. Leave close-up sub cameras at the default `0.50` unless an individual shot needs a separate framing override. Verify this in `output/reports/face_center_crop_usage.json`; master rows should include `subjectScreenX: 0.54`, while sub-camera rows should remain `0.5`.

## Encoder Choice

For speed on NVIDIA systems, use:

```json
{
  "render": {
    "videoEncoder": "h264_nvenc",
    "nvencPreset": "p4",
    "cq": 19
  }
}
```

Benchmark with a short sample before a full render. `cq=19` is high quality but can create large files. If file size is too large, test `cq=23` or `cq=25`.

For interview videos, default long renders to 30fps unless 60fps is specifically required:

```json
{
  "render": {
    "outputFps": "30000/1001",
    "precomposeOverlayFps": "30000/1001"
  }
}
```

This must be applied in the filter graph immediately after each source segment trim, before color correction, zoom, subtitle overlays, and title/logo overlays. A final `-r 30000/1001` alone is not enough, because it still makes the expensive filters process the original 60fps frames.

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

## Full Render Order

Recommended full pipeline:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"

.\.video-edit\venvs\whisper-cu128\Scripts\python.exe .\scripts\video_edit_run.py --action transcribe-dropped-faster
python .\scripts\video_edit_run.py --action auto-sync-dropped
python .\scripts\video_edit_run.py --action compare-transcripts
python .\scripts\video_edit_run.py --action review-subtitles
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action generate-role-aware-ass
python .\scripts\video_edit_run.py --action render-selected
```

After render, verify:

```powershell
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<final-video>"
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels -of json "<final-video>"
```

Also inspect sample frames from early, interviewer, onscreen, multicam switch, and late sections. Confirm:

- logo is the specified image and size;
- speaker subtitles use purple/black correctly;
- subtitle style matches the pre-app PNG-style baseline, not the simplified ASS fallback;
- corrected subtitle terms are present;
- audio remains synced after cuts or silence shortening;
- the 31:52 area and its surrounding five-minute QA render do not contain audio/video content mismatch;
- camera color is consistent, especially skin tone;
- every camera video segment has the intended 20% push-in without over-cropping faces or hands;
- denoise/mastering did not create pumping or clipped speech.

## Important Rules

- Full subtitles are literal utterance subtitles, not summaries.
- Interviewer omission mode may summarize questions, but normal full-subtitle mode must not.
- After subtitle generation, Codex must review and correct obvious unnatural transcription errors before final render.
- Do not use weak transcript matches for multicam sync decisions.
- Do not process full renders frame-by-frame in Python/OpenCV unless no FFmpeg equivalent exists. Prefer one-pass FFmpeg filter graphs for color, crop, scale, subtitles, audio cleanup, and encoding.
