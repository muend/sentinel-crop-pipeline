import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


@pytest.fixture
def base_cfg():
    return {
        "data_provider": "cdse",
        "aoi": {"path": "data/aoi/urla_ilce_interim.geojson",
                "min_scene_overlap_pct": 60},
        "time": {"start": "2025-04-01", "end": "2025-10-31", "crop": None},
        "search": {"collection": "sentinel-2-l2a", "max_cloud_cover_pct": 20},
        "scl_filter": {"enabled": True, "max_invalid_pct": 30,
                       "invalid_classes": [0, 1, 3, 8, 9, 10, 11]},
        "ai_review": {"judge_provider": "none", "min_confidence": 0.6},
        "bands": {"base": ["B02", "B03", "B04", "B08"], "extra": []},
        "download": {"method": "process_api", "resolution_m": 10,
                     "max_auto_size_mb": 200, "out_dir": "data/raw"},
        "preprocessing": {"resampling": "bilinear", "normalization": "reflectance",
                          "indices": ["NDVI", "NDRE"], "out_dir": "data/interim"},
        "patching": {"patch_size": 32, "stride": 32, "block_factor": 4,
                     "max_invalid_frac": 0.4, "export_format": "npy",
                     "cog_dir": "data/patches/cog",
                     "train_dir": "data/patches/train",
                     "index_file": "data/patches/index.csv"},
        "labeling": {"source": "vector",
                     "vector_path": "data/labels/parcels.geojson",
                     "attribute": "crop_type",
                     "out_dir": "data/patches/labels",
                     "all_touched": False},
        "split": {"train": 0.7, "val": 0.15, "test": 0.15, "seed": 42},
        "logging": {"dir": "logs", "level": "INFO"},
    }


def write_raw_scene(path, size=64, bands=("B02", "B03", "B04", "B08"),
                    dn_value=5000, cloud_rows=0):
    """Synthetic downloaded scene: uint16 DN bands + SCL, band descriptions set.

    First `cloud_rows` rows are SCL class 9 (cloud high prob.), rest class 4.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(bands) + 1
    data = np.full((n, size, size), dn_value, dtype=np.uint16)
    scl = np.full((size, size), 4, dtype=np.uint16)
    if cloud_rows:
        scl[:cloud_rows, :] = 9
    data[-1] = scl
    profile = dict(driver="GTiff", height=size, width=size, count=n,
                   dtype="uint16", crs="EPSG:32635",
                   transform=from_origin(500000, 4250000, 10, 10))
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
        for i, name in enumerate(list(bands) + ["SCL"], start=1):
            dst.set_band_description(i, name)
    return path
