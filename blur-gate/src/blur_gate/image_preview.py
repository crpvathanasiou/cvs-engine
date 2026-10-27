"""Helpers for BlurGate UI image preview (load bytes + browser zoom HTML)."""

from __future__ import annotations

import base64
import html
from pathlib import Path

import cv2
import numpy as np

from blur_gate.scoring import SUPPORTED_SUFFIXES

IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class PreviewImageError(ValueError):
    """Readable failure while opening a preview image."""


def normalize_manual_path(raw: str) -> Path:
    """Strip optional quotes and expand a user-supplied Windows/Unix path."""
    text = str(raw).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    if not text:
        raise PreviewImageError("Enter an image path.")
    return Path(text).expanduser()


def load_preview_bytes(path: Path | str) -> tuple[bytes, str, Path]:
    """Load original image bytes for embedding after a decode check.

    Validates PNG/JPG/JPEG with OpenCV ``imdecode`` but returns the untouched
    file bytes (no re-encode / rewrite of the source).
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise PreviewImageError(f"Image file not found: {file_path}")
    suffix = file_path.suffix
    if suffix not in SUPPORTED_SUFFIXES:
        raise PreviewImageError(
            f"Unsupported image type {suffix!r}; expected PNG/JPG/JPEG"
        )
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        raise PreviewImageError(f"Could not read image: {exc}") from exc
    if not data:
        raise PreviewImageError(f"Image file is empty: {file_path}")
    mime = IMAGE_MIME.get(suffix.lower())
    if mime is None:
        raise PreviewImageError(
            f"Unsupported image type {suffix!r}; expected PNG/JPG/JPEG"
        )
    # Decode-check only; do not use the decoded array for display.
    buffer = np.frombuffer(data, dtype=np.uint8)
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise PreviewImageError(f"Unreadable or corrupt image: {file_path}")
    return data, mime, file_path.resolve()


def build_zoom_pan_html(
    image_bytes: bytes,
    *,
    mime: str,
    viewport_height: int = 420,
) -> str:
    """Return self-contained HTML for Fit / Zoom± / drag-pan (no Python round-trip)."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    src = f"data:{mime};base64,{encoded}"
    # Escape is unnecessary for base64 but keeps the template safe if mime changes.
    safe_src = html.escape(src, quote=True)
    height = max(200, int(viewport_height))
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {{ margin: 0; font-family: system-ui, sans-serif; background: #111; color: #eee; }}
  .toolbar {{
    display: flex; gap: 8px; align-items: center; padding: 8px;
    background: #1e1e1e; border-bottom: 1px solid #333;
  }}
  .toolbar button {{
    background: #333; color: #eee; border: 1px solid #555; border-radius: 4px;
    padding: 4px 10px; cursor: pointer;
  }}
  .toolbar button:hover {{ background: #444; }}
  #viewport {{
    position: relative; width: 100%; height: {height}px; overflow: hidden;
    cursor: grab; background: #000;
    user-select: none;
  }}
  #viewport.dragging {{ cursor: grabbing; }}
  #stage {{
    position: absolute; left: 50%; top: 50%;
    transform-origin: center center;
    will-change: transform;
  }}
  #stage img {{
    display: block; max-width: none; pointer-events: none;
  }}
</style>
</head>
<body>
  <div class="toolbar">
    <button type="button" id="zoomOut">Zoom −</button>
    <button type="button" id="zoomIn">Zoom +</button>
    <button type="button" id="fit">Fit</button>
    <span id="zoomLabel">100%</span>
  </div>
  <div id="viewport">
    <div id="stage"><img id="img" src="{safe_src}" alt="preview" /></div>
  </div>
<script>
(function() {{
  const viewport = document.getElementById('viewport');
  const stage = document.getElementById('stage');
  const img = document.getElementById('img');
  const zoomLabel = document.getElementById('zoomLabel');
  let scale = 1, tx = 0, ty = 0;
  let dragging = false, lastX = 0, lastY = 0;

  function apply() {{
    stage.style.transform =
      'translate(-50%, -50%) translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
    zoomLabel.textContent = Math.round(scale * 100) + '%';
  }}

  function fit() {{
    const nw = img.naturalWidth || 1;
    const nh = img.naturalHeight || 1;
    const vw = viewport.clientWidth;
    const vh = viewport.clientHeight;
    scale = Math.min(vw / nw, vh / nh);
    if (!isFinite(scale) || scale <= 0) scale = 1;
    tx = 0; ty = 0;
    apply();
  }}

  function zoomBy(factor) {{
    scale = Math.min(16, Math.max(0.05, scale * factor));
    apply();
  }}

  img.onload = fit;
  if (img.complete) fit();

  document.getElementById('zoomIn').onclick = function() {{ zoomBy(1.25); }};
  document.getElementById('zoomOut').onclick = function() {{ zoomBy(0.8); }};
  document.getElementById('fit').onclick = fit;

  viewport.addEventListener('mousedown', function(e) {{
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    viewport.classList.add('dragging');
    e.preventDefault();
  }});
  window.addEventListener('mouseup', function() {{
    dragging = false; viewport.classList.remove('dragging');
  }});
  window.addEventListener('mousemove', function(e) {{
    if (!dragging) return;
    tx += e.clientX - lastX;
    ty += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    apply();
  }});
  viewport.addEventListener('wheel', function(e) {{
    e.preventDefault();
    zoomBy(e.deltaY < 0 ? 1.1 : 0.9);
  }}, {{ passive: false }});
}})();
</script>
</body>
</html>
"""
