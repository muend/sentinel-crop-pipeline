# Examples

Small reference outputs so you can see what the pipeline produces without
running it, plus demo input for the label stage.

- `selection_results.example.json` — two entries from a real Urla run
  (2026-07): one accepted scene and one rejected by the SCL pixel check
  (`scl_invalid=49.1%` on a scene that passed the metadata cloud filter —
  the reason the pixel-based check exists). `needs_manual_review: true`
  means layer-2 AI review was disabled, so acceptance rests on layer-1 only.
- `index.example.csv` — first rows of a real `data/patches/index.csv`:
  per-patch split assignment, `spatial_block_id` (group-aware split key),
  COG/npy paths, invalid-pixel fraction.
- `sample_parcels.geojson` — three synthetic parcels (tomato, maize,
  vineyard) inside the interim Urla AOI. Not real ground truth; use it to
  try the label stage:

```bash
python -m src.cli label --config config/default.yaml
# after setting labeling.vector_path: examples/sample_parcels.geojson
```
