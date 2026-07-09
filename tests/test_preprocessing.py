import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from sentinel_crop_pipeline.preprocessing import normalize
from sentinel_crop_pipeline.preprocessing.indices import ndvi
from sentinel_crop_pipeline.preprocessing.pipeline import preprocess_scene
from sentinel_crop_pipeline.preprocessing.resample import resample_to_grid
from sentinel_crop_pipeline.preprocessing.scl_mask import invalid_fraction, valid_mask
from tests.conftest import write_raw_scene


def test_valid_mask_and_fraction():
    scl = np.array([[4, 9], [3, 5]], dtype=np.uint8)
    mask = valid_mask(scl)
    assert mask.tolist() == [[True, False], [False, True]]
    assert invalid_fraction(scl) == 0.5


def test_ndvi_safe_division():
    nir = np.array([[0.8, 0.0]], dtype=np.float32)
    red = np.array([[0.2, 0.0]], dtype=np.float32)
    out = ndvi(nir, red)
    assert out[0, 0] == pytest.approx(0.6)
    assert np.isnan(out[0, 1])


def test_reflectance_normalization():
    arr = np.array([[[5000.0, 20000.0]]], dtype=np.float32)
    out = normalize.reflectance(arr)
    assert out[0, 0, 0] == pytest.approx(0.5)
    assert out[0, 0, 1] == 1.0  # clipped


def test_minmax_normalization_ignores_nan():
    arr = np.array([[[0.0, 5.0, 10.0, np.nan]]], dtype=np.float32)
    out = normalize.minmax(arr)
    assert out[0, 0, 0] == 0.0
    assert out[0, 0, 2] == 1.0
    assert np.isnan(out[0, 0, 3])


def test_preprocess_scene_masks_and_appends(base_cfg, tmp_path):
    raw = write_raw_scene(tmp_path / "raw" / "scene1.tif", size=32,
                          dn_value=5000, cloud_rows=16)
    out = tmp_path / "interim" / "scene1_stack.tif"
    names = preprocess_scene(raw, out, base_cfg)
    # NDRE skipped (no B05), NDVI + MASK appended
    assert names == ["B02", "B03", "B04", "B08", "NDVI", "MASK"]
    with rasterio.open(out) as src:
        data = src.read()
        assert src.dtypes[0] == "float32"
    b02, mask = data[0], data[-1]
    assert np.all(np.isnan(b02[:16]))            # cloud rows masked
    assert b02[20, 20] == pytest.approx(0.5)     # 5000/10000
    assert mask[:16].sum() == 0 and mask[16:].mean() == 1.0


def test_preprocess_requires_scl(base_cfg, tmp_path):
    path = tmp_path / "noscl.tif"
    profile = dict(driver="GTiff", height=8, width=8, count=1, dtype="uint16",
                   crs="EPSG:32635", transform=from_origin(0, 0, 10, 10))
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.zeros((1, 8, 8), dtype=np.uint16))
        dst.set_band_description(1, "B02")
    with pytest.raises(ValueError, match="SCL"):
        preprocess_scene(path, tmp_path / "out.tif", base_cfg)


def test_resample_20m_to_10m():
    src = np.full((8, 8), 7.0, dtype=np.float32)
    src_transform = from_origin(0, 160, 20, 20)
    dst_transform = from_origin(0, 160, 10, 10)
    out = resample_to_grid(src, src_transform, "EPSG:32635",
                           (16, 16), dst_transform, method="bilinear")
    assert out.shape == (16, 16)
    assert np.allclose(out, 7.0)


def test_resample_rejects_unknown_method():
    with pytest.raises(ValueError):
        resample_to_grid(np.zeros((2, 2), np.float32), from_origin(0, 0, 20, 20),
                         "EPSG:32635", (4, 4), from_origin(0, 0, 10, 10),
                         method="nearest")
