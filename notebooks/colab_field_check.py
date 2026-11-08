"""Inspect one private field and optionally download a small location-check image."""

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from pyproj import Transformer
import rasterio
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import transform

from sentinel_crop_pipeline.discovery.providers.cdse import CdseProvider
from sentinel_crop_pipeline.utils.geo import utm_epsg_for


def load_field(path, field_id=None):
    collection = json.loads(Path(path).read_text(encoding="utf-8"))
    features = collection.get("features", [])
    if field_id:
        features = [f for f in features if f.get("properties", {}).get("field_id") == field_id]
    if len(features) != 1:
        raise ValueError("Select exactly one field with --field-id.")
    feature = features[0]
    props = feature.get("properties", {})
    if not re.fullmatch(r"[A-Za-z0-9_-]+", props.get("field_id", "")):
        raise ValueError("Field needs a safe, nonempty field_id.")
    if not props.get("map_address"):
        raise ValueError("Field needs its reviewed neighborhood/locality address.")
    polygon = shape(feature["geometry"])
    if polygon.geom_type not in ("Polygon", "MultiPolygon") or not polygon.is_valid or polygon.is_empty:
        raise ValueError("Field must be a valid polygon, not a candidate point.")
    west, south, east, north = polygon.bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Expected WGS84 GeoJSON coordinates in longitude/latitude order.")
    point = Point(float(props["reference_longitude"]), float(props["reference_latitude"]))
    if not polygon.covers(point):
        raise ValueError("Address reference point is outside the selected field.")
    return feature, polygon


def context_window(polygon, padding_m=200):
    epsg = utm_epsg_for(polygon)
    to_utm = Transformer.from_crs(4326, epsg, always_xy=True).transform
    to_wgs = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    projected = transform(to_utm, polygon)
    west, south, east, north = projected.bounds
    context = box(west - padding_m, south - padding_m, east + padding_m, north + padding_m)
    return transform(to_wgs, context), projected.area


def inspect_raster(path, provider, context, bands):
    epsg, bounds, width, height = provider._utm_bbox(context, 10)
    with rasterio.open(path) as src:
        if src.descriptions != tuple(bands + ["SCL"]) or src.dtypes != ("uint16",) * 5:
            raise ValueError("Unexpected raster bands or dtype.")
        if not src.crs or src.crs.to_epsg() != epsg or (src.width, src.height) != (width, height):
            raise ValueError("Raster CRS or dimensions do not match the requested field context.")
        if not np.allclose(src.bounds, bounds, rtol=0, atol=1e-6):
            raise ValueError("Raster bounds do not match the requested field context.")
        if not np.allclose(src.res, (10, 10), rtol=0, atol=1e-9):
            raise ValueError("Expected a 10 m raster grid.")
        if not np.any(src.read([1, 2, 3, 4]) > 0):
            raise ValueError("No optical data returned.")
        scl = src.read(5)
        if not np.isin(scl, np.arange(12)).all() or not np.any(scl != 0):
            raise ValueError("Invalid or empty SCL band.")
        return {"crs": src.crs.to_string(), "width": width, "height": height,
                "bounds": list(src.bounds), "transform": list(src.transform)[:6],
                "band_names": list(src.descriptions)}


def save_overlay(raster_path, feature, output, scene_day, reference_day):
    import matplotlib.pyplot as plt

    with rasterio.open(raster_path) as src:
        rgb = src.read([3, 2, 1]).astype("float32")
        scl = src.read(5)
        valid = ~np.isin(scl, [0, 1, 3, 8, 9, 10, 11])
        if not valid.any():
            raise ValueError("No SCL-usable pixels available for the preview.")
        lo, hi = np.percentile(rgb[:, valid], [2, 98])
        if hi <= lo:
            raise ValueError("Not enough RGB contrast for a useful preview.")
        rgb = np.moveaxis(np.clip((rgb - lo) / (hi - lo), 0, 1), 0, -1)
        bounds = src.bounds
        projected = transform(Transformer.from_crs(4326, src.crs, always_xy=True).transform,
                              shape(feature["geometry"]))
        fig, axes = plt.subplots(1, 2, figsize=(12, 6), sharex=True, sharey=True)
        for ax in axes:
            ax.imshow(rgb, extent=(bounds.left, bounds.right, bounds.bottom, bounds.top),
                      alpha=valid.astype(float), interpolation="nearest")
            ax.set_xlabel(f"Easting (m), {src.crs}")
        axes[0].set_title("Sentinel-2 RGB / SCL-masked")
        axes[1].set_title("Same image + draft field boundary")
        pieces = [projected] if projected.geom_type == "Polygon" else projected.geoms
        for piece in pieces:
            axes[1].plot(*piece.exterior.xy, color="#ffd166", linewidth=2, label="Draft boundary")
            for ring in piece.interiors:
                axes[1].plot(*ring.xy, color="#ffd166", linewidth=2)
        axes[1].legend(loc="upper right")
        axes[0].set_ylabel("Northing (m)")
        props = feature["properties"]
        fig.suptitle(f"{props['field_id']} | {props['map_address']}\n"
                     f"Sentinel request day: {scene_day}; reference view: {reference_day}")
        fig.text(0.5, 0.01, "Location check only; boundary and positional alignment remain unaccepted. "
                 "RGB display stretch only; raw pixels unchanged.", ha="center", fontsize=8)
        fig.tight_layout(rect=(0, 0.04, 1, 0.91))
        fig.savefig(output, dpi=150)
        plt.show()
        plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", required=True, type=Path)
    parser.add_argument("--field-id")
    parser.add_argument("--catalog-aoi", required=True, type=Path,
                        help="Separate public/coarse AOI for metadata search; private field filtering is local.")
    parser.add_argument("--reference-date", required=True, type=date.fromisoformat)
    parser.add_argument("--scene-date", type=date.fromisoformat,
                        help="Require this exact request day instead of choosing another candidate date.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--download", action="store_true",
                        help="Opt in to one small context image; default is metadata search only.")
    parser.add_argument("--out-dir", type=Path, default=Path("data/quicklooks/field_check"))
    args = parser.parse_args(argv)
    if not 0 <= args.days <= 31:
        parser.error("--days must be between 0 and 31.")
    feature, polygon = load_field(args.aoi, args.field_id)
    context, area = context_window(polygon)
    catalog_data = json.loads(args.catalog_aoi.read_text(encoding="utf-8"))
    if catalog_data.get("type") == "FeatureCollection":
        from shapely.ops import unary_union
        catalog_region = unary_union([shape(f["geometry"]) for f in catalog_data["features"]])
    else:
        catalog_region = shape(catalog_data.get("geometry", catalog_data))
    if not catalog_region.is_valid or not catalog_region.covers(context):
        raise ValueError("Public catalog AOI must be valid and cover the full review context.")
    provider = CdseProvider({"preprocessing": {"resampling": "nearest"},
                             "download": {"max_auto_size_mb": 10}})
    # Transmit only the separately supplied public AOI; exact field filtering stays local.
    scenes = provider.search(catalog_region, str(args.reference_date - timedelta(days=args.days)),
                             str(args.reference_date + timedelta(days=args.days)), max_cloud_cover=20)
    scenes = [s for s in scenes if s.geometry and shape(s.geometry).covers(context)]
    if args.scene_date:
        scenes = [s for s in scenes if date.fromisoformat(s.datetime[:10]) == args.scene_date]
    scenes.sort(key=lambda s: (abs((date.fromisoformat(s.datetime[:10]) - args.reference_date).days),
                               s.cloud_cover, s.datetime, s.id))
    if not scenes:
        raise ValueError("No scene covers the full context in this date/cloud window.")
    print(f"Field area: about {area:.0f} m2 ({area / 100:.0f} 10 m pixel-area equivalents).")
    print("Candidate metadata cloud cover is scene-wide; AOI pixel quality is not checked yet.")
    for scene in scenes[:5]:
        print(scene.datetime, f"cloud={scene.cloud_cover:.1f}%", scene.id)
    if not args.download:
        print("Metadata search only. No image downloaded. Add --download for one location-check image.")
        return
    if not os.environ.get("CDSE_CLIENT_ID") or not os.environ.get("CDSE_CLIENT_SECRET"):
        raise ValueError("Load CDSE_CLIENT_ID and CDSE_CLIENT_SECRET from Colab Secrets first.")
    scene = scenes[0]
    bands = ["B02", "B03", "B04", "B08"]
    with TemporaryDirectory(prefix="field_check_") as directory:
        source = provider.download(scene, context, bands, Path(directory), resolution_m=10)
        raster_info = inspect_raster(source, provider, context, bands)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        args.out_dir.mkdir(parents=True, exist_ok=True)
        target = args.out_dir / f"{feature['properties']['field_id']}_{scene.datetime[:10]}_{digest[:12]}.tif"
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Conflicting existing image; no overwrite performed.")
        if not target.exists():
            staging = target.with_suffix(".tif.partial")
            try:
                shutil.copyfile(source, staging)
                if hashlib.sha256(staging.read_bytes()).hexdigest() != digest:
                    raise ValueError("Image copy checksum failed.")
                inspect_raster(staging, provider, context, bands)
                staging.replace(target)
            finally:
                staging.unlink(missing_ok=True)
        inspect_raster(target, provider, context, bands)
    metadata = {"purpose": "location_check_only", "field": feature,
                "context_epsg4326": mapping(context), "reference_view_date": str(args.reference_date),
                "reference_date_note": "View date may include imagery acquired earlier.",
                "candidate_scene_id": scene.id, "candidate_datetime": scene.datetime,
                "exact_source_product_ids_verified": False,
                "source_note": "Process API filters the full UTC day, not the exact STAC item.",
                "raster": raster_info, "sha256": digest, "resampling": "NEAREST",
                "alignment_accepted": False, "crop_type_verified": False}
    target.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    save_overlay(target, feature, target.with_suffix(".png"), scene.datetime[:10], args.reference_date)
    print("Saved location-check image, private provenance, and overlay under:", args.out_dir)


if __name__ == "__main__":
    main()
