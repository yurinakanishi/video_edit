# Edit Instruction

## Current Request

- Keep the current digest section unchanged.
- Use the full main interview, not a shortened excerpt. The main content window is `519.14` to `2985.485` seconds on the master camera.
- Use `output/reports/captions.md` as the source for main-section emphasis captions.
- Main captions are not full subtitles. They are large emphasis captions for important statements only.
- Remove Japanese comma punctuation `、` from display captions.
- Preserve the existing company movie bridge in full.
- After the company movie ends, cut any silent/waiting dead time so the left interviewer begins speaking immediately.
- The post-company-movie first shot should use the left interviewer close-up (`person_01` / `cam_person_01`) aligned to the same master-audio speech start.

## People And Screen Positions

- Left: `person_01`, 矢野, interviewer, source camera `cam_person_01`.
- Middle: `person_02`, 根本, interviewee, source camera `cam_person_02`.
- Right: `person_03`, 村田, interviewee, source camera `cam_person_03`.

## Main Edit Rules

- The speaking person must be visible in every main-section cut.
- Prefer a single close-up when the active speaker is reliable.
- Use the three-person wide camera when speaker attribution is uncertain.
- Use two-person split views for exchanges between interviewer and interviewee, or when reaction coverage is useful.
- Use three-person split views periodically to keep visual rhythm and ensure everyone remains represented.
- Change camera/layout approximately every 15 seconds across the full main section.

## Caption JSON

- Build or update a project-local JSON derived from `captions.md`.
- Each caption item should include:
  - source caption number from `captions.md`
  - master timeline start/end
  - display text
  - search keys or evidence
  - inferred `speaker_person_id`
  - speaker position/name metadata
  - confidence and selection method
- Caption text must not contain `、`.

## Render Target

- Render a full-length 720p / 30fps preview.
- Output should remain browser-compatible H.264 `yuv420p`.
