"""Read-only loaders for the dashboard.

Everything here reads files already on disk (logs/, data/) and does light
parsing. No network, no API calls, no writes - keeping this module free of
Streamlit imports also makes it unit-testable without the [dashboard] extra.
"""

import csv
import json
import re
from pathlib import Path

_PCT = re.compile(r"([\d.]+)\s*%")


def parse_note_pct(note: str | None) -> float | None:
    """Extract the first percentage from a check note, e.g. 'cloud_cover=8.4% ...'."""
    if not note:
        return None
    m = _PCT.search(note)
    return float(m.group(1)) if m else None


def geojson_center(obj) -> tuple[float, float] | None:
    """(lat, lon) of the bbox center of any GeoJSON-like structure, so map
    views follow the configured AOI instead of a hardcoded location."""
    xs: list[float] = []
    ys: list[float] = []

    def walk(o):
        if isinstance(o, (list, tuple)):
            if len(o) >= 2 and all(isinstance(v, (int, float)) for v in o[:2]):
                xs.append(float(o[0]))
                ys.append(float(o[1]))
            else:
                for item in o:
                    walk(item)
        elif isinstance(o, dict):
            for key in ("features", "geometry", "coordinates", "polygon"):
                if key in o:
                    walk(o[key])

    walk(obj)
    if not xs:
        return None
    return (min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2


def scene_status(entry: dict) -> str:
    """rejected | needs_manual_review | accepted (manual-review implies accepted)."""
    if not entry.get("accepted"):
        return "rejected"
    if entry.get("needs_manual_review"):
        return "needs_manual_review"
    return "accepted"


def scene_date(scene_id: str) -> str:
    """Sensing date from a Sentinel-2 product id, or '' if not parseable."""
    m = re.search(r"_(\d{8})T\d{6}_", scene_id)
    return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else ""


def load_selection_results(log_dir: str | Path) -> list[dict]:
    path = Path(log_dir) / "selection_results.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def load_catalog_geometries(catalog_file: str | Path) -> dict[str, dict]:
    """scene_id -> GeoJSON footprint, for logs written before geometry was logged."""
    path = Path(catalog_file)
    if not path.exists():
        return {}
    return {s["id"]: s["geometry"] for s in json.loads(path.read_text())
            if s.get("geometry")}


def selection_table(results: list[dict]) -> list[dict]:
    """Flatten selection entries into table rows."""
    rows = []
    for r in results:
        checks = r.get("checks", {})
        rows.append({
            "scene_id": r.get("scene_id", ""),
            "date": scene_date(r.get("scene_id", "")),
            "status": scene_status(r),
            "cloud_pct": parse_note_pct(checks.get("cloud_metadata", {}).get("note")),
            "aoi_overlap_pct": parse_note_pct(checks.get("aoi_overlap", {}).get("note")),
            "scl_invalid_pct": parse_note_pct(checks.get("scl_stats", {}).get("note")),
            "ai_verdict": r.get("ai_verdict"),
            "ai_confidence": r.get("ai_confidence"),
            "reasons": "; ".join(r.get("reasons", [])),
        })
    return rows


def load_index(index_file: str | Path) -> list[dict]:
    path = Path(index_file)
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_run_logs(log_dir: str | Path) -> list[dict]:
    """run_*.json summaries, newest first."""
    logs = []
    for p in sorted(Path(log_dir).glob("run_*.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        logs.append({"file": p.name, "stage": d.get("stage", "?"),
                     "started": d.get("started", ""),
                     "finished": d.get("finished", ""),
                     "summary": d.get("summary", {})})
    return logs


def patch_bounds_wgs84(cog_path: str | Path):
    """Patch footprint as (lon,lat) ring, or None if the file is unreadable."""
    import rasterio
    from pyproj import Transformer
    try:
        with rasterio.open(cog_path) as src:
            b, crs = src.bounds, src.crs
    except Exception:
        return None
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    corners = [(b.left, b.bottom), (b.right, b.bottom),
               (b.right, b.top), (b.left, b.top), (b.left, b.bottom)]
    return [list(tr.transform(x, y)) for x, y in corners]


def read_patch_rgb(cog_path: str | Path):
    """(rgb uint8 HxWx3, band_names) percentile-stretched from B04/B03/B02."""
    import numpy as np
    import rasterio
    with rasterio.open(cog_path) as src:
        names = [d or f"band_{i}" for i, d in enumerate(src.descriptions, 1)]
        want = [b for b in ("B04", "B03", "B02") if b in names]
        idxs = [names.index(b) + 1 for b in want] if len(want) == 3 else [1, 2, 3]
        arr = src.read(idxs).astype("float32")
    finite = arr[np.isfinite(arr)]
    if finite.size:
        lo, hi = np.percentile(finite, (2, 98))
        arr = np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1)
    rgb = (np.nan_to_num(np.moveaxis(arr, 0, -1)) * 255).astype("uint8")
    return rgb, names


def read_label_mask(label_path: str | Path):
    """uint8 class mask, or None."""
    import rasterio
    try:
        with rasterio.open(label_path) as src:
            return src.read(1)
    except Exception:
        return None


def load_class_map(labels_dir: str | Path) -> dict[str, int]:
    path = Path(labels_dir) / "class_map.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())
