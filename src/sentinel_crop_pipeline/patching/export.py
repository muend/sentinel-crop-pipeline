"""Patch writers.

Primary output: COG (georeferenced, opens in QGIS, reproducible). Secondary:
npy (or TFRecord) derived from the same array for direct Keras/TF feeding.
NaN is replaced with 0 in training exports; use the MASK band to ignore those
pixels in the loss.
"""

import json
import logging
from pathlib import Path

import numpy as np
import rasterio

log = logging.getLogger("patching")
_cog_warned = False


def write_cog(path: str | Path, arr: np.ndarray, transform, crs,
              band_names: list[str]) -> Path:
    """Write a georeferenced patch; COG driver with tiled-GTiff fallback."""
    global _cog_warned
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    base = dict(
        count=arr.shape[0], height=arr.shape[1], width=arr.shape[2],
        dtype=str(arr.dtype), transform=transform, crs=crs,
    )
    try:
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), \
                rasterio.open(path, "w", driver="COG", compress="DEFLATE", **base) as dst:
            dst.write(arr)
            if "MASK" in band_names:
                dst.write_mask((arr[band_names.index("MASK")] > 0).astype("uint8") * 255)
            for i, n in enumerate(band_names, start=1):
                dst.set_band_description(i, n)
    except Exception:
        # Older GDAL without the COG driver: tiled GTiff is functionally close.
        if not _cog_warned:
            log.warning("COG driver unavailable, falling back to tiled GTiff")
            _cog_warned = True
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), \
                rasterio.open(path, "w", driver="GTiff", tiled=True, blockxsize=256,
                              blockysize=256, compress="deflate", **base) as dst:
            dst.write(arr)
            if "MASK" in band_names:
                dst.write_mask((arr[band_names.index("MASK")] > 0).astype("uint8") * 255)
            for i, n in enumerate(band_names, start=1):
                dst.set_band_description(i, n)
    return path


def write_npy(path: str | Path, arr: np.ndarray, meta: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.nan_to_num(arr, nan=0.0).astype(np.float32))
    Path(str(path) + ".json").write_text(json.dumps(meta, indent=2, default=str))
    return path


def write_tfrecord(path: str | Path, arr: np.ndarray, meta: dict) -> Path:
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise ImportError(
            "export_format: tfrecord requires tensorflow. "
            "pip install 'sentinel-crop-pipeline[tfrecord]' or use export_format: npy"
        ) from exc
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.nan_to_num(arr, nan=0.0).astype(np.float32)
    feature = {
        "patch": tf.train.Feature(
            float_list=tf.train.FloatList(value=data.ravel())),
        "shape": tf.train.Feature(
            int64_list=tf.train.Int64List(value=list(data.shape))),
        "meta": tf.train.Feature(bytes_list=tf.train.BytesList(
            value=[json.dumps(meta, default=str).encode()])),
    }
    example = tf.train.Example(features=tf.train.Features(feature=feature))
    with tf.io.TFRecordWriter(str(path)) as writer:
        writer.write(example.SerializeToString())
    return path
