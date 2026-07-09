"""CDSE provider: STAC search, Sentinel Hub Process API download, OData fallback.

CDSE is the default provider because it is consistent with the project's
declared methodology, maintained by ESA/EU, and needs no Google account.
STAC search is public; downloads require OAuth2 client credentials
(CDSE_CLIENT_ID / CDSE_CLIENT_SECRET in .env).

Download strategy: prefer the Sentinel Hub Process API hosted on CDSE, which
returns only the AOI window (bandwidth/storage saving) instead of the full
~1 GB SAFE product. AOIs larger than the 2500 px/axis Process API limit are
split into sub-tiles and mosaicked. download_odata() remains as a
full-product fallback.
"""

import math
import os
import time
from pathlib import Path

import numpy as np
import pyproj
import requests
from shapely.geometry import mapping
from shapely.ops import transform as shp_transform

from src.utils.geo import bbox_dims_px, utm_epsg_for
from .base import DataProvider, ProviderError, Scene

STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"
TOKEN_URL = ("https://identity.dataspace.copernicus.eu/auth/realms/CDSE"
             "/protocol/openid-connect/token")
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
ODATA_PRODUCTS = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
ODATA_DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1/Products({pid})/$value"

MAX_PROCESS_DIM = 2500     # Process API hard limit per axis
RETRY_STATUS = (429, 500, 502, 503, 504)


def _evalscript(bands: list[str]) -> str:
    all_bands = list(bands) + ["SCL"]
    inputs = ", ".join(f'"{b}"' for b in all_bands)
    outputs = ", ".join(f"s.{b}" for b in all_bands)
    return (
        "//VERSION=3\n"
        "function setup() {\n"
        f'  return {{input: [{{bands: [{inputs}], units: "DN"}}],\n'
        f'          output: {{bands: {len(all_bands)}, sampleType: "UINT16"}}}};\n'
        "}\n"
        f"function evaluatePixel(s) {{ return [{outputs}]; }}\n"
    )


def _tile_grid(width: int, height: int,
               max_dim: int = MAX_PROCESS_DIM) -> list[tuple[int, int, int, int]]:
    """Split raster dims into <= max_dim windows: (col_off, row_off, w, h)."""
    def axis_splits(total: int) -> list[tuple[int, int]]:
        n = math.ceil(total / max_dim)
        step = math.ceil(total / n)
        return [(off, min(step, total - off)) for off in range(0, total, step)]

    return [(c, r, w, h)
            for r, h in axis_splits(height)
            for c, w in axis_splits(width)]


class CdseProvider(DataProvider):
    name = "cdse"

    def __init__(self, config: dict | None = None, session: requests.Session | None = None):
        self.config = config or {}
        self.session = session or requests.Session()
        self._token: str | None = None
        self._token_expiry = 0.0

    # -- http ---------------------------------------------------------------

    def _request(self, method: str, url: str, retries: int = 4, backoff: float = 2.0,
                 **kwargs) -> requests.Response:
        """Request with exponential backoff on 429/5xx (CDSE rate limits)."""
        for attempt in range(retries + 1):
            resp = self.session.request(method, url, timeout=180, **kwargs)
            if resp.status_code < 400:
                return resp
            if resp.status_code in RETRY_STATUS and attempt < retries:
                time.sleep(backoff ** attempt)
                continue
            raise ProviderError(
                f"{method} {url} failed: HTTP {resp.status_code} {resp.text[:300]}")
        raise ProviderError("unreachable")

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        cid = os.environ.get("CDSE_CLIENT_ID")
        secret = os.environ.get("CDSE_CLIENT_SECRET")
        if not cid or not secret:
            raise ProviderError(
                "CDSE_CLIENT_ID / CDSE_CLIENT_SECRET not set. Create an OAuth client at "
                "https://shapps.dataspace.copernicus.eu/dashboard/ and put them in .env")
        resp = self._request("POST", TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
        })
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + float(data.get("expires_in", 600))
        return self._token

    # -- search ---------------------------------------------------------------

    def search(self, aoi_geom, start: str, end: str,
               max_cloud_cover: float = 100.0) -> list[Scene]:
        """STAC item search (no auth). Cloud cover is also filtered client-side
        for robustness across STAC deployments with partial query support."""
        collection = self.config.get("search", {}).get("collection", "sentinel-2-l2a")
        payload = {
            "collections": [collection],
            "intersects": mapping(aoi_geom),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "limit": 100,
        }
        scenes: list[Scene] = []
        url = STAC_SEARCH_URL
        while url:
            resp = self._request("POST", url, json=payload)
            page = resp.json()
            for feat in page.get("features", []):
                scene = self._to_scene(feat)
                if scene is None:
                    continue
                if scene.cloud_cover is not None and scene.cloud_cover > max_cloud_cover:
                    continue
                scenes.append(scene)
            url, payload = self._next_link(page)
        return scenes

    def _to_scene(self, feat: dict) -> Scene | None:
        props = feat.get("properties", {})
        ptype = str(props.get("product:type") or props.get("productType") or "")
        if ptype and not ("L2A" in ptype or ptype == "S2MSI2A"):
            return None  # keep only L2A
        cloud = props.get("eo:cloud_cover", props.get("cloudCover"))
        return Scene(
            id=feat["id"],
            provider=self.name,
            datetime=props.get("datetime", ""),
            cloud_cover=float(cloud) if cloud is not None else None,
            geometry=feat.get("geometry"),
            properties={k: props[k] for k in ("datetime", "eo:cloud_cover", "product:type",
                                              "platform", "grid:code")
                        if k in props},
        )

    @staticmethod
    def _next_link(page: dict):
        for link in page.get("links", []):
            if link.get("rel") == "next":
                return link["href"], link.get("body") or None
        return None, None

    # -- download (Process API) ------------------------------------------------

    def _utm_bbox(self, aoi_geom, resolution_m: int):
        """AOI bbox snapped to the resolution grid in the local UTM zone."""
        epsg = utm_epsg_for(aoi_geom)
        tr = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}",
                                         always_xy=True).transform
        minx, miny, maxx, maxy = shp_transform(tr, aoi_geom).bounds
        minx = math.floor(minx / resolution_m) * resolution_m
        miny = math.floor(miny / resolution_m) * resolution_m
        maxx = math.ceil(maxx / resolution_m) * resolution_m
        maxy = math.ceil(maxy / resolution_m) * resolution_m
        width = round((maxx - minx) / resolution_m)
        height = round((maxy - miny) / resolution_m)
        return epsg, (minx, miny, maxx, maxy), width, height

    def estimate_size_mb(self, aoi_geom, n_bands: int, resolution_m: int = 10) -> float:
        width, height, _ = bbox_dims_px(aoi_geom, resolution_m)
        return width * height * (n_bands + 1) * 2 / 1e6  # +1 SCL, uint16

    def _process_request(self, bbox: tuple, epsg: int, width: int, height: int,
                         day: str, evalscript: str, mime: str = "image/tiff",
                         data_type: str = "sentinel-2-l2a") -> bytes:
        resampling = str(self.config.get("preprocessing", {})
                         .get("resampling", "bilinear")).upper()
        request = {
            "input": {
                "bounds": {
                    "bbox": list(bbox),
                    "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{epsg}"},
                },
                "data": [{
                    "type": data_type,
                    "dataFilter": {"timeRange": {
                        "from": f"{day}T00:00:00Z", "to": f"{day}T23:59:59Z"}},
                    "processing": {"upsampling": resampling, "downsampling": resampling},
                }],
            },
            "output": {
                "width": width, "height": height,
                "responses": [{"identifier": "default", "format": {"type": mime}}],
            },
            "evalscript": evalscript,
        }
        headers = {"Authorization": f"Bearer {self._get_token()}", "Accept": mime}
        return self._request("POST", PROCESS_URL, json=request, headers=headers).content

    def download(self, scene: Scene, aoi_geom, bands: list[str], out_dir: str | Path,
                 resolution_m: int = 10, assume_yes: bool = False) -> Path:
        """AOI-cropped stack (bands + SCL, uint16 DN) via Process API.

        Output grid is the local UTM zone. AOIs above the per-request pixel
        limit are fetched as sub-tiles and mosaicked. 20 m bands are resampled
        server-side to the requested resolution.
        """
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.merge import merge as rio_merge

        epsg, bbox, width, height = self._utm_bbox(aoi_geom, resolution_m)
        est_mb = width * height * (len(bands) + 1) * 2 / 1e6
        max_auto = float(self.config.get("download", {}).get("max_auto_size_mb", 200))
        if est_mb > max_auto and not assume_yes:
            raise ProviderError(
                f"Estimated download {est_mb:.0f} MB > max_auto_size_mb={max_auto:.0f}. "
                "Re-run with --yes to confirm.")

        minx, _, _, maxy = bbox
        day = scene.datetime[:10]
        script = _evalscript(bands)
        tiles = _tile_grid(width, height)

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{scene.id}.tif"

        memfiles, datasets = [], []
        try:
            for col_off, row_off, w, h in tiles:
                tile_bbox = (
                    minx + col_off * resolution_m,
                    maxy - (row_off + h) * resolution_m,
                    minx + (col_off + w) * resolution_m,
                    maxy - row_off * resolution_m,
                )
                content = self._process_request(tile_bbox, epsg, w, h, day, script)
                mem = MemoryFile(content)
                memfiles.append(mem)
                datasets.append(mem.open())

            if len(datasets) == 1:
                out_path.write_bytes(memfiles[0].read())
            else:
                mosaic, transform = rio_merge(datasets)
                profile = datasets[0].profile
                profile.update(height=mosaic.shape[1], width=mosaic.shape[2],
                               transform=transform, driver="GTiff",
                               compress="deflate")
                with rasterio.open(out_path, "w", **profile) as dst:
                    dst.write(mosaic)
        finally:
            for ds in datasets:
                ds.close()
            for mem in memfiles:
                mem.close()

        self._tag_bands(out_path, list(bands) + ["SCL"])
        return out_path

    @staticmethod
    def _tag_bands(path: Path, names: list[str]) -> None:
        import rasterio
        with rasterio.open(path, "r+") as dst:
            for i, n in enumerate(names[: dst.count], start=1):
                dst.set_band_description(i, n)

    def get_scl_mask(self, scene: Scene, aoi_geom, resolution_m: int = 20) -> np.ndarray:
        """Fetch only the SCL band over the AOI (small request at 20 m)."""
        from rasterio.io import MemoryFile

        epsg, bbox, width, height = self._utm_bbox(aoi_geom, resolution_m)
        width, height = min(width, MAX_PROCESS_DIM), min(height, MAX_PROCESS_DIM)
        script = (
            "//VERSION=3\n"
                        'function setup() { return {input: [{bands: ["SCL"]}],'
            ' output: {bands: 1, sampleType: "UINT8"}}; }\n'
            "function evaluatePixel(s) { return [s.SCL]; }\n"
        )
        content = self._process_request(bbox, epsg, width, height,
                                        scene.datetime[:10], script)
        with MemoryFile(content) as mem, mem.open() as src:
            return src.read(1).astype(np.uint8)

    def get_preview(self, scene: Scene, aoi_geom, max_px: int = 512) -> bytes:
        """Small RGB PNG over the AOI for layer-2 AI review."""
        epsg, bbox, width, height = self._utm_bbox(aoi_geom, 10)
        scale = max(width, height) / max_px
        if scale > 1:
            width, height = round(width / scale), round(height / scale)
        # 3.5x gain: rough true-color brightness for typical L2A reflectance
        script = (
            "//VERSION=3\n"
            'function setup() { return {input: [{bands: ["B04","B03","B02"]}],'
            ' output: {bands: 3, sampleType: "AUTO"}}; }\n'
            "function evaluatePixel(s) {"
            " return [3.5 * s.B04, 3.5 * s.B03, 3.5 * s.B02]; }\n"
        )
        return self._process_request(bbox, epsg, width, height,
                                     scene.datetime[:10], script,
                                     mime="image/png")

    # -- download (OData fallback) ----------------------------------------------

    def download_odata(self, scene: Scene, out_dir: str | Path,
                       assume_yes: bool = False) -> Path:
        """Full SAFE product zip (typically ~1 GB). Reports size before download."""
        name = scene.id if scene.id.endswith(".SAFE") else f"{scene.id}.SAFE"
        url = (f"{ODATA_PRODUCTS}?$filter=Name eq '{name}'"
               "&$select=Id,Name,ContentLength")
        items = self._request("GET", url).json().get("value", [])
        if not items:
            raise ProviderError(f"OData product not found for '{name}'")
        pid, size = items[0]["Id"], int(items[0].get("ContentLength") or 0)
        size_mb = size / 1e6
        max_auto = float(self.config.get("download", {}).get("max_auto_size_mb", 200))
        if size_mb > max_auto and not assume_yes:
            raise ProviderError(
                f"Product is {size_mb:.0f} MB > max_auto_size_mb={max_auto:.0f}. "
                "Re-run with --yes to confirm.")

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{name}.zip"
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        with self.session.get(ODATA_DOWNLOAD.format(pid=pid), headers=headers,
                              stream=True, timeout=600) as resp:
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        return out_path
