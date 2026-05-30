# Hanaoka Hiroyuki Tokyo Oasis Radio Editing Instructions

## Project Role

- This directory contains the project-specific instructions and implementation for the Tokyo Oasis radio still-image subtitle video.
- Run commands from the repository root.
- Set the project context when using shared tools:

```powershell
$env:VIDEO_EDIT_PROJECT = "hanaoka_hiroyuki_tokyo_oasis_radio"
```

- Keep active media inside this project directory. Do not use the old root-level `hanaoka_hiroyuki_tokyo_oasis_radio/source` path for implementation.
- Put project-specific scripts under `projects/hanaoka_hiroyuki_tokyo_oasis_radio/scripts`.
- Generated transcripts, intermediate audio, subtitle files, logs, and rendered videos belong under `projects/hanaoka_hiroyuki_tokyo_oasis_radio/output`.

## Source Materials

- Main still image: `source/images/東京オアシス20260205_img1.jpg`
- Alternate still image: `source/images/東京オアシス20260205_img2.jpg`
- Right logo: `source/images/kiitos_logo.webp`
- Source audio: `source/audio/東京オアシス20260205 花岡洋行様.wav`

## Editing Goal

- Use the main still image as a fixed full-video visual.
- Use the radio audio as the source audio.
- Transcribe the audio with Whisper Large V3.
- Analyze the opening greeting section and the final music section, then remove both from the final video.
- Burn Japanese subtitles into the final MP4.
- Separate subtitle colors for interviewer and interviewee.

## Cut Policy

### Opening Greeting

- First transcribe the full source audio, including the opening.
- Identify the opening greeting by combining transcript content, timestamps, and waveform/audio inspection.
- Start the final edit at the first substantive interview exchange after the greeting or program intro.
- Avoid cutting into the first meaningful word of the interview body.

### Ending Music

- Identify the end of spoken content from the transcript.
- Confirm the transition into music using waveform and audio statistics.
- Cut final music from the delivery.
- Leave only a short natural pause after the last spoken line if needed.

## Transcription And Subtitle Policy

- Use Whisper Large V3 with Japanese language settings.
- Prefer timestamped segment output plus SRT or JSON so edits can be audited.
- Use PNG subtitle overlays for the visual subtitle style. ASS/SRT files may still be generated as audit artifacts.
- Keep subtitle lines readable: normally one or two lines, with natural Japanese phrase breaks.
- Avoid unnatural orphan subtitles or line starts such as `しております` / `ております`; keep endings with their governing phrase, e.g. `お招きしております`.
- Merge adjacent Whisper segments when a segment begins with dependent continuations such as `っていう`, `という`, or `ので`, so subtitle cards do not begin with dangling connective phrases.
- Protect domain and name terms such as `キートス`, `新理事`, `花岡洋行`, `青少年の居場所`, `認定NPO法人`, and common phrases like `お話し` / `お伺い` from being split across subtitle lines.
- Fix obvious transcription errors, especially names, program terms, and places.
- Preserve the meaning of spoken content; light cleanup of fillers is allowed when it improves readability.

## Speaker Color Policy

- Subtitle styling should follow the PNG overlay look used by `projects/engineer-type-demo-interview`.
- Match the practical `engineer-type-demo-interview` subtitle scale: about 80px Yu Gothic Bold, 4px tracking, 18px horizontal padding, 10px vertical padding, 6px line gap, 10px corner radius, fully opaque boxes, and a low 16px bottom margin.
- Subtitle text should be white with no black outline, matching the reference PNG subtitle style.
- Subtitle box background for 長谷川さん / interviewer captions: pink.
- Subtitle box background for 花岡洋行さん / interviewee captions: green.
- Subtitle boxes should be fully opaque unless the user asks for transparency.
- Place subtitles at the bottom with the same low margin as `engineer-type-demo-interview`.
- Ambiguous short backchannels should inherit the surrounding speaker when clear.
- If automatic speaker detection is weak, inspect text and audio manually before final render.

## Title And Logo Policy

- Add a persistent top-left title overlay: `【東京オアシス】花岡洋行さん出演会`
- Make the title large, matching the scale of the `engineer-type-demo-interview` top-left title treatment.
- Match the `engineer-type-demo-interview` chapter/title PNG style: white rectangular box, orange title text, orange translucent lower stripe, and a solid orange underline.
- Add the Kiitos logo at the top right using `source/images/kiitos_logo.webp`.
- Make the Kiitos logo large and place it inside a white rectangular box.
- Keep title and logo clear of the subtitle area.
- The title should use a compact boxed treatment that matches the functional overlay style of `engineer-type-demo-interview`.

## Implementation Pipeline

1. Scan project-local source files.
2. Generate a work WAV for analysis if needed.
3. Run Whisper Large V3 transcription.
4. Produce a transcript audit file with timestamps.
5. Detect candidate start and end cut times from transcript and audio.
6. Generate cut audio.
7. Generate role-colored box-backed PNG subtitle overlays aligned to the cut audio. Also write SRT/ASS audit files.
8. Render the still-image video with burned PNG subtitles, top-left title, and top-right Kiitos logo.
9. Verify decode, duration, first seconds, subtitle readability, and ending cut.

## Verification Checklist

- All active paths are under `projects/hanaoka_hiroyuki_tokyo_oasis_radio`.
- `img1` is used as the fixed visual.
- Opening greeting is absent from final output.
- Final music section is absent from final output.
- 長谷川さん / interviewer subtitles use pink box backgrounds.
- 花岡洋行さん / interviewee subtitles use green box backgrounds.
- The title `【東京オアシス】花岡洋行さん出演会` is visible at top left.
- The Kiitos logo from `source/images/kiitos_logo.webp` is visible at top right.
- Subtitles are readable and do not cover important image content.
- The final MP4 has valid video and audio streams.
- `ffmpeg -v error -i <output> -f null -` reports no decode errors.
