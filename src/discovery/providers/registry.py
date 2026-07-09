"""Provider lookup by config name."""

from .base import DataProvider, ProviderError


def get_provider(cfg: dict) -> DataProvider:
    name = str(cfg.get("data_provider", "cdse")).lower()
    if name == "cdse":
        from .cdse import CdseProvider
        return CdseProvider(cfg)
    if name == "gee":
        from .gee import GeeProvider
        return GeeProvider(cfg)
    raise ProviderError(f"Unknown data_provider '{name}' (expected: cdse | gee)")
