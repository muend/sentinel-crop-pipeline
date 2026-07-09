import csv
import json
from collections import defaultdict

import numpy as np
import rasterio

from sentinel_crop_pipeline.patching.tiler import iter_windows, run_patching
from sentinel_crop_pipeline.preprocessing.pipeline import preprocess_scene
from tests.conftest import write_raw_scene


def test_iter_windows_counts():
    assert len(list(iter_windows(64, 64, 32, 32))) == 4
    assert len(list(iter_windows(64, 64, 32, 16))) == 9   # 50% overlap
    assert len(list(iter_windows(30, 30, 32, 32))) == 0   # too small


def _prepare(tmp_path, base_cfg, cloud_rows=32, size=64):
    """Raw scene, top `cloud_rows` rows cloudy -> interim stack."""
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
    raw = write_raw_scene(tmp_path / "raw" / "scene1.tif", size=size,
                          cloud_rows=cloud_rows)
    preprocess_scene(raw, tmp_path / "interim" / "scene1_stack.tif", cfg)
    return cfg


def test_patching_drops_invalid_and_writes_outputs(tmp_path, base_cfg):
    # Top half cloudy: the 2 top 32x32 patches are 100% invalid and dropped.
    cfg = _prepare(tmp_path, base_cfg, cloud_rows=32)
    records = run_patching(cfg)
    assert len(records) == 2

    for rec in records:
        with rasterio.open(rec["cog_path"]) as src:
            assert src.width == src.height == 32
            assert "MASK" in src.descriptions
            assert src.crs is not None and src.transform is not None
        arr = np.load(rec["train_path"])
        assert arr.shape[0] == 6 and not np.isnan(arr).any()
        meta = json.loads(open(rec["train_path"] + ".json").read())
        assert meta["patch_id"] == rec["patch_id"]
        assert meta["spatial_block_id"] == rec["spatial_block_id"]

    with open(cfg["patching"]["index_file"]) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert all(r["split"] in ("train", "val", "test") for r in rows)
    assert all(r["spatial_block_id"] for r in rows)


def test_no_spatial_block_crosses_splits(tmp_path, base_cfg):
    """Acceptance: a spatial_block_id never appears in more than one split."""
    cfg = _prepare(tmp_path, base_cfg, cloud_rows=0)
    cfg["patching"]["patch_size"] = 8
    cfg["patching"]["stride"] = 8
    cfg["patching"]["block_factor"] = 2   # 16px blocks -> 16 blocks of 4 patches
    records = run_patching(cfg)
    assert len(records) == 64

    block_splits = defaultdict(set)
    for r in records:
        block_splits[r["spatial_block_id"]].add(r["split"])
    assert len(block_splits) == 16
    offenders = {b: s for b, s in block_splits.items() if len(s) > 1}
    assert not offenders, f"blocks in multiple splits: {offenders}"
    # all three splits populated in this scenario
    assert {s for ss in block_splits.values() for s in ss} == {"train", "val", "test"}


def test_neighbouring_patches_share_block(tmp_path, base_cfg):
    cfg = _prepare(tmp_path, base_cfg, cloud_rows=0)
    cfg["patching"]["patch_size"] = 8
    cfg["patching"]["stride"] = 8
    cfg["patching"]["block_factor"] = 4   # 32px blocks -> 4x4 patches per block
    records = run_patching(cfg)
    by_id = {r["patch_id"]: r for r in records}
    # adjacent patches within one 32px block
    assert (by_id["scene1_stack_r0_c0"]["spatial_block_id"]
            == by_id["scene1_stack_r8_c8"]["spatial_block_id"])
    # patches in different 32px blocks
    assert (by_id["scene1_stack_r0_c0"]["spatial_block_id"]
            != by_id["scene1_stack_r0_c32"]["spatial_block_id"])


def test_group_split_ratios_with_many_blocks(tmp_path, base_cfg):
    cfg = _prepare(tmp_path, base_cfg, cloud_rows=0)
    cfg["patching"]["patch_size"] = 8
    cfg["patching"]["stride"] = 8
    cfg["patching"]["block_factor"] = 1   # 64 singleton blocks
    records = run_patching(cfg)
    counts = {s: sum(1 for r in records if r["split"] == s)
              for s in ("train", "val", "test")}
    assert sum(counts.values()) == 64
    # deficit-greedy over singleton blocks lands within 1 patch of each target
    for split, ratio in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        assert abs(counts[split] - 64 * ratio) <= 1, counts


def test_split_deterministic_with_seed(tmp_path, base_cfg):
    cfg = _prepare(tmp_path, base_cfg, cloud_rows=0)
    cfg["patching"]["patch_size"] = 8
    cfg["patching"]["stride"] = 8
    first = {r["patch_id"]: r["split"] for r in run_patching(cfg)}
    second = {r["patch_id"]: r["split"] for r in run_patching(cfg)}
    assert first == second


def test_patch_georeference_matches_window(tmp_path, base_cfg):
    cfg = _prepare(tmp_path, base_cfg, cloud_rows=0)
    records = run_patching(cfg)
    rec = next(r for r in records if r["patch_id"].endswith("_r32_c32"))
    src_path = f"{cfg['preprocessing']['out_dir']}/scene1_stack.tif"
    with rasterio.open(src_path) as src, rasterio.open(rec["cog_path"]) as patch:
        expected_x, expected_y = src.xy(32, 32, offset="ul")
        got_x, got_y = patch.transform * (0, 0)
        assert (got_x, got_y) == (expected_x, expected_y)
        assert patch.crs == src.crs


def test_index_paths_are_posix(tmp_path, base_cfg):
    # index.csv must stay readable on Linux/macOS training environments
    cfg = _prepare(tmp_path, base_cfg, cloud_rows=0)
    for rec in run_patching(cfg):
        assert "\\" not in rec["cog_path"]
        assert "\\" not in rec["train_path"]
