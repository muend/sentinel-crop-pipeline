# Colab technical pilot

These notebooks run the data-preparation package in Google Colab with persistent Google Drive storage. They do not train or evaluate a crop model.

1. Run `01_colab_drive_setup.ipynb` to mount Drive and create `MyDrive/TUBITAK_Urla`.
2. Use `02_colab_cdse_connection.ipynb` for CDSE authentication, package installation, catalog search, a small optional download, verified Drive persistence, and RGB preview. Run cells in order; later cells depend on earlier variables. Review the download cell before running the entire notebook.

Store `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` in Colab Secrets and grant the notebook access. Never paste credentials into notebook cells or commit executed outputs containing tokens. A successful authentication check alone does not establish Process API access.

The small helper scripts mirror the notebook's download/save/preview cells. Upload a script into the existing Colab session and run it with `%run -i <script_name.py>` to reuse variables from earlier cells. Save the temporary image to Drive before the runtime ends; the save helper verifies its checksum and raster grid and records provenance. The RGB stretch changes display only.

## Pilot area limitation

The hardcoded June 2025 AOI in the download cell and `colab_pilot_download.py` is a historical **technical test**, not an approved agricultural study area. The owner identified its old center as forest. Successful transfer, usable SCL pixels, or an RGB preview does not verify agricultural use or crop identity. Do not reuse that area or year for bulk research collection.

Field coordinates, candidate lists, boundary drafts, and private research notes are excluded from Git and are not distributed with these notebooks. Keep local AOI files under `data/aoi/local/`; keep parcel labels under `data/labels/`. Do not commit real field records as notebook outputs or embed them in documentation.

Candidate points are not field polygons. Confirm a dated reference, neighborhood/locality, coordinates, field boundary, and raster overlay before adopting a research AOI. Keep all dates for the same field in one spatial split.

The Process API request filters a full UTC day, not an exact STAC item. The provenance record therefore treats the selected catalog item as a candidate reference rather than a verified exclusive source product.

For classroom demonstration materials, see [`output/ders/`](../output/ders/). Their dates and counts describe the recorded historical demonstration.
