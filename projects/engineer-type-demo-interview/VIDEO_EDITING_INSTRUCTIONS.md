# new-folder-2 Interview Video Editing Instructions

## Project Role

- This directory contains the project-specific instructions for the interview edit.
- Do not change shared app code for this project's one-off decisions. Put project-specific automation under `projects/new-folder-2/scripts`.
- Use shared app scripts only as reusable building blocks through `scripts/video_edit_run.py` or direct script calls.
- Treat `project_state.json`, the media manifest, and project-local `output` reports as the current working state, but do not commit generated outputs.
- For the current full-render handoff procedure, also read `projects/new-folder-2/ENGINEER_TYPE_RENDER_PROCEDURE.md`.

## Source Handling

- Run all commands from the repository root.
- Set the project context before using shared app scripts:

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"
```

- Active media must be project-local. Videos belong under `projects/new-folder-2/source/video`, external audio under `projects/new-folder-2/source/audio`, images/logos under `projects/new-folder-2/source/images`.
- Reuse existing transcript outputs when the user explicitly asks not to re-transcribe.
- Do not fall back to root-level `source` or `output` directories, old `.video-edit` runtime config, or media outside this project.

## Editing Goal

- Produce a polished long-form interview edit from the active project media.
- Use the selected master camera as the safe base shot and use close-up cameras only when sync, source coverage, and speaker-role checks support the cut.
- Prefer faithful full subtitles over summarized subtitles. Question/omission summaries are allowed only when explicitly using omission-card behavior.
- Keep app-level renderer decisions in project config or timeline JSON so they can be regenerated.

## Recommended Pipeline

```powershell
$env:VIDEO_EDIT_PROJECT = "new-folder-2"

python .\scripts\video_edit_run.py --action auto-sync-dropped
python .\scripts\video_edit_run.py --action compare-transcripts
python .\scripts\video_edit_run.py --action review-subtitles
python .\scripts\video_edit_run.py --action apply-subtitle-corrections
python .\scripts\video_edit_run.py --action classify-subtitle-speakers
python .\scripts\video_edit_run.py --action classify-subtitle-speakers-audio
python .\scripts\video_edit_run.py --action generate-role-aware-ass
python .\scripts\video_edit_run.py --action build-timeline
python .\scripts\video_edit_run.py --action validate-timeline
python .\scripts\video_edit_run.py --action render-selected
```

- Use `transcribe-dropped-faster` only when a suitable faster-whisper/CUDA environment is available or the user approves transcription.
- For short QA renders, disable silence shortening when exact source/video sync is being checked.
- For final delivery, silence shortening may be enabled with the project state's configured thresholds.

## Transcription And Subtitles

- Use the project transcript manifest under `projects/new-folder-2/output/transcripts/manifest_sources`.
- Review subtitles before a final render. Correct obvious unnatural transcription errors through the subtitle correction workflow rather than editing final ASS/PNG outputs as the only source.
- Speaker roles should distinguish:
  - `onscreen`: visible interviewee / visible speaker.
  - `interviewer`: offscreen interviewer or questioner.
- For stereo external audio, prefer `scripts/classify_speakers_audio_features.py` or the `classify-subtitle-speakers-audio` action.
- Positive `lrDb` is generally left-channel dominant/offscreen interviewer; negative `lrDb` is generally right-channel dominant/visible interviewee. Treat weak separation as ambiguous and inspect context.
- Do not mark a caption as interviewer only because it is short or ends with a question mark. A visible speaker can ask or quote a rhetorical question.
- Preserve Japanese phrase boundaries in full subtitle line breaks. Avoid splitting protected domain terms such as `FDE`, `PDM`, `SaaS`, `SIer`, `Claude Code`, `プロダクトマネージャー`, `ジョブディスクリプション`, and `リバースエンジニアリング`.

## Camera, Sync, And Color

- Waveform sync is the primary source for camera/audio alignment. Transcript comparison is a fallback and sanity check only when its manifest fingerprint matches the active project.
- For external-audio renders, rely on the renderer's external-audio cut sync guard before accepting close-up segments. Low-score, shifted, or short segments should fall back to the master camera.
- Long-form QA must include user-reported bad-cut areas. The historical problem area for this project is around `31:52`; render a surrounding QA sample before accepting a full rerender.
- Enable close-up masking so close-up cameras appear only while the visible speaker is speaking:

```json
{
  "render": {
    "closeupsOnlyWhenOnscreenSpeaker": true,
    "closeupSpeechPadding": 0.18,
    "closeupSpeechGapMerge": 0.8
  }
}
```

- Color matching should sample actual used timeline ranges, not generic timestamps. Compare each sub-camera sample against the master camera at the same synced timeline moment.
- White balance should be background/neutral-pixel first. Skin helps exposure QA but should not drive channel gains by itself.
- Apply any shared clean/white final look as `render.outputLookFilter`, not as a master-only camera override.

## Framing And Output

- For normal interview deliverables, use multicam settings through project state:

```json
{
  "render": {
    "multicamMode": "speaker-aware",
    "globalVideoZoom": 1.2,
    "faceCenterCrop": true,
    "faceCenterCropAxis": "x",
    "audioDenoise": true,
    "audioMastering": true,
    "outputFps": "30000/1001"
  }
}
```

- Do not apply `fps=30000/1001` inside every camera segment before concat. Trim/style segments first, concat, then apply one shared output FPS conversion.
- Keep the 20% push-in from over-cropping faces, hands, or important context. Check `person_crop_usage.json` or `face_center_crop_usage.json` and sample frames after rendering.
- Use `h264_nvenc` for fast samples when available, but benchmark quality and file size before a full render.

## Verification Checklist

- The active `VIDEO_EDIT_PROJECT` is `new-folder-2`.
- All active media paths are inside this project directory.
- The timeline validates before any adapter or renderer runs.
- Speaker subtitle colors are correct for onscreen vs interviewer captions.
- Subtitle corrections are present in the rendered output.
- Audio remains synced after multicam cuts and after optional silence shortening.
- Close-up shots do not use sources outside their valid synced coverage.
- Camera color is consistent, especially pale background/wall temperature.
- The output has a valid audio stream and decodes cleanly with ffmpeg/ffprobe.
