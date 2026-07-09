"""Optional Google Earth Engine provider (quick prototyping, e.g. Colab).

Not the default: GEE requires a registered Google Cloud project (post-2024
policy), which conflicts with the one-command setup goal. Install extras:
`pip install "sentinel-crop-pipeline[gee]"` and run `earthengine authenticate`.

Current scope: search only. Download/SCL access via GEE is planned for a later
phase; use CDSE for production data pulls.
"""

import os
from pathlib import Path

from shapely.geometry import mapping

from .base import DataProvider, ProviderError, ProviderNotAvailable, Scene

GEE_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"


class GeeProvider(DataProvider):
    name = "gee"

    def __init__(self, config: dict | None = None):
        try:
            import ee  # noqa: F401
        except ImportError as exc:
            raise ProviderNotAvailable(
                "earthengine-api not installed. "
                "pip install 'sentinel-crop-pipeline[gee]'") from exc
        self.ee = ee
        self.config = config or {}
        try:
            ee.Initialize(project=os.environ.get("GEE_PROJECT") or None)
        except Exception as exc:
            raise ProviderNotAvailable(
                f"GEE init failed (run `earthengine authenticate`, set GEE_PROJECT): {exc}"
            ) from exc

    def search(self, aoi_geom, start: str, end: str,
               max_cloud_cover: float = 100.0) -> list[Scene]:
        ee = self.ee
        coll = (
            ee.ImageCollection(GEE_COLLECTION)
            .filterBounds(ee.Geometry(mapping(aoi_geom)))
            .filterDate(start, end)
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", max_cloud_cover))
        )
        feats = coll.getInfo().get("features", [])
        scenes = []
        for f in feats:
            props = f.get("properties", {})
            ts = props.get("system:time_start")
            iso = ""
            if ts is not None:
                from datetime import datetime, timezone
                iso = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            scenes.append(Scene(
                id=f.get("id", props.get("PRODUCT_ID", "unknown")),
                provider=self.name,
                datetime=iso,
                cloud_cover=props.get("CLOUDY_PIXEL_PERCENTAGE"),
                geometry=f.get("geometry"),
                properties={"PRODUCT_ID": props.get("PRODUCT_ID")},
            ))
        return scenes

    def download(self, scene: Scene, aoi_geom, bands: list[str], out_dir: str | Path,
                 resolution_m: int = 10, assume_yes: bool = False) -> Path:
        raise ProviderError(
            "GEE download is not implemented; the GEE path is search-only for now. "
            "Use data_provider: cdse for production downloads.")

    def get_scl_mask(self, scene: Scene, aoi_geom, resolution_m: int = 20):
        raise ProviderError(
            "GEE SCL access is not implemented; use data_provider: cdse, or disable "
            "scl_filter for GEE prototyping.")
