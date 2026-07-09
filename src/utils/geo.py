"""AOI loading and geometry helpers."""

import json
import math
from pathlib import Path

import pyproj
from shapely.geometry import shape
from shapely.ops import transform as shp_transform, unary_union

_EQUAL_AREA = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform


def load_aoi(path: str | Path):
    """Load AOI polygon(s) from GeoJSON (EPSG:4326). Multiple features are unioned."""
    gj = json.loads(Path(path).read_text())
    if gj.get("type") == "FeatureCollection":
        return unary_union([shape(f["geometry"]) for f in gj["features"]])
    if gj.get("type") == "Feature":
        return shape(gj["geometry"])
    return shape(gj)


def overlap_pct(aoi_geom, scene_geom) -> float:
    """Percent of AOI area covered by a scene footprint (equal-area projection)."""
    a = shp_transform(_EQUAL_AREA, aoi_geom)
    s = shp_transform(_EQUAL_AREA, scene_geom)
    if a.area == 0:
        return 0.0
    return 100.0 * a.intersection(s).area / a.area


def utm_epsg_for(geom) -> int:
    lon, lat = geom.centroid.x, geom.centroid.y
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def bbox_dims_px(geom, resolution_m: float) -> tuple[int, int, int]:
    """(width_px, height_px, utm_epsg) of the AOI bbox at the given resolution."""
    epsg = utm_epsg_for(geom)
    tr = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform
    g = shp_transform(tr, geom)
    minx, miny, maxx, maxy = g.bounds
    return (
        math.ceil((maxx - minx) / resolution_m),
        math.ceil((maxy - miny) / resolution_m),
        epsg,
    )
