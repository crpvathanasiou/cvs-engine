# CVS Experiment Engine — Code Map

Semantic map of the repository after Milestone 0 / 0.3 documentation alignment. Status labels:

| Status | Meaning |
| --- | --- |
| implemented scaffold | Exists and is usable as structure / tooling |
| placeholder | Directory or package present; no real logic yet |
| deferred | Intentionally not started |
| proposed | Documented intent; not created or not authorized yet |
| future milestone | Planned under a later roadmap item |

---

## Package and application areas

### `src/cvs_engine/`

**Status:** implemented scaffold

Main Python package. Imports as `cvs_engine`. Currently version metadata and empty subpackages only.

### `src/cvs_engine/datasets/`

**Status:** placeholder → **proposed S1.1+**

Future dataset / case / split loaders for the Stage 1 data contract. No loader classes yet. Small synthetic fixtures may appear later for tests; they are not the primary research dataset.

### `src/cvs_engine/models/`

**Status:** placeholder → **proposed S1.2 / S1.3+**

Future encoder wrappers, aggregation modules, and prediction heads. No model code yet. Stage 1 keeps the visual encoder frozen; Stage 2 fine-tunes it.

### `src/cvs_engine/tasks/`

**Status:** placeholder → **proposed S1.3+ / Stage 2**

Future task definitions (for example total-score vs criterion-level formulations). Deferred.

### `src/cvs_engine/training/`

**Status:** placeholder → **proposed S1.3+ / Stage 2**

Future training modules and train entrypoints (Stage 1 head/aggregation training; later Stage 2 fine-tuning). Deferred.

### `src/cvs_engine/evaluation/`

**Status:** placeholder → **proposed S1.4+**

Future metrics, predictions export, and report helpers. Deferred.

### `src/cvs_engine/utils/`

**Status:** placeholder → **future milestone**

Future shared helpers (seeds, IO, path utilities). Deferred beyond empty package init.

### `src/cvs_engine/stages/` (proposed)

**Status:** proposed — **do not create in Milestone 0.3**

Thin future orchestration layer for independently executable Stage 1 and Stage 2 entrypoints, reusing the shared packages above. Not present in the repository yet.

---

## Config, tests, UI, docs, rules, scripts

### `configs/`

**Status:** placeholder → **proposed S1.1+ Hydra discipline**

Folders present: `experiment/`, `dataset/`, `model/`, `task/`, `training/` (typically `.gitkeep` only). Real Hydra configs deferred until Stage 1 data/training milestones.

### `tests/`

**Status:** implemented scaffold (import smoke) → expands in Stage 1 milestones

Current: import/smoke tests for package availability. Future: data contract, cache, aggregation/training smoke, metrics/export, and handoff checks. Functionality milestones must add meaningful tests for introduced behavior.

### `ui/app.py`

**Status:** implemented scaffold (Milestone 0) → **optional later extension**

Minimal Streamlit visibility shell: project identity, milestone status, commands, future artifact locations, import check. No inference, upload, or medical predictions. Both stages must eventually support CLI execution without Streamlit.

### `.ai/`

**Status:** implemented scaffold

- Long-lived canonical docs (`00–09`): reference, roadmap, standards, handoff, code map
- Operational logs (`90–99`): current milestone, implementation report, review, corrections

### `.cursor/rules/cvs-engine.mdc`

**Status:** implemented scaffold (Milestone 0.3)

Cursor project rule with YAML frontmatter (`alwaysApply: true`): no clinical claims, two-stage architecture, frozen-encoder Stage 1 definition, milestone-bounded work, implemented-vs-planned separation, Poetry, Linux/DGX-ready, verification and reporting expectations. References canonical `.ai/` documents.

### `scripts/`

**Status:** implemented scaffold

Helper PowerShell scripts for test/lint/typecheck/format/quality. Prefer `poetry run python -m pytest` for tests on Windows.

---

## Expected later artifact roots (not required yet)

| Path | Status | Purpose |
| --- | --- | --- |
| `outputs/<experiment_id>/stage1/` | proposed | Stage 1 checkpoints, predictions, metrics, report, config snapshot |
| `outputs/<experiment_id>/stage2/` | proposed | Stage 2 counterparts |
| Shared dataset / feature-cache roots | proposed | May live outside experiment dirs; referenced by stable identifiers |
| `checkpoints/` | deferred / may nest under stage outputs | Saved weights (layout may evolve with stage dirs) |
| `reports/` | deferred / may nest under stage outputs | Evaluation reports |
| `mlruns/` | deferred (optional later) | Local MLflow tracking |

---

## Quick orientation for agents

1. Change package logic under `src/cvs_engine/` only when the approved milestone requires it.
2. Put experiment knobs under `configs/` when introducing runnable experiments.
3. Keep UI changes limited to visibility unless a UI milestone is approved.
4. Do not create `src/cvs_engine/stages/` until authorized.
5. Update `.ai/91_implementation_report.md` after implementation work.
6. Consult `.ai/01_implementation_roadmap.md` / `.ai/90_current_milestone.md` for what comes next — do not implement ahead.
