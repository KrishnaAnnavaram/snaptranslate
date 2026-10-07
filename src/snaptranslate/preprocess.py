"""Image preprocessing for OCR on NumPy arrays (no OpenCV).

Photos of signs and menus have uneven light and small text. Tesseract reads dark text on a light
background best, at a text height of about 30 pixels. These steps prepare such an image.
"""

from __future__ import annotations

import numpy as np


def to_grayscale(img: np.ndarray) -> np.ndarray:
    """RGB(A) or gray uint8 array -> 2-D float array in 0..255 (ITU-R BT.601 luma)."""
    a = np.asarray(img)
    if a.ndim == 2:
        return a.astype(np.float64)
    if a.ndim == 3 and a.shape[2] in (3, 4):
        rgb = a[..., :3].astype(np.float64)
        return rgb @ np.array([0.299, 0.587, 0.114])
    raise ValueError(f"unsupported image shape {a.shape}")


def autocontrast(gray: np.ndarray, cutoff: float = 1.0) -> np.ndarray:
    """Stretch the gray levels between the cutoff percentiles to 0..255."""
    lo, hi = np.percentile(gray, [cutoff, 100 - cutoff])
    if hi - lo < 1e-6:
        return np.clip(gray, 0, 255)
    return np.clip((gray - lo) * 255.0 / (hi - lo), 0, 255)


def otsu_threshold(gray: np.ndarray) -> float:
    """The threshold that maximises the between-class variance of the histogram."""
    hist, edges = np.histogram(np.clip(gray, 0, 255), bins=256, range=(0, 256))
    p = hist.astype(np.float64) / max(1, hist.sum())
    levels = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(p)
    w1 = 1 - w0
    mu = np.cumsum(p * levels)
    mu_t = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mu_t * w0 - mu) ** 2 / (w0 * w1)
    between[~np.isfinite(between)] = 0
    return float(levels[int(np.argmax(between))])


def binarize(gray: np.ndarray, threshold: float | None = None) -> np.ndarray:
    """Return a uint8 image with text black (0) on white (255).

    If most pixels are dark (light text on a dark sign), the image is inverted first.
    """
    t = otsu_threshold(gray) if threshold is None else threshold
    dark = gray < t
    if dark.mean() > 0.5:
        dark = ~dark
    return np.where(dark, 0, 255).astype(np.uint8)


def upscale(gray: np.ndarray, min_height: int = 600) -> np.ndarray:
    """Nearest-neighbour upscale by an integer factor until the height is at least min_height."""
    h = gray.shape[0]
    if h >= min_height or h == 0:
        return gray
    f = int(np.ceil(min_height / h))
    return np.repeat(np.repeat(gray, f, axis=0), f, axis=1)


def prepare_for_ocr(img: np.ndarray, min_height: int = 600) -> np.ndarray:
    return binarize(autocontrast(upscale(to_grayscale(img), min_height)))
