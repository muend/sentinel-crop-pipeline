"""Provider abstraction.

Implementations: CDSE (default) and GEE (optional). New providers (Planet,
Landsat, ...) implement DataProvider and register in registry.py.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path


class ProviderError(RuntimeError):
    pass


class ProviderNotAvailable(ProviderError):
    """Provider dependencies or credentials are missing."""


@dataclass
class Scene:
    id: str
    provider: str
    datetime: str                 # ISO 8601
    cloud_cover: float | None
    geometry: dict                # GeoJSON footprint
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(**{k: d[k] for k in ("id", "provider", "datetime", "cloud_cover",
                                        "geometry", "properties")})


class DataProvider(ABC):
    name: str = "base"

    @abstractmethod
    def search(self, aoi_geom, start: str, end: str,
               max_cloud_cover: float = 100.0) -> list[Scene]:
        """Return scenes intersecting the AOI in [start, end] (ISO dates)."""

    @abstractmethod
    def download(self, scene: Scene, aoi_geom, bands: list[str], out_dir: str | Path,
                 resolution_m: int = 10, assume_yes: bool = False) -> Path:
        """Download an AOI-cropped band stack (bands + SCL) as GeoTIFF."""

    @abstractmethod
    def get_scl_mask(self, scene: Scene, aoi_geom, resolution_m: int = 20):
        """Return the SCL band over the AOI as a 2D uint8 array."""
