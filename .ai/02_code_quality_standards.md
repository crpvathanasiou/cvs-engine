# CVS Experiment Engine — Code Quality Standards

Engineering standards for this ML research repository. Keep rigor; skip production-API assumptions that do not apply to V1.

## Language and tooling

| Standard | Requirement |
| --- | --- |
| Python | **3.11.x** only (`>=3.11,<3.12`) |
| Dependencies | **Poetry** (`pyproject.toml` + `poetry.lock`) |
| Lint | **Ruff** (`poetry run ruff check .`) |
| Types | **Pyright** (`poetry run pyright`) |
| Tests | **pytest** (`poetry run python -m pytest`) |
| Paths | Prefer **Linux/DGX-ready**, POSIX-friendly paths; avoid Windows-only assumptions in core package code |

## Not applicable (V1 / research scaffold)

Mark these as **N/A** unless a future milestone explicitly approves them:

- FastAPI route / OpenAPI contract standards
- API endpoint versioning, auth middleware, rate limits
- OpenAI / LLM wrapper guardrail starter patterns
- Production backend SLOs, multi-tenant SaaS assumptions
- Cloud deployment / hospital integration requirements

## ML research discipline

### Reproducibility

- Set and document **deterministic seeds** for runs that claim reproducibility
- Prefer config-driven experiments over hardcoded hyperparameters in scripts
- Record seeds, config identity, and artifact paths in implementation reports

### Config-driven experiments (Hydra)

- Keep experiment knobs in `configs/` (dataset, model, task, training, experiment)
- Do not scatter magic constants across training scripts when a config key should exist
- Prefer composing configs over one-off CLI-only overrides for lasting experiments

### PyTorch / Lightning style

- Separate **dataset**, **model**, **task**, **training**, and **evaluation** concerns
- Prefer Lightning modules/trainers for training loops once Stage 1 training milestones begin
- Keep device handling explicit and DGX-friendly (CUDA optional, CPU smoke possible)
- Stage 1 keeps the visual encoder frozen; Stage 2 may fine-tune it. Do not conflate the two.

### Dataset / dataloader boundaries

- Dataset code lives under `src/cvs_engine/datasets/`
- Loaders must not embed training loops or metric side effects
- Case-level mappings to images and reference scores must be explicit; do not treat interval-level labels as per-image ground truth by default
- Small synthetic fixtures are for deterministic tests; they are not the primary research dataset
- A thin `src/cvs_engine/stages/` orchestration layer is proposed only; create it only when authorized

### Metrics correctness

- Metrics live under `evaluation/` (or clearly named helpers)
- Prefer tested metric helpers over ad-hoc notebook calculations for claimed results
- Never present research metrics as clinical performance claims

## Testing expectations

- Keep a **smoke-test** suite that runs quickly under pytest
- Milestone 0: import/package smoke tests
- Future Stage 1 milestones: data contract / case load, feature-cache integrity, aggregation or training smoke, metrics/export and handoff checks as authorized
- **Functionality changes must include meaningful tests** for introduced behavior, relevant failure cases, and affected integration boundaries
- Documentation-only milestones do not invent artificial Python tests for prose edits
- Do not require GPU for default CI-style smoke tests unless explicitly approved
- Distinguish historical verification evidence from checks run for the current milestone

## Code style and typing

- Follow Ruff selected rules (`E`, `F`, `I`, `B`, `UP`)
- Prefer explicit types on public functions and dataset/model interfaces
- Avoid unused imports and dead starter code
- Keep modules small and milestone-scoped

## Safety and research ethics (code-facing)

- **No medical claims** in UI copy, logs, README, or metric labels that imply clinical advice
- Do not implement decision-support phrasing (“safe to proceed”, “operate”, etc.)
- Predictions, when added, are experiment artifacts only

## Delivery discipline for Cursor

- Implement **only** the approved milestone in `.ai/90_current_milestone.md`
- Prefer **small milestones** over large multi-feature dumps
- After implementation, update `.ai/91_implementation_report.md` with:
  - changed files
  - summary
  - verification commands and results
  - limitations
  - intentionally not implemented
- Do not expand into the next milestone “while you are here”

## Artifact discipline

Expected later artifact locations (create only when the milestone requires them):

| Path | Purpose |
| --- | --- |
| `outputs/<experiment_id>/stage1/` | Stage 1 checkpoints, predictions, metrics, report, config snapshot |
| `outputs/<experiment_id>/stage2/` | Stage 2 counterparts |
| Shared dataset / feature-cache roots | May live outside experiment dirs; referenced by stable IDs |
| `checkpoints/` / `reports/` | May nest under stage outputs as layouts settle |
| `mlruns/` / Lightning logs | Optional tracking logs (when enabled) |

Do not commit large binary artifacts or dataset blobs unless explicitly approved.

Paths must support different dataset roots locally and in the cloud. Stage 2 handoff requires original-image access plus reconstruction metadata; Stage 1 embedding caches alone cannot support encoder fine-tuning.

## Quality gate baseline

Before marking a milestone implementation complete:

```powershell
poetry run python -m pytest
poetry run ruff check .
poetry run pyright
```

Add milestone-specific smoke commands (train one step, export predictions, Streamlit launch) only when that milestone’s acceptance criteria require them.
