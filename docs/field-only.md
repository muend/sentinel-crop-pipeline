# Field-only imagery

Use `config/urla_fields.yaml` for the field-focused workflow. The historical
rectangular AOI in `config/default.yaml` is a technical demonstration, not a
field inventory. Real field polygons and outputs stay private and ignored by Git.
Use a current repository checkout installed with `pip install -e .`; the
published 0.3.2 wheel predates this field-only feature.

## Inputs and validity

Place reviewed WGS84 GeoJSON polygons in `data/aoi/local/fields.geojson`.
Each field should have a stable `field_id`, neighborhood/locality, coordinate
reference, and dated evidence. Field geometry is an input to review, not a
product-type label inferred from a satellite image. Do not use candidate points,
village centers, NDVI thresholds, or SCL vegetation classes as field boundaries.

`preprocessing.field_mask_path` enables a geometric mask in addition to SCL.
The conservative mask excludes polygon holes, non-field areas, and every pixel
touched by the field boundary. Only complete interior pixels remain. Invalid
optical/index values become NaN; `FIELD_MASK` records geometric membership and
`MASK` records the combined field, source, and SCL validity. The raster's dataset
mask also marks invalid pixels for GIS applications. The native pixel grid and
resolution are preserved.

This excludes pixels outside the supplied boundary; boundary accuracy and
land-use interpretation still need review. No method can remove mixed content
already present within the sensor's footprint by increasing display size.

## Local processing of an existing download

After placing an existing raw image in `data/raw/fields/`, run:

```powershell
python -m sentinel_crop_pipeline.cli preprocess --config config/urla_fields.yaml
```

For a compact crop of just one field, including private polygon/checksum
provenance, run this fully local operation:

```powershell
python -m sentinel_crop_pipeline.preprocessing.field_mask --input data/raw/fields/scene.tif --fields data/aoi/local/fields.geojson --field-id FIELD_ID --output data/interim/field_crops/FIELD_ID_crop.tif
```

The crop writes a COG at the original resolution and keeps only usable interior
pixels. Everything else is NoData; its preview should use transparency. The
source download remains intact. Keep per-field crop exports outside the
full-scene preprocessing input/output batch folders when producing patches so
the same scene is not consumed twice.

For future approved collection, `download.field_only: true` writes the API
response into a temporary directory and persists only compact per-field COGs
under `data/raw/fields/`, with individual field IDs, masks, and private provenance.
The temporary context is discarded after crop export. This mode requires
Process API downloads and the explicit field polygon file; it does not silently
fall back to saving an unmasked rectangle.

## Training patches

The field-only configuration sets `patching.require_field_mask: true` and
`patching.min_field_fraction: 1.0`. It rejects historical unmasked stacks and
accepts a window only when every cell lies inside the field mask. SCL/cloud
validity is still checked separately. Missing field files, wrong geometry/CRS,
or no interior pixels cause an explicit failure instead of silently accepting
background. The field mask is an extra input band; consumers must use the
recorded band names rather than assume the historical six-channel stack.

Small or narrow fields may yield a crop but no full 256x256 training patch.
Choose the model's sampling strategy after reviewing real field sizes. Do not
upscale pixels or relax field purity merely to manufacture training samples.
Keep each field's dates together when defining spatial evaluation groups.

Remote collection still requires the user's approved area/date scope. The
preprocess/crop operations above do not contact Copernicus. A context download
can support alignment review, but it is not a field-only dataset artifact.
