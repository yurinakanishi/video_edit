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
```

Expected output:

```text
projects\<project-id>\output\reports\full_transcript_speaker_roles.json
```

Use strict interviewer patterns and manual ranges when needed. Do not classify a caption as interviewer only because the sentence is short. If the visible speaker is talking, keep it `onscreen`.

Generate role-aware ASS subtitles:

```powershell
python .\scripts\video_edit_run.py --action generate-role-aware-ass
```

The role-aware style is:

- onscreen speaker: semi-transparent light purple box with white text;
- interviewer: semi-transparent black box with white text.

For visual style, the baseline is the pre-app PNG subtitle look, not the simplified ASS fallback. Use the PNG overlay style from `scripts/generate_full_transcript_png_overlays.py` and `scripts/subtitle_png_style.py` for QA clips and for final renders when command length allows it: large Yu Gothic Bold text, tracked lettering, dynamic-width rounded boxes, semi-transparent purple for onscreen speaker, and semi-transparent black for interviewer. If the transcript is sourced from external audio, create a timeline-shifted SRT from the existing SRT and point `render.subtitlePath` at it; this is a timestamp conversion, not a new transcription. If ASS is required for long command-length reasons, it must be styled to visually match this PNG baseline as closely as possible, not as plain minimal ASS text.

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

The renderer samples each selected camera and uses the long master/first camera as the reference. Sub-camera color samples must be taken at `timeline timestamp + sync offset`, not at the raw master timestamp, so the sampled frames represent the same interview moment. It should prefer detected skin-color samples when available, then fall back to neutral/global frame statistics. The sub cameras must be adjusted toward the long master camera, not the other way around. The report must be checked after render:

```text
projects\<project-id>\output\reports\camera_color_match.json
```

If a camera is still too warm or too cool after automatic matching, adjust with lightweight FFmpeg color filters or project config values rather than per-frame Python/OpenCV rawvideo processing for the full timeline.

For the current project, the color target is the long main camera `ST7_7550.MP4`. 2cam/sub-camera footage must be normalized toward that master camera so skin tone and overall warmth do not jump across multicam cuts.

## Global 20% Video Zoom

Apply a consistent 20% push-in to every camera video segment. This is a video-only transform: do not zoom subtitles, title graphics, right-top logo, glossary overlays, or omission cards.

The intended visual result is a 1.2x scale centered on the source frame, then cropped back to the final 1920x1080 canvas. This shows roughly the central 83% of each source frame. If the requirement is an exact 80% visible crop instead, use `globalVideoZoom = 1.25`.

Preferred renderer behavior:

```json
{
  "render": {
    "globalVideoZoom": 1.2
  }
}
```

`scripts/render_app_interview.py` reads `render.globalVideoZoom` and composes this transform into the per-camera FFmpeg visual filter graph after source color matching and before overlays/subtitles are burned.

When person-aware crops are enabled, treat the 20% zoom as the minimum push-in. Do not double-zoom tight face crops so far that the speaker's head, hands, or important context are cut unnaturally. Check `output/reports/person_crop_usage.json` and sample frames after render.

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
