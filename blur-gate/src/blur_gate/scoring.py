"""Shared sharpness scoring (Streamlit-independent).

v1 preprocessing
----------------
1. Decode supported PNG/JPG/JPEG as 8-bit BGR (OpenCV ``imread`` / ndarray BGR).
2. Convert to grayscale with ``cv2.COLOR_BGR2GRAY``.
3. Compute Laplacian variance with ``cv2.Laplacian(..., ddepth=cv2.CV_64F, ksize=1,
   borderType=cv2.BORDER_REFLECT_101)``.

Scoring uses the **native** image resolution. Do not resize, sharpen, denoise, or
otherwise enhance the image before scoring. UI preview resizing must not affect this
path. Changing resolution or preprocessing requires threshold reassessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import numpy.typing as npt

METHOD_NAME = "laplacian_variance"
PREPROCESSING_VERSION = "v1_native_gray_laplacian_k1_reflect101"

# Explicit border mode for Laplacian (documented; matches common OpenCV default).
LAPLACIAN_BORDER_MODE = cv2.BORDER_REFLECT_101
LAPLACIAN_KSIZE = 1

SUPPORTED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"})


class ImageReadError(Exception):
    """Raised when an image cannot be decoded. Distinct from blur rejection."""


@dataclass(frozen=True, slots=True)
class SharpnessResult:
    """Sharpness measurement for one image (no threshold decision)."""

    sharpness_score: float
    width: int
    height: int
    method: str = METHOD_NAME
    preprocessing_version: str = PREPROCESSING_VERSION


def score_bgr(image_bgr: npt.NDArray[np.uint8]) -> SharpnessResult:
    """Score an in-memory 8-bit BGR image at native resolution.

    Parameters
    ----------
    image_bgr:
        HxWx3 uint8 BGR array (OpenCV convention). Grayscale 2-D arrays are rejected
        so callers use one shared BGR path.
    """
    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("image_bgr must have shape (H, W, 3)")
    if image_bgr.dtype != np.uint8:
        raise ValueError("image_bgr must be dtype uint8 (8-bit)")

    height, width = int(image_bgr.shape[0]), int(image_bgr.shape[1])
    if height < 1 or width < 1:
        raise ValueError("image_bgr must have positive height and width")

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(
        gray,
        ddepth=cv2.CV_64F,
        ksize=LAPLACIAN_KSIZE,
        borderType=LAPLACIAN_BORDER_MODE,
    )
    score = float(np.asarray(laplacian).var())
    return SharpnessResult(
        sharpness_score=score,
        width=width,
        height=height,
    )


def load_bgr(path: Path | str) -> npt.NDArray[np.uint8]:
    """Load a supported image file as 8-bit BGR, or raise ``ImageReadError``."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ImageReadError(f"File not found: {file_path}")
    if file_path.suffix not in SUPPORTED_SUFFIXES:
        raise ImageReadError(f"Unsupported image suffix: {file_path.suffix}")

    # IMREAD_COLOR → 8-bit BGR; fails closed on unreadable bytes.
    image = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ImageReadError(f"Unreadable or corrupt image: {file_path}")
    array = np.asarray(image)
    if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3:
        raise ImageReadError(f"Unexpected decoded layout for: {file_path}")
    return cast(npt.NDArray[np.uint8], array)


def score_file(path: Path | str) -> SharpnessResult:
    """Load a file and score it with the same path as ``score_bgr``."""
    return score_bgr(load_bgr(path))
