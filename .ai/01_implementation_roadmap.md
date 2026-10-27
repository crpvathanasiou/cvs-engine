# CVS Experiment Engine — Implementation Roadmap

Concrete roadmap for Cursor. Implement **only** the approved milestone.

Historical Milestone 0 / 0.1 / 0.2 evidence remains in `.ai/91_implementation_report.md` and `.ai/92_review_report.md`. The active forward roadmap is the **Stage 1** sequence below. Small synthetic fixtures remain appropriate for deterministic tests; they are **not** the primary research dataset.

---

## Milestone 0 — Environment, workflow, minimal UI setup

**Status:** COMPLETE / PASS (historical)

### Objective

Convert the repo into a Linux/DGX-ready CVS Experiment Engine scaffold with Poetry tooling and a minimal local visibility UI.

### Scope

- Project identity `cvs-engine` / `src/cvs_engine/`
- Package and config placeholders
- pytest / Ruff / Pyright
- Streamlit shell at `ui/app.py`
- `.ai/` handoff docs and Cursor rules

### Exclusions

No datasets, training, models, metrics, MLflow, or CVS scoring.

### Acceptance criteria

Package imports; quality gates pass; UI launches; project no longer presents as FastAPI/OpenAI starter.

### Verification

`poetry install`, `poetry run python -m pytest`, `poetry run ruff check .`, `poetry run pyright`, Streamlit launch.

---

## Milestone 0.1 / 0.2 / 0.3 — Documentation and rule alignment

**Status:**

| Milestone | Status |
| --- | --- |
| 0.1 — Long-lived `.ai/` docs | Complete (historical) |
| 0.2 — `.ai/` numbering and roles | Complete (historical) |
| 0.3 — Cursor rule (`.mdc`) + stage architecture docs | Implementation complete; review acceptance pending |

These milestones authorize documentation / Cursor-rule corrections only. They do not implement Stage 1 functionality.

---

## Proposed Stage 1 milestones

The following replaces the earlier synthetic-first 1A–1E sequence as the **active** implementation plan. Stage 1 uses a frozen pretrained encoder, trains aggregation/prediction modules, and produces Stage 2 handoff artifacts. Stage 1 includes predictor training; it is not limited to feature extraction.

### S1.1 — Data contract, manifest/case loading, and split handling

**Status:** Proposed (next implementation milestone; **not authorized** until approved in `.ai/90_current_milestone.md`)

#### Objective

Define and load the Stage 1 data contract: images, case definitions, reference annotations, and video-safe splits.

#### Required input

- Prepared Cholec80 / Cholec80-CVS image set and annotation sources (paths configurable).
- Explicit case-definition and split specification (versions recorded).
- Decisions or provisional defaults for identifier conventions and case-to-image / case-to-score mappings.

#### Expected output

- Loadable case/manifest/split interfaces or modules under the shared package.
- Documented dataset / case-definition / split version identifiers.
- Tests covering load success, mapping integrity, and video-level split separation.
- Config hooks for dataset roots that differ locally vs cloud.

#### Exclusions

- Encoder / feature extraction
- Training loops and prediction heads
- Stage 2 fine-tuning
- MLflow, advanced UI, cloud provisioning
- Re-running original video preprocessing or interval audit

#### Acceptance criteria

1. Cases load with explicit image lists and reference scores.
2. Splits separate by video with no leakage across train/val/test.
3. Versions and paths are recorded in a reproducible way.
4. Meaningful tests cover introduced load/mapping/split behavior.
5. Quality gates pass.

---

### S1.2 — Frozen encoder, feature extraction, and cache

**Status:** Proposed (future; after S1.1)

#### Objective

Extract image embeddings with a **frozen** pretrained visual encoder and cache them for reuse.

#### Required input

- S1.1 case/image loading and splits.
- Chosen encoder identity and exact weights/revision (must be settled before or during this milestone).
- Preprocessing specification compatible with the encoder.

#### Expected output

- Feature extraction path that keeps encoder weights frozen.
- Feature-cache identity mapped back to source images.
- Configuration snapshot recording encoder, preprocessing, and cache identity.
- Tests for cache write/read, frozen-weight expectation, and mapping integrity.

#### Exclusions

- Encoder fine-tuning (Stage 2)
- Prediction-head training beyond what is needed to smoke-test feature shapes (prefer defer full training to S1.3)
- Cloud setup, MLflow, UI inference

#### Acceptance criteria

1. Embeddings can be extracted and reloaded from cache without recomputation when inputs are unchanged.
2. Encoder weights remain frozen during Stage 1 extraction.
3. Cache identity and source-image mapping are explicit.
4. Quality gates and new tests pass.

---

### S1.3 — Case aggregation and prediction-head training

**Status:** Proposed (future; after S1.2)

#### Objective

Combine image embeddings within each case and train a prediction head (and, if selected, a trainable aggregation module).

#### Required input

- Cached Stage 1 features and case/split definitions from S1.1–S1.2.
- Settled or explicitly provisional choices for aggregation method, head architecture, and initial scoring formulation (total score and/or criteria).
- Training hyperparameters (config-driven).

#### Expected output

- Trainable aggregation (optional) and prediction-head modules.
- Local training entry for Stage 1 that writes checkpoints reconstructing the trained modules.
- Config snapshots for reproducible runs.
- Tests for aggregation shapes, training smoke, and checkpoint write/load of trained modules.

#### Exclusions

- Encoder weight updates
- Stage 2 sequential fine-tuning strategies (documentable later; not required here)
- Full paper-ready ablations, MLflow requirement, advanced UI

#### Acceptance criteria

1. A Stage 1 training run completes on the approved data path and writes checkpoints.
2. Aggregation operates at case level from cached image embeddings.
3. Trained modules are reconstructible from saved artifacts plus recorded encoder identity.
4. Quality gates and new tests pass.

---

### S1.4 — Evaluation, predictions, reports, and Stage 2 handoff

**Status:** Proposed (future; after S1.3)

#### Objective

Evaluate Stage 1 predictions and export metrics, case-level predictions, reports, and handoff artifacts for Stage 2.

#### Required input

- Trained Stage 1 modules and compatible feature cache / configs.
- Shared split definitions.
- Access path to **original images** for Stage 2 handoff (features alone are insufficient for encoder fine-tuning).

#### Expected output

- Case-level predictions and metrics under the proposed layout, for example:

```text
outputs/<experiment_id>/stage1/
```

- Execution report and configuration snapshot for the Stage 1 run.
- Stage 2 handoff information: original-image access, encoder identity/weights/revision, preprocessing, and trained-module checkpoints sufficient to reconstruct compatible models.
- Tests for metrics/export helpers and handoff artifact presence checks.

#### Exclusions

- Stage 2 training itself
- Clinical interpretation language
- Mandatory MLflow or cloud deployment

#### Acceptance criteria

1. Eval produces metrics and case-level predictions.
2. Stage 2 handoff includes original-image access info plus reconstruction metadata.
3. Artifacts are stage-scoped and experiment-identifiable.
4. Quality gates and new tests pass.

---

## Optional later work (not on the critical Stage 1 path)

| Theme | Intent |
| --- | --- |
| MLflow local tracking | Optional experiment tracking |
| Streamlit experiment visibility extension | Richer local artifact visibility (still no clinical claims) |
| Cloud GPU setup (e.g. RunPod) | Optional Stage 2 / heavy-run infrastructure |
| Stage 2 encoder fine-tuning | Unfreeze/adapt encoder with prediction/aggregation modules |
| Criterion formulations and sequential fine-tuning | Research variants after Stage 1 baseline |
| Paper-ready evaluation pipeline | Reproducible tables, ablations, publication export |
| Human-in-the-loop review | Reviewer workflows for validation |

Each later item must define objective, scope, exclusions, acceptance criteria, and verification before implementation approval.

---

## Workflow rule

1. Approve one milestone in `.ai/90_current_milestone.md`.
2. Implement only that milestone.
3. Record results in `.ai/91_implementation_report.md`.
4. Review via `.ai/92_review_report.md` / corrections in `.ai/93_corrections.md`.
5. Do not start the next milestone until accepted.
6. Functionality changes must include meaningful tests for introduced behavior.
