"""LabelSource interface: vector ground truth -> patch-aligned raster masks.

Implementations: VectorLabelSource (field GPS polygons, GeoJSON/Shapefile),
CksImportSource (manual CKS export import). A QGIS/Label Studio bridge is
planned; both tools already export GeoJSON, which VectorLabelSource reads.
"""

from abc import ABC, abstractmethod


class LabelSourceError(RuntimeError):
    pass


class LabelSource(ABC):
    @abstractmethod
    def features(self) -> list[tuple[dict, str]]:
        """(GeoJSON geometry in EPSG:4326, crop label string) pairs."""
