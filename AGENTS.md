# AGENTS.md

## Project Usage Modes

This repository is used in two main ways.

### 1. App Operation

When the project is used as an application, the user operates it through the normal UI.

- Keep the Electron UI workflow as the primary operator experience.
- Shared workflow actions should continue to run through the app-controlled pipeline.
- Do not change project-specific behavior in shared app code unless the behavior is reusable across projects.

### 2. Direct Codex Work

When the user opens this repository and gives Codex direct instructions, create and work inside a project-specific workspace under `projects/<project-id>/`.

Required flow:

1. Move or copy the user-specified source files into the project directory under `projects/<project-id>/source/`.
2. Create or update the project state and project-local structure for that work.
3. Prefer reusable shared pipeline parts from `video_edit_core/` and `scripts/`.
4. If the requested edit needs project-specific logic, create a project-local script under `projects/<project-id>/scripts/`.
5. Keep generated files under the active project's `output/` tree.

Project-local scripts are for one-off ordering, selection, tuning, QA, or render logic that should not become shared app behavior.

### 3. Project Tests

When creating project-shaped fixtures for tests or smoke runs, group them under a named test workspace, for example `projects/__smoke__/<test-name>/<run-id>/`.

- Do not leave test fixtures as top-level `projects/<fixture-name>` entries.
- Use the same project-local shape inside the named test workspace when the app or pipeline expects a normal project.
- For Electron smoke tests, prefer `VIDEO_EDIT_PROJECTS_ROOT` to point project creation and discovery at the active test run directory.

## Rendering Workflow

Never start with a final production render.

For every direct Codex editing task:

1. First create a lightweight, fast preview render.
2. Make the preview available for user review.
3. Apply the user's review feedback and correction requests.
4. Iterate with additional previews as needed.
5. Only run the final production render after the user has confirmed the result is ready.

The preview stage should be optimized for speed and reviewability. The final render should be produced only after the edit decisions, timing, subtitles, audio, overlays, and visual treatment are accepted.

## AI Editing Methodology

For AI-assisted editing work, keep the AI responsible for edit decisions and keep Python responsible for validation and rendering.

Prefer this layered structure:

1. Analysis JSON: media probes, transcript, speaker diarization, face/person tracks, framing, camera quality, audio levels, and named entities.
2. Semantic JSON: highlight candidates, topics, strong quotes, entity explainers, subtitle candidates, and editorial intent.
3. Edit Decision JSON: the final timeline, selected source ranges, camera/layout choices, captions, overlays, audio behavior, and transitions.

The key artifact is `edit_plan.json`. It should describe what the finished video should show, not how FFmpeg should spell the filter graph. Do not ask an AI model to produce the final production `filter_complex` as the source of truth. Generate FFmpeg/OpenCV/overlay operations from validated JSON in Python.

Keep identity concepts separate:

- `speaker_id` is a diarized audio speaker.
- `face_track_id` is a tracked face in video.
- `person_id` is a confirmed real person.

Do not render names, titles, departments, biographies, or person-specific lower thirds unless they come from a verified project source such as `people_map.json`. AI-inferred identities must remain placeholders until confirmed.

Design project-local schemas and scripts to support any number of participants and cameras. Avoid hard-coded assumptions such as exactly two speakers, exactly three people, exactly four cameras, or count-specific layout names unless the requested output explicitly requires that exact count. Use participant-aware and count-independent concepts such as `wide_group`, `single`, `person_with_bio`, `speaker_reaction_pair`, `split_grid`, and `auto_by_media_count`.

Use seconds for timing and normalized coordinates for analysis geometry by default. Convert to preview, final, or master pixels during rendering.

Keep full transcripts separate from editorial captions:

- `transcript.json` is the source transcript.
- `semantic_marks.json` contains caption candidates and highlights.
- `edit_plan.json` contains the captions that will actually be displayed.

Before rendering, validate at minimum:

- all referenced media IDs, person IDs, speaker IDs, face track IDs, and style IDs exist;
- all source ranges are within media duration;
- timeline gaps and overlaps are intentional;
- captions and overlays do not collide unless explicitly allowed;
- person labels require a verified people map.

When the project needs custom ordering, selection, tuning, QA, or render behavior, keep that logic under `projects/<project-id>/scripts/` unless it is clearly reusable across projects.

## Shared vs Project-Specific Code

- Put reusable Python implementation in `video_edit_core/`.
- Keep `scripts/*.py` as stable CLI entry points, workflow actions, compatibility wrappers, or shared tools.
- Keep project-specific automation under `projects/<project-id>/scripts/`.
- Do not move project-local scripts into shared code just because they are useful for one project.
- Extract shared helpers only when they clearly apply across projects.

## Expected Codex Behavior

Before project-specific work, read the active project's:

- `VIDEO_EDITING_INSTRUCTIONS.md`
- `scripts/`
- `config/`
- relevant `project_state.json` and output reports, when present

Use existing shared actions where possible, for example:

- `python scripts/video_edit_run.py --action build-timeline`
- `python scripts/video_edit_run.py --action validate-timeline`
- `python scripts/video_edit_run.py --action render-selected`

Prefer timeline JSON plus validation before rendering. If rendering is blocked, report the missing input or validation issue clearly instead of inventing a workaround.
