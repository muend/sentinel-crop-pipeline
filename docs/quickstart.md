# Quickstart: run the pipeline on your own AOI

## 1. Install

```bash
git clone https://github.com/muend/sentinel-crop-pipeline && cd sentinel-crop-pipeline
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest            # sanity check, no network needed
```

## 2. Credentials (.env)

1. Register (free) at https://dataspace.copernicus.eu/
2. Create an OAuth client: https://shapps.dataspace.copernicus.eu/dashboard/
   -> User settings -> OAuth clients
3. `cp .env.example .env` and fill `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`
4. Optional, for AI scene review: get a free Gemini key at
   https://aistudio.google.com/apikey, put it in `GEMINI_API_KEY`, install
   `pip install -e ".[ai]"`, and set `ai_review.judge_provider: gemini` in
   config. Without a key the pipeline runs layer-1 rules only.

## 3. Define your AOI

The repo ships with `data/aoi/urla_ilce_interim.geojson` — an interim
placeholder rectangle over Urla district. To use your own area, export it as
GeoJSON (EPSG:4326), e.g. from QGIS: right-click layer -> Export -> Save
Features As -> GeoJSON, put it under `data/aoi/` and set `aoi.path`.

Large AOIs are handled automatically: downloads above the Process API's
2500 px/axis limit are split into sub-tiles and mosaicked.

## 4. Configure dates and crop

```yaml
time:
  start: "2025-04-01"
  end: "2025-10-31"
  crop: cotton          # optional; uses config/crop_calendar.yaml windows
```

Add your own crops to `config/crop_calendar.yaml` as `sowing`/`harvest`
month-day pairs (windows crossing new year, e.g. wheat, are handled).

## 5. First live run: discover

```bash
python -m sentinel_crop_pipeline.cli discover --config config/default.yaml
```

Console output and `logs/run_discover_*.json` report: scenes found, accepted,
rejected (with per-check reasons), and needs_manual_review counts.
`logs/selection_results.json` has the full per-scene audit trail. If too few
scenes pass, tune `search.max_cloud_cover_pct`, `aoi.min_scene_overlap_pct`,
or `scl_filter.max_invalid_pct` and re-run — discovery is cheap.

Note: `discover` without `--skip-scl` calls the Process API per candidate
scene (needs credentials). Use `--skip-scl` for a free, metadata-only pass.

## 6. Download, preprocess, patch, label

```bash
python -m sentinel_crop_pipeline.cli download --config config/default.yaml     # add --yes above size threshold
python -m sentinel_crop_pipeline.cli preprocess --config config/default.yaml
python -m sentinel_crop_pipeline.cli patch --config config/default.yaml
# when you have parcel polygons (labeling.vector_path):
python -m sentinel_crop_pipeline.cli label --config config/default.yaml
```

## 7. Use the patches

- `data/patches/cog/` — drop into QGIS to inspect visually
- `data/patches/train/` — `np.load(path)` gives a `(bands, H, W)` float32
  array; band order is in the sidecar `.json` (last band = MASK)
- `data/patches/labels/` — uint8 masks aligned to patches; ids in
  `class_map.json`
- `data/patches/index.csv` — `split` (spatially blocked 70/15/15) and
  `spatial_block_id` columns

```python
import csv
import numpy as np

with open("data/patches/index.csv", newline="") as f:
    train = [r for r in csv.DictReader(f) if r["split"] == "train"]
X = [np.load(r["train_path"]) for r in train]
y = [np.load(r["label_path"].replace(".tif", ".npy")) for r in train]
```

## 8. Review the run (optional dashboard)

```bash
pip install -e ".[dashboard]"
streamlit run src/sentinel_crop_pipeline/dashboard/app.py
```

Opens a local, read-only review UI: scene map + table, patch/label browser,
split map, run history. It renders existing files only and makes no API calls.

## Troubleshooting

- `CDSE_CLIENT_ID ... not set` — fill `.env` (discover works without it if you
  pass `--skip-scl`; download never does).
- `Estimated download ... exceeds max_auto_size_mb` — re-run with `--yes` or
  raise the threshold in config.
- Zero patches produced — check `patching.max_invalid_frac` against your
  scenes' cloudiness, and that AOI size >= patch_size pixels.
- Judge always `needs_manual_review` — check the API key is in `.env` and the
  matching extra is installed (`pip install -e ".[ai]"`).
