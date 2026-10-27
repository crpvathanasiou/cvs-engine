"""Saved-execution metadata (``blur_gate_info.json``) for UI reopen without rescoring."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from blur_gate.decision import validate_threshold

INFO_FILENAME = "blur_gate_info.json"
INFO_SCHEMA_VERSION = "1"
RUN_REPORT_FILENAME = "run.json"
VIEWABLE_STATUSES = frozenset({"completed", "completed_with_errors"})


class RunInfoError(ValueError):
    """Readable failure while reading or deriving saved-execution metadata."""


@dataclass(frozen=True)
class SavedExecution:
    """One export folder that can be reopened in the UI."""

    output_dir: Path
    info: dict[str, Any]

    @property
    def folder_name(self) -> str:
        return self.output_dir.name

    @property
    def label(self) -> str:
        created = str(self.info.get("created_at", "unknown"))
        threshold = self.info.get("threshold", "?")
        return f"{created} · threshold={threshold} · {self.folder_name}"


def _empty_executions() -> list[SavedExecution]:
    return []


def _empty_issues() -> list[str]:
    return []


@dataclass(frozen=True)
class ListedExecutions:
    """Viewable executions plus per-folder unavailability warnings."""

    executions: list[SavedExecution] = field(default_factory=_empty_executions)
    issues: list[str] = field(default_factory=_empty_issues)


def info_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / INFO_FILENAME


def run_report_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / RUN_REPORT_FILENAME


def is_viewable_status(status: object) -> bool:
    return str(status) in VIEWABLE_STATUSES


def _require_nonnegative_int(value: object, label: str) -> int:
    """Require a true nonnegative ``int`` (reject bools and floats)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise RunInfoError(f"{label} must be a nonnegative integer")
    if value < 0:
        raise RunInfoError(f"{label} must be a nonnegative integer")
    return value


def _require_threshold(value: object) -> float:
    try:
        return validate_threshold(value)
    except (TypeError, ValueError) as exc:
        raise RunInfoError(
            "threshold must be a finite nonnegative number"
        ) from exc


def validate_info_values(info: dict[str, Any], *, source_label: str) -> dict[str, Any]:
    """Shared validation for stored info and values derived from ``run.json``."""
    required = (
        "created_at",
        "status",
        "threshold",
        "method",
        "preprocessing_version",
        "blur_gate_version",
        "source_dataset_root",
        "counts",
    )
    missing = [key for key in required if key not in info]
    if missing:
        raise RunInfoError(
            f"{source_label} missing fields: {', '.join(missing)}"
        )

    created_at = str(info["created_at"]).strip()
    if not created_at:
        raise RunInfoError(f"{source_label} missing created_at")

    status = str(info["status"]).strip()
    if not status:
        raise RunInfoError(f"{source_label} missing status")

    threshold = _require_threshold(info["threshold"])

    method = str(info["method"]).strip()
    preprocessing = str(info["preprocessing_version"]).strip()
    version = str(info["blur_gate_version"]).strip()
    if not method or not preprocessing or not version:
        raise RunInfoError(
            f"{source_label} method/version fields are incomplete"
        )

    counts = info["counts"]
    if not isinstance(counts, dict):
        raise RunInfoError(f"{source_label} counts must be an object")
    counts_map = cast(dict[str, Any], counts)
    for key in ("input", "accepted", "rejected", "error"):
        if key not in counts_map:
            raise RunInfoError(f"{source_label} counts missing {key!r}")

    try:
        input_count = _require_nonnegative_int(counts_map["input"], "counts.input")
        accepted = _require_nonnegative_int(counts_map["accepted"], "counts.accepted")
        rejected = _require_nonnegative_int(counts_map["rejected"], "counts.rejected")
        error_count = _require_nonnegative_int(counts_map["error"], "counts.error")
    except RunInfoError:
        raise
    except (TypeError, ValueError) as exc:
        raise RunInfoError(f"{source_label} has invalid count values") from exc

    if input_count != accepted + rejected + error_count:
        raise RunInfoError(
            "counts are inconsistent: "
            f"input ({input_count}) != accepted ({accepted}) + "
            f"rejected ({rejected}) + error ({error_count})"
        )

    return {
        "schema_version": str(info.get("schema_version", INFO_SCHEMA_VERSION)),
        "created_at": created_at,
        "status": status,
        "threshold": threshold,
        "method": method,
        "preprocessing_version": preprocessing,
        "blur_gate_version": version,
        "source_dataset_root": str(info.get("source_dataset_root", "") or ""),
        "counts": {
            "input": input_count,
            "accepted": accepted,
            "rejected": rejected,
            "error": error_count,
        },
    }


def build_info_from_run_report(run: dict[str, Any]) -> dict[str, Any]:
    """Derive ``blur_gate_info.json`` contents from an existing BlurGate ``run.json``."""
    try:
        blur = run.get("blur_gate")
        if not isinstance(blur, dict):
            raise RunInfoError("run.json missing blur_gate object")
        blur_map = cast(dict[str, Any], blur)

        status = str(run.get("status", "")).strip()
        if not status:
            raise RunInfoError("run.json missing status")

        counts = run.get("counts")
        if isinstance(counts, dict):
            counts_map = cast(dict[str, Any], counts)
        elif status == "failed":
            # Early failures may write run.json before any images were counted.
            counts_map = {"input": 0, "accepted": 0, "rejected": 0, "error": 0}
        else:
            raise RunInfoError("run.json missing counts object")

        source = run.get("source_dataset")
        source_root = ""
        if isinstance(source, dict):
            source_root = str(cast(dict[str, Any], source).get("root", "") or "")

        created_at = str(run.get("created_at", "")).strip()
        if not created_at:
            raise RunInfoError("run.json missing created_at")

        draft: dict[str, Any] = {
            "schema_version": INFO_SCHEMA_VERSION,
            "created_at": created_at,
            "status": status,
            "threshold": blur_map.get("threshold"),
            "method": blur_map.get("method", ""),
            "preprocessing_version": blur_map.get("preprocessing_version", ""),
            "blur_gate_version": blur_map.get("version", ""),
            "source_dataset_root": source_root,
            "counts": {
                "input": counts_map.get("input"),
                "accepted": counts_map.get("accepted"),
                "rejected": counts_map.get("rejected"),
                "error": counts_map.get("error"),
            },
        }
        return validate_info_values(draft, source_label="run.json")
    except RunInfoError:
        raise
    except (TypeError, ValueError, KeyError) as exc:
        raise RunInfoError(f"Could not derive metadata from run.json: {exc}") from exc


def write_run_info(output_dir: Path | str, info: dict[str, Any]) -> Path:
    """Write ``blur_gate_info.json`` only when absent. Never overwrites."""
    out = Path(output_dir)
    path = info_path(out)
    if path.exists():
        return path
    validated = validate_info_values(info, source_label=INFO_FILENAME)
    try:
        out.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(validated, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RunInfoError(f"Could not write {INFO_FILENAME}: {exc}") from exc
    return path


def write_run_info_from_report(output_dir: Path | str, run: dict[str, Any]) -> Path:
    """Persist info derived from the filter report for a new (or legacy) run folder."""
    return write_run_info(output_dir, build_info_from_run_report(run))


def load_run_info(output_dir: Path | str) -> dict[str, Any]:
    """Load existing info, or derive+save from ``run.json`` when missing.

    Existing ``blur_gate_info.json`` is never overwritten or repaired when invalid.
    """
    out = Path(output_dir)
    path = info_path(out)
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RunInfoError(f"Could not read {INFO_FILENAME}: {exc}") from exc
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RunInfoError(f"Malformed {INFO_FILENAME}: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise RunInfoError(f"{INFO_FILENAME} must be a JSON object")
        return validate_info_values(
            cast(dict[str, Any], raw),
            source_label=INFO_FILENAME,
        )

    report_path = run_report_path(out)
    if not report_path.is_file():
        raise RunInfoError(f"Missing {INFO_FILENAME} and {RUN_REPORT_FILENAME}")
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RunInfoError(f"Could not read {RUN_REPORT_FILENAME}: {exc}") from exc
    try:
        run_raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RunInfoError(f"Malformed {RUN_REPORT_FILENAME}: {exc.msg}") from exc
    if not isinstance(run_raw, dict):
        raise RunInfoError(f"{RUN_REPORT_FILENAME} must be a JSON object")
    info = build_info_from_run_report(cast(dict[str, Any], run_raw))
    write_run_info(out, info)
    return info


def list_saved_executions(export_dir: Path | str) -> ListedExecutions:
    """List viewable run folders under the fixed export root, newest first.

    Invalid metadata folders are omitted from the selectable list but reported in
    ``issues`` (never silently dropped). Failed/incomplete statuses stay excluded
    from completed results without being treated as malformed metadata.
    """
    root = Path(export_dir)
    if not root.is_dir():
        return ListedExecutions()

    found: list[SavedExecution] = []
    issues: list[str] = []
    children = sorted(
        (child for child in root.iterdir() if child.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for child in children:
        try:
            info = load_run_info(child)
        except RunInfoError as exc:
            issues.append(f"{child.name}: {exc}")
            continue
        if not is_viewable_status(info["status"]):
            continue
        found.append(SavedExecution(output_dir=child.resolve(), info=info))
    return ListedExecutions(executions=found, issues=issues)


def result_from_saved_execution(execution: SavedExecution) -> dict[str, Any]:
    """Build the UI ``last_result`` dict from saved metadata (no scoring)."""
    counts = cast(dict[str, Any], execution.info["counts"])
    return {
        "status": str(execution.info["status"]),
        "output_dir": str(execution.output_dir),
        "input": int(counts["input"]),
        "accepted": int(counts["accepted"]),
        "rejected": int(counts["rejected"]),
        "error": int(counts["error"]),
        "threshold": float(execution.info["threshold"]),
    }


def load_execution_result(output_dir: Path | str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load info + UI result for one folder. Raises if not a completed execution."""
    out = Path(output_dir).resolve()
    try:
        info = load_run_info(out)
    except RunInfoError:
        raise
    except (TypeError, ValueError, OSError) as exc:
        raise RunInfoError(f"Could not load execution metadata: {exc}") from exc
    if not is_viewable_status(info["status"]):
        raise RunInfoError(
            f"Execution status is {info['status']!r}; only completed runs can be opened."
        )
    execution = SavedExecution(output_dir=out, info=info)
    return info, result_from_saved_execution(execution)
