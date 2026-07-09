"""End-to-end integration with a mock provider: discover-like selection ->
"download" (synthetic write) -> preprocess -> patch. No network."""

import numpy as np
from shapely.geometry import box, mapping

from sentinel_crop_pipeline.discovery.providers.base import DataProvider, Scene
from sentinel_crop_pipeline.discovery.scene_selector import SceneSelector
from sentinel_crop_pipeline.patching.tiler import run_patching
from sentinel_crop_pipeline.preprocessing.pipeline import run_preprocess
from tests.conftest import write_raw_scene

AOI = box(26.65, 38.25, 26.85, 38.36)


class MockProvider(DataProvider):
    name = "mock"

    def __init__(self):
        footprint = mapping(box(26.0, 38.0, 27.5, 39.0))
        self.scenes = [
            Scene("S2_GOOD_0615", "mock", "2025-06-15T09:00:00Z", 8.0, footprint),
            Scene("S2_CLOUDY_0620", "mock", "2025-06-20T09:00:00Z", 65.0, footprint),
            Scene("S2_GOOD_0705", "mock", "2025-07-05T09:00:00Z", 3.0, footprint),
        ]

    def search(self, aoi_geom, start, end, max_cloud_cover=100.0):
        return [s for s in self.scenes
                if s.cloud_cover is None or s.cloud_cover <= max_cloud_cover]

    def download(self, scene, aoi_geom, bands, out_dir, resolution_m=10,
                 assume_yes=False):
        from pathlib import Path
        return write_raw_scene(Path(out_dir) / f"{scene.id}.tif", size=64,
                               bands=tuple(bands), cloud_rows=8)

    def get_scl_mask(self, scene, aoi_geom, resolution_m=20):
        scl = np.full((20, 20), 4, dtype=np.uint8)
        scl[:2] = 9  # 10% invalid, under the 30% limit
        return scl


def test_full_pipeline_mock(tmp_path, base_cfg):
    cfg = dict(base_cfg)
    cfg["download"] = dict(base_cfg["download"], out_dir=str(tmp_path / "raw"))
    cfg["preprocessing"] = dict(base_cfg["preprocessing"],
                                out_dir=str(tmp_path / "interim"))
    cfg["patching"] = dict(
        base_cfg["patching"],
        cog_dir=str(tmp_path / "patches/cog"),
        train_dir=str(tmp_path / "patches/train"),
        index_file=str(tmp_path / "patches/index.csv"),
    )

    provider = MockProvider()
    selector = SceneSelector(cfg, crop_calendar={}, provider=provider)

    # discover: metadata filter drops the 65% cloudy scene at search time
    scenes = provider.search(AOI, "2025-04-01", "2025-10-31", max_cloud_cover=20)
    accepted = [s for s in scenes if selector.should_include(s, AOI).accepted]
    assert [s.id for s in accepted] == ["S2_GOOD_0615", "S2_GOOD_0705"]

    # download + preprocess + patch
    for scene in accepted:
        provider.download(scene, AOI, cfg["bands"]["base"],
                          cfg["download"]["out_dir"])
    stacks = run_preprocess(cfg)
    assert len(stacks) == 2

    records = run_patching(cfg)
    # 64x64 with 8 cloud rows: all 4 patches per scene stay under 40% invalid
    assert len(records) == 8
    splits = {r["split"] for r in records}
    assert splits <= {"train", "val", "test"}


def test_cli_label_fails_cleanly_without_patches(tmp_path, base_cfg):
    import yaml
    from sentinel_crop_pipeline.cli import main

    cfg = dict(base_cfg)
    cfg["patching"] = dict(
        base_cfg["patching"],
        index_file=str(tmp_path / "missing_index.csv"),
    )
    cfg["labeling"] = dict(
        base_cfg["labeling"],
        vector_path=str(tmp_path / "labels/parcels.geojson"),
    )
    # keep test run logs out of the real logs/ dir
    cfg["logging"] = {"dir": str(tmp_path / "logs"), "level": "INFO"}

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg))

    assert main(["label", "--config", str(config_path)]) == 1