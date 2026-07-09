import pytest
from shapely.geometry import box

from src.utils.config import all_bands, load_config, normalize_band
from src.utils.geo import bbox_dims_px, load_aoi, overlap_pct, utm_epsg_for


def test_load_default_config():
    cfg = load_config("config/default.yaml")
    assert cfg["data_provider"] == "cdse"
    assert cfg["bands"]["base"] == ["B02", "B03", "B04", "B08"]
    assert cfg["split"]["train"] == 0.70


def test_band_aliases():
    assert normalize_band("B2") == "B02"
    assert normalize_band("b8") == "B08"
    assert normalize_band("B8A") == "B8A"
    assert normalize_band("B11") == "B11"


def test_all_bands_merges_extra(base_cfg):
    base_cfg["bands"]["extra"] = ["B05", "B11"]
    assert all_bands(base_cfg) == ["B02", "B03", "B04", "B08", "B05", "B11"]


def test_missing_required_key(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("data_provider: cdse\n")
    with pytest.raises(ValueError, match="missing required"):
        load_config(p)


def test_load_aoi_example():
    geom = load_aoi("data/aoi/urla_example.geojson")
    assert geom.is_valid
    assert utm_epsg_for(geom) == 32635  # zone 35N for Urla


def test_overlap_pct():
    aoi = box(26.65, 38.25, 26.85, 38.36)
    assert overlap_pct(aoi, box(26.0, 38.0, 27.5, 39.0)) == pytest.approx(100.0)
    assert overlap_pct(aoi, box(28.0, 39.0, 29.0, 40.0)) == 0.0
    half = box(26.65, 38.25, 26.75, 38.36)
    assert overlap_pct(aoi, half) == pytest.approx(50.0, abs=1.0)


def test_bbox_dims_px_reasonable():
    aoi = box(26.65, 38.25, 26.85, 38.36)
    w, h, epsg = bbox_dims_px(aoi, 10)
    assert epsg == 32635
    # ~17.5 km x ~12.2 km at 10 m
    assert 1500 < w < 2100
    assert 1000 < h < 1500
