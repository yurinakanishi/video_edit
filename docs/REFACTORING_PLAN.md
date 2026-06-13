# Phased Refactoring Plan

Scope: shared Python code (`video_edit_core/`, `scripts/`), project workspaces (focus: `projects/layer-x-domain-expert/`), and repo infrastructure.
Out of scope: the Electron/Next.js app under `app/` (only its Python invocation contract is treated as a frozen interface).

Date: 2026-06-12. Based on a full audit of the codebase.

---

## 1. Current-State Diagnosis (what the debt actually is)

### Quantified baseline

| Metric | Value |
|---|---|
| Python files | 151 (~20k+ LOC) |
| `video_edit_core/` (the "reusable" layer) | 11 files, ~1.6k LOC |
| Business logic stranded in `scripts/` | ~10k+ LOC (top offender: `render_multicam.py`, 3,747 lines) |
| Project-local scripts in `layer-x-domain-expert` | 84 (57 with copy-pasted JSON I/O, 41 mutating `edit_plan.json` in place, 0 with backups) |
| Project scripts importing `video_edit_core` | 1 of 84 |
| Tests / CI | 0 / 0 |
| Dependency manifests | 1 partial file (3 pinned packages); core deps (Pillow, numpy, cv2, whisper) implicit |
| `import logging` | 0 (everything is `print()`) |
| Formal schemas | 1 (`config/timeline.schema.json`); `edit_plan.json`, person plans, overlay manifests are convention-only |

### Root causes (in priority order)

1. **No safety net.** Zero tests, zero CI, no dependency manifest, no linter. Every refactor today is a blind refactor. This is why debt accumulates: nothing can be safely changed, so everything is added alongside.
2. **The core/scripts inversion.** `video_edit_core/` is 1.6k lines while `scripts/` holds 10k+ lines of domain logic (`render_multicam.py` 3,747, `build_edit_timeline.py` 1,000, `ffmpeg_timeline_adapter.py` 992, `timeline_graphics_adapter.py` 818, `analyze_person_bboxes.py` 803, …). The intended architecture (core = library, scripts = thin CLI) exists only for 7 compat shims.
3. **Systematic duplication in shared scripts.** `media_manifest()` ×8, `bool_value()` ×10+, FFmpeg path resolution ×13, ~150 lines of person-edit-plan logic duplicated between `build_edit_timeline.py` and `render_multicam.py`, Japanese line-break rules ×3, `clamp`/`now_iso`/`as_float`/`canonical_path_key` re-defined per script (one defined twice *within* `render_multicam.py`).
4. **Two parallel render architectures.** Legacy config-driven monolith (`render_multicam.py`) vs the timeline pipeline (`build_edit_timeline.py` → `timeline_validate` → `ffmpeg_timeline_adapter.py`/`timeline_graphics_adapter.py`). They duplicate segment/crop/person logic and drift independently.
5. **The one-off-script explosion in projects.** `layer-x-domain-expert` accumulated 84 scripts that are ~80% copy-pasted scaffolding (root resolution ×3 naming variants, `read_json`/`write_json` ×57, `event_duration()` ×22, `srt_time_to_seconds()` ×8) around small bits of unique editorial logic. The recurring operations (caption timing alignment, overlay split/merge, source-window trim, layout enforcement, audio policy, preview rendering) are clearly generalizable but were never promoted.
6. **Untyped, drifting data model.** `edit_plan.json` is the key artifact per `AGENTS.md`, yet it has no shared schema, no typed accessors, and observable drift: timeline-as-array vs `{events: []}` handled three different ways; three competing metadata keys for the same caption-continuation concept; per-script differences in source-window resolution priority. 41 scripts mutate it in place with no backup and only ad-hoc `revision_notes` appends.
7. **Hygiene and observability gaps.** No logging; inconsistent error handling (`SystemExit` vs `RuntimeError` vs silent `except: return {}`); hardcoded Windows paths (font `C:\Windows\Fonts\YuGothB.ttc`, choco FFmpeg default, venv paths); stale metadata (`engineer-type-demo-interview/project.json` still says `new-folder-2`; `project_state.json` in layer-x points at a nonexistent `current.timeline.json`); stub project `projects/st7_7550.mp4/`; 132 report JSONs with no retention policy; README contradicts `.gitignore`.

### Guiding principles for the refactor

- **Behavior-preserving first.** Phases 0–2 must not change any rendered output or JSON artifact byte-for-byte (except where a bug is documented and approved).
- **The app contract is frozen.** `config/workflow_actions.json`, `video_edit_run.py --action …` CLI, and script names invoked by the Electron app keep working at every phase boundary. `check_architecture.py` must pass at every commit.
- **Strangler pattern, not big-bang.** New core modules are added, call sites migrate incrementally, old copies are deleted only when the last caller moves.
- **One phase = one mergeable theme.** Each phase has explicit exit criteria and can pause indefinitely without leaving the repo in a half-state.
- **Don't gold-plate.** No plugin systems, no ORM-style abstraction over JSON, no speculative multi-renderer framework. Promote only operations that have already recurred ≥3 times.

---

## 2. Phase 0 — Safety Net (foundations before any code moves)

**Goal:** make refactoring verifiable. No production code changes.

### 0.1 Packaging and dependencies
- Add root `pyproject.toml` defining the `video_edit_core` package (setuptools or hatchling), with:
  - core deps: `Pillow`, `numpy`
  - extras: `analysis` (`opencv-python`, `ultralytics`, `mediapipe`, `easyocr`), `transcribe` (`openai-whisper`, `faster-whisper`)
  - pinned Python version (match the running interpreter; runtime evidence says 3.14, confirm before pinning)
- Fold `reference-assets/config/requirements.analysis.txt` pins into the extras; keep the file as a pointer or delete it.
- Keep the `scripts/video_edit_core/__init__.py` import shim for now (it is load-bearing for `python scripts/foo.py` invocation and enforced by `check_architecture.py`); revisit in Phase 5.

### 0.2 Lint and type checking
- Add `ruff` config (start permissive: pyflakes + isort + obvious correctness rules; no style churn yet). Wire into root `package.json` next to `arch:check` (e.g. `lint:py`).
- Add `mypy` (or pyright) in **non-blocking** mode scoped to `video_edit_core/` only. Type-hint coverage is already ~91% — exploit it.
- Run `ruff --fix` once for unused imports only (the audits found bulk unused `video_edit_core.paths` imports across ~12 scripts). This is the only Phase 0 code touch.

### 0.3 Test harness + characterization tests
- Add `pytest` with a `tests/` tree:
  - `tests/unit/` — start with the already-pure modules: `video_edit_core/composition.py` (anchors, crop targets, bbox scoring), `timeline/validation.py` (schema + semantic checks against fixture timelines), `transcription_quality.py` (SRT formatting, confidence filtering), caption wrap rules.
  - `tests/golden/` — **characterization tests that freeze current behavior**:
    - `build_edit_timeline.py` on a synthetic fixture project → golden `current.timeline.json`
    - `ffmpeg_timeline_adapter.py` on a fixture timeline → golden FFmpeg command/filtergraph JSON (compare the command report, don't run FFmpeg)
    - `timeline_graphics_adapter.py` → golden layer manifests
    - `timeline_validate` → golden pass/fail outcomes for valid/invalid fixtures
  - Fixture projects live under `projects/__smoke__/refactor-golden/<run-id>/…` per the documented test-workspace convention (and fix `projects/__smoke__/` to actually follow that documented shape — today it holds one stray artifact at the wrong level).
- Tests must not require GPU, Whisper models, or real media: use tiny generated WAV/MP4 fixtures (ffmpeg `testsrc`/`sine`) created by a fixture-builder script, or pure-JSON fixtures where possible.
- Mark anything needing real FFmpeg with `@pytest.mark.ffmpeg` so the suite degrades gracefully.

### 0.4 CI
- Add a minimal GitHub Actions workflow (or local pre-commit equivalent if CI is not desired): `ruff` + `pytest tests/unit tests/golden` + `python scripts/check_architecture.py`.

**Exit criteria:** `pip install -e .` works; `pytest` green; golden outputs committed; `arch:check` green; CI (or documented local gate) runs all three.

**Risk:** golden tests can be brittle against timestamps/abs paths. Mitigate by normalizing (`generated_at`, absolute paths) before comparison — add a small comparator helper in `tests/`.

---

## 3. Phase 1 — Deduplicate the Shared Layer (mechanical extraction)

**Goal:** every helper that exists ≥2 times in `scripts/` exists exactly once in `video_edit_core/`. Behavior-preserving; golden tests must stay green.

### 1.1 New core modules

| New module | Absorbs | Today duplicated in |
|---|---|---|
| `video_edit_core/config.py` | `nested()`, `bool_value()`/`bool_config`, `int_config`, `optional_path`, media-manifest loading (`media_manifest()`, `manifest_camera_paths()`) | `app_config.py` + `transcription_quality.py` + 10+ scripts |
| `video_edit_core/tools.py` | FFmpeg/ffprobe path resolution (config → env → PATH; kill the `C:\ProgramData\chocolatey\...` literal default), `run_text()`, `probe_duration()`, common subprocess wrappers | 13 scripts + `audio/silence.py` + `replace_video_audio.py` |
| `video_edit_core/jsonio.py` | `load_json`/`write_json` with consistent encoding/indent/trailing-newline, plus a normalized-report writer (`schema_version`, `generated_at`) | 5+ shared scripts, 57 project scripts (migrated in Phase 4) |
| `video_edit_core/timeutil.py` | `now_iso()`, SRT time parse/format, `HH:MM:SS.xx` conversions, ms helpers — one canonical seconds-based API with explicit converters at boundaries | `build_edit_timeline.py`, `ffmpeg_timeline_adapter.py`, `timeline_changed_regions.py`, `transcription_quality.py`, `app_config.py` |
| `video_edit_core/geometry.py` | `clamp()`, `as_float()`, normalized-coordinate helpers, path-key normalization (`canonical_path_key`/`normalized_path_key` — pick one) | `composition.py`, `build_edit_timeline.py`, `render_multicam.py` (×2 internally), `auto_sync_app_sources.py` |
| `video_edit_core/logging.py` | thin stdlib-logging setup: human logs → stderr, machine-readable result JSON → stdout (preserves the app's stdout-parsing contract) | replaces ad-hoc `print` patterns incrementally |

### 1.2 Consolidate existing core
- `paths.py`: remove its private duplicate of app-config loading; depend on `app_config.load_app_config()`.
- `app_config.py`: after `config.py` extraction it should shrink to app-config load/fingerprint only (currently a 298-line junk drawer including punchline text parsing — move that to graphics/captions in Phase 2).
- Strip CLI `main()` out of `timeline/validation.py` and `audio/silence.py` into their existing `scripts/` wrappers (`timeline_validate.py`, `shorten_silences.py`) so core is import-only.
- Replace the hardcoded font path in `graphics/subtitle_png.py` with config + sensible default chain.

### 1.3 Migrate call sites
- Update all ~43 shared scripts to import from the new modules; delete local copies as each migrates. Use `ruff` to verify no orphaned helpers remain.
- Fix the fragile cross-script imports: `transcribe_manifest_sources_faster.py` importing from `transcribe_manifest_sources`, and `analyze_person_bboxes.py`/`classify_subtitle_speakers.py` importing `face_mesh_metrics` — move the shared parts (`choose_primary`, `manifest_sources`, face-mesh helpers) into core (`video_edit_core/analysis/face_mesh.py`, `video_edit_core/transcription/manifest.py`).
- Delete confirmed dead code: `video_edit_run.py` unused helpers (`add_audio_args`, `add_silence_args`, `selected_mode`); decide fate of orphaned `retime_subtitles_readable.py` (332 lines, zero references — archive or register as an action, don't keep limbo).

**Exit criteria:** zero duplicate helper definitions across `scripts/` (verified by a small AST-grep check added to `check_architecture.py`); golden + unit tests green; `arch:check` green.

**Effort:** small-to-medium, highly mechanical. Do it as many small PRs (one module + its call-site migration each).

---

## 4. Phase 2 — Break Up the God Scripts (logic moves into core)

**Goal:** invert the core/scripts ratio. Every `scripts/*.py` becomes a CLI wrapper (arg parsing + orchestration only, target ≤150 lines); domain logic lives in cohesive, unit-testable core modules.

### 2.1 Target core layout

```
video_edit_core/
  config.py, tools.py, jsonio.py, timeutil.py, geometry.py, logging.py   # Phase 1
  composition.py                      # existing, unchanged
  timeline/
    model.py          # typed accessors (Phase 3 expands)
    validation.py
    build.py          # from build_edit_timeline.py (~950 lines of logic)
    changed_regions.py# from timeline_changed_regions.py
  render/
    ffmpeg_graph.py   # from ffmpeg_timeline_adapter.py filtergraph assembly
    graphics_layers.py# from timeline_graphics_adapter.py (remotion/blender exports)
    otio.py           # from timeline_otio_adapter.py
    multicam/         # decomposed render_multicam.py — see 2.2
  captions/
    wrap.py           # JP line-break rules (3 copies today) + layer-x caption_wrap_rules.py
    overlays.py       # PNG overlay manifest generation (generate_full_transcript_png_overlays.py, punchline, chapter/title)
    ass.py            # generate_role_aware_ass.py logic
    srt.py            # SRT read/write/retime (incl. retime_subtitles_readable.py if kept)
  transcription/
    manifest.py, whisper_runner.py, faster_whisper_runner.py, quality.py (existing), compare.py
  analysis/
    person_bboxes.py  # from analyze_person_bboxes.py (YOLO+tracking)
    face_mesh.py      # from scripts/face_mesh_metrics.py
    person_edit_plan.py # from build_person_edit_plan.py + the ~150-line block duplicated between build_edit_timeline.py and render_multicam.py
    speaker_audio.py  # classify_speakers_audio_features.py
    speaker_visual.py # classify_subtitle_speakers.py
    blocking.py       # analyze_multicam_blocking.py
    sync.py           # auto_sync_app_sources.py (cross-correlation) + clap-sync concepts
  audio/silence.py    # existing
  graphics/subtitle_png.py, thumbnails.py
```

### 2.2 `render_multicam.py` decomposition (the 3,747-line centerpiece)

Treat as its own sub-project, done in slices, each behind golden render-command tests:

1. **Freeze behavior:** extend golden tests to cover `render_multicam.py`'s *planning* outputs (segment plan, color filters, overlay manifest, final FFmpeg command report) on a fixture project — before touching it.
2. Extract in dependency order, deleting from the script as each lands:
   - manifest/source resolution → `config.py` (done in Phase 1)
   - `frame_visual_stats()` (~185 lines) + `camera_color_match_filters()` (~183 lines) → `render/multicam/color.py`
   - segment planning, `constrain_segments_to_source_coverage()` (~200), `guard_segments_by_external_audio_sync()` (~180) → `render/multicam/segments.py`
   - person-plan/crop logic (the block duplicated with `build_edit_timeline.py`, incl. `face_center_subject_screen_x`, `adjusted_face_center_crop_x`) → `analysis/person_edit_plan.py` — **one implementation, two consumers**
   - overlay orchestration (its calls into `generate_title_png_overlay.py`, `generate_chapter_title_png_overlays.py`, omission cards) → `captions/overlays.py` as function calls instead of subprocess hops
   - FFmpeg command assembly → `render/multicam/command.py`
   - the ~577-line `main()` → a ~100-line pipeline function + CLI shim
3. `render_app_interview.py` stays a ≤12-line shim (enforced by `check_architecture.py`).

### 2.3 Dispatcher cleanup
- `video_edit_run.py`: replace the hardcoded `command_for_action()`/`commands_for_action()` if/elif chains (~25 special cases, with ~60 near-duplicated lines across remotion/blender permutations) with a declarative action table: `action -> [stage specs]`, parameterized by overlay backend. Keep `config/workflow_actions.json` as the single manifest; the Python table only describes composition of stages.

**Exit criteria:** no file in `scripts/` >300 lines; `video_edit_core/` carries the logic with unit tests on extracted modules (color matching, segment constraints, caption wrapping at minimum); golden renders unchanged; app workflow actions verified via the existing Electron smoke entry or a CLI dry-run of every action in `workflow_actions.json`.

**Effort:** the largest phase. Sequence: adapters (`ffmpeg_timeline_adapter`, `timeline_graphics_adapter`) → analysis scripts → captions/overlays → `render_multicam.py` slices → dispatcher.

---

## 5. Phase 3 — Formalize the Data Model (schemas, typed access, safe mutation)

**Goal:** end "dict soup". Every artifact that crosses a script boundary has a schema; the key artifacts have typed accessors; mutations are validated, backed up, and auditable.

### 3.1 Schemas (JSON Schema files under `config/schemas/`)
- Promote `edit_plan.json` to a first-class shared schema (`edit_plan.schema.json`, version `edit_plan/v2`). `AGENTS.md` names it the key artifact, yet today it exists only as a layer-x convention. The schema must resolve the observed drift **by decree**:
  - `timeline` is an array of events. Full stop. (Kill the `{events: []}` legacy form; migrate the 3 layer-x scripts that still write it.)
  - one canonical continuation key (`caption_continuation_root_id`), one canonical source-window resolution order (`audio_alignment.source_window_sec` → `metadata.source_start_sec` → parsed `source_timecode`) — documented in the schema description and implemented once in core.
  - seconds everywhere; event-local vs absolute clocks explicitly named (`start`/`end` event-local; `*_abs_sec` absolute) per the existing convention.
- Add schemas for the other unschema'd artifacts: `person_edit_plan`, subtitle overlay layout (`video-edit-subtitle-layout/v1` — currently checked by a single inline `if`), graphics layer manifests, sync offsets report.
- Replace the hand-rolled JSON Schema engine in `timeline/validation.py` with the `jsonschema` package (keep the semantic checks — overlap, source refs, durations — as Python; that's the valuable part).

### 3.2 Typed model layer
- `video_edit_core/edit_plan/model.py`: lightweight dataclasses (`EditPlan`, `TimelineEvent`, `CaptionOverlay`, `SourceRange`, `AudioAlignment`) with `from_dict`/`to_dict` that tolerate unknown keys (forward-compat) but normalize the known ones. Not an ORM — just typed access plus the canonical helpers (`event_duration`, `ref_window`, `caption_source_window`, `overlay_root_id`) that are currently copy-pasted in 12–22 project scripts each with subtle differences.
- Same treatment, smaller scale, for timeline JSON (`timeline/model.py`).

### 3.3 Safe mutation API
- `video_edit_core/edit_plan/store.py`:
  - `load(project) -> EditPlan` (validates on read, warns on drift)
  - `mutate(project, fn, *, note, dry_run=False)` — context that: snapshots to `output/reports/backups/edit_plan.<ts>.json` (rotating, e.g. keep 20), applies, validates against schema + semantic checks, appends a structured `revision_notes` entry (script name, note, timestamp, diff summary), writes atomically (temp + rename), and supports `--dry-run` to emit the diff report without writing.
  - This replaces today's pattern: 41 scripts writing `edit_plan.json` in place with zero backups.
- Validation gate: `validate_edit_plan` becomes a shared action (`scripts/edit_plan_validate.py` + `video_edit_run.py` action), and the preview-render entry points refuse to render an invalid plan (matching the `AGENTS.md` validate-before-render requirement, which is currently aspirational).

### 3.4 Identity hygiene
- Add `people_map.json` support in core (`video_edit_core/people.py`): `speaker_id`/`face_track_id`/`person_id` separation per `AGENTS.md`. Replace the hardcoded `PERSON_NAMES` dicts found in ~6 layer-x scripts; unverified identities render as placeholders.

**Exit criteria:** `edit_plan.json` for layer-x validates against the new schema (after a one-time migration script with a report); all mutations in newly-written code go through the store; backup + revision-note trail demonstrated; round-trip property test (load → save → byte-identical for normalized files).

**Risk:** schema-by-decree can break old scripts. Mitigation: the 84 layer-x scripts are mostly one-shot history (see Phase 4) — only the recurring operations get migrated; the rest are archived, not fixed.

---

## 6. Phase 4 — Project Tooling Kit (tame the one-off-script explosion)

**Goal:** the next project does **not** generate 84 scripts. Recurring editorial operations become parameterized shared tools; project dirs keep only genuinely bespoke logic.

### 4.1 Promote the recurring operation families
From the layer-x audit, these recur enough (≥3 similar scripts each) to justify promotion into `video_edit_core/edit_plan/ops/` + a project-facing CLI:

| Op family | Layer-x evidence | Shared tool |
|---|---|---|
| Caption ↔ audio timing alignment + audit | 8+ scripts (`align_caption_timing_to_audio`, `audit_caption_audio_timing`, keyword variants…) | `ops/caption_timing.py` (align, audit; keyword/speech-window strategies as parameters) |
| Overlay split/merge/condense/normalize | 10+ scripts (`split_long_caption_overlays…`, `condense…two_line_units`, `normalize…two_lines`, dedupe, continuation) | `ops/caption_layout.py` (uses `captions/wrap.py`) |
| Source-window / phrase trim & repair | 6+ scripts | `ops/caption_source.py` |
| Cut-boundary vs caption visibility policy | 3 scripts | `ops/cut_policy.py` |
| Speaker layout enforcement + audit | 4+ scripts | `ops/layout.py` |
| Audio source policy + audits | 4+ scripts | `ops/audio_policy.py` |
| Edit-plan preview rendering | 4 render entry points incl. the 1,800-line `render_test_project1_style_preview.py` | `video_edit_core/render/edit_plan_preview.py` + one CLI with `--range`, `--tail`, `--grid`, segment-cache reuse |

Each op = pure function `(EditPlan, params) -> (EditPlan, Report)`, executed through the Phase 3 mutation store (giving every operation dry-run, backup, validation, and audit trail for free).

### 4.2 Project CLI
- `scripts/edit_plan_tool.py` (registered in `workflow_actions.json` where app-relevant): `edit_plan_tool align-captions --strategy audio …`, `edit_plan_tool audit --all`, `edit_plan_tool preview --range 60 120`, etc. Audits exit non-zero on failure so they compose into gates.

### 4.3 Layer-x cleanup
- Migrate the recurring-op scripts to thin calls into the shared ops (or delete where the CLI fully covers them).
- Move genuinely one-shot history (date-stamped feedback scripts, named-person fixes, single-event surgery like `fix_first_digest_start_to_speech.py`) to `projects/layer-x-domain-expert/scripts/archive/` — keep for provenance, mark non-runnable in the project instructions.
- Resolve the caption SSOT drift: per the project's own declared policy, `main_caption_plan.json` is a demoted cache, yet ~15 scripts still write it. The shared ops read it only as input and never write it; document this in `VIDEO_EDITING_INSTRUCTIONS.md`.
- Fix stale state: `project_state.json` points at a nonexistent `output/timelines/current.timeline.json`; either generate it from `edit_plan.json` via a bridge (see Phase 5) or update the state to the edit-plan path.
- Report retention: add `edit_plan_tool reports prune` — keep canonical artifacts (`edit_plan.json`, `transcript.json`, `semantic_marks.json`, attribution/sync inputs) + latest N per report family, archive the rest of the ~132 JSONs to `output/reports/archive/`. Update `.gitignore` so archived reports aren't tracked.

### 4.4 Project template
- `scripts/video_edit_run.py --action init-project` (or a small `scripts/init_project.py`): scaffolds the documented shape (`VIDEO_EDITING_INSTRUCTIONS.md` from template, `scripts/`, `config/`, `source/`, `output/`, `project.json`, `project_state.json`) so future projects start consistent. Template instructions point to the shared ops CLI first, project-local scripts second.

**Exit criteria:** each promoted op has unit tests + a golden run against a layer-x fixture reproducing a historical result; layer-x `scripts/` shrinks to bespoke + archive; a new fixture project can run the full caption-QA loop using only shared tools.

---

## 7. Phase 5 — Pipeline Unification (one render architecture)

**Goal:** eliminate the dual-pipeline split and the edit-plan/timeline gap. One canonical flow: **analysis → semantic → `edit_plan.json` → `current.timeline.json` → validated render**, exactly as `AGENTS.md` prescribes but the code never implemented end-to-end.

### 5.1 Bridge edit_plan → timeline
- `video_edit_core/timeline/from_edit_plan.py`: compile a validated `EditPlan` into `current.timeline.json` (schema `video-edit-timeline/v1`). This closes the current rift where the app pipeline expects a timeline the Codex workflow never produces.
- Project preview/final renders then go through the existing validated path: `timeline_validate` → `ffmpeg_timeline_adapter` (and graphics adapters for overlays). The layer-x bespoke renderer (`render_test_project1_style_preview.py` logic, by then living in `render/edit_plan_preview.py`) is reworked to consume the compiled timeline, or retired if the shared adapter covers its features.

### 5.2 Converge or retire `render_multicam.py`
- After Phase 2, `render_multicam` is a set of core modules + a thin CLI. Decide per feature: capabilities the timeline pipeline lacks (color matching, omission cards, music bed, audio-sync guards) are exposed as timeline-pipeline features (timeline schema additions + adapter support); then the legacy config-driven entry becomes a compatibility wrapper that *builds a timeline and renders it*.
- Keep `render_app_interview.py` shim and the workflow action names stable for the app; only the implementation route changes. Update `check_architecture.py` rules as the internals move (it currently hardcodes the wrapper list and core file inventory).
- Only after the app actions are verified on the unified path: delete the legacy direct-render code path.

### 5.3 Entry-point modernization
- Make `python -m video_edit_core.cli …` (or installed console script `video-edit`) the canonical invocation; keep `scripts/*.py` as wrappers for the app contract. The `scripts/video_edit_core/__init__.py` `__path__` shim can then be dropped once the app spawns either the module form or wrappers that bootstrap `sys.path` explicitly — coordinate with (but don't modify logic in) the app's spawn code, and update `check_architecture.py` accordingly.

**Exit criteria:** every workflow action in `config/workflow_actions.json` runs through the unified pipeline on a fixture project; preview-first then final render verified on one real project; legacy path deleted; `arch:check` updated and green.

**Risk:** highest-risk phase (rendered output may shift). Mitigate with side-by-side renders (legacy vs unified) on fixture + one real project, diffing command reports and spot-checking frames before cutover. This phase is deliberately last and can be deferred without diminishing Phases 0–4 value.

---

## 8. Phase 6 — Hygiene, Docs, Observability (continuous, finish-line sweep)

Items here are low-risk and can be interleaved from Phase 1 onward; the phase exists to ensure they finish.

### 6.1 Repo hygiene
- Fix `projects/engineer-type-demo-interview/project.json` (`"id": "new-folder-2"` and stale `projects/new-folder-2/` paths); decide whether the hundreds of historical reports referencing the old id are rewritten (probably not — note it in the project README) .
- Remove or properly register the stub `projects/st7_7550.mp4/`.
- Restructure `projects/__smoke__/` to the documented `<test-name>/<run-id>/` shape (done with Phase 0 fixtures).
- Align `README.md` with reality (`.gitignore` *does* track `project_state.json` and output JSON); move `AI_VIDEO_EDITING_BOOK2.md` under `docs/`.
- Review what's tracked: the very large committed JSONs (25k-line Remotion layer manifests, 24k-line attribution files) — keep canonical inputs, gitignore regenerable layer manifests.

### 6.2 Observability and errors
- Adopt the Phase 1 `logging.py` everywhere as call sites get touched: logs → stderr with levels, final machine-readable result → stdout (preserves app parsing). No separate "logging migration" pass — it rides along with Phases 1–4 edits.
- Standardize errors: `VideoEditError` hierarchy in core (`ConfigError`, `ValidationError`, `RenderError`); CLI wrappers map them to exit codes + a structured error JSON. Eliminate the silent `except (OSError, json.JSONDecodeError): return {}` config loads — fail loud with the file path.

### 6.3 Configuration and portability
- Sweep remaining hardcoded Windows paths (fonts, tool defaults, venv paths in layer-x transcription scripts) into config with documented defaults.
- Document Python setup in `README.md`: interpreter version, `pip install -e .[analysis,transcribe]`, FFmpeg expectation, GPU/whisper venv notes.

### 6.4 Docs
- Update `AGENTS.md` + `docs/video_edit_method.md` to reflect the unified pipeline, the edit-plan ops CLI, the mutation/backup contract, and the project template.
- Per-project `VIDEO_EDITING_INSTRUCTIONS.md` for layer-x: reconcile with `Edit Instruction.md` (two overlapping instruction files today), document the archive policy and SSOT rules.
- Add module docstrings to all `video_edit_core` modules (currently package-level only).

**Exit criteria:** lint/type gates blocking for `video_edit_core/`; no hardcoded machine paths outside config; docs match behavior; metrics table below achieved.

---

## 9. Sequencing, Effort, and Success Metrics

### Order and rationale

```
Phase 0 (safety net)          ── prerequisite for everything
Phase 1 (dedupe shared)       ── mechanical, builds the core toolbox
Phase 2 (god scripts → core)  ── biggest chunk; depends on 1
Phase 3 (data model)          ── depends on 1; can overlap late Phase 2
Phase 4 (project tooling)     ── depends on 3 (ops use the typed model + store)
Phase 5 (pipeline unification)── depends on 2+3+4; highest risk, last
Phase 6 (hygiene/docs)        ── interleaved; closed out at the end
```

### Rough effort (sized for one developer + AI assistance)

| Phase | Size | Natural PR count |
|---|---|---|
| 0 | S–M (1–3 days) | 3–4 |
| 1 | M (2–4 days) | 6–8 small PRs |
| 2 | L (1.5–3 weeks) | 12–20 slices |
| 3 | M–L (1–2 weeks) | 5–8 |
| 4 | M–L (1–2 weeks) | 8–12 |
| 5 | L (1–2 weeks + verification renders) | 5–8 |
| 6 | S spread out | ongoing |

### Success metrics (before → after)

| Metric | Now | Target |
|---|---|---|
| Tests / CI | 0 / none | unit + golden suite, gate on every PR |
| Largest file in `scripts/` | 3,747 lines | ≤300 lines (CLI wrappers only) |
| `video_edit_core` share of shared-code LOC | ~14% | ≥85% |
| Duplicate helper definitions across `scripts/` | dozens | 0 (enforced by arch check) |
| Project scripts using shared core (layer-x model) | 1/84 | all active scripts; one-shots archived |
| `edit_plan.json` mutations with backup + validation | 0/41 scripts | 100% via mutation store |
| Formal schemas | 1 | timeline, edit_plan, person_edit_plan, overlay layouts, graphics layers |
| Render architectures | 2 divergent | 1 unified (+ thin compat wrapper) |
| Dependency manifest | 1 partial file | `pyproject.toml` with extras, pinned Python |
| New-project scaffold | manual, inconsistent | `init-project` template |

### Standing rules during the refactor

1. `python scripts/check_architecture.py` and the test suite pass on every commit.
2. The app's action surface (`config/workflow_actions.json` + script names) never breaks mid-phase.
3. Preview-first rendering discipline applies to all verification renders (per `AGENTS.md`).
4. No new one-off script may copy-paste `read_json`/root-resolution boilerplate once Phase 1 lands — project scripts import from core.
5. Every deletion of legacy code happens only after its golden test moves to the replacement.
