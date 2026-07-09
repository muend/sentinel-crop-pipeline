"""Rasterize label polygons onto the existing patch grid.

For every patch in index.csv, polygons are burned into a uint8 mask aligned to
the patch transform/CRS (background = 0). Class ids come from the sorted set of
labels and are written to <out_dir>/class_map.json. index.csv gains a
label_path column.
"""

import csv
import json
import logging
from pathlib import Path

import numpy as np
import pyproj
import rasterio
from rasterio.features import rasterize as rio_rasterize
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

from .base import LabelSourceError
from .cks import CksImportSource
from .vector import VectorLabelSource

log = logging.getLogger("labeling")


def get_label_source(cfg: dict):
    lcfg = cfg.get("labeling", {})
    source = str(lcfg.get("source", "vector")).lower()
    attribute = lcfg.get("attribute", "crop_type")
    if source == "vector":
        return VectorLabelSource(lcfg.get("vector_path",
                                          "data/labels/parcels.geojson"), attribute)
    if source == "cks":
        return CksImportSource(lcfg.get("cks_import_dir",
                                        "data/raw/cks_import"), attribute)
    raise LabelSourceError(f"Unknown labeling.source '{source}' (vector | cks)")


def build_class_map(features: list[tuple[dict, str]]) -> dict[str, int]:
    """label -> id, 1-based; 0 is background."""
    return {label: i for i, label in
            enumerate(sorted({lab for _, lab in features}), start=1)}


def _shapes_in_crs(features, class_map, dst_crs) -> list[tuple]:
    tr = pyproj.Transformer.from_crs("EPSG:4326", str(dst_crs),
                                     always_xy=True).transform
    return [(shp_transform(tr, shape(geom)), class_map[label])
            for geom, label in features]


def run_labeling(cfg: dict, logger=None) -> list[dict]:
    lcfg = cfg.get("labeling", {})
    out_dir = Path(lcfg.get("out_dir", "data/patches/labels"))
    all_touched = bool(lcfg.get("all_touched", False))
    index_file = Path(cfg.get("patching", {})
                      .get("index_file", "data/patches/index.csv"))
    if not index_file.exists():
        raise LabelSourceError(f"{index_file} not found; run `patch` first")

    features = get_label_source(cfg).features()
    class_map = build_class_map(features)

    with open(index_file) as f:
        records = list(csv.DictReader(f))

    shapes_cache: dict[str, list] = {}
    labeled = 0
    empty = 0
    for rec in records:
        with rasterio.open(rec["cog_path"]) as patch:
            crs_key = str(patch.crs)
            if crs_key not in shapes_cache:
                shapes_cache[crs_key] = _shapes_in_crs(features, class_map,
                                                       patch.crs)
            shapes = shapes_cache[crs_key]
            mask = rio_rasterize(
                shapes, out_shape=(patch.height, patch.width),
                transform=patch.transform, fill=0, dtype="uint8",
                all_touched=all_touched)
            profile = dict(driver="GTiff", height=patch.height,
                           width=patch.width, count=1, dtype="uint8",
                           crs=patch.crs, transform=patch.transform,
                           compress="deflate")
        label_path = out_dir / rec["scene"] / f"{rec['patch_id']}_label.tif"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(label_path, "w", **profile) as dst:
            dst.write(mask[None])
        np.save(str(label_path).replace(".tif", ".npy"), mask)
        rec["label_path"] = label_path.as_posix()   # portable index paths
        labeled += 1
        if mask.max() == 0:
            empty += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "class_map.json").write_text(
        json.dumps({"background": 0, **class_map}, indent=2))

    fieldnames = list(records[0].keys()) if records else []
    with open(index_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    if logger:
        logger.set_summary(patches_labeled=labeled,
                           patches_without_labels=empty,
                           classes=class_map,
                           class_map_file=str(out_dir / "class_map.json"))
    return records
