"""Private field polygons, conservative raster masks, and local field-only crops."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window
from shapely.geometry import mapping, shape
from shapely.ops import transform as transform_geometry, unary_union

from sentinel_crop_pipeline.preprocessing.scl_mask import valid_mask


def load_fields(path: str | Path, field_id: str | None = None) -> list[dict]:
    """Read valid WGS84 polygons; reject ambiguous CRS, points, and empty input."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    declared_crs = data.get("crs", {}).get("properties", {}).get("name")
    if declared_crs and declared_crs not in ("EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84"):
        raise ValueError("Field GeoJSON must use WGS84 longitude/latitude coordinates.")
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    else:
        raise ValueError("Expected field GeoJSON Feature or FeatureCollection.")
    if field_id is not None:
        features = [f for f in features if (f.get("properties") or {}).get("field_id") == field_id]
    if not features:
        raise ValueError("No matching field polygons found.")
    for feature in features:
        if not feature.get("geometry"):
            raise ValueError("Field geometry is missing.")
        polygon = shape(feature["geometry"])
        if polygon.geom_type not in ("Polygon", "MultiPolygon") or polygon.is_empty or not polygon.is_valid:
            raise ValueError("Fields must be nonempty valid polygons; candidate points are not field boundaries.")
        west, south, east, north = polygon.bounds
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("Field coordinates must be WGS84 longitude/latitude.")
    return features


def field_mask_for_grid(features: list[dict], crs, transform, out_shape: tuple[int, int]) -> np.ndarray:
    """Keep interior pixels, excluding every cell touched by any union boundary.

    Polygon holes remain excluded. Boundary cells are conservatively removed
    instead of treating a pixel-center test as full-pixel field coverage.
    """
    if crs is None:
        raise ValueError("Raster CRS is required for field masking.")
    geometry = unary_union([shape(f["geometry"]) for f in features])
    project = Transformer.from_crs(4326, crs, always_xy=True).transform
    geometry = transform_geometry(project, geometry)
    inside = geometry_mask([mapping(geometry)], out_shape=out_shape, transform=transform, invert=True)
    boundary = geometry_mask([mapping(geometry.boundary)], out_shape=out_shape,
                             transform=transform, invert=True, all_touched=True)
    return inside & ~boundary


def write_field_crop(in_path: str | Path, out_path: str | Path,
                     fields_path: str | Path, field_id: str | None = None) -> dict:
    """Write one compact field-only COG and private provenance without network IO."""
    features = load_fields(fields_path, field_id)
    if len(features) != 1:
        raise ValueError("Select exactly one field for a per-field crop.")
    in_path, out_path = Path(in_path), Path(out_path)
    if in_path.resolve() == out_path.resolve():
        raise ValueError("Field crop must not overwrite its source raster.")
    with rasterio.open(in_path) as src:
        field = field_mask_for_grid(features, src.crs, src.transform, (src.height, src.width))
        rows, cols = np.where(field)
        if not len(rows):
            raise ValueError("No complete interior field pixels on this raster grid.")
        window = Window(int(cols.min()), int(rows.min()), int(cols.max() - cols.min() + 1),
                        int(rows.max() - rows.min() + 1))
        data = src.read(window=window)
        field = field[window.toslices()]
        keep = field & (src.dataset_mask(window=window) > 0)
        names = list(src.descriptions)
        if "SCL" in names:
            keep &= valid_mask(data[names.index("SCL")])
        if "MASK" in names:
            keep &= data[names.index("MASK")] > 0
        if not keep.any():
            raise ValueError("No usable field pixels after source/SCL masking.")
        nodata = np.nan if np.issubdtype(data.dtype, np.floating) else 0
        data[:, ~keep] = nodata
        crop_transform = src.window_transform(window)
        base = dict(height=data.shape[1], width=data.shape[2], count=src.count,
                    dtype=str(data.dtype), crs=src.crs, transform=crop_transform, nodata=nodata)
        source_crs = str(src.crs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(out_path, "w", driver="COG", compress="DEFLATE", **base) as dst:
            dst.write(data)
            dst.write_mask(keep.astype("uint8") * 255)
            for index, name in enumerate(names, start=1):
                if name:
                    dst.set_band_description(index, name)
            dst.update_tags(field_only="true", field_pixel_policy="interior_without_boundary_cells")
    record = {
        "purpose": "field_only_crop", "field": features[0], "source_crs": source_crs,
        "source_sha256": hashlib.sha256(in_path.read_bytes()).hexdigest(),
        "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "field_pixel_policy": "interior_without_boundary_cells",
        "interior_field_pixels": int(field.sum()), "retained_pixels": int(keep.sum()),
        "width": int(data.shape[2]), "height": int(data.shape[1]),
        "transform": list(crop_transform)[:6], "resolution_changed": False,
        "crop_type_verified": False,
    }
    out_path.with_suffix(".json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> None:
    """Run a local field-only crop; no credentials or remote services are used."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--fields", required=True, type=Path)
    parser.add_argument("--field-id")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    record = write_field_crop(args.input, args.output, args.fields, args.field_id)
    print(f"Field-only crop: {record['retained_pixels']} retained pixels, "
          f"{record['width']}x{record['height']}; original grid preserved.")


if __name__ == "__main__":
    main()
