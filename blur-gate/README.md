# BlurGate — Deterministic Blur Filter

Small, standalone CPU tool for filtering excessively blurry images from a surgical-video extraction dataset.

It measures **image sharpness only** (variance of the Laplacian). It does **not** predict CVS, use CVS labels, or treat rejection as CVS = 0.

**Fundamental rule:** source images exist once under the extraction output. BlurGate reads them in place and writes **metadata only** describing the accepted subset. It never copies, moves, renames, deletes, re-encodes, or modifies source images, and never creates an output `images/` directory, hard links, or symbolic links.

## UI workflow

1. Launch the UI.
2. Enter the **Dataset folder** (extraction root with `images/`, `manifest.jsonl`, `run.json`, `video-folder-mapping.csv`).
3. Enter a **Threshold**.
4. Click **Filter dataset** once (editing inputs does not start a run).

Images with a score below the threshold are excluded. A higher threshold rejects more images.

Each run writes a unique folder under the fixed project path:

```text
<blur-gate project root>/blur_gate_export/<YYYYMMDD_HHMMSS>_<id>/
```

That export root is resolved from the application location (not the current working directory) and is not user-editable. Previous runs are preserved. Outputs:

| File | Role |
| --- | --- |
| `manifest.jsonl` | Accepted source records only (source-relative paths preserved) |
| `results.csv` | One row per input: `image_id`, `path`, `sharpness_score`, `decision`, `reason` |
| `rejected.txt` | UTF-8 plain text: one absolute path per rejected image (manifest order); empty if none |
| `video-folder-mapping.csv` | Videos with ≥1 accepted image |
| `run.json` | Filter report with threshold, provenance, and counts |
| `blur_gate_info.json` | Compact saved-execution metadata for UI reopen (derived from the run report) |

`rejected.txt` lists only `reject` decisions (score < threshold). Accepted images and scoring/read errors are omitted; errors remain in `results.csv`. Paths resolve against the original source dataset root.

There is no `accepted.csv`. Progress shows processed/total, percent, current path, elapsed time, speed, and ETA. 100% appears only after successful finalization.

The UI keeps the dataset/threshold inputs for starting a **new** filter run. Below them, a **Previous execution** dropdown lists completed folders under `blur_gate_export/` (newest first, labeled with date/time, threshold, and folder name). Selecting one opens that run’s saved results without filtering or rescoring. A compact read-only metadata summary (status, threshold, method/version, dataset root, counts) appears directly under the dropdown. Older folders missing `blur_gate_info.json` get it derived once from their existing `run.json` (other export files are left untouched). Failed or incomplete runs are not shown as completed results.

After a successful run, the UI shows an Accept/Reject pie chart (green/red) from the stored counts, plus **Total scanned files** (input count). Errors are listed separately and are not part of the pie. The new run is selected automatically in the dropdown.

Below the chart, the **Rejected image viewer** reads that run’s `rejected.txt` automatically (first image, then Previous/Next in file order). Zoom + / Zoom − / Fit and drag-pan run in the browser without re-filtering. An optional Image path + Open image control supports a one-off manual PNG/JPG view; **Back to rejected** returns to image 1 of N. Switching executions resets the viewer to that run’s first rejected image and exits manual mode.

## Method (v1)

1. Decode PNG/JPG/JPEG as 8-bit BGR.
2. Convert to grayscale.
3. Compute Laplacian variance with `cv2.CV_64F`, `ksize=1`, and `borderType=cv2.BORDER_REFLECT_101`.
4. Lower scores indicate lower measured sharpness.
5. Reject when `sharpness_score < threshold`; **accept at equality**.

Scoring uses **native resolution**. This is a sharpness **heuristic**. No default threshold is claimed as calibrated for surgical images.

## Requirements

- Python 3.11
- Poetry

## Install (Windows PowerShell)

```powershell
cd blur-gate
poetry config virtualenvs.in-project true
poetry install
```

## Launch UI

```powershell
cd blur-gate
poetry run streamlit run ui/app.py
```

## Quality checks

```powershell
cd blur-gate
poetry run python -m pytest
poetry run ruff check .
poetry run pyright
```

## Source dataset contract (input)

| File | Role |
| --- | --- |
| `run.json` | Extraction report (`schema_version: "2"`, `pipeline_name: frame_extraction`, workbook identity, videos[], segments[], `counts.images_exported`) |
| `manifest.jsonl` | **Authoritative** image list |
| `video-folder-mapping.csv` | Columns `OriginalVideo`, `ImageFolder` (UTF-8 with or without BOM) |
| `images/<video_id>/<segment_id>/<original_filename>` | Source pixels |

Manifest `path` values are relative to the source dataset root. Stage 1 should resolve images against that source root, not the metadata export folder.

The full-manifest row count must equal `run.json` → `counts.images_exported`.

## Python API (sketch)

```python
from blur_gate import filter_dataset, make_config

result = filter_dataset(
    r"D:\datasets\cholec80_extracted",
    r"D:\datasets\cholec80_blur_meta_t120",
    make_config(120.0),
)
print(result.status, result.counts)
```

## Out of scope

- CVS Engine / Stage 1 / Stage 2 wiring
- Multiprocessing, GPU, cloud SDKs, databases
- Automatic surgical threshold recommendation
- Copying images into the filter output
