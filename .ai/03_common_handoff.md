# CVS Experiment Engine — Common Handoff

Operational handoff for a new Cursor session. Read this before implementing.

## Documentation roles

| Range | Role |
| --- | --- |
| `00–09` | Long-lived canonical project documents |
| `90–99` | Operational milestone / review logs |

Canonical docs:

- `.ai/00_project_reference.md`
- `.ai/01_implementation_roadmap.md`
- `.ai/02_code_quality_standards.md`
- `.ai/04_code_map.md`

Operational logs:

- `.ai/90_current_milestone.md`
- `.ai/91_implementation_report.md`
- `.ai/92_review_report.md`
- `.ai/93_corrections.md`

Project rule: `.cursor/rules/cvs-engine.mdc`

## Current project

**CVS Experiment Engine** — reusable ML experiment infrastructure for AI-assisted Critical View of Safety (CVS) scoring research in laparoscopic cholecystectomy.

**Architecture:** one repository and one shared Python package, with two independently executable stages (Stage 1 frozen-encoder + head training; Stage 2 encoder fine-tuning). Stage orchestration such as `src/cvs_engine/stages/` is proposed only until authorized.

## Current accepted / pending state

| Item | Status |
| --- | --- |
| Milestone 0 — Environment, workflow, minimal UI | **PASS / accepted** |
| Milestone 0.1 / 0.2 — `.ai/` documentation normalization | Complete (historical) |
| Milestone 0.3 — Cursor rule + stage architecture docs | **Implementation complete; review acceptance pending** |
| S1.1 — Data contract, manifest/case loading, splits | **Next proposed work — not approved for implementation yet** |

## Latest verification summary

### Milestone 0 (historical)

| Check | Result |
| --- | --- |
| `poetry run python -m pytest` | PASS |
| `poetry run ruff check .` | PASS |
| `poetry run pyright` | PASS |
| Streamlit UI (`ui/app.py`) | Launched successfully |

### Milestone 0.2 (historical docs-only re-check)

| Check | Result |
| --- | --- |
| `poetry run python -m pytest` | PASS (2 passed) |
| `poetry run ruff check .` | PASS |
| `poetry run pyright` | PASS (0 errors) |

### Milestone 0.3 (docs / rule alignment)

| Check | Result |
| --- | --- |
| `.cursor/rules/cvs-engine.mdc` frontmatter | PASS |
| Active `.mdc` path references | PASS |
| Stage / S1.1 documentation consistency | PASS |
| `poetry run python -m pytest` | PASS (2 passed) |
| `poetry run ruff check .` | PASS |
| `poetry run pyright` | PASS (0 errors) |
| `git diff --check` | NOT RUN (no Git repository) |

Historical results above must remain distinguishable from these Milestone 0.3 checks. Full evidence: `.ai/91_implementation_report.md`.

Re-run quality gates after any implementation milestone. Prefer `poetry run python -m pytest` on Windows.

## Current limitations

Still **not** implemented:

- No Stage 1 / Stage 2 executable pipelines
- No dataset loaders, case manifests, or split handling
- No frozen-encoder feature extraction or caches
- No prediction-head training or evaluation exports
- No encoder fine-tuning
- No MLflow
- No CVS scoring / medical predictions
- No decision support
- No `src/cvs_engine/stages/` directory (proposed only)

Package modules under `src/cvs_engine/` remain scaffold/`__init__.py` placeholders except project metadata.

## Next proposed work

**S1.1 — Data contract, manifest/case loading, and split handling** — pending explicit approval in `.ai/90_current_milestone.md`.

Do **not** implement S1.1 (or any later milestone) until approved.

## Standard structure for future Cursor task prompts

Future authorized Cursor tasks should use this three-part structure:

1. **Project context, existing environment, and authorized scope** — what exists, what is in scope for this task, and what must be preserved.
2. **Required implementation, boundaries, and verification** — concrete changes, exclusions, and checks to run.
3. **Delivery report with evidence, limitations, and gaps** — append to `.ai/91_implementation_report.md` and return the structured delivery report.

Functionality changes must include meaningful tests for the introduced behavior, relevant failure cases, and affected integration boundaries. Documentation-only milestones do not invent artificial Python tests for prose edits.

## Workflow boundaries

1. Implement only the milestone written in `.ai/90_current_milestone.md`.
2. Do not expand scope into training, metrics, MLflow, UI behavior, or Stage 2 unless that milestone requires them.
3. Update `.ai/91_implementation_report.md` after implementation.
4. Leave review findings for `.ai/92_review_report.md` and corrections for `.ai/93_corrections.md`.
5. Distinguish implemented behavior from planned/proposed functionality.

## Exact instruction for a new Cursor session

```text
1. Inspect long-lived docs under .ai/ (00_project_reference, 01_implementation_roadmap,
   02_code_quality_standards, 03_common_handoff, 04_code_map).
2. Inspect operational files (.ai/90_current_milestone.md and .ai/91_implementation_report.md).
3. Inspect the repo structure (src/cvs_engine, configs, tests, ui, scripts, .cursor/rules).
4. Implement ONLY the approved milestone — nothing beyond it.
5. Run required verification commands.
6. Update .ai/91_implementation_report.md with changed files, summary, verification,
   limitations, and intentionally not implemented items.
```

## Safety reminder

No clinical claims. No medical predictions. No decision support unless a future approved milestone explicitly redesigns that boundary (not expected in early milestones).
