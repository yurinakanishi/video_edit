# Refactoring Implementation Plan

Companion to [`docs/REFACTORING_PLAN.md`](./REFACTORING_PLAN.md), which holds the diagnosis, rationale, and phase design.
This file is the **execution checklist**: ordered work items, per-item scope, verification steps, and status tracking.

How to use this file:

- Work top to bottom. Items within a phase are ordered by dependency.
- Each work item is sized to be one reviewable change (one PR / one commit series).
- Check off items as they land. Add a date and short note on completion.
- Every item ends with the same gate unless stated otherwise: **`pytest` green + `python scripts/check_architecture.py` green + app action surface unchanged.**
- Out of scope everywhere: the Electron app under `app/` (its Python spawn contract is a frozen interface).

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Phase 0 — Safety Net

### P0.1 Packaging: `pyproject.toml`
- [ ] Confirm the active Python interpreter version used by the app and local runs (check `VIDEO_EDIT_PYTHON`, the `.video-edit/venvs/` interpreters, and recent report metadata).
- [ ] Create root `pyproject.toml`:
  - package: `video_edit_core` (the root package only; `scripts/` is not packaged)
  - core deps: `Pillow`, `numpy`
  - extras: `analysis = [opencv-python, ultralytics==8.4.60, mediapipe==0.10.35, easyocr==1.7.2]`, `transcribe = [openai-whisper, faster-whisper]`, `dev = [pytest, ruff, mypy, jsonschema]`
  - `requires-python` pinned to the confirmed version
- [ ] Verify `pip install -e .[dev]` works in a clean venv and `import video_edit_core` resolves to the root package.
- [ ] Update `reference-assets/config/requirements.analysis.txt` to point at the extra (or delete it and update `reference-assets/README.md`).

### P0.2 Lint and type checks
- [ ] Add `ruff` config to `pyproject.toml`: pyflakes (`F`), isort (`I`), and correctness-only rules; exclude `projects/*/scripts/archive/` (future) and `app/`.
- [ ] Add `lint:py` script to root `package.json` alongside `arch:check`.
- [ ] One-time cleanup commit: `ruff --fix` for **unused imports only** (notably the bulk unused `video_edit_core.paths` imports in overlay/thumbnail scripts). No other autofixes.
- [ ] Add `mypy` config scoped to `video_edit_core/` only, non-blocking (`mypy --ignore-missing-imports video_edit_core`); add `typecheck:py` script.

### P0.3 Test harness
- [ ] Create `tests/` with `tests/unit/`, `tests/golden/`, `tests/fixtures/`, and a `conftest.py` that sets `VIDEO_EDIT_PROJECTS_ROOT` to a temp/smoke path.
- [ ] Write the fixture builder (`tests/fixtures/build_fixture_project.py`): generates a tiny project under `projects/__smoke__/refactor-golden/<run-id>/fixture-project/` with `project.json`, `project_state.json`, a media manifest, and tiny generated media (ffmpeg `testsrc`/`sine`, ≤2 s clips). Mark media-dependent tests `@pytest.mark.ffmpeg`.
- [ ] Restructure `projects/__smoke__/` to the documented `<test-name>/<run-id>/` shape; relocate or delete the stray `projects/__smoke__/output/reports/source_coverage_usage.json`.
- [ ] Unit tests for already-pure modules:
  - [ ] `video_edit_core/composition.py` (anchors, crop targets, bbox scoring)
  - [ ] `video_edit_core/timeline/validation.py` (valid/invalid fixture timelines, semantic checks: overlap, source refs, duration bounds)
  - [ ] `video_edit_core/transcription_quality.py` (SRT time formatting, low-confidence filtering)
- [ ] Golden comparator helper in `tests/golden/`: normalizes `generated_at`/timestamps and absolute paths before diffing.
- [ ] Golden tests (freeze current behavior, do not fix anything they reveal):
  - [ ] `build_edit_timeline.py` on the fixture project → golden `current.timeline.json`
  - [ ] `ffmpeg_timeline_adapter.py` on a fixture timeline → golden command/filtergraph report (do not execute FFmpeg)
  - [ ] `timeline_graphics_adapter.py` → golden layer manifests (remotion + blender job JSON)
  - [ ] `timeline_validate` → golden pass/fail outcomes

### P0.4 CI / local gate
- [ ] Add `.github/workflows/python.yml` (or, if CI is unwanted, a documented `pnpm run check:py` composite): `ruff` + `pytest tests/unit tests/golden -m "not ffmpeg"` + `python scripts/check_architecture.py`.
- [ ] Document the developer setup in `README.md` (interpreter, `pip install -e .[dev]`, FFmpeg expectation).

**Phase 0 exit:** clean-venv install works; suite green; goldens committed; gate runs all three checks.

---

## Phase 1 — Deduplicate the Shared Layer

Each item: create the core module with unit tests → migrate all call sites → delete local copies → gate.

### P1.1 `video_edit_core/config.py`
- [ ] Move/unify: `nested()` (exists in both `app_config.py` and `transcription_quality.py`), `bool_value`/`bool_config`, `int_config`, `optional_path`, `media_manifest()`, `manifest_camera_paths()`.
- [ ] Migrate call sites (≥10 scripts incl. `video_edit_run.py`, `render_multicam.py`, `build_edit_timeline.py`, `ffmpeg_timeline_adapter.py`, `transcribe_manifest_sources*.py`, `auto_sync_app_sources.py`, `analyze_multicam_blocking.py`, thumbnail scripts).

### P1.2 `video_edit_core/tools.py`
- [ ] FFmpeg/ffprobe resolution chain: app config → env → `PATH`; remove the `C:\ProgramData\chocolatey\bin\ffmpeg.exe` literal default (13 scripts).
- [ ] Move `run_text()`, `probe_duration()` (currently duplicated in `audio/silence.py` and `replace_video_audio.py`); add a `run_ffmpeg(args, *, capture)` wrapper.

### P1.3 `video_edit_core/jsonio.py`
- [ ] `load_json(path)`, `write_json(path, payload)` (utf-8, `ensure_ascii=False`, indent 2, trailing newline, atomic write option).
- [ ] `write_report(path, payload, *, schema_version)` that injects `schema_version` + `generated_at`.
- [ ] Migrate the 5+ shared-script copies (`build_edit_timeline.py`, `review_subtitles.py`, `apply_subtitle_corrections.py`, `compare_manifest_transcripts.py`, `check_architecture.py`). (Project scripts migrate in Phase 4.)

### P1.4 `video_edit_core/timeutil.py`
- [ ] Canonical seconds-based API with explicit converters: `now_iso()`, SRT parse/format (`HH:MM:SS,mmm`), overlay timestamp (`HH:MM:SS.xx`), ms label helpers.
- [ ] Migrate `build_edit_timeline.py`, `ffmpeg_timeline_adapter.py`, `timeline_changed_regions.py`, `transcription_quality.py`, `app_config.py` call sites.

### P1.5 `video_edit_core/geometry.py`
- [ ] `clamp()`, `as_float()`, normalized-coordinate helpers; **one** canonical `canonical_path_key()` (today: two names, and `render_multicam.py` defines it twice internally at L1290/L2057).
- [ ] Migrate `composition.py` consumers, `build_edit_timeline.py`, `render_multicam.py`, `auto_sync_app_sources.py`, `timeline/validation.py`.

### P1.6 `video_edit_core/logging.py`
- [ ] Stdlib logging setup: human logs → stderr (level via env/flag), machine-readable final JSON → stdout (preserves the app's stdout-parsing contract).
- [ ] Adopt only in scripts touched by P1.1–P1.5; broader adoption rides along with later phases.

### P1.7 Core consolidation
- [ ] `paths.py`: drop its private app-config loader; depend on `app_config.load_app_config()`.
- [ ] Move CLI `main()` out of `timeline/validation.py` → `scripts/timeline_validate.py`; out of `audio/silence.py` → `scripts/shorten_silences.py` (wrappers already exist; keep re-export contract that `check_architecture.py` enforces).
- [ ] `graphics/subtitle_png.py`: replace hardcoded `C:\Windows\Fonts\YuGothB.ttc` with config key + default chain.

### P1.8 Fix cross-script imports
- [ ] `video_edit_core/analysis/face_mesh.py` ← move `scripts/face_mesh_metrics.py` library parts; update importers (`analyze_person_bboxes.py`, `classify_subtitle_speakers.py`); keep `scripts/face_mesh_metrics.py` as a re-export shim or delete after migration.
- [ ] `video_edit_core/transcription/manifest.py` ← `choose_primary`, `manifest_sources` from `transcribe_manifest_sources.py`; remove the `transcribe_manifest_sources_faster.py` → `transcribe_manifest_sources` cross-import.

### P1.9 Dead code
- [ ] Delete unused helpers in `video_edit_run.py`: `add_audio_args`, `add_silence_args`, `selected_mode`.
- [ ] Decide `retime_subtitles_readable.py` (332 lines, zero references): register as workflow action **or** move logic to `captions/srt.py` in Phase 2 **or** delete. No limbo.

### P1.10 Enforcement
- [ ] Extend `check_architecture.py`: fail if any function name from a denylist (`media_manifest`, `bool_value`, `read_json`, `write_json`, `clamp`, `now_iso`, `canonical_path_key`, …) is *defined* in `scripts/*.py` rather than imported from core.

**Phase 1 exit:** zero duplicate helper definitions in `scripts/` (enforced); goldens unchanged.

---

## Phase 2 — Break Up the God Scripts

Order: adapters → analysis → captions/overlays → `render_multicam.py` slices → dispatcher. Each extraction: move logic to core module + unit tests → script becomes wrapper → goldens green.

### P2.1 Timeline adapters
- [ ] `video_edit_core/render/ffmpeg_graph.py` ← `ffmpeg_timeline_adapter.py` (992 lines → wrapper ≤150).
- [ ] `video_edit_core/render/graphics_layers.py` ← `timeline_graphics_adapter.py` (818 lines); extract the embedded Blender script template into a separate resource file.
- [ ] `video_edit_core/render/otio.py` ← `timeline_otio_adapter.py` (274 lines).
- [ ] `video_edit_core/timeline/changed_regions.py` ← `timeline_changed_regions.py` (311 lines).

### P2.2 Timeline builder
- [ ] `video_edit_core/timeline/build.py` ← `build_edit_timeline.py` (~950 lines of logic). Split internally: report ingestion, overlay layout intake, person-plan application, timeline assembly (`build_timeline()` is ~130 lines — break it up).

### P2.3 Analysis modules
- [ ] `video_edit_core/analysis/person_bboxes.py` ← `analyze_person_bboxes.py` (803 lines; keep YOLO/mediapipe imports lazy).
- [ ] `video_edit_core/analysis/person_edit_plan.py` ← `build_person_edit_plan.py` (483 lines) **plus** the ~150-line duplicated block from `build_edit_timeline.py` (L494–648) and `render_multicam.py` (L1290–1438), incl. `face_center_subject_screen_x` / `adjusted_face_center_crop_x`. One implementation, two consumers. Verify with goldens on both pipelines.
- [ ] `video_edit_core/analysis/speaker_audio.py` ← `classify_speakers_audio_features.py` (399 lines).
- [ ] `video_edit_core/analysis/speaker_visual.py` ← `classify_subtitle_speakers.py` (569 lines).
- [ ] `video_edit_core/analysis/blocking.py` ← `analyze_multicam_blocking.py` (352 lines).
- [ ] `video_edit_core/analysis/sync.py` ← `auto_sync_app_sources.py` (731 lines, audio cross-correlation).

### P2.4 Captions / overlays / transcription
- [ ] `video_edit_core/captions/wrap.py` ← unify the 3 copies of JP line-break rules (`generate_full_transcript_png_overlays.py`, `generate_punchline_png_overlays.py`, `generate_role_aware_ass.py`) + fold in `projects/layer-x-domain-expert/scripts/caption_wrap_rules.py` (660 lines) if compatible; otherwise reconcile in Phase 4.
- [ ] `video_edit_core/captions/overlays.py` ← `generate_full_transcript_png_overlays.py` (738), `generate_punchline_png_overlays.py`, `generate_title_png_overlay.py`, `generate_chapter_title_png_overlays.py`, `generate_omission_card.py` — exposed as functions so `render_multicam` stops shelling out to sibling scripts.
- [ ] `video_edit_core/captions/ass.py` ← `generate_role_aware_ass.py`.
- [ ] `video_edit_core/captions/srt.py` ← SRT handling from `review_subtitles.py` / `apply_subtitle_corrections.py` (+ `retime_subtitles_readable.py` if kept).
- [ ] `video_edit_core/transcription/whisper_runner.py` / `faster_whisper_runner.py` / `compare.py` ← `transcribe_manifest_sources.py` (154), `transcribe_manifest_sources_faster.py` (145), `compare_manifest_transcripts.py` (328).
- [ ] `video_edit_core/graphics/thumbnails.py` ← `generate_thumbnail_candidates.py` (685) + `generate_project_thumbnail.py`.

### P2.5 `render_multicam.py` decomposition (slice by slice)
- [ ] **First:** extend goldens to freeze `render_multicam` planning outputs on the fixture project (segment plan, color filters, overlay manifest, final FFmpeg command report).
- [ ] Slice 1: `render/multicam/color.py` ← `frame_visual_stats()` (~185 lines) + `camera_color_match_filters()` (~183).
- [ ] Slice 2: `render/multicam/segments.py` ← segment planning + `constrain_segments_to_source_coverage()` (~200) + `guard_segments_by_external_audio_sync()` (~180).
- [ ] Slice 3: person/crop logic → already in `analysis/person_edit_plan.py` (P2.3); delete the local copy.
- [ ] Slice 4: overlay orchestration → calls into `captions/overlays.py` (no more subprocess to sibling scripts); music bed + omission card hookups.
- [ ] Slice 5: `render/multicam/command.py` ← FFmpeg command assembly.
- [ ] Slice 6: `render/multicam/pipeline.py` ← the 577-line `main()` becomes a ~100-line pipeline function; `scripts/render_multicam.py` becomes arg parsing + pipeline call.
- [ ] `render_app_interview.py` stays a ≤12-line shim (arch-check enforced).

### P2.6 Dispatcher
- [ ] `video_edit_run.py`: replace `command_for_action()` / `commands_for_action()` if/elif chains with a declarative table `action -> [stage specs]`, parameterized by overlay backend (remotion/blender permutations currently ~60 near-duplicate lines).
- [ ] Dry-run verification: iterate every action in `config/workflow_actions.json`, resolve its command list, assert all referenced scripts exist.

### P2.7 Enforcement
- [ ] Add to `check_architecture.py`: max 300 lines per `scripts/*.py`; update its required-core-files inventory for the new module layout.

**Phase 2 exit:** no `scripts/*.py` over 300 lines; goldens unchanged; every workflow action passes dry-run.

---

## Phase 3 — Data Model, Schemas, Safe Mutation

### P3.1 Schemas (`config/schemas/`)
- [ ] `edit_plan.schema.json` (`edit_plan/v2`), resolving drift by decree:
  - `timeline` = array of events (kill `{events: []}`)
  - canonical continuation key: `caption_continuation_root_id`
  - canonical source-window priority: `audio_alignment.source_window_sec` → `metadata.source_start_sec` → parsed `source_timecode`
  - seconds everywhere; `start`/`end` event-local, `*_abs_sec` absolute
- [ ] `person_edit_plan.schema.json`
- [ ] `subtitle_layout.schema.json` (formalizes `video-edit-subtitle-layout/v1`)
- [ ] `graphics_layers.schema.json`, `sync_offsets.schema.json`
- [ ] Replace the hand-rolled validator engine in `timeline/validation.py` with the `jsonschema` package; keep the semantic checks (overlap, refs, durations) as Python.

### P3.2 Typed model
- [ ] `video_edit_core/edit_plan/model.py`: dataclasses `EditPlan`, `TimelineEvent`, `CaptionOverlay`, `SourceRange`, `AudioAlignment`; tolerant `from_dict`/`to_dict`; canonical helpers `event_duration`, `ref_window`, `caption_source_window`, `overlay_root_id` (replacing the 8–22 copy-pasted variants in layer-x).
- [ ] `video_edit_core/timeline/model.py`: same treatment, smaller scale.
- [ ] Round-trip property test: load → save → byte-identical for normalized files.

### P3.3 Mutation store
- [ ] `video_edit_core/edit_plan/store.py`:
  - `load(project)` validates on read, warns on drift
  - `mutate(project, fn, *, note, dry_run=False)`: rotating backup to `output/reports/backups/edit_plan.<ts>.json` (keep ~20) → apply → schema + semantic validation → structured `revision_notes` append (script, note, timestamp, diff summary) → atomic write
  - `--dry-run` emits diff report without writing
- [ ] Gitignore the backups directory.

### P3.4 Migration + gates
- [ ] One-time migration script (project-local, `projects/layer-x-domain-expert/scripts/`): normalize `edit_plan.json` to v2 (timeline shape, continuation keys), emit migration report. Run with backup.
- [ ] `scripts/edit_plan_validate.py` + `validate-edit-plan` action in `workflow_actions.json`.
- [ ] Preview/final render entry points refuse to render an invalid plan.

### P3.5 Identity hygiene
- [ ] `video_edit_core/people.py`: `people_map.json` loading; `speaker_id` / `face_track_id` / `person_id` separation; placeholder rendering for unverified identities.
- [ ] Create `projects/layer-x-domain-expert/people_map.json` from the existing verified names; replace the ~6 hardcoded `PERSON_NAMES` dicts.

**Phase 3 exit:** layer-x `edit_plan.json` validates against v2; mutation store demonstrated end-to-end with backup + revision note; round-trip test green.

---

## Phase 4 — Project Tooling Kit

### P4.1 Shared ops (`video_edit_core/edit_plan/ops/`)
Each op = pure function `(EditPlan, params) -> (EditPlan, Report)`, run through the mutation store. Each gets unit tests + a golden run against a layer-x fixture reproducing one historical result.

- [ ] `ops/caption_timing.py` — align + audit (strategies: audio speech-window, keyword) — replaces 8+ layer-x scripts
- [ ] `ops/caption_layout.py` — split/merge/condense/normalize/dedupe/continuation (uses `captions/wrap.py`) — replaces 10+
- [ ] `ops/caption_source.py` — source-window/phrase trim + repair — replaces 6+
- [ ] `ops/cut_policy.py` — cut-boundary vs caption visibility — replaces 3
- [ ] `ops/layout.py` — speaker layout enforcement + audit — replaces 4+
- [ ] `ops/audio_policy.py` — single-audio-source policy + quality audits — replaces 4+
- [ ] `video_edit_core/render/edit_plan_preview.py` — consolidate `render_test_project1_style_preview.py` (~1,800 lines), `render_limited_preview.py`, `render_tail_preview.py`, `render_sync_review_grid.py` into one renderer with `--range`, `--tail`, `--grid`, segment-cache reuse

### P4.2 CLI
- [ ] `scripts/edit_plan_tool.py`: `align-captions`, `audit --all`, `layout`, `audio-policy`, `preview --range A B`, `reports prune`, `validate`. Audits exit non-zero on failure.
- [ ] Register app-relevant subcommands in `config/workflow_actions.json`.

### P4.3 Layer-x cleanup
- [ ] Migrate recurring-op scripts to thin calls into shared ops; delete where the CLI fully covers them.
- [ ] Move one-shot history (date-stamped `*_20260611.py` feedback scripts, named-person fixes, single-event surgery) to `projects/layer-x-domain-expert/scripts/archive/`; mark non-runnable in instructions; exclude from lint.
- [ ] Enforce caption SSOT: shared ops read `main_caption_plan.json` only as input, never write it (today ~15 scripts still write it). Document in the project `VIDEO_EDITING_INSTRUCTIONS.md`.
- [ ] Fix `project_state.json`: resolve the dangling `output/timelines/current.timeline.json` reference (bridge lands in Phase 5; until then point state at the edit-plan path).
- [ ] `edit_plan_tool reports prune`: keep canonical artifacts + latest N per report family; archive the rest of the ~132 report JSONs to `output/reports/archive/`; update `.gitignore` so archived reports are untracked.

### P4.4 Project template
- [ ] `init-project` action (template `VIDEO_EDITING_INSTRUCTIONS.md`, `scripts/`, `config/`, `source/`, `output/`, `project.json`, `project_state.json`); template instructions point to shared ops CLI first.

**Phase 4 exit:** layer-x active scripts ≤ bespoke set + archive; a fresh fixture project completes the full caption-QA loop using only shared tools.

---

## Phase 5 — Pipeline Unification

### P5.1 edit_plan → timeline bridge
- [ ] `video_edit_core/timeline/from_edit_plan.py`: compile validated `EditPlan` → `current.timeline.json` (`video-edit-timeline/v1`); add timeline schema extensions if needed for edit-plan features (layouts, overlay refs).
- [ ] Wire into `edit_plan_tool` (`compile-timeline`) and `workflow_actions.json`.
- [ ] Rework `render/edit_plan_preview.py` to consume the compiled timeline through `timeline_validate` → `render/ffmpeg_graph.py`; retire bespoke render code paths it no longer needs.

### P5.2 Converge `render_multicam`
- [ ] Gap analysis: features the timeline pipeline lacks (color matching, omission cards, music bed, audio-sync guards) → add as timeline schema fields + adapter support, one feature per PR.
- [ ] Convert the legacy config-driven entry to: build timeline → validate → render. Keep `render_app_interview.py` shim and all action names stable.
- [ ] Side-by-side verification: legacy vs unified on fixture + one real project; diff command reports; spot-check frames; preview-first per `AGENTS.md`.
- [ ] Delete the legacy direct-render path; update `check_architecture.py` rules.

### P5.3 Entry-point modernization
- [ ] Add `video_edit_core/cli.py` + console script (`video-edit`) as canonical invocation; `scripts/*.py` remain wrappers for the app contract.
- [ ] Drop the `scripts/video_edit_core/__init__.py` `__path__` shim once wrappers bootstrap imports explicitly (or the app spawns module form); update `check_architecture.py`.

**Phase 5 exit:** every workflow action runs the unified pipeline on the fixture project; one real project verified preview→final; legacy path deleted.

---

## Phase 6 — Hygiene, Docs, Observability (interleaved; close out at end)

### P6.1 Repo hygiene
- [ ] Fix `projects/engineer-type-demo-interview/project.json` (`"id": "new-folder-2"` + stale paths); note in the project docs that historical reports retain the old id.
- [ ] Remove or properly register `projects/st7_7550.mp4/`.
- [ ] Align `README.md` with `.gitignore` reality (project_state and output JSON **are** tracked).
- [ ] Move `AI_VIDEO_EDITING_BOOK2.md` → `docs/`.
- [ ] Tracked-artifact review: gitignore regenerable layer manifests (25k-line Remotion JSONs); keep canonical inputs.

### P6.2 Errors and logging
- [ ] `VideoEditError` hierarchy (`ConfigError`, `ValidationError`, `RenderError`) in core; CLI wrappers map to exit codes + structured error JSON.
- [ ] Eliminate silent `except (OSError, json.JSONDecodeError): return {}` config loads — fail loud with file path.
- [ ] Logging adoption sweep for any scripts not touched by Phases 1–4.

### P6.3 Portability
- [ ] Sweep remaining hardcoded Windows paths (fonts, tool defaults, layer-x venv paths) into config with documented defaults.

### P6.4 Docs
- [ ] Update `AGENTS.md` + `docs/video_edit_method.md`: unified pipeline, ops CLI, mutation/backup contract, project template.
- [ ] Layer-x: reconcile `VIDEO_EDITING_INSTRUCTIONS.md` with `Edit Instruction.md`; document archive + SSOT policy.
- [ ] Module docstrings across `video_edit_core/`; flip `mypy` to blocking for `video_edit_core/`.

---

## Tracking

| Phase | Items | Done | Status |
|---|---:|---:|---|
| 0 — Safety net | 16 | 0 | not started |
| 1 — Dedupe | 18 | 0 | not started |
| 2 — God scripts | 24 | 0 | not started |
| 3 — Data model | 14 | 0 | not started |
| 4 — Project tooling | 14 | 0 | not started |
| 5 — Unification | 9 | 0 | not started |
| 6 — Hygiene/docs | 12 | 0 | not started |

### Standing rules (every PR)
1. `python scripts/check_architecture.py` green.
2. `pytest` green (goldens unchanged unless the change intentionally alters behavior, with the golden update reviewed explicitly).
3. App action surface (`config/workflow_actions.json` + script names) unbroken.
4. Strangler pattern: old code deleted only after the last caller migrates.
5. No new copy-pasted scaffolding in project scripts once Phase 1 lands.
