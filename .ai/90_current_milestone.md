# Current Milestone — CVS Experiment Engine

Operational snapshot for the active ChatGPT + Cursor + review cycle.

**Numbering rule:** `00–09` = long-lived canonical docs; `90–99` = operational milestone/review logs.

## Project identity

This repository is the **CVS Experiment Engine**: reusable experiment infrastructure for AI-assisted Critical View of Safety (CVS) scoring research in laparoscopic cholecystectomy.

It is a research/ML scaffold, not a clinical product and not a FastAPI/OpenAI service.

**Architecture:** one repository and one shared Python package, with two independently executable stages (Stage 1 frozen-encoder + predictor training; Stage 2 encoder fine-tuning).

## Canonical long-lived docs (00–09)

| File | Role |
| --- | --- |
| `.ai/00_project_reference.md` | Project identity, boundaries, I/O contract |
| `.ai/01_implementation_roadmap.md` | Stage 1 roadmap (S1.1–S1.4) and optional later work |
| `.ai/02_code_quality_standards.md` | ML research engineering standards |
| `.ai/03_common_handoff.md` | Session restart handoff |
| `.ai/04_code_map.md` | Semantic repository map |

Project rule: `.cursor/rules/cvs-engine.mdc`

## Operational logs (90–99)

| File | Role |
| --- | --- |
| `.ai/90_current_milestone.md` | This file — current state + approved/pending milestone |
| `.ai/91_implementation_report.md` | Implementation evidence and verification |
| `.ai/92_review_report.md` | Review status and findings |
| `.ai/93_corrections.md` | Correction rounds |

## Current state

| Item | Status |
| --- | --- |
| Milestone 0 — Environment, workflow, minimal UI | **PASS / accepted** |
| Milestone 0.1 — Normalize long-lived `.ai/` docs | Completed (historical) |
| Milestone 0.2 — Normalize `.ai/` numbering and roles | Completed (historical) |
| Milestone 0.3 — Cursor rules and stage architecture alignment | **Current authorized milestone — implementation complete; review acceptance pending** |
| S1.1 — Data contract, manifest/case loading, splits | **Next proposed work; not approved for implementation** |

## Research target (future milestones)

Eventually the engine will support Stage 1 frozen-encoder experiments and Stage 2 fine-tuning for:

- CVS criterion-level scoring
- Total CVS score estimation
- Satisfactory / unsatisfactory CVS classification
- Confidence / uncertainty handling
- Evidence-based review
- Later human-in-the-loop validation

## Minimal UI (unchanged)

A local Streamlit app at `ui/app.py` answers project identity, milestone status, commands, and future artifact locations. It does **not** train models, load datasets, or show medical predictions.

## Medical / clinical stance

**No medical claims are implemented.** No CVS model, predictions, or clinical decision support exist yet.

---

## Approved milestone: 0.3 — Cursor rules and stage architecture alignment

### Objective

Correct the Cursor project rule to `.mdc` with valid frontmatter, and align repository documentation with the agreed two-stage architecture and proposed Stage 1 roadmap (S1.1–S1.4), including a compact input/output contract.

### Scope

- Rename / update `.cursor/rules/cvs-engine.md` → `.cursor/rules/cvs-engine.mdc` with YAML frontmatter
- Update README and `.ai/` canonical / operational docs for stage architecture consistency
- Replace the active synthetic-first roadmap with proposed Stage 1 milestones S1.1–S1.4
- Document the proposed I/O contract and artifact layout
- Document the proposed (not created) `src/cvs_engine/stages/` orchestration layer
- Preserve historical Milestone 0 / 0.1 / 0.2 evidence
- Append Milestone 0.3 implementation evidence; optionally append a pending-review note to the review report

### Explicit exclusions

- S1.1 and all Stage 1 / Stage 2 executable functionality
- Python source, tests, Streamlit UI, scripts
- `pyproject.toml` / `poetry.lock` changes
- Dependency install/upgrade, model downloads, training, cloud setup
- Creating `src/cvs_engine/stages/` or stage entrypoints

### Acceptance criteria

1. `.cursor/rules/cvs-engine.mdc` exists with the intended frontmatter; active references use the `.mdc` path.
2. Stage definitions are consistent across updated documents; existing vs proposed structures are clearly distinguished.
3. Roadmap identifies S1.1 as proposed and unimplemented.
4. Historical verification evidence remains intact and distinguishable.
5. Diff stays within documentation and Cursor-rule scope.
6. Available quality gates are run or recorded as NOT RUN with explanation.
7. Implementation completion is distinguished from review acceptance.

### Completion status

| Gate | Status |
| --- | --- |
| Authorized implementation | Complete (see `.ai/91_implementation_report.md`) |
| Independent / human review acceptance | **Pending** |

### Prior accepted milestone

**Milestone 0 — Environment, Workflow, and Minimal UI Setup** — PASS (see `.ai/91_implementation_report.md` and `.ai/92_review_report.md`).

Milestone 0.1 / 0.2 documentation normalizations are complete as historical docs work.
