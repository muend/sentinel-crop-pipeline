# Session handoff

State transfer document for continuing development in a new working session.
Read this file plus README.md and docs/architecture.md before making changes.

## Project

Sentinel-2 data preparation pipeline for CNN/U-Net crop classification
(TUBITAK 2209-A study, Izmir/Urla; backup sites Menemen plain, K. Menderes
basin). Open source, Apache 2.0, config-driven, provider-agnostic.
Repo: https://github.com/muend/sentinel-crop-pipeline (branch main).
Local working copy: C:\Projeler\sentinel-crop-pipeline

## Phase status

| Phase | Scope | State |
|---|---|---|
| 1 | DataProvider ABC, CdseProvider (STAC search, OAuth2, Process API, OData fallback, backoff), rule-based SceneSelector, CLI | done, tested |
| 2 | SCL masking (NaN + MASK band), reflectance/minmax normalization, NDVI/NDRE/NDWI, 20m->10m resample util | done, tested |
| 3 | Patch generation (COG + npy/TFRecord), spatially-blocked group-aware 70/15/15 split (spatial_block_id) | done, tested (revised: random split replaced after review) |
| 4 | SceneJudge plugin layer (GeminiFlashJudge default, ClaudeJudge optional, graceful degradation -> needs_manual_review), VectorLabelSource + CKS manual import + rasterize to patch-aligned masks, CLI label | done, tested |
| 5 | Release prep: CONTRIBUTING, CI workflow, demo run with real data | NOT started |
| 6 | Local Streamlit dashboard (optional extra) | NOT started, spec below |
| 6b | Dashboard write-back (manual review decisions to review_decisions.csv) | deliberately deferred, do not build with 6 |

Test suite: 60 tests, all passing (pytest, no network needed; mocks +
synthetic rasters). Live CDSE download/judge paths NOT yet exercised with real
credentials - first live `discover` run by the project owner is the immediate
next step.

## Live validation results (2026-07-09, DONE)

Live discover ran successfully with real CDSE credentials on the interim AOI:
- STAC search: 48 L2A scenes (2025-04-01..2025-10-31, all tile T35SMC,
  ~5-10 day cadence - good time-series density)
- Layer 1 with SCL pixel check: 47 accepted, 1 rejected
  (S2C 2025-10-28: scl_invalid=49.1% > 30% - the SCL check caught a scene
  that passed the metadata cloud filter, exactly as designed)
- Thresholds (cloud 20%, overlap 60%, scl 30%) validated; no recalibration
  needed for now.
- Owner's .env has CDSE credentials AND GEMINI_API_KEY (local only, gitignored,
  never commit). Config still judge_provider: none; all accepted scenes were
  flagged needs_manual_review as expected. Enabling Gemini judge requires
  `pip install -e ".[ai]"` + config change - GeminiFlashJudge is NOT yet
  live-tested.

## Immediate next steps (in order)

1. First live download on a SUBSET (full run = 47 scenes x ~81 MB = ~3.8 GB;
   don't start with that). Narrow time.start/end to one month (~6 scenes,
   ~0.5 GB), re-run discover, then `download --yes`, `preprocess`, `patch` -
   verifies the tiled download+mosaic path end to end.
2. Optionally live-test GeminiFlashJudge on the subset (judge_provider: gemini).
3. Phase 5 (release prep), then Phase 6 (dashboard, spec below).

## Phase 6 spec (agreed, do not re-negotiate)

Streamlit app at src/dashboard/app.py, run with
`streamlit run src/dashboard/app.py`. Packaged as optional extra
`pip install -e ".[dashboard]"` - core pipeline must not depend on Streamlit.
Constraints: fully local, single user, no auth, READ-ONLY MVP, and NO live API
calls (no CDSE/Gemini/Claude requests from the dashboard; it only reads files
already on disk under logs/ and data/). Views:
1. Scene map: AOI boundary + scene footprints, color-coded by
   accept/reject/needs_manual_review (from logs/selection_results.json)
2. Scene table: cloud %, SCL stats, judge verdict/confidence/reason;
   filterable/sortable
3. Patch/label browser: RGB composite + label mask side-by-side or overlaid
   (opacity slider) from data/patches/
4. Split map: patches colored by split via spatial_block_id - visual proof of
   spatial separation
5. Run history: summaries from logs/run_*.json

## Key design decisions (do not silently reverse)

- CDSE default provider; STAC endpoint https://stac.dataspace.copernicus.eu/v1,
  collection sentinel-2-l2a (verified against live catalog 2026-07).
  Cloud-cover and product-type re-filtered client-side for robustness.
- Downloads via Sentinel Hub Process API on CDSE, UTM bbox output; AOIs above
  2500 px/axis are auto-tiled (_tile_grid) and mosaicked. OData full-SAFE
  fallback exists (download.method: odata).
- Mask, don't delete: invalid SCL classes {0,1,3,8,9,10,11} -> NaN + MASK band.
- Split is group-aware over spatial blocks (spatial_block_id, deficit-greedy,
  seeded). Random patch-level split is forbidden (spatial autocorrelation
  inflates F1/IoU). Acceptance test: test_no_spatial_block_crosses_splits.
- Layer-2 judge: plugin pattern, judge_provider: gemini|claude|none.
  Graceful degradation is mandatory - missing key/SDK/429 => scene flagged
  needs_manual_review, layer-1 decision stands, pipeline never stops. Model id
  lives in config (ai_review.model, default gemini-3.1-flash-lite) because
  Google's lineup changes; no quota numbers in code, only 429 backoff.
- CKS: manual import only (data/raw/cks_import/), no scraping ever. Legal note
  in README and src/labeling/cks.py.
- data/aoi/urla_ilce_interim.geojson is an INTERIM placeholder bbox, not the
  official district boundary (OSM boundary APIs unreachable from the build
  env). Owner's field parcels arrive later (TUBITAK months 3-5); swapping the
  file is the only change needed.
- License Apache 2.0 (owner's explicit choice over MIT).
- Code style: English, terse engineer-style comments, no marketing language,
  short technical commit messages.

## Environment notes

- Owner machine: Windows, Python 3.12 venv at .venv, deps from
  `pip install -e ".[dev]"`. Use `python -m pytest` (not bare `pytest`) if
  PATH picks up a global pytest.
- Git LF/CRLF warnings on Windows are benign; .gitattributes added
  (`* text=auto`).
- Known incident: during the previous session, file syncs occasionally
  truncated files edited in place (fixed for pyproject.toml, cli.py,
  test_cdse_provider.py and others; full integrity sweep passed). If a weird
  SyntaxError appears, first check the file tail for truncation and compare
  with git history.
- Judge SDKs are optional extras: .[ai] -> google-genai (GEMINI_API_KEY),
  .[claude] -> anthropic (ANTHROPIC_API_KEY). Without them judge degrades
  gracefully; 60-test suite needs neither.

## File map (non-obvious bits)

- src/discovery/judge.py        SceneJudge ABC + Gemini/Claude impls + get_judge
- src/discovery/scene_selector.py  layer-1 checks + layer-2 wiring +
                                   SelectionResult(needs_manual_review)
- src/patching/tiler.py         spatial_block_id + _assign_splits (group-aware)
- src/labeling/rasterize.py     run_labeling: index.csv patches -> label tifs,
                                class_map.json, adds label_path column
- src/utils/run_logger.py       logs/run_<stage>_<ts>.json audit trail
- config/default.yaml           single source of runtime truth; aoi.path,
                                ai_review.judge_provider, patching.block_factor,
                                labeling.* are the frequently-tuned knobs
- tests/conftest.py             base_cfg fixture + write_raw_scene synthetic
                                scene builder (used by most tests)

## How to resume in a new session

1. Mount folder: C:\Projeler\sentinel-crop-pipeline
2. Opening message should include: "Read docs/HANDOFF.md first", the live
   discover results (log summaries) if available, and the current task
   (threshold calibration / Phase 5 / Phase 6 per the spec above).
3. Verify before changing anything: `python -m pytest` -> 60 passed.
4. Update this file at the end of each session (phase table + next steps).
