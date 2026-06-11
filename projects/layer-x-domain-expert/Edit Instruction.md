# Edit Instruction

## Current Request

- Opening digest should be shortened to about one minute by keeping only the strongest question/answer beats. Current target implementation is `61.0` seconds, recorded in `output/reports/digest_one_minute_shortening_report.json`.
- The first digest question must start at the captioned phrase `開発に関わる仕事をする中で`. Cut the leading phrase `ちなみにお二人の中でこれまで` from both video and audio. Current first digest trim is recorded in `output/reports/first_digest_question_trim_report.json`; current digest duration is `61.0` seconds.
- Use the full main interview, not a shortened excerpt. The main content window is `519.14` to `2985.485` seconds on the master camera.
- Use `output/reports/edit_plan.json` `timeline[].overlays[type=caption]` as the single source of truth for all rendered emphasis captions.
- Main captions are not full subtitles. They are large emphasis captions for important statements only.
- In the main section, do not show interviewer questions or prompts from the left interviewer as emphasis captions. Keep main captions focused on the interviewees' answers and key statements. Digest question captions are allowed.
- Remove Japanese comma punctuation `、` from display captions.
- Preserve the existing company movie bridge in full.
- After the company movie ends, cut any silent/waiting dead time so the left interviewer begins speaking immediately.
- The post-company-movie first shot should use the left interviewer close-up (`person_01` / `cam_person_01`) aligned to the same master-audio speech start.
- Apply noise reduction to the interview audio to reduce the constant broadband "ザー" environmental noise while keeping the company movie from being over-processed.
- Do not switch interview audio sources mid-video. Use one continuous interview audio source from digest through main and closing.
- Current selected interview audio source: `cam_person_02`, based on `output/reports/audio_source_quality_audit.json`.
- `group_wide` remains the transcript/reference clock source, but it must not be used as final interview audio because it ends before the separate final thanks take.

## People And Screen Positions

- Left: `person_01`, 矢野, interviewer, source camera `cam_person_01`.
- Middle: `person_02`, 根本, interviewee, source camera `cam_person_02`.
- Right: `person_03`, 村田, interviewee, source camera `cam_person_03`.

## Main Edit Rules

- The speaking person must be visible in every main-section cut.
- Speaker attribution must use `output/reports/voice_speaker_attribution.json` as the primary source, because it combines voice-quality analysis with transcript role constraints.
- Mouth-motion based `speaker_activity_analysis.json` is secondary evidence only and must not override reliable voice attribution.
- Record speaker attribution per utterance so each transcript/audio segment has a `speaker_person_id`, name, screen position, confidence, and method.
- Main-section layout selection must be linked to the voice speaker window:
  - one reliable speaker in the cut window: speaker close-up is allowed;
  - two speakers in the cut window: use a two-person split including both;
  - three speakers or uncertain attribution: use a three-person split or wide camera.
- Prefer a single close-up when the active speaker is reliable.
- Use the three-person wide camera when speaker attribution is uncertain.
- Use two-person split views for exchanges between interviewer and interviewee, or when reaction coverage is useful.
- Do not cut directly from one two-person split to another two-person split. After any two-person split, insert a single close-up, three-person wide shot, or three-person split before using another two-person split.
- Preserve the real seating order in all split layouts: `person_01` / left person, then `person_02` / middle person, then `person_03` / right person. For two-person splits, keep the same left-to-right subset order and never reverse it to follow the active speaker.
- Use three-person split views periodically to keep visual rhythm and ensure everyone remains represented.
- Change camera/layout approximately every 15 seconds across the full main section.
- Run `projects/layer-x-domain-expert/scripts/enforce_split_layout_rules.py` after timeline changes. It normalizes split panel order, removes consecutive two-person splits, and converts any main event with a missing trusted voice-attributed speaker to a three-person split.
- Generate `output/reports/main_speaker_layout_audit.json` before rendering and treat any missing-speaker violation as a blocker.

## Caption JSON

- Do not use a markdown caption source. The markdown caption file and its generation script have been removed.
- Update caption timing, text, speaker, and visibility directly in `output/reports/edit_plan.json`.
- Each rendered caption overlay should include:
  - master timeline/source start/end metadata
  - display text
  - search keys or evidence when available
  - inferred `speaker_person_id`
  - speaker position/name metadata
  - confidence and selection method
- Caption text must not contain `、`.
- Main-section caption JSON must exclude left-interviewer question prompts such as `どう考えていますか`, `ありますか`, `でしょうか`, and similar setup questions. If a question was split into multiple caption parts, remove the whole split group.
- Remove non-editorial caption fragments before rendering. This includes short reactions, greetings, setup phrases, dangling clauses, and captions that do not express the core question or answer (for example `めっちゃ大事です`).
- Display captions may be editorially condensed from the transcript when needed. Prefer short declarative wording that preserves the meaning and fits in one or two natural lines instead of verbatim filler such as `という`, `感覚があって`, or other trailing hedges.
- If a transcript phrase would become three or more visual lines, or would require sequential caption parts to avoid overflow, rewrite it as a concise editorial caption that preserves the core meaning in one or two lines. For example, use `バックオフィスの仕事は前提ミスが許されない通説がある` instead of verbatim multi-line wording such as `結構やっぱりバックオフィスの仕事って前提ミスが許されませんっていう通説としてあるじゃないですか`.
- Caption vertical placement should sit one step lower than the previous preview in both digest and main sections. Current 720p render anchors: digest caption bottom `y=684`, main caption bottom `y=704`.
- Run `projects/layer-x-domain-expert/scripts/prune_irrelevant_caption_overlays.py` after caption/timeline regeneration so removed filler captions do not return. If `normalize_caption_overlays_two_lines.py` is run, run the prune script again after normalization because normalization can rebuild split caption parts from their source text.
- Caption wrapping must use `projects/layer-x-domain-expert/scripts/caption_wrap_rules.py` for both render and `caption_review.md`.
- Do not force long captions into two visual lines by cutting at arbitrary character positions. Split them into sequential 1-2 line caption overlays at natural phrase boundaries.
- After caption or timeline changes, run `normalize_caption_overlays_two_lines.py`, `condense_caption_overlays_to_two_line_units.py`, `export_caption_review_md.py`, and `audit_caption_line_breaks.py`. Treat any line-break audit issue as a blocker before preview rendering.

## Render Target

- Render a full-length 720p / 30fps preview.
- Output should remain browser-compatible H.264 `yuv420p`.
- Interview audio should use per-segment denoise plus final loudness mastering: highpass, lowpass, `afftdn`, `anlmdn`, compression, dynamic normalization, and final `loudnorm`.
- The company movie may keep its own embedded audio; this is the only intentional non-interview audio exception.
