"""Field purity, holes, grid alignment, and fail-closed patch generation."""

import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer
import rasterio
from shapely.geometry import Polygon, box, mapping
from shapely.ops import transform

from sentinel_crop_pipeline.patching.tiler import run_patching
from sentinel_crop_pipeline.patching.export import write_cog
from sentinel_crop_pipeline.cli import _download_field_crops
from sentinel_crop_pipeline.preprocessing.field_mask import field_mask_for_grid, load_fields, write_field_crop
from sentinel_crop_pipeline.preprocessing.pipeline import preprocess_scene
from tests.conftest import write_raw_scene


def field_file(tmp_path, geometry):
    geographic = transform(Transformer.from_crs(32635, 4326, always_xy=True).transform, geometry)
    path = tmp_path / "fields.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(geographic),
         "properties": {"field_id": "SYNTHETIC", "map_address": "Synthetic field"}}
    ]}), encoding="utf-8")
    return path


def assert_pixel_footprints_inside(mask, affine, geometry):
    for row, col in zip(*np.where(mask)):
        corners = [affine * (col + dc, row + dr) for dc, dr in ((0, 0), (1, 0), (1, 1), (0, 1))]
        assert geometry.buffer(1e-6).covers(Polygon(corners))


def test_strict_mask_excludes_boundary_and_hole_cells(tmp_path):
    raw = write_raw_scene(tmp_path / "raw.tif")
    polygon = Polygon([(500080, 4249440), (500560, 4249440), (500500, 4249920), (500080, 4249920)],
                      holes=[[(500200, 4249700), (500300, 4249700),
                              (500300, 4249800), (500200, 4249800)]])
    path = field_file(tmp_path, polygon)
    with rasterio.open(raw) as src:
        mask = field_mask_for_grid(load_fields(path), src.crs, src.transform, (src.height, src.width))
        assert mask.any() and not mask[0].any() and not mask[25, 25]
        assert_pixel_footprints_inside(mask, src.transform, polygon)


def test_field_preprocessing_combines_cloud_and_geometric_masks(tmp_path, base_cfg):
    raw = write_raw_scene(tmp_path / "raw.tif", cloud_rows=32)
    path = field_file(tmp_path, box(500080, 4249440, 500560, 4249920))
    base_cfg["preprocessing"]["field_mask_path"] = str(path)
    out = tmp_path / "stack.tif"
    names = preprocess_scene(raw, out, base_cfg)
    with rasterio.open(out) as src:
        data = src.read()
        field = data[names.index("FIELD_MASK")] > 0
        keep = data[names.index("MASK")] > 0
        assert field.any() and keep.any()
        assert not keep[:32].any() and not np.any(keep & ~field)
        assert np.isnan(data[0, ~keep]).all()
        assert (src.dataset_mask() > 0).tolist() == keep.tolist()


def test_crop_preserves_source_and_contains_only_full_field_pixels(tmp_path):
    raw = write_raw_scene(tmp_path / "raw.tif")
    before = hashlib.sha256(raw.read_bytes()).hexdigest()
    polygon = box(500080, 4249440, 500560, 4249920)
    path = field_file(tmp_path, polygon)
    out = tmp_path / "field.tif"
    record = write_field_crop(raw, out, path, "SYNTHETIC")
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == before == record["source_sha256"]
    with rasterio.open(out) as src:
        keep = src.dataset_mask() > 0
        assert src.width < 64 and src.height < 64 and src.res == (10, 10)
        assert_pixel_footprints_inside(keep, src.transform, polygon)
        assert np.all(src.read(1)[keep] == 5000)
        assert keep.sum() == record["retained_pixels"]
        assert src.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"
    assert record == write_field_crop(raw, out, path, "SYNTHETIC")


def test_empty_or_nonpolygon_field_input_fails(tmp_path):
    path = tmp_path / "points.geojson"
    path.write_text(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [10, 50]},
                                "properties": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="polygons"):
        load_fields(path)


def test_field_only_patching_rejects_old_stack_then_accepts_only_field_windows(tmp_path, base_cfg):
    raw = write_raw_scene(tmp_path / "raw.tif")
    folder = tmp_path / "interim"
    folder.mkdir()
    stack = folder / "stack.tif"
    base_cfg["preprocessing"]["out_dir"] = str(folder)
    base_cfg["patching"].update(require_field_mask=True, min_field_fraction=1.0,
        patch_size=8, stride=8, cog_dir=str(tmp_path / "cog"), train_dir=str(tmp_path / "npy"),
        index_file=str(tmp_path / "index.csv"))
    preprocess_scene(raw, stack, base_cfg)
    with pytest.raises(ValueError, match="FIELD_MASK required"):
        run_patching(base_cfg)
    fields = field_file(tmp_path, box(500080, 4249440, 500560, 4249920))
    base_cfg["preprocessing"]["field_mask_path"] = str(fields)
    preprocess_scene(raw, stack, base_cfg)
    records = run_patching(base_cfg)
    assert 0 < len(records) < 64
    for record in records:
        with rasterio.open(record["cog_path"]) as src:
            field = src.read(src.descriptions.index("FIELD_MASK") + 1)
            assert np.all(field == 1)


def test_download_persists_only_field_crops_and_discards_context(tmp_path):
    fields = field_file(tmp_path, box(500080, 4249440, 500560, 4249920))
    temporary_sources = []

    class OfflineProvider:
        def download(self, scene, aoi, bands, out_dir, **kwargs):
            path = write_raw_scene(Path(out_dir) / "context.tif")
            temporary_sources.append(path)
            return path

    output = tmp_path / "dataset"
    paths = _download_field_crops(OfflineProvider(), SimpleNamespace(id="SCENE"), None,
                                 ["B02", "B03", "B04", "B08"], output, fields, 10, False)
    assert len(paths) == 1 and paths[0].name == "SCENE_SYNTHETIC.tif"
    assert not temporary_sources[0].exists()
    assert not (output / "context.tif").exists()
    with rasterio.open(paths[0]) as src:
        assert src.width < 64 and src.height < 64 and src.tags()["field_only"] == "true"


def test_patch_cog_exposes_combined_mask_to_gis(tmp_path):
    raw = write_raw_scene(tmp_path / "raw.tif", size=8)
    arr = np.ones((2, 8, 8), dtype="float32")
    arr[0, :4] = np.nan
    arr[1, :4] = 0
    with rasterio.open(raw) as src:
        result = write_cog(tmp_path / "patch.tif", arr, src.transform, src.crs, ["B02", "MASK"])
    with rasterio.open(result) as src:
        assert not src.dataset_mask()[:4].any() and src.dataset_mask()[4:].all()
