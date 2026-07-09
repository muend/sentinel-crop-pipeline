import csv
import json

import numpy as np
import pyproj
import pytest
import rasterio

from src.labeling import CksImportSource, LabelSourceError, VectorLabelSource
from src.labeling.rasterize import build_class_map, run_labeling
from src.patching.tiler import run_patching
from src.preprocessing.pipeline import preprocess_scene
from tests.conftest import write_raw_scene

# Scene grid (see conftest): EPSG:32635, origin (500000, 4250000), 64x64 @10m.
_TO_WGS84 = pyproj.Transformer.from_crs("EPSG:32635", "EPSG:4326",
                                        always_xy=True).transform


def _utm_rect_as_wgs84(x0, y0, x1, y1):
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return [[list(_TO_WGS84(x, y)) for x, y in corners]]


def _parcels_geojson(path):
    """Two parcels: tomato over the NW patch, maize over the SE patch."""
    features = [
        {"type": "Feature",
         "properties": {"crop_type": "tomato"},
         "geometry": {"type": "Polygon",
                      "coordinates": _utm_rect_as_wgs84(
                          500000, 4249680, 500320, 4250000)}},
        {"type": "Feature",
         "properties": {"crop_type": "maize"},
         "geometry": {"type": "Polygon",
                      "coordinates": _utm_rect_as_wgs84(
                          500320, 4249360, 500640, 4249680)}},
        {"type": "Feature",                      # skipped: no crop_type
         "properties": {"note": "unlabeled"},
         "geometry": {"type": "Polygon",
                      "coordinates": _utm_rect_as_wgs84(
                          500000, 4249360, 500050, 4249400)}},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection",
                                "features": features}))
    return path


def _prepare(tmp_path, base_cfg):
    cfg = dict(base_cfg)
    cfg["download"] = dict(base_cfg["download"], out_dir=str(tmp_path / "raw"))
    cfg["preprocessing"] = dict(base_cfg["preprocessing"],
                                out_dir=str(tmp_path / "interim"))
    cfg["patching"] = dict(
        base_cfg["patching"],
        cog_dir=str(tmp_path / "patches/cog"),
        train_dir=str(tmp_path / "patches/train"),
        index_file=str(tmp_path / "patches/index.csv"),
    )
    cfg["labeling"] = dict(
        base_cfg["labeling"],
        vector_path=str(_parcels_geojson(tmp_path / "labels/parcels.geojson")),
        out_dir=str(tmp_path / "patches/labels"),
    )
    raw = write_raw_scene(tmp_path / "raw" / "scene1.tif", size=64)
    preprocess_scene(raw, tmp_path / "interim" / "scene1_stack.tif", cfg)
    run_patching(cfg)   # 4 patches of 32x32
    return cfg


def test_vector_source_reads_and_skips_unlabeled(tmp_path):
    path = _parcels_geojson(tmp_path / "parcels.geojson")
    feats = VectorLabelSource(path).features()
    assert len(feats) == 2
    assert {label for _, label in feats} == {"tomato", "maize"}


def test_vector_source_missing_attribute(tmp_path):
    path = _parcels_geojson(tmp_path / "parcels.geojson")
    with pytest.raises(LabelSourceError, match="no features with attribute"):
        VectorLabelSource(path, attribute="species").features()


def test_class_map_is_deterministic():
    feats = [({}, "tomato"), ({}, "maize"), ({}, "tomato")]
    assert build_class_map(feats) == {"maize": 1, "tomato": 2}


def test_run_labeling_writes_aligned_masks(tmp_path, base_cfg):
    cfg = _prepare(tmp_path, base_cfg)
    records = run_labeling(cfg)
    assert all(r.get("label_path") for r in records)

    class_map = json.loads(
        (tmp_path / "patches/labels/class_map.json").read_text())
    assert class_map == {"background": 0, "maize": 1, "tomato": 2}

    by_id = {r["patch_id"]: r for r in records}
    nw = by_id["scene1_stack_r0_c0"]        # tomato parcel
    se = by_id["scene1_stack_r32_c32"]      # maize parcel
    with rasterio.open(nw["label_path"]) as src:
        nw_mask = src.read(1)
        with rasterio.open(nw["cog_path"]) as patch:
            assert src.transform == patch.transform and src.crs == patch.crs
    with rasterio.open(se["label_path"]) as src:
        se_mask = src.read(1)

    # reprojection edges aside, each parcel dominates its patch
    assert (nw_mask == 2).mean() > 0.9
    assert (se_mask == 1).mean() > 0.9
    npy = np.load(nw["label_path"].replace(".tif", ".npy"))
    assert npy.shape == (32, 32) and npy.dtype == np.uint8

    # index.csv rewritten with label_path
    with open(cfg["patching"]["index_file"]) as f:
        rows = list(csv.DictReader(f))
    assert all("label_path" in r and r["label_path"] for r in rows)


def test_run_labeling_requires_patch_index(tmp_path, base_cfg):
    cfg = dict(base_cfg)
    cfg["patching"] = dict(base_cfg["patching"],
                           index_file=str(tmp_path / "missing.csv"))
    with pytest.raises(LabelSourceError, match="run `patch` first"):
        run_labeling(cfg)


def test_cks_source_requires_manual_import(tmp_path):
    src = CksImportSource(import_dir=tmp_path / "cks_import")
    (tmp_path / "cks_import").mkdir()
    with pytest.raises(LabelSourceError, match="official permission"):
        src.features()


def test_cks_source_reads_manual_export(tmp_path):
    import_dir = tmp_path / "cks_import"
    _parcels_geojson(import_dir / "cks_export.geojson")
    feats = CksImportSource(import_dir=import_dir).features()
    assert len(feats) == 2
