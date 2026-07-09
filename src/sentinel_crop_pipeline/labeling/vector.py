"""Field polygon labels from GeoJSON (native) or Shapefile (needs fiona)."""

import json
from pathlib import Path

from .base import LabelSource, LabelSourceError


class VectorLabelSource(LabelSource):
    def __init__(self, path: str | Path, attribute: str = "crop_type"):
        self.path = Path(path)
        self.attribute = attribute

    def features(self) -> list[tuple[dict, str]]:
        if not self.path.exists():
            raise LabelSourceError(f"label file not found: {self.path}")
        suffix = self.path.suffix.lower()
        if suffix in (".geojson", ".json"):
            return self._from_geojson()
        if suffix == ".shp":
            return self._from_shapefile()
        raise LabelSourceError(
            f"unsupported label format '{suffix}' (geojson | json | shp)")

    def _from_geojson(self) -> list[tuple[dict, str]]:
        gj = json.loads(self.path.read_text())
        feats = gj.get("features", []) if gj.get("type") == "FeatureCollection" \
            else [gj]
        return self._extract(
            (f.get("geometry"), f.get("properties") or {}) for f in feats)

    def _from_shapefile(self) -> list[tuple[dict, str]]:
        try:
            import fiona
        except ImportError as exc:
            raise LabelSourceError(
                "shapefile input needs fiona: pip install fiona "
                "(or export to GeoJSON from QGIS)") from exc
        with fiona.open(self.path) as src:
            return self._extract(
                (dict(f["geometry"]), dict(f["properties"])) for f in src)

    def _extract(self, pairs) -> list[tuple[dict, str]]:
        out, missing = [], 0
        for geom, props in pairs:
            label = props.get(self.attribute)
            if geom is None or label in (None, ""):
                missing += 1
                continue
            out.append((geom, str(label)))
        if not out:
            raise LabelSourceError(
                f"{self.path}: no features with attribute '{self.attribute}'")
        if missing:
            import logging
            logging.getLogger("labeling").warning(
                "%s: skipped %d features without '%s'",
                self.path, missing, self.attribute)
        return out
