# Yuri Nakanishi Tokyo Oasis Radio Editing Instructions

## Project Role

- This directory contains the project-specific instructions and implementation for the Tokyo Oasis video interview with 中西裕理.
- Run commands from the repository root.
- Set the project context when using shared tools:

```powershell
$env:VIDEO_EDIT_PROJECT = "yuri_nakanishi_tokyo_oasis_radio"
```

- Keep active media inside this project directory.
- Put project-specific scripts under `projects/yuri_nakanishi_tokyo_oasis_radio/scripts`.
- Generated transcripts, sync maps, subtitle files, logs, and rendered videos belong under `projects/yuri_nakanishi_tokyo_oasis_radio/output`.
- Prefer reusable shared pipeline parts from the app/shared toolchain, especially scripts under the repository `scripts/` directory that are exposed through the app workflow. Project-local scripts may wrap those tools for this one-off sync/render requirement.

## Source Materials

- Source video: `source/東京オアシス20260528.mp4`
- Edited source audio: `source/東京オアシス20260528.wav`
- Still images: `source/東京オアシス20260528_img1.jpg`, `source/東京オアシス20260528_img2.jpg`
- Right logo: `source/kiitos_logo.webp`

## Editing Goal

- Use the MP4 video as the visual source, not a fixed still image.
- Use the WAV file as the only final audio source.
- Do not use the audio embedded in the MP4 in the final render.
- The MP4 is recorded in chronological order, but the WAV has already removed stumbles, retakes, and repeated phrasing. Analyze transcripts and audio/video waveforms, then cut the video so it follows the edited WAV cleanly.
- Remove the opening introduction section and the final music section, as done in the 花岡洋行 project.
- Burn Japanese subtitles into the final MP4.
- Separate subtitle colors by speaker. 中西裕理 / interviewee subtitles must be blue.

## Sync Policy

- Treat the edited WAV as the timing authority.
- Transcribe the edited WAV and the MP4 audio with Whisper Large V3 or the project-standard faster-whisper Large V3 path.
- Compare transcript text, timestamps, audio features, and waveform similarity to align video portions to the edited WAV.
- Cut and concatenate video segments to match the edited WAV timeline. Prefer keeping video motion continuous around speech; cut away from obvious retakes or dead time.
- If exact waveform alignment is ambiguous, prefer transcript order and visible speech continuity over preserving original MP4 timing.
- Replace all rendered audio with the edited WAV after applying the same opening and ending cuts.

## Cut Policy

### Opening Introduction

- First transcribe the full edited WAV, including the opening.
- Identify the opening greeting/program setup using transcript content and waveform timing.
- Start the final edit at the first substantive interview exchange after the greeting.
- Avoid cutting into the first meaningful word of the interview body.

### Ending Music

- Identify the final spoken closing from the transcript.
- Confirm the transition into music using waveform/audio statistics.
- Exclude the final music section from the delivery.
- Leave only a short natural pause after the last spoken line if needed.

## Subtitle Policy

- Use Japanese transcription with timestamps.
- Keep subtitle lines readable: one or two lines, with natural Japanese phrase breaks.
- Avoid orphan line starts such as `しております`, `ております`, `という`, `っていう`, or a line starting only with a particle.
- Protect domain and name terms such as `キートス`, `中西裕理`, `東京オアシス`, `青少年の居場所`, and `認定NPO法人`.
- Fix obvious transcription errors in names, program terms, and places.
- Preserve the spoken meaning; light cleanup of fillers is allowed when it improves readability.

## Visual Style

- Follow the subtitle/title/logo style used in the 花岡洋行 Tokyo Oasis project and the `engineer-type-demo-interview` reference.
- Use large rounded subtitle boxes at the bottom, fully opaque.
- Interviewer / 長谷川さん subtitles: pink box.
- Interviewee / 中西裕理 subtitles: blue box.
- Subtitle text: white, large Yu Gothic Bold style, no outline.
- Add a persistent top-left title overlay: `【東京オアシス】中西裕理さん出演会`
- Match the title style from the 花岡洋行 project: white rectangular box, orange title text, translucent orange lower stripe, and orange underline.
- Add the Kiitos logo at top right using `source/kiitos_logo.webp`, inside a white rectangular box.

## Implementation Pipeline

1. Create project-local config and scripts, using shared app scripts where practical.
2. Build a media manifest and transcript workspace under `output/`.
3. Transcribe the edited WAV and MP4 audio.
4. Detect opening and ending cut points on the edited WAV.
5. Compare edited-WAV transcript segments against MP4 transcript/audio and build a video sync map.
6. Render cut/concatenated video segments using the MP4 video stream only.
7. Use the edited WAV, cut to the same final spoken range, as the only audio source.
8. Generate speaker-colored subtitle overlays from the final edited-WAV transcript.
9. Burn subtitles, title, and Kiitos logo into the synced video.
10. Verify sync, decode, duration, subtitle readability, opening removal, ending music removal, and audio source replacement.

## Verification Checklist

- All active paths are under `projects/yuri_nakanishi_tokyo_oasis_radio`.
- MP4 video is used for visuals.
- WAV audio is used for final audio; MP4 audio is not mapped into the final output.
- Opening introduction is absent from final output.
- Ending music section is absent from final output.
- Video cuts follow the edited WAV and remain visually coherent.
- 中西裕理 / interviewee subtitles use blue box backgrounds.
- 長谷川さん / interviewer subtitles use pink box backgrounds.
- Title `【東京オアシス】中西裕理さん出演会` is visible at top left.
- Kiitos logo from `source/kiitos_logo.webp` is visible at top right.
- Final MP4 has valid video and audio streams.
- `ffmpeg -v error -i <output> -f null -` reports no decode errors.
