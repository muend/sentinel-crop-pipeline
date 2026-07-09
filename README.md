# sentinel-crop-pipeline

![CI](https://github.com/muend/sentinel-crop-pipeline/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-Apache--2.0-green)

A reproducible Sentinel-2 data preparation pipeline for crop classification
and CNN/U-Net training: scene discovery, AOI-cropped download, cloud masking,
band stacking, spectral indices, fixed-size training patches, and ground-truth
label masks. Config-driven; change the AOI, dates, crop, bands, or patch size
in `config/default.yaml` without touching code.

Scope: this repository prepares training-ready data. Model training and
evaluation are done downstream by the consuming project; the patch/label
output format (float32 arrays + MASK band + spatially blocked splits) is
designed for that.

Built for a TUBITAK 2209-A crop mapping study (Izmir/Urla), designed to be
reusable for any Sentinel-2 crop pattern project.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | CDSE provider, rule-based scene selection, CLI | done |
| 2 | SCL masking, band stack, indices, normalization | done |
| 3 | Patch generation, COG + npy/TFRecord export, spatially-blocked 70/15/15 split | done |
| 4 | AI scene review (SceneJudge: Gemini/Claude), vector LabelSource, CKS import | done |
| 5 | CI, contributing guide, examples, release prep | done |
| 6 | Local review dashboard (optional extra) | planned |

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env    # then fill in CDSE credentials
```

CDSE credentials: create a free account at https://dataspace.copernicus.eu/,
then an OAuth client at https://shapps.dataspace.copernicus.eu/dashboard/
(User settings -> OAuth clients). Put the client id/secret in `.env`.
STAC search works without credentials; downloads and the SCL pixel check
require them.

## Quickstart

```bash
# 1. find candidate scenes, apply selection rules, write data/catalog/scenes.json
python -m src.cli discover --config config/default.yaml

# 2. download AOI-cropped stacks (reports estimated size first)
python -m src.cli download --config config/default.yaml

# 3. mask clouds (SCL), normalize, compute NDVI/NDRE -> data/interim/
python -m src.cli preprocess --config config/default.yaml

# 4. cut 256x256 patches -> COG + npy + data/patches/index.csv with splits
python -m src.cli patch --config config/default.yaml

# 5. rasterize field polygons to patch-aligned label masks
python -m src.cli label --config config/default.yaml

# or stages 1-4 in sequence (label is NOT included: it needs parcel data
# that usually arrives later; run it separately when ready):
python -m src.cli run-all --config config/default.yaml
```

`pip install -e .` also provides the `sentinel-crop` console command, e.g.
`sentinel-crop discover --config config/default.yaml`.

Each stage is independent: it reads the previous stage's output from disk, so a
failure in one stage does not affect the others. Every run writes a summary to
`logs/run_<stage>_<timestamp>.json` (scenes found/rejected/accepted, patch
counts), usable directly for methodology reporting.

Run tests: `pytest`

## Interim AOI

`data/aoi/urla_ilce_interim.geojson` is a simplified rectangle covering Urla
district — an INTERIM placeholder, not the official boundary. When real field
parcels (or an official boundary export) are available, replace the file and
point `aoi.path` at it; no code change is needed. The interim AOI (~31 x 27 km)
exceeds the Process API's 2500 px/axis limit at 10 m, so downloads are
automatically split into sub-tiles and mosaicked.

## Configuration

Key settings in `config/default.yaml`:

- `aoi.path` — GeoJSON polygon(s), EPSG:4326
- `time.start/end`, `time.crop` — set `crop: tomato` to restrict scenes to the
  sowing-harvest window in `config/crop_calendar.yaml`
- `search.max_cloud_cover_pct` — metadata pre-filter (default 20)
- `scl_filter` — pixel-based cloud/shadow limit computed from the real SCL band
- `ai_review.judge_provider` — `gemini | claude | none` (layer-2 review)
- `bands.base/extra` — B02/B03/B04/B08 by default; add B05..B12 as needed
- `patching.patch_size/stride` — stride < patch_size gives overlapping patches
- `patching.block_factor` — spatial block size for the group-aware split
- `labeling.source` — `vector` (GeoJSON/Shapefile) or `cks` (manual import)
- `split` — train/val/test ratios (default 70/15/15)

## Train/val/test split

The split is group-aware over spatial blocks, not random per patch: each patch
is keyed to a fixed world-grid cell (`spatial_block_id` in index.csv, cell side
= `block_factor` x patch size) and whole blocks are assigned to one split.
Neighbouring or overlapping patches therefore never end up in both train and
test, which would otherwise inflate F1/IoU through spatial autocorrelation.

## Data providers

Default is CDSE (Copernicus Data Space Ecosystem): the official ESA/EU source,
no Google account needed. Downloads use the Sentinel Hub Process API hosted on
CDSE, which returns only the AOI window instead of full ~1 GB SAFE products;
`download.method: odata` switches to full-product download.

`data_provider: gee` selects the optional Google Earth Engine provider
(search-only for now, `pip install ".[gee]"`). GEE requires a registered Google
Cloud project, so it is not the default. New providers can be added by
implementing `DataProvider` in `src/discovery/providers/`.

## Scene selection

Layer 1 (always on, deterministic): cloud metadata threshold, crop-calendar
date window, AOI overlap percentage, and a pixel-based SCL statistic over the
AOI.

Layer 2 (optional): an AI judge reviews an RGB preview of each scene that
passed layer 1. Judges follow the same plugin pattern as providers
(`SceneJudge`): `gemini` (default; free-tier Gemini Flash-Lite, needs
`GEMINI_API_KEY`, `pip install ".[ai]"`) or `claude` (needs
`ANTHROPIC_API_KEY`, `pip install ".[claude]"`). The model id is set in config
(`ai_review.model`) because Google's lineup changes frequently.

Graceful degradation: with `judge_provider: none`, a missing key/SDK, or a
failed API call (429/quota/timeout), the pipeline continues on the layer-1
result and flags the scene `needs_manual_review: true` in the selection log —
scenes are never auto-rejected by an unavailable judge. All decisions land in
`logs/selection_results.json` with per-check notes.

## Ground truth

`labeling.source: vector` reads field parcel polygons (GeoJSON natively,
Shapefile with `pip install ".[shapefile]"`) with the crop label in a property
(`labeling.attribute`, default `crop_type`), and rasterizes them into uint8
masks aligned to each patch (background = 0; class ids in
`data/patches/labels/class_map.json`).

CKS (Ciftci Kayit Sistemi) data is supported only via manual import
(`labeling.source: cks`): access requires permission from the
Provincial/District Directorate of Agriculture and Forestry, and this tool
does not and will not fetch it automatically. Place an officially obtained
export under `data/raw/cks_import/`.

Manual labeling: QGIS and Label Studio both export GeoJSON, which the vector
source reads directly — no custom labeling UI is planned.

## Output layout

```
data/
  catalog/scenes.json        accepted scenes (discover)
  raw/<scene>.tif            AOI-cropped uint16 stacks, bands + SCL (download)
  interim/<scene>_stack.tif  float32, NaN-masked, indices + MASK (preprocess)
  patches/cog/               georeferenced patches, open in QGIS (patch)
  patches/train/             npy/tfrecord + meta json for training (patch)
  patches/labels/            uint8 label masks + class_map.json (label)
  patches/index.csv          patch_id, scene, split, spatial_block_id, paths
logs/                        per-run JSON summaries
```

## Examples and contributing

`examples/` has reference outputs (selection audit log, patch index) from a
real Urla run and synthetic demo parcels for the label stage. Contributions:
see [CONTRIBUTING.md](CONTRIBUTING.md). To cite this software, see
[CITATION.cff](CITATION.cff).

## License

Apache 2.0. Sentinel-2 data: Copernicus Sentinel data, ESA — see the
[legal notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice).
