"""Preprocessing: SCL mask -> normalize -> indices -> float32 stack.

Input: data/raw/<scene>.tif written by the download stage (bands + SCL, with
band descriptions). Output: data/interim/<scene>_stack.tif, float32, where
invalid pixels are NaN (masked, not deleted — keeps time series aligned) and a
MASK band (1 valid / 0 invalid) is appended for downstream filtering.
"""

import logging
from pathlib import Path

import numpy as np
import rasterio

from src.preprocessing import indices as idx
from src.preprocessing import normalize as norm
from src.preprocessing.scl_mask import DEFAULT_INVALID_CLASSES, valid_mask

log = logging.getLogger("preprocess")


def preprocess_scene(in_path: str | Path, out_path: str | Path, cfg: dict) -> list[str]:
    """Process one downloaded scene stack. Returns the output band names."""
    with rasterio.open(in_path) as src:
        descriptions = [d or f"band_{i}" for i, d in enumerate(src.descriptions, 1)]
        data = src.read()
        profile = src.profile

    if "SCL" not in descriptions:
        raise ValueError(f"{in_path}: no SCL band found; cannot mask clouds")
    scl = data[descriptions.index("SCL")]
    band_names = [d for d in descriptions if d != "SCL"]
    bands = data[[descriptions.index(b) for b in band_names]].astype(np.float32)

    mask = valid_mask(
        scl, tuple(cfg.get("scl_filter", {}).get("invalid_classes",
                                                 DEFAULT_INVALID_CLASSES)))
    bands[:, ~mask] = np.nan

    mode = cfg.get("preprocessing", {}).get("normalization", "reflectance")
    if mode == "reflectance":
        bands = norm.reflectance(bands)
    elif mode == "minmax":
        bands = norm.minmax(bands)
    else:
        raise ValueError(f"Unknown normalization '{mode}' (reflectance | minmax)")

    out_names = list(band_names)
    for name in cfg.get("preprocessing", {}).get("indices", []) or []:
        name = str(name).upper()
        if name not in idx.INDEX_BANDS:
            log.warning("unknown index %s, skipping", name)
            continue
        b1, b2, fn = idx.INDEX_BANDS[name]
        if b1 not in out_names or b2 not in out_names:
            log.warning("%s needs bands %s/%s not in stack, skipping", name, b1, b2)
            continue
        arr = fn(bands[out_names.index(b1)], bands[out_names.index(b2)])
        bands = np.concatenate([bands, arr[None]], axis=0)
        out_names.append(name)

    bands = np.concatenate([bands, mask.astype(np.float32)[None]], axis=0)
    out_names.append("MASK")

    profile.update(count=len(out_names), dtype="float32", nodata=None)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(bands)
        for i, n in enumerate(out_names, start=1):
            dst.set_band_description(i, n)
    return out_names


def run_preprocess(cfg: dict, logger=None) -> list[Path]:
    raw_dir = Path(cfg.get("download", {}).get("out_dir", "data/raw"))
    out_dir = Path(cfg.get("preprocessing", {}).get("out_dir", "data/interim"))
    inputs = sorted(raw_dir.glob("*.tif"))
    outputs = []
    for tif in inputs:
        out = out_dir / f"{tif.stem}_stack.tif"
        names = preprocess_scene(tif, out, cfg)
        outputs.append(out)
        if logger:
            logger.event("preprocessed", scene=tif.stem, bands=names, output=str(out))
    if logger:
        logger.set_summary(scenes_in=len(inputs), scenes_out=len(outputs))
    return outputs
