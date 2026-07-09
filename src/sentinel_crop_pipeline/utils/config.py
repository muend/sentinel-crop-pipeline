"""Config loading and validation."""

from pathlib import Path

import yaml

REQUIRED_KEYS = ("data_provider", "aoi", "time", "search")

# Accept short band names (B2) and canonicalize to zero-padded (B02).
BAND_ALIASES = {
    "B1": "B01", "B2": "B02", "B3": "B03", "B4": "B04", "B5": "B05",
    "B6": "B06", "B7": "B07", "B8": "B08", "B9": "B09",
}


def normalize_band(name: str) -> str:
    name = str(name).upper()
    return BAND_ALIASES.get(name, name)


def load_config(path: str | Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ValueError(f"Config missing required keys: {missing}")
    bands = cfg.setdefault("bands", {})
    bands["base"] = [normalize_band(b) for b in bands.get("base", ["B02", "B03", "B04", "B08"])]
    bands["extra"] = [normalize_band(b) for b in bands.get("extra", []) or []]
    return cfg


def all_bands(cfg: dict) -> list[str]:
    return cfg["bands"]["base"] + cfg["bands"]["extra"]


def load_crop_calendar(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}
