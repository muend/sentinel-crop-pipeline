"""Reflectance normalization to [0, 1]. NaN (masked) pixels pass through."""

import numpy as np

REFLECTANCE_SCALE = 10000.0  # standard S2 L2A DN -> reflectance divisor


def reflectance(arr: np.ndarray) -> np.ndarray:
    """Fixed scale: DN / 10000, clipped to [0, 1]."""
    return np.clip(arr / REFLECTANCE_SCALE, 0.0, 1.0).astype(np.float32)


def minmax(arr: np.ndarray) -> np.ndarray:
    """Per-band min-max over valid (non-NaN) pixels. arr shape: (bands, h, w)."""
    out = np.full(arr.shape, np.nan, dtype=np.float32)
    for i in range(arr.shape[0]):
        band = arr[i]
        if np.all(np.isnan(band)):
            continue
        lo, hi = np.nanmin(band), np.nanmax(band)
        out[i] = (band - lo) / (hi - lo) if hi > lo else np.zeros_like(band)
    return out
