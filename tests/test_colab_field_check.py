"""Reject mismatched field/address records and shifted review rasters offline."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box, mapping

from sentinel_crop_pipeline.discovery.providers.cdse import CdseProvider

_SPEC = importlib.util.spec_from_file_location(
    "colab_field_check", Path(__file__).resolve().parents[1] / "notebooks/colab_field_check.py"
)
review = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(review)


def field_record(tmp_path, geometry=None, point=(10.001, 50.001)):
    feature = {"type": "Feature", "geometry": mapping(geometry if geometry is not None else box(10, 50, 10.002, 50.002)),
               "properties": {"field_id": "SYNTHETIC-01", "map_address": "Synthetic test area",
                              "reference_longitude": point[0], "reference_latitude": point[1]}}
    path = tmp_path / "field.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    return path


def test_rejects_candidate_point_as_field(tmp_path):
    with pytest.raises(ValueError, match="valid polygon"):
        review.load_field(field_record(tmp_path, Point(10.001, 50.001)))


def test_rejects_address_point_outside_field(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        review.load_field(field_record(tmp_path, point=(11, 51)))


def test_metadata_search_transmits_public_region_only(tmp_path, monkeypatch):
    field_path = field_record(tmp_path)
    public_region = box(9, 49, 11, 51)
    public_path = tmp_path / "public.geojson"
    public_path.write_text(json.dumps(mapping(public_region)), encoding="utf-8")
    transmitted = []

    class MetadataOnlyProvider:
        def __init__(self, config):
            pass

        def search(self, region, *args, **kwargs):
            transmitted.append(region)
            return []

    monkeypatch.setattr(review, "CdseProvider", MetadataOnlyProvider)
    with pytest.raises(ValueError, match="No scene"):
        review.main(["--aoi", str(field_path), "--catalog-aoi", str(public_path),
                     "--reference-date", "2026-06-09"])
    assert len(transmitted) == 1 and transmitted[0].equals(public_region)


def test_context_covers_field_and_raster_shift_is_rejected(tmp_path):
    _, polygon = review.load_field(field_record(tmp_path))
    context, area = review.context_window(polygon)
    assert context.covers(polygon) and area > 0
    provider = CdseProvider()
    epsg, bounds, width, height = provider._utm_bbox(context, 10)
    bands = ["B02", "B03", "B04", "B08"]
    for shift in (0, 10):
        raster = tmp_path / f"context_{shift}.tif"
        with rasterio.open(raster, "w", driver="GTiff", width=width, height=height, count=5,
                           dtype="uint16", crs=f"EPSG:{epsg}",
                           transform=from_origin(bounds[0] + shift, bounds[3], 10, 10)) as dst:
            data = np.full((5, height, width), 1000, dtype="uint16")
            data[4] = 4
            dst.write(data)
            for index, name in enumerate(bands + ["SCL"], start=1):
                dst.set_band_description(index, name)
        if shift:
            with pytest.raises(ValueError, match="bounds"):
                review.inspect_raster(raster, provider, context, bands)
        else:
            info = review.inspect_raster(raster, provider, context, bands)
            assert info["crs"] == f"EPSG:{epsg}"
