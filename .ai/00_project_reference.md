# CVS Experiment Engine — Project Reference

Canonical project reference for the ChatGPT + Cursor + review workflow.

## Project identity

| Field | Value |
| --- | --- |
| Name | CVS Experiment Engine |
| Package | `cvs_engine` (`src/cvs_engine/`) |
| Poetry project | `cvs-engine` |
| Domain | AI-assisted Critical View of Safety (CVS) scoring research |
| Procedure context | Laparoscopic cholecystectomy |
| Product type | Research / ML experiment infrastructure |

This repository is **not** a FastAPI service, OpenAI starter, clinical product, or production decision-support system.

## Research / PhD context

The engine supports PhD research on AI-assisted CVS assessment from surgical video/image data. The long-term research target is reusable, reproducible experiment infrastructure for:

- Criterion-level CVS scoring
- Total CVS score estimation
- Satisfactory / unsatisfactory CVS classification
- Confidence / uncertainty handling
- Evidence-oriented review workflows
- Later human-in-the-loop validation

## Target problem

**AI-assisted CVS scoring** — develop and evaluate models that estimate Critical View of Safety criteria from laparoscopic cholecystectomy imagery, under controlled research conditions, with strict separation from clinical deployment claims.

The prediction unit is an **image set / case** containing images from:

- The same surgical video.
- An explicitly defined temporal assessment context.

The system produces **one overall CVS prediction per image set**.

The primary target is an overall score from **0 to 6**. The three reference criterion scores each take values **0, 1, or 2**:

1. Two structures entering the gallbladder.
2. Cystic plate exposure/dissection.
3. Hepatocystic triangle clearance.

The overall reference score equals the sum of the three criterion scores. Predicting the individual criteria is an additional supported research objective.

These are research outputs, not instructions for clinical decisions.

## Non-goals and safety boundaries

Do **not** treat this repo as:

- A clinical decision-support product
- A medical device or FDA/CE pathway deliverable
- A production hospital API or cloud SaaS
- A generic LLM chatbot / OpenAI wrapper
- A FastAPI production backend starter

**Explicit safety stance (current and V1):**

- No clinical claims
- No medical predictions presented as care guidance
- No decision support for live surgery
- No patient-facing outputs
- Research experiment outputs only, when implemented

## Agreed architecture (one repo, two stages)

Maintain **one repository** and **one shared Python package**, with **two independently executable stages**.

Each stage will have its own entrypoint, configuration, output artifacts, and execution report. Shared functionality remains in the existing dataset, model, task, training, evaluation, and utility packages.

| Stage | Role |
| --- | --- |
| **Stage 1** | Load images, case definitions, reference annotations, and splits. Extract and cache embeddings with a **frozen** pretrained visual encoder. Combine image embeddings within each case. Train a prediction head and, if selected, a trainable aggregation module. Evaluate and export checkpoints, metrics, predictions, and reports. Stage 1 includes predictor training; it is not limited to feature extraction. |
| **Stage 2** | Adapt the visual encoder through fine-tuning, together with the appropriate prediction and aggregation modules. Use original images and relevant Stage 1 handoff artifacts. Support later investigation of direct total-score prediction, criterion-specific prediction followed by summation, and sequential criterion-focused fine-tuning. |

Important distinctions:

- Cached Stage 1 embeddings alone **cannot** support encoder fine-tuning. Changes to encoder weights or preprocessing require a new compatible feature cache.
- Distinguish three heads sharing one encoder from three independently trained models.
- Sequential fine-tuning is a training strategy that can be combined with different output formulations.
- Stage 1 will run primarily locally. Stage 2 may run on cloud GPU infrastructure later. RunPod is a possible future choice, **not** a current dependency.
- Both stages must eventually support CLI execution without launching Streamlit.

### Proposed stage orchestration (not implemented)

A thin future orchestration layer such as `src/cvs_engine/stages/` may coordinate Stage 1 / Stage 2 entrypoints while reusing the shared packages above. This directory and any executable stage entrypoints are **proposed only** and must not be created until an approved milestone authorizes them.

## Current system boundary (after Milestone 0.3 docs alignment)

**In scope today (implemented):**

- Poetry-managed Python 3.11 project
- Package scaffold under `src/cvs_engine/` (placeholder subpackages)
- Placeholder config folders under `configs/`
- Quality gates: pytest, Ruff, Pyright
- Minimal Streamlit visibility UI at `ui/app.py`
- `.ai/` planning / handoff / review docs
- `.cursor/rules/cvs-engine.mdc` (always-apply project rule)

**Out of scope today (not implemented):**

- Stage 1 / Stage 2 executable pipelines
- Dataset loaders, case manifests, and split handling
- Frozen-encoder feature extraction and caches
- Prediction-head training and evaluation exports
- Encoder fine-tuning
- MLflow tracking
- Advanced UI (upload, viewers, inference controls)
- Cloud / DGX / RunPod deployment automation

## Proposed input / output contract

This section documents the **intended** research contract. It does **not** invent existing CSV columns, claim inspection of unavailable data, or prescribe a final serialization format.

### Identifiers and mappings

- **Video, image, temporal-context, and case identifiers** must be explicit and stable across runs.
- Each case must have an **explicit mapping** to its images and to its **reference annotation / score**.
- Do **not** automatically treat an interval-level annotation as independently verified ground truth for every image.
- The extraction frequency used in preprocessing (for example one frame per second) does **not** determine how many images the model must use per case.

### Splits and versions

- Train / validation / test separation must be by **video** (no video leakage across splits).
- Comparable Stage 1 and Stage 2 experiments must share the same split definitions.
- Dataset version, case-definition version, and split version must be recorded for each experiment.

### Model and preprocessing provenance

- Encoder identity and exact weights / revision must be recorded.
- Preprocessing and the resolved configuration must be snapshotted with the run.
- Feature-cache identity must map cached embeddings back to source images.
- Checkpoints for trained modules must include enough information to reconstruct the complete model used for predictions.

### Predictions and reports

- Case-level predictions, metrics, and execution reports are required Stage outputs when those milestones are implemented.

### Proposed artifact layout

```text
outputs/<experiment_id>/stage1/
outputs/<experiment_id>/stage2/
```

Each stage directory should hold its own checkpoints, predictions, metrics, report, and configuration snapshot.

Shared datasets and reusable feature caches may live outside these directories and be referenced by stable identifiers. Paths must support different dataset roots locally and in the cloud.

The Stage 2 handoff must include access to the **original images** and the information needed to reconstruct the encoder and compatible trained modules.

### Decisions left open

The following remain open until settled before or during the relevant Stage 1 milestones:

- Encoder and pretrained checkpoint
- Number and selection of images per case
- Aggregation method
- Prediction-head architecture and initial scoring formulation
- Training hyperparameters

## Data preparation context (planning assumption)

The initial dataset is **Cholec80 with Cholec80-CVS annotations**. Preprocessing has already extracted images at one frame per second from selected intervals; five problematic intervals have been excluded. Assume this prepared dataset is suitable for current planning. Do not repeat preprocessing or reopen the original interval audit in documentation-only or early Stage 1 planning work unless a future milestone explicitly reopens that topic.

Small synthetic fixtures remain appropriate for deterministic tests. They are **not** the primary research dataset.

## Future functional areas

| Area | Intent | Timing |
| --- | --- | --- |
| Stage 1 data contract | Manifests, cases, splits, annotations | Proposed S1.1 |
| Frozen encoder + feature cache | Embedding extraction and reuse | Proposed S1.2 |
| Aggregation + head training | Case-level prediction training | Proposed S1.3 |
| Evaluation + Stage 2 handoff | Metrics, predictions, reports, artifacts | Proposed S1.4 |
| Stage 2 encoder fine-tuning | Unfreeze / adapt encoder with heads | After Stage 1 |
| Optional MLflow | Local experiment tracking | Optional later |
| Streamlit visibility extension | Richer local experiment visibility | Optional later |
| Cloud GPU execution | Stage 2 / heavy runs (e.g. RunPod) | Optional later |

See `.ai/01_implementation_roadmap.md` for milestone detail. Historical Milestone 0 / 0.1 / 0.2 scaffold work remains accepted documentation and environment baseline.

## Current status

**Milestone 0 — Environment, workflow, and minimal UI setup — COMPLETE / PASS**

**Milestone 0.1 / 0.2 — `.ai/` documentation normalization — COMPLETE** (historical docs milestones)

**Milestone 0.3 — Cursor rules and stage architecture alignment — implementation complete; review acceptance pending**

Documentation now describes the two-stage architecture and the proposed Stage 1 roadmap (S1.1–S1.4). **S1.1 is the next proposed implementation milestone and is not authorized by Milestone 0.3.**

## Clinical disclaimer

**No clinical claims. No medical predictions. No decision support yet.**

Any future scoring outputs are research experiment artifacts only until explicitly redesigned and approved for a different scope.
