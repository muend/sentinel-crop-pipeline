"""Local review dashboard (Phase 6). Read-only: renders files already under
logs/ and data/. No CDSE/Gemini/Claude calls - API keys are never touched.

Run from the repo root:

    streamlit run src/dashboard/app.py

Needs the optional extra:  pip install -e ".[dashboard]"
"""

import sys
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st
import yaml

# streamlit runs this file as a script, not a package member
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.dashboard import data as d  # noqa: E402

st.set_page_config(page_title="sentinel-crop-pipeline", layout="wide")

STATUS_COLORS = {          # RGBA
    "accepted": [46, 160, 67, 90],
    "needs_manual_review": [255, 165, 0, 90],
    "rejected": [218, 54, 51, 90],
}
SPLIT_COLORS = {
    "train": [31, 119, 180, 120],
    "val": [255, 127, 14, 120],
    "test": [214, 39, 40, 120],
}


@st.cache_data
def _cfg() -> dict:
    p = Path("config/default.yaml")
    return yaml.safe_load(p.read_text()) if p.exists() else {}


@st.cache_data
def _aoi_geojson(path: str):
    p = Path(path)
    if not p.exists():
        return None
    import json
    return json.loads(p.read_text())


@st.cache_data
def _bounds(cog_path: str):
    return d.patch_bounds_wgs84(cog_path)


cfg = _cfg()
log_dir = cfg.get("logging", {}).get("dir", "logs")
index_file = cfg.get("patching", {}).get("index_file", "data/patches/index.csv")
labels_dir = cfg.get("labeling", {}).get("out_dir", "data/patches/labels")
aoi_path = cfg.get("aoi", {}).get("path", "data/aoi/urla_ilce_interim.geojson")

st.title("sentinel-crop-pipeline — run review")
st.caption("Read-only. Renders logs/ and data/ from disk; makes no API calls.")

tab_map, tab_scenes, tab_patches, tab_split, tab_runs = st.tabs(
    ["Scene map", "Scene table", "Patch browser", "Split map", "Run history"])

results = d.load_selection_results(log_dir)
catalog_geoms = d.load_catalog_geometries("data/catalog/scenes.json")


with tab_map:
    if not results:
        st.info("No logs/selection_results.json yet — run `discover` first.")
    else:
        features = []
        for r in results:
            geom = r.get("geometry") or catalog_geoms.get(r.get("scene_id"))
            if not geom:
                continue
            status = d.scene_status(r)
            features.append({
                "type": "Feature", "geometry": geom,
                "properties": {"scene_id": r["scene_id"], "status": status,
                               "color": STATUS_COLORS[status]},
            })
        missing = len(results) - len(features)
        if missing:
            st.warning(f"{missing} scene(s) lack a stored footprint "
                       "(older discover log). Re-run `discover` to log geometry.")
        layers = []
        aoi = _aoi_geojson(aoi_path)
        if aoi:
            layers.append(pdk.Layer(
                "GeoJsonLayer", aoi, stroked=True, filled=False,
                get_line_color=[0, 0, 0, 255], line_width_min_pixels=2))
        if features:
            layers.append(pdk.Layer(
                "GeoJsonLayer", {"type": "FeatureCollection", "features": features},
                stroked=True, filled=True, get_fill_color="properties.color",
                get_line_color=[60, 60, 60, 200], line_width_min_pixels=1,
                pickable=True))
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(latitude=38.3, longitude=26.77, zoom=8),
            tooltip={"text": "{scene_id}\n{status}"},
            map_style=None))
        st.caption("green = accepted, orange = needs manual review, red = rejected; "
                   "black outline = AOI")

with tab_scenes:
    if not results:
        st.info("No selection results yet.")
    else:
        df = pd.DataFrame(d.selection_table(results))
        statuses = st.multiselect("Status", sorted(df["status"].unique()),
                                  default=list(df["status"].unique()))
        st.dataframe(df[df["status"].isin(statuses)], width="stretch",
                     hide_index=True)

with tab_patches:
    index = d.load_index(index_file)
    if not index:
        st.info(f"No {index_file} yet — run `patch` first.")
    else:
        scenes = sorted({r["scene"] for r in index})
        scene = st.selectbox("Scene", scenes)
        rows = [r for r in index if r["scene"] == scene]
        patch = st.selectbox("Patch", [r["patch_id"] for r in rows])
        row = next(r for r in rows if r["patch_id"] == patch)

        rgb, _ = d.read_patch_rgb(row["cog_path"])
        label = d.read_label_mask(row["label_path"]) if row.get("label_path") else None
        col1, col2 = st.columns(2)
        col1.image(rgb, caption=f"{patch} (RGB)", width="stretch")
        if label is not None:
            import numpy as np
            opacity = st.slider("Label overlay opacity", 0.0, 1.0, 0.5)
            classes = d.load_class_map(labels_dir)
            palette = [[0, 0, 0], [230, 25, 75], [60, 180, 75], [255, 225, 25],
                       [0, 130, 200], [245, 130, 48], [145, 30, 180], [70, 240, 240]]
            colored = np.zeros((*label.shape, 3), dtype="uint8")
            for cid in np.unique(label):
                colored[label == cid] = palette[int(cid) % len(palette)]
            blend = (rgb * (1 - opacity) + colored * opacity).astype("uint8")
            col2.image(blend, caption="RGB + label mask", width="stretch")
            if classes:
                st.caption("classes: " + ", ".join(f"{k}={v}" for k, v in classes.items()))
        else:
            col2.info("No label mask for this patch — run `label` when parcel "
                      "data is available.")
        st.caption(f"split={row['split']}  block={row['spatial_block_id']}  "
                   f"invalid_frac={row['invalid_frac']}")

with tab_split:
    index = d.load_index(index_file)
    if not index:
        st.info(f"No {index_file} yet — run `patch` first.")
    else:
        scenes = sorted({r["scene"] for r in index})
        scene = st.selectbox("Scene (patch grids are identical across scenes)",
                             scenes, key="split_scene")
        rows = [r for r in index if r["scene"] == scene]
        polys = []
        for r in rows:
            ring = _bounds(r["cog_path"])
            if ring:
                polys.append({"polygon": ring, "split": r["split"],
                              "block": r["spatial_block_id"],
                              "color": SPLIT_COLORS.get(r["split"], [128] * 3 + [120])})
        if not polys:
            st.warning("Patch COGs not readable — did data/patches/cog move?")
        else:
            st.pydeck_chart(pdk.Deck(
                layers=[pdk.Layer("PolygonLayer", polys, get_polygon="polygon",
                                  get_fill_color="color",
                                  get_line_color=[40, 40, 40, 200],
                                  line_width_min_pixels=1, pickable=True)],
                initial_view_state=pdk.ViewState(latitude=38.3, longitude=26.77,
                                                 zoom=9),
                tooltip={"text": "split: {split}\nblock: {block}"},
                map_style=None))
            st.caption("blue = train, orange = val, red = test. Whole spatial "
                       "blocks share one split — adjacent patches never straddle "
                       "train/test.")

with tab_runs:
    runs = d.load_run_logs(log_dir)
    if not runs:
        st.info("No run logs yet.")
    else:
        st.dataframe(pd.DataFrame(
            [{"stage": r["stage"], "started": r["started"],
              "finished": r["finished"],
              **{k: v for k, v in r["summary"].items() if not isinstance(v, dict)}}
             for r in runs]), width="stretch", hide_index=True)
        with st.expander("Raw summaries"):
            for r in runs:
                st.write(f"`{r['file']}`", r["summary"])
