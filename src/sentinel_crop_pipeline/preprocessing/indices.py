"""Spectral indices. Inputs are reflectance arrays; NaN marks masked pixels."""

import numpy as np


def _safe_ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    num, den = a - b, a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(den) > 1e-12, num / den, np.nan)
    return out.astype(np.float32)


def ndvi(nir, red):
    return _safe_ratio(nir, red)


def ndre(nir, rededge):
    # Red-edge index (B05); cf. Bantchina & Gundogdu (2024) for crop mapping use.
    return _safe_ratio(nir, rededge)


def ndwi(green, nir):
    return _safe_ratio(green, nir)


# name -> (band_arg_1, band_arg_2, fn); fn(band_1, band_2)
INDEX_BANDS = {
    "NDVI": ("B08", "B04", ndvi),
    "NDRE": ("B08", "B05", ndre),
    "NDWI": ("B03", "B08", ndwi),
}
