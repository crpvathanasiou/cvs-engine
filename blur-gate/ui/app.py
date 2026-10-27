"""BlurGate Streamlit UI — dataset folder + threshold → filter once.

Scoring and filtering use the shared ``blur_gate`` package. Source images are never
copied or modified. Metadata exports go under a fixed project-local folder.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, cast

import streamlit as st
import streamlit.components.v1 as components

from blur_gate.config import ConfigError, make_config
from blur_gate.dataset_filter import DatasetFilterError, filter_dataset
from blur_gate.decision import validate_threshold
from blur_gate.decision_lookup import (
    ClassificationLookupError,
    DecisionLookupCache,
)
from blur_gate.export_layout import export_root, new_run_output_dir
from blur_gate.image_preview import (
    PreviewImageError,
    build_zoom_pan_html,
    load_preview_bytes,
    normalize_manual_path,
)
from blur_gate.progress import ProgressUpdate, describe_progress
from blur_gate.rejected_index import RejectedIndexError, RejectedPathIndex
from blur_gate.run_info import (
    RunInfoError,
    list_saved_executions,
    load_execution_result,
    load_run_info,
)
from blur_gate.scoring import METHOD_NAME, PREPROCESSING_VERSION
from blur_gate.version import __version__

EXPORT_HINT = "blur_gate_export/<timestamp>_<id>/"
ACCEPT_COLOR = "#2ca02c"
REJECT_COLOR = "#d62728"


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "dataset_folder": "",
        "threshold": 0.0,
        "last_result": None,
        "last_error": None,
        "job_progress_summary": None,
        "manual_path_input": "",
        "selected_run_dir": None,
        "selected_run_info": None,
        "selected_run_load_error": None,
        # Viewer state (persists across ordinary reruns; reset on new filter run).
        "viewer_mode": "rejected",  # "rejected" | "manual"
        "viewer_index": 0,
        "viewer_rejected_file": None,
        "viewer_offsets": {},
        "viewer_path": None,
        "viewer_error": None,
        "viewer_image_bytes": None,
        "viewer_image_mime": None,
        "viewer_initialized_for": None,
        "viewer_classification": None,
        "viewer_classification_error": None,
        "viewer_decision_cache": DecisionLookupCache(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    cache_obj: object = st.session_state.viewer_decision_cache
    if not isinstance(cache_obj, DecisionLookupCache):
        st.session_state.viewer_decision_cache = DecisionLookupCache()


def _decision_cache() -> DecisionLookupCache:
    cache_obj: object = st.session_state.viewer_decision_cache
    if not isinstance(cache_obj, DecisionLookupCache):
        cache = DecisionLookupCache()
        st.session_state.viewer_decision_cache = cache
        return cache
    return cache_obj


def _reset_viewer_state() -> None:
    st.session_state.viewer_mode = "rejected"
    st.session_state.viewer_index = 0
    st.session_state.viewer_rejected_file = None
    st.session_state.viewer_offsets = {}
    st.session_state.viewer_path = None
    st.session_state.viewer_error = None
    st.session_state.viewer_image_bytes = None
    st.session_state.viewer_image_mime = None
    st.session_state.viewer_initialized_for = None
    st.session_state.viewer_classification = None
    st.session_state.viewer_classification_error = None


def _progress_bar_value(update: ProgressUpdate) -> float:
    """Only ``completed`` may show 1.0. Other phases stay below 100%."""
    if update.phase == "completed":
        return 1.0
    if update.fraction is None:
        return 0.0
    return min(float(update.fraction), 0.999)


def _apply_progress_widgets(
    bar: Any,
    status: Any,
    update: ProgressUpdate,
) -> None:
    bar.progress(_progress_bar_value(update), text=update.message)
    status.markdown(describe_progress(update))
    st.session_state.job_progress_summary = {
        "phase": update.phase,
        "processed": update.processed,
        "total": update.total,
        "current_path": update.current_path,
        "elapsed_seconds": update.elapsed_seconds,
        "images_per_second": update.images_per_second,
        "eta_seconds": update.eta_seconds,
        "message": update.message,
        "detail": describe_progress(update),
    }


def _render_completion_chart(result: dict[str, Any]) -> None:
    """Render Accept/Reject pie from stored run counts (no dataset reread)."""
    accepted = int(result["accepted"])
    rejected = int(result["rejected"])
    errors = int(result["error"])
    total = int(result["input"])
    classified = accepted + rejected

    if classified == 0:
        st.info("No classified images")
    else:
        accept_label = f"Accept: {accepted}"
        reject_label = f"Reject: {rejected}"
        spec: dict[str, Any] = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": "Accept vs Reject",
            "width": 320,
            "height": 280,
            "data": {
                "values": [
                    {
                        "category": "Accept",
                        "count": accepted,
                        "label": accept_label,
                    },
                    {
                        "category": "Reject",
                        "count": rejected,
                        "label": reject_label,
                    },
                ]
            },
            "mark": {"type": "arc", "outerRadius": 120},
            "encoding": {
                "theta": {"field": "count", "type": "quantitative", "stack": True},
                "color": {
                    "field": "label",
                    "type": "nominal",
                    "scale": {
                        "domain": [accept_label, reject_label],
                        "range": [ACCEPT_COLOR, REJECT_COLOR],
                    },
                    "legend": {"title": None},
                },
                "tooltip": [
                    {"field": "category", "type": "nominal", "title": "Category"},
                    {"field": "count", "type": "quantitative", "title": "Images"},
                ],
            },
        }
        st.vega_lite_chart(spec, width="content")  # pyright: ignore[reportUnknownMemberType]
        st.caption(f"Accept: {accepted} · Reject: {rejected}")

    st.write(f"Total scanned files: {total}")
    if errors > 0:
        st.write(
            f"Errors: {errors} (excluded from the pie chart; "
            "total scanned includes accepted + rejected + errors)"
        )


def _clear_viewer_image() -> None:
    st.session_state.viewer_image_bytes = None
    st.session_state.viewer_image_mime = None


def _show_viewer_image(path: Path | str) -> None:
    try:
        data, mime, resolved = load_preview_bytes(path)
    except PreviewImageError as exc:
        st.session_state.viewer_error = str(exc)
        st.session_state.viewer_path = str(Path(path))
        _clear_viewer_image()
        return
    st.session_state.viewer_error = None
    st.session_state.viewer_path = str(resolved)
    st.session_state.viewer_image_bytes = data
    st.session_state.viewer_image_mime = mime


def _rejected_index_for_state() -> RejectedPathIndex | None:
    rejected_file = st.session_state.viewer_rejected_file
    result_obj: object = st.session_state.last_result
    if rejected_file is None or not isinstance(result_obj, dict):
        return None
    result = cast(dict[str, Any], result_obj)
    index = RejectedPathIndex(
        rejected_file,
        expected_count=int(result["rejected"]),
    )
    offsets_obj: object = st.session_state.viewer_offsets
    if isinstance(offsets_obj, dict):
        index.restore_offsets(cast(dict[int, int], offsets_obj))
    return index


def _load_rejected_at(index: int) -> None:
    path_index = _rejected_index_for_state()
    if path_index is None:
        st.session_state.viewer_error = "rejected.txt is unavailable for this run."
        _clear_viewer_image()
        return
    try:
        absolute = path_index.path_at(index)
    except RejectedIndexError as exc:
        st.session_state.viewer_error = str(exc)
        st.session_state.viewer_path = None
        _clear_viewer_image()
        return
    st.session_state.viewer_offsets = path_index.offsets
    st.session_state.viewer_index = index
    st.session_state.viewer_mode = "rejected"
    st.session_state.viewer_path = absolute
    _show_viewer_image(absolute)


def _ensure_viewer_initialized(result: dict[str, Any]) -> None:
    output_dir = str(result["output_dir"])
    if st.session_state.viewer_initialized_for == output_dir:
        return
    rejected_count = int(result["rejected"])
    try:
        path_index = RejectedPathIndex.open_for_run(
            output_dir,
            expected_count=rejected_count,
        )
    except RejectedIndexError as exc:
        st.session_state.viewer_initialized_for = output_dir
        st.session_state.viewer_rejected_file = None
        st.session_state.viewer_offsets = {}
        st.session_state.viewer_index = 0
        st.session_state.viewer_mode = "rejected"
        st.session_state.viewer_error = str(exc)
        st.session_state.viewer_path = None
        _clear_viewer_image()
        return

    st.session_state.viewer_initialized_for = output_dir
    st.session_state.viewer_rejected_file = str(path_index.path)
    st.session_state.viewer_offsets = {}
    st.session_state.viewer_index = 0
    st.session_state.viewer_mode = "rejected"
    st.session_state.viewer_error = None
    if rejected_count == 0:
        st.session_state.viewer_path = None
        _clear_viewer_image()
        return
    _load_rejected_at(0)


def _on_previous_rejected() -> None:
    if st.session_state.viewer_mode != "rejected":
        return
    index = int(st.session_state.viewer_index)
    if index <= 0:
        return
    _load_rejected_at(index - 1)


def _on_next_rejected() -> None:
    if st.session_state.viewer_mode != "rejected":
        return
    result_obj: object = st.session_state.last_result
    if not isinstance(result_obj, dict):
        return
    total = int(cast(dict[str, Any], result_obj)["rejected"])
    index = int(st.session_state.viewer_index)
    if index >= total - 1:
        return
    _load_rejected_at(index + 1)


def _on_open_manual() -> None:
    try:
        path = normalize_manual_path(str(st.session_state.manual_path_input))
    except PreviewImageError as exc:
        st.session_state.viewer_mode = "manual"
        st.session_state.viewer_error = str(exc)
        st.session_state.viewer_path = str(st.session_state.manual_path_input)
        _clear_viewer_image()
        return
    st.session_state.viewer_mode = "manual"
    st.session_state.viewer_path = str(path)
    _show_viewer_image(path)


def _on_back_to_rejected() -> None:
    result_obj: object = st.session_state.last_result
    if not isinstance(result_obj, dict):
        return
    rejected = int(cast(dict[str, Any], result_obj)["rejected"])
    st.session_state.viewer_mode = "rejected"
    if rejected <= 0:
        st.session_state.viewer_index = 0
        st.session_state.viewer_path = None
        st.session_state.viewer_error = None
        st.session_state.viewer_classification = None
        st.session_state.viewer_classification_error = None
        _clear_viewer_image()
        return
    # Spec: clear manual mode and display the FIRST rejected image.
    _load_rejected_at(0)


def _update_classification_label(result: dict[str, Any], mode: str) -> None:
    """Refresh saved-classification label for the currently displayed path."""
    display_path = st.session_state.viewer_path
    if not display_path:
        st.session_state.viewer_classification = None
        st.session_state.viewer_classification_error = None
        return

    cache = _decision_cache()
    if mode == "rejected":
        # Membership in rejected.txt is authoritative; never treat absence as Passed.
        st.session_state.viewer_classification = cache.label_for_rejected_membership()
        st.session_state.viewer_classification_error = None
        return

    info_obj: object = st.session_state.selected_run_info
    source_root = ""
    if isinstance(info_obj, dict):
        source_root = str(
            cast(dict[str, Any], info_obj).get("source_dataset_root", "") or ""
        )
    try:
        label = cache.label_for_manual_path(
            output_dir=str(result["output_dir"]),
            source_dataset_root=source_root,
            image_path=str(display_path),
        )
    except ClassificationLookupError as exc:
        st.session_state.viewer_classification = None
        st.session_state.viewer_classification_error = str(exc)
        return
    st.session_state.viewer_classification = label
    st.session_state.viewer_classification_error = None


def _render_image_viewer(result: dict[str, Any]) -> None:
    _ensure_viewer_initialized(result)
    rejected_count = int(result["rejected"])
    mode = str(st.session_state.viewer_mode)
    index = int(st.session_state.viewer_index)

    # Re-resolve/load only the selected rejected image on ordinary reruns so
    # missing files surface immediately without rescanning the whole list.
    if (
        mode == "rejected"
        and rejected_count > 0
        and st.session_state.viewer_rejected_file is not None
    ):
        _load_rejected_at(index)

    _update_classification_label(result, mode)

    st.subheader("Rejected image viewer")
    if rejected_count == 0 and mode == "rejected":
        st.info("No rejected images")

    nav_cols = st.columns([1, 1, 4])
    with nav_cols[0]:
        st.button(
            "Previous",
            key="viewer_prev",
            disabled=(mode != "rejected" or rejected_count == 0 or index <= 0),
            on_click=_on_previous_rejected,
        )
    with nav_cols[1]:
        st.button(
            "Next",
            key="viewer_next",
            disabled=(
                mode != "rejected"
                or rejected_count == 0
                or index >= rejected_count - 1
            ),
            on_click=_on_next_rejected,
        )
    with nav_cols[2]:
        if mode == "manual":
            st.write("Manual image")
        elif rejected_count > 0:
            st.write(f"Image {index + 1} of {rejected_count}")
        else:
            st.write("Image — of 0")

    display_path = st.session_state.viewer_path
    if display_path:
        # Escape only for HTML rendering; filesystem path in session state is unchanged.
        path_text = str(display_path)
        name = Path(path_text).name
        safe_name = html.escape(name, quote=True)
        safe_path = html.escape(path_text, quote=True)
        classification_obj: object = st.session_state.viewer_classification
        class_html = ""
        if isinstance(classification_obj, str) and classification_obj:
            class_html = (
                f" · <strong>Classification:</strong> "
                f"{html.escape(classification_obj, quote=True)}"
            )
        st.markdown(
            f"<div><strong>File:</strong> {safe_name}{class_html}</div>"
            f"<div style='word-break:break-all;white-space:normal;'>"
            f"<strong>Path:</strong> {safe_path}</div>",
            unsafe_allow_html=True,
        )

    class_error_obj: object = st.session_state.viewer_classification_error
    if class_error_obj:
        st.error(str(class_error_obj))

    if st.session_state.viewer_error:
        st.error(str(st.session_state.viewer_error))


    image_bytes_obj: object = st.session_state.viewer_image_bytes
    mime_obj: object = st.session_state.viewer_image_mime
    if isinstance(image_bytes_obj, bytes | bytearray) and isinstance(mime_obj, str):
        viewer_html = build_zoom_pan_html(bytes(image_bytes_obj), mime=mime_obj)
        components.html(viewer_html, height=480, scrolling=False)

    st.text_input("Image path", key="manual_path_input")
    manual_cols = st.columns([1, 1, 2])
    with manual_cols[0]:
        st.button("Open image", key="viewer_open_manual", on_click=_on_open_manual)
    with manual_cols[1]:
        st.button(
            "Back to rejected",
            key="viewer_back_rejected",
            on_click=_on_back_to_rejected,
            disabled=(mode != "manual"),
        )


def _apply_saved_execution(
    output_dir: Path | str,
    *,
    reset_viewer: bool,
    sync_selection_key: bool = False,
) -> None:
    """Open a saved run from export metadata only (never starts filtering)."""
    try:
        info, result = load_execution_result(output_dir)
    except RunInfoError as exc:
        st.session_state.selected_run_load_error = str(exc)
        st.session_state.selected_run_info = None
        st.session_state.last_result = None
        _reset_viewer_state()
        return
    if reset_viewer:
        _reset_viewer_state()
    st.session_state.selected_run_load_error = None
    st.session_state.selected_run_info = info
    resolved = str(Path(result["output_dir"]).resolve())
    # Only assign the selectbox key before the widget exists (or from on_change).
    if sync_selection_key:
        st.session_state.selected_run_dir = resolved
    st.session_state.last_result = result
    st.session_state.last_error = None


def _on_previous_execution_change() -> None:
    selected = st.session_state.selected_run_dir
    if not selected:
        return
    _apply_saved_execution(str(selected), reset_viewer=True, sync_selection_key=False)


def _render_saved_metadata(info: dict[str, Any], output_dir: Path | str) -> None:
    """Compact read-only summary for the selected export folder."""
    folder = Path(output_dir)
    counts = cast(dict[str, Any], info["counts"])
    st.markdown(
        f"<div style='font-size:0.95rem;line-height:1.45;'>"
        f"<strong>Saved execution</strong> "
        f"(<code>{html.escape(folder.name, quote=True)}</code>)<br/>"
        f"Date/time: {html.escape(str(info['created_at']), quote=True)} · "
        f"Status: {html.escape(str(info['status']), quote=True)}<br/>"
        f"Threshold: {html.escape(str(info['threshold']), quote=True)}<br/>"
        f"Method: {html.escape(str(info['method']), quote=True)} · "
        f"Preprocessing: {html.escape(str(info['preprocessing_version']), quote=True)} · "
        f"BlurGate {html.escape(str(info['blur_gate_version']), quote=True)}<br/>"
        f"Dataset root: "
        f"<span style='word-break:break-all;'>"
        f"{html.escape(str(info['source_dataset_root']), quote=True)}</span><br/>"
        f"Total images: {int(counts['input'])} · "
        f"Accepted: {int(counts['accepted'])} · "
        f"Rejected: {int(counts['rejected'])} · "
        f"Errors: {int(counts['error'])}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _clear_selected_execution_display() -> None:
    """Drop metadata/chart/preview so a failed selection cannot leave stale UI."""
    st.session_state.selected_run_info = None
    st.session_state.last_result = None
    _reset_viewer_state()


def _render_previous_execution_section() -> None:
    """Dropdown + metadata for reopening runs under ``blur_gate_export/``."""
    st.subheader("Previous execution")
    listed = list_saved_executions(export_root())
    executions = listed.executions
    for issue in listed.issues:
        st.warning(issue)

    if not executions:
        st.caption(f"No completed executions found under `{EXPORT_HINT}` yet.")
        if st.session_state.last_result is not None or st.session_state.selected_run_info:
            _clear_selected_execution_display()
        return

    options = [str(item.output_dir) for item in executions]
    labels = {str(item.output_dir): item.label for item in executions}

    current_obj: object = st.session_state.selected_run_dir
    current = str(current_obj) if current_obj else ""
    if current not in options:
        # Prefer the run already shown in last_result when it is still listed.
        last_obj: object = st.session_state.last_result
        preferred = ""
        if isinstance(last_obj, dict):
            preferred = str(cast(dict[str, Any], last_obj).get("output_dir", ""))
            preferred = str(Path(preferred).resolve()) if preferred else ""
        st.session_state.selected_run_dir = (
            preferred if preferred in options else options[0]
        )

    st.selectbox(
        "Select a previous execution",
        options=options,
        format_func=lambda path: labels.get(str(path), str(path)),
        key="selected_run_dir",
        on_change=_on_previous_execution_change,
        help=(
            "Opens saved results from blur_gate_export/ without filtering or "
            "rescoring source images."
        ),
    )

    selected = str(st.session_state.selected_run_dir)
    last_obj = st.session_state.last_result
    last_dir = ""
    if isinstance(last_obj, dict):
        last_dir = str(
            Path(str(cast(dict[str, Any], last_obj).get("output_dir", ""))).resolve()
        )
    if last_dir != selected:
        # Selectbox already owns selected_run_dir; do not reassign that key here.
        _apply_saved_execution(selected, reset_viewer=True, sync_selection_key=False)

    load_error_obj: object = st.session_state.selected_run_load_error
    if load_error_obj:
        st.error(str(load_error_obj))
        # Ensure chart/preview/metadata from a prior selection are not kept.
        st.session_state.selected_run_info = None
        st.session_state.last_result = None
        return

    info_obj: object = st.session_state.selected_run_info
    if not isinstance(info_obj, dict):
        try:
            st.session_state.selected_run_info = load_run_info(selected)
            info_obj = st.session_state.selected_run_info
        except RunInfoError as exc:
            st.session_state.selected_run_load_error = str(exc)
            _clear_selected_execution_display()
            st.error(str(exc))
            return
    _render_saved_metadata(cast(dict[str, Any], info_obj), selected)


def _render_completion_summary() -> None:
    result_obj: object = st.session_state.last_result
    if isinstance(result_obj, dict):
        result = cast(dict[str, Any], result_obj)
        st.success(
            f"Filtering {result['status']}: "
            f"accepted={result['accepted']}, rejected={result['rejected']}, "
            f"error={result['error']}"
        )
        st.write(f"Output folder: `{result['output_dir']}`")
        _render_completion_chart(result)
        _render_image_viewer(result)
        return

    error_obj: object = st.session_state.last_error
    if error_obj:
        st.error(str(error_obj))


def _run_filter() -> None:
    """Execute filtering once for an explicit button press."""
    st.session_state.last_result = None
    st.session_state.last_error = None
    st.session_state.job_progress_summary = None
    st.session_state.selected_run_load_error = None
    _reset_viewer_state()

    source = Path(str(st.session_state.dataset_folder)).expanduser()
    try:
        threshold = validate_threshold(st.session_state.threshold)
        cfg = make_config(threshold)
    except (ConfigError, ValueError) as exc:
        st.session_state.last_error = f"Invalid threshold: {exc}"
        st.error(st.session_state.last_error)
        return

    if not str(st.session_state.dataset_folder).strip():
        st.session_state.last_error = "Enter a dataset folder."
        st.error(st.session_state.last_error)
        return
    if not source.is_dir():
        st.session_state.last_error = f"Not a directory: {source}"
        st.error(st.session_state.last_error)
        return

    progress = st.progress(0.0, text="Reading dataset metadata…")
    status = st.empty()

    def _on_progress(update: ProgressUpdate) -> None:
        _apply_progress_widgets(progress, status, update)

    try:
        # Unique run directory + export root are prepared only for this click.
        export_root().mkdir(parents=True, exist_ok=True)
        output_dir = new_run_output_dir()
        result = filter_dataset(
            source,
            output_dir,
            cfg,
            progress_update_callback=_on_progress,
            progress_every=25,
        )
    except (DatasetFilterError, ConfigError, ValueError, OSError) as exc:
        st.session_state.last_error = f"Dataset filtering failed: {exc}"
        st.error(st.session_state.last_error)
        return

    resolved_out = str(Path(result.output_dir).resolve())
    # Set selection before the selectbox widget is created below.
    st.session_state.selected_run_dir = resolved_out
    st.session_state.last_result = {
        "status": result.status,
        "output_dir": resolved_out,
        "input": result.counts.input,
        "accepted": result.counts.accepted,
        "rejected": result.counts.rejected,
        "error": result.counts.error,
        "threshold": cfg.threshold,
    }
    try:
        st.session_state.selected_run_info = load_run_info(resolved_out)
        st.session_state.selected_run_load_error = None
    except RunInfoError as exc:
        st.session_state.selected_run_info = None
        st.session_state.selected_run_load_error = str(exc)
    # Refresh dropdown options (includes the new run) then chart/viewer.
    _render_previous_execution_section()
    _render_completion_summary()


def main() -> None:
    st.set_page_config(page_title="BlurGate", layout="centered")
    _init_state()

    st.title("BlurGate")
    st.caption(
        f"v{__version__} · method={METHOD_NAME} · "
        f"preprocessing={PREPROCESSING_VERSION} · CPU only"
    )
    st.write(
        "Images with a score below the threshold are excluded. "
        "A higher threshold rejects more images."
    )
    st.caption(
        "Metadata-only export under the fixed project folder "
        f"`{EXPORT_HINT}`. Source images are never copied or modified."
    )

    st.text_input(
        "Dataset folder",
        key="dataset_folder",
        help=(
            "Extraction output root containing images/, manifest.jsonl, "
            "run.json, and video-folder-mapping.csv."
        ),
    )
    st.number_input(
        "Threshold",
        min_value=0.0,
        step=1.0,
        format="%.4f",
        key="threshold",
    )

    run = st.button("Filter dataset", type="primary")
    if run:
        _run_filter()
    else:
        _render_previous_execution_section()
        _render_completion_summary()
        summary_obj: object = st.session_state.job_progress_summary
        if isinstance(summary_obj, dict) and st.session_state.last_result is None:
            phase = str(cast(dict[str, Any], summary_obj).get("phase", ""))
            detail = str(
                cast(dict[str, Any], summary_obj).get(
                    "detail", cast(dict[str, Any], summary_obj).get("message", "")
                )
            )
            if phase == "failed" and detail:
                st.error(detail)


if __name__ == "__main__":
    main()

