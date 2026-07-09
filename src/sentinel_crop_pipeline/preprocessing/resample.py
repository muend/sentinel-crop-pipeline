"""Grid resampling (e.g. 20 m bands onto the 10 m grid).

The Process API download path already delivers a uniform grid; this is used by
the SAFE/OData workflow where bands come at native resolutions.
"""

import numpy as np
from rasterio.warp import Resampling, reproject

METHODS = {"bilinear": Resampling.bilinear, "cubic": Resampling.cubic}


def resample_to_grid(arr: np.ndarray, src_transform, src_crs,
                     dst_shape: tuple[int, int], dst_transform,
                     method: str = "bilinear") -> np.ndarray:
    if method not in METHODS:
        raise ValueError(f"resampling must be one of {sorted(METHODS)}")
    dst = np.full(dst_shape, np.nan, dtype=np.float32)
    reproject(
        source=arr.astype(np.float32),
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=src_crs,
        resampling=METHODS[method],
    )
    return dst
