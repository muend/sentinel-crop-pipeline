"""CKS (Ciftci Kayit Sistemi) manual import connector.

Legal note: access to CKS data requires permission from the Provincial or
District Directorate of Agriculture and Forestry. This tool does NOT fetch CKS
data automatically and no scraping support will be added. The user places an
officially obtained export (GeoJSON or Shapefile) under data/raw/cks_import/;
this connector only reads those local files.
"""

from pathlib import Path

from .base import LabelSource, LabelSourceError
from .vector import VectorLabelSource

DEFAULT_IMPORT_DIR = "data/raw/cks_import"


class CksImportSource(LabelSource):
    def __init__(self, import_dir: str | Path = DEFAULT_IMPORT_DIR,
                 attribute: str = "crop_type"):
        self.import_dir = Path(import_dir)
        self.attribute = attribute

    def features(self) -> list[tuple[dict, str]]:
        files = sorted(p for p in self.import_dir.glob("*")
                       if p.suffix.lower() in (".geojson", ".json", ".shp"))
        if not files:
            raise LabelSourceError(
                f"No CKS export found under {self.import_dir}/. CKS data must be "
                "obtained with official permission from the Provincial/District "
                "Directorate of Agriculture and Forestry and copied there "
                "manually; this tool does not fetch it.")
        out = []
        for path in files:
            out.extend(VectorLabelSource(path, self.attribute).features())
        return out
