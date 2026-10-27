"""Minimal local visibility UI for the CVS Experiment Engine (Milestone 0)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent


def check_cvs_engine_import() -> tuple[bool, str]:
    """Return whether cvs_engine imports and a short status message."""
    try:
        import cvs_engine

        version = getattr(cvs_engine, "__version__", "unknown")
        return True, f"cvs_engine imported successfully (version {version})."
    except Exception as exc:
        return False, f"cvs_engine import failed: {exc}"


def path_status(relative: str) -> str:
    path = REPO_ROOT / relative
    if path.exists():
        return f"Present: `{relative}`"
    return f"Not present yet: `{relative}` (expected in later milestones)"


st.set_page_config(
    page_title="CVS Experiment Engine",
    page_icon=None,
    layout="centered",
)

st.title("CVS Experiment Engine")
st.caption("Milestone 0 — Environment and Workflow Setup")

st.warning(
    "No CVS model is implemented yet.\n\n"
    "No medical predictions are available in Milestone 0."
)

st.header("What is this project?")
st.write(
    "Reusable experiment infrastructure for AI-assisted Critical View of Safety "
    "(CVS) scoring in laparoscopic cholecystectomy research. "
    "This repository is a research/ML scaffold, not a clinical product."
)

st.header("Current milestone")
st.write(
    "**Milestone 0** prepares the development environment, repository structure, "
    "project rules, handoff files, a minimal testable package, and this local "
    "visibility UI. No training, datasets, or CVS scoring logic are included."
)

st.header("What is implemented now")
st.markdown(
    """
- Poetry project identity: `cvs-engine`
- Package layout under `src/cvs_engine/`
- Placeholder config folders under `configs/`
- Quality tooling: pytest, Ruff, Pyright
- Minimal Streamlit visibility shell (this page)
- `.ai/` handoff files and Cursor project rules
"""
)

st.header("What is not implemented yet")
st.markdown(
    """
- Model training / Lightning modules
- Real or toy datasets and dataloaders
- CVS prediction or medical scoring
- MLflow tracking
- Prediction viewers, image display, file upload
- VLMs, SAM-2, Optuna, advanced UI
"""
)

st.header("Useful commands")
st.code(
    "\n".join(
        [
            "poetry install",
            "poetry run pytest",
            "poetry run ruff check .",
            "poetry run pyright",
            "poetry run streamlit run ui/app.py",
        ]
    ),
    language="powershell",
)

st.header("Expected future artifacts")
st.markdown(
    """
| Location | Purpose |
| --- | --- |
| `checkpoints/` | Saved model weights (later milestones) |
| `outputs/predictions.csv` | Experiment predictions (later milestones) |
| `reports/` | Evaluation reports (later milestones) |
| MLflow runs | Experiment tracking (later milestone) |
"""
)

for relative in ("checkpoints", "outputs/predictions.csv", "reports"):
    st.text(path_status(relative))

st.header("Environment / project status")
ok, message = check_cvs_engine_import()
if ok:
    st.success(message)
else:
    st.error(message)

python_spec = importlib.util.find_spec("streamlit")
st.text(
    "Streamlit is available."
    if python_spec is not None
    else "Streamlit was not found in the active environment."
)

st.caption(
    "This UI is a lightweight experiment visibility layer only. "
    "It does not run inference or make medical claims."
)
