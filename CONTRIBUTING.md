# Contributing

Bug reports, provider/judge implementations, and doc fixes are welcome.

## Setup

```bash
git clone https://github.com/muend/sentinel-crop-pipeline && cd sentinel-crop-pipeline
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest       # must pass before and after your change; no network needed
```

## Ground rules

- Every change keeps the test suite green. New behaviour needs a test
  (mocks/synthetic rasters — tests must not hit the network).
- Runtime behaviour is config-driven: new knobs go in `config/default.yaml`
  with a short comment, not as code constants.
- Never commit credentials. `.env` is gitignored; placeholders belong in
  `.env.example`.
- CKS and similar permission-gated data sources are manual-import only.
  Do not add scraping or automated access.
- Code, comments, and docs are English. Keep comments short and functional;
  explain *why*, not *what*. No marketing language.
- Commit messages: short and technical (`Fix SCL mask indexing bug`), no
  multi-paragraph epics.

## Adding a data provider

Implement `DataProvider` (`src/sentinel_crop_pipeline/discovery/providers/base.py`): `search()`,
`download()`, `get_scl_mask()`. Register it in `providers/registry.py` and add
tests with mocked responses. Heavy SDKs go in an optional extra in
`pyproject.toml`, with graceful degradation when the extra is missing.

## Adding a scene judge

Implement `SceneJudge` (`src/sentinel_crop_pipeline/discovery/judge.py`): `evaluate(scene, preview)
-> JudgeResult`. Any failure (missing key, quota, timeout) must degrade to
`needs_manual_review`, never stop the pipeline or auto-reject a scene.

## Do not silently reverse

Design decisions recorded in `docs/architecture.md` (spatially blocked split,
mask-don't-delete, CDSE default, judge degradation) have documented rationale.
Open an issue before changing them.
