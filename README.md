# CVS Experiment Engine

Reusable experiment infrastructure for AI-assisted Critical View of Safety (CVS) scoring research.

## Purpose

This repository provides a clean, Linux/DGX-ready scaffold for PhD research on AI-assisted CVS scoring in laparoscopic cholecystectomy. It is an ML experiment engine, not a clinical product and not a FastAPI/OpenAI starter.

The prediction unit is an **image set / case** from the same surgical video and an explicitly defined temporal assessment context. The system is intended to produce **one overall CVS prediction per case** (overall score 0–6 as the sum of three criterion scores of 0/1/2). These are research outputs, not clinical instructions.

## Architecture

**One repository**, one shared Python package (`src/cvs_engine/`), with **two independently executable stages**:

| Stage | Intent |
| --- | --- |
| Stage 1 | Frozen pretrained encoder → embedding cache → case aggregation → prediction-head training → evaluation and Stage 2 handoff |
| Stage 2 | Encoder fine-tuning with compatible prediction/aggregation modules, using original images and Stage 1 handoff artifacts |

A thin stage orchestration layer (for example `src/cvs_engine/stages/`) is **proposed only** and is not present yet. Shared logic stays in the existing package areas. See `.ai/00_project_reference.md` and `.ai/01_implementation_roadmap.md`.

## Current Status

**Milestone 0** (environment, workflow, minimal UI) is complete.

**Milestone 0.3** aligned Cursor rules and documentation with the two-stage architecture. Stage 1 / Stage 2 executable pipelines are **not** implemented. The next proposed implementation milestone is **S1.1** (data contract, manifest/case loading, splits), pending approval.

## Local Setup

Requires Python 3.11.x and Poetry.

```powershell
poetry config virtualenvs.in-project true
poetry install
```

## Quality Checks

```powershell
poetry run python -m pytest
poetry run ruff check .
poetry run pyright
```

Or via helper scripts:

```powershell
.\scripts\test.ps1
.\scripts\lint.ps1
.\scripts\typecheck.ps1
.\scripts\quality.ps1
```

> Note: Prefer `poetry run python -m pytest` over `poetry run pytest` on Windows if a stale global `pytest.exe` launcher interferes with imports.

## Minimal UI

Local experiment visibility shell (no inference, no medical predictions):

```powershell
poetry run streamlit run ui/app.py
```

The UI shows project identity, milestone status, useful commands, expected future artifact locations, and a basic `cvs_engine` import check. Both stages must eventually support CLI execution without Streamlit.

## Project Structure

```text
src/cvs_engine/          # Main package (scaffold only; stages/ not created yet)
configs/                 # Hydra/config placeholders (experiment, dataset, model, task, training)
scripts/                 # Quality helper scripts
tests/                   # Import smoke tests
ui/app.py                # Minimal Streamlit visibility UI
.ai/                     # Project handoff and milestone documents
.cursor/rules/           # Cursor project rule (cvs-engine.mdc)
```

Proposed later outputs (not created yet):

```text
outputs/<experiment_id>/stage1/
outputs/<experiment_id>/stage2/
```

## What Is Not Implemented Yet

- Stage 1 / Stage 2 executable pipelines and `src/cvs_engine/stages/`
- Case/manifest/split loaders and frozen-encoder feature caches
- Aggregation modules, prediction-head training, and evaluation exports
- Encoder fine-tuning
- MLflow, Optuna, VLMs, SAM-2
- Advanced UI (upload, viewers, inference controls)
- Cloud / DGX / RunPod deployment automation

## Documentation

| Path | Role |
| --- | --- |
| `.ai/00_project_reference.md` | Identity, boundaries, I/O contract |
| `.ai/01_implementation_roadmap.md` | Stage 1 milestones (S1.1–S1.4) |
| `.ai/03_common_handoff.md` | Session restart handoff |
| `.ai/90_current_milestone.md` | Approved / pending milestone |
| `.cursor/rules/cvs-engine.mdc` | Always-apply Cursor project rule |
