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

## Rendering Workflow

Never start with a final production render.

For every direct Codex editing task:

1. First create a lightweight, fast preview render.
2. Make the preview available for user review.
3. Apply the user's review feedback and correction requests.
4. Iterate with additional previews as needed.
5. Only run the final production render after the user has confirmed the result is ready.

The preview stage should be optimized for speed and reviewability. The final render should be produced only after the edit decisions, timing, subtitles, audio, overlays, and visual treatment are accepted.

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
