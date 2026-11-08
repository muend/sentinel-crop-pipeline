"""Fixed-size patch generation from preprocessed stacks.

Each patch keeps its CRS/transform (COG). Patches with too many invalid pixels
(MASK band) are dropped.

Train/val/test split is group-aware over spatial blocks: patches are keyed to
fixed world-grid cells (cell side = block_factor * patch_size pixels) and whole
blocks are assigned to one split. Neighbouring or overlapping patches share a
block and therefore never cross splits - a random patch-level split would let
spatial autocorrelation inflate F1/IoU on the test set.
"""

import csv
import math
import random
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from sentinel_crop_pipeline.patching.export import write_cog, write_npy, write_tfrecord

SPLITS = ("train", "val", "test")


def iter_windows(width: int, height: int, size: int, stride: int):
    for row in range(0, height - size + 1, stride):
        for col in range(0, width - size + 1, stride):
            yield row, col


def spatial_block_id(transform, crs, row: int, col: int,
                     patch_size: int, block_factor: int) -> str:
    """Block id from the patch's upper-left world position on a fixed grid.

    The grid origin is the CRS origin, so ids are stable across scenes that
    share a CRS (same UTM zone).
    """
    x, y = transform * (col, row)
    block_m = abs(transform.a) * patch_size * block_factor
    epsg = crs.to_epsg() if crs is not None else 0
    return f"{epsg}_{math.floor(x / block_m)}_{math.floor(y / block_m)}"


def _invalid_frac(arr: np.ndarray, mask_index: int | None) -> float:
    if mask_index is not None:
        return float(1.0 - np.mean(arr[mask_index]))
    return float(np.mean(np.isnan(arr[0])))


def _assign_splits(records: list[dict], split_cfg: dict) -> None:
    """Group-aware split: all patches of a spatial block get the same split.

    Blocks are shuffled with the configured seed, then greedily assigned to
    the split with the largest remaining deficit vs. its target patch count.
    With many blocks the result converges to the configured ratios; with few
    blocks it is necessarily coarse.
    """
    ratios = {k: float(split_cfg.get(k, d))
              for k, d in (("train", 0.70), ("val", 0.15), ("test", 0.15))}
    total_ratio = sum(ratios.values())
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError(f"split ratios must sum to 1.0, got {total_ratio}")
    if not records:
        return

    blocks: dict[str, list[int]] = {}
    for i, rec in enumerate(records):
        blocks.setdefault(rec["spatial_block_id"], []).append(i)
    block_ids = sorted(blocks)
    random.Random(int(split_cfg.get("seed", 42))).shuffle(block_ids)

    n = len(records)
    targets = {s: n * ratios[s] for s in SPLITS}
    counts = dict.fromkeys(SPLITS, 0)
    for bid in block_ids:
        split = max(SPLITS, key=lambda s: targets[s] - counts[s])
        for i in blocks[bid]:
            records[i]["split"] = split
        counts[split] += len(blocks[bid])


def run_patching(cfg: dict, logger=None) -> list[dict]:
    pcfg = cfg.get("patching", {})
    size = int(pcfg.get("patch_size", 256))
    stride = int(pcfg.get("stride", size))
    block_factor = int(pcfg.get("block_factor", 4))
    max_invalid = float(pcfg.get("max_invalid_frac", 0.4))
    require_field_mask = bool(pcfg.get("require_field_mask", False))
    min_field_fraction = float(pcfg.get("min_field_fraction", 0.0))
    if not 0 <= min_field_fraction <= 1:
        raise ValueError("patching.min_field_fraction must be between 0 and 1")
    export_format = str(pcfg.get("export_format", "npy")).lower()
    cog_dir = Path(pcfg.get("cog_dir", "data/patches/cog"))
    train_dir = Path(pcfg.get("train_dir", "data/patches/train"))
    index_file = Path(pcfg.get("index_file", "data/patches/index.csv"))

    interim = sorted(Path(cfg.get("preprocessing", {})
                          .get("out_dir", "data/interim")).glob("*.tif"))
    records: list[dict] = []
    skipped = 0
    skipped_field = 0

    for tif in interim:
        with rasterio.open(tif) as src:
            names = [d or f"band_{i}" for i, d in enumerate(src.descriptions, 1)]
            mask_index = names.index("MASK") if "MASK" in names else None
            field_index = names.index("FIELD_MASK") if "FIELD_MASK" in names else None
            if (require_field_mask or min_field_fraction > 0) and field_index is None:
                raise ValueError(f"{tif}: FIELD_MASK required; preprocess with field_mask_path first")
            if field_index is not None and mask_index is None:
                raise ValueError(f"{tif}: FIELD_MASK requires a combined MASK band")
            for row, col in iter_windows(src.width, src.height, size, stride):
                win = Window(col, row, size, size)
                arr = src.read(window=win)
                if field_index is not None:
                    if np.any((arr[mask_index] > 0) & (arr[field_index] <= 0)):
                        raise ValueError(f"{tif}: valid pixels found outside FIELD_MASK")
                    if float(np.mean(arr[field_index] > 0)) < min_field_fraction:
                        skipped_field += 1
                        continue
                invalid = _invalid_frac(arr, mask_index)
                if invalid > max_invalid:
                    skipped += 1
                    continue
                pid = f"{tif.stem}_r{row}_c{col}"
                transform = src.window_transform(win)
                block = spatial_block_id(src.transform, src.crs, row, col,
                                         size, block_factor)
                meta = {
                    "patch_id": pid, "scene": tif.stem, "row": row, "col": col,
                    "bands": names, "crs": str(src.crs),
                    "transform": list(transform)[:6],
                    "invalid_frac": round(invalid, 4),
                    "spatial_block_id": block,
                }
                cog_path = write_cog(cog_dir / tif.stem / f"{pid}.tif",
                                     arr, transform, src.crs, names)
                if export_format == "npy":
                    train_path = write_npy(train_dir / tif.stem / f"{pid}.npy",
                                           arr, meta)
                elif export_format == "tfrecord":
                    train_path = write_tfrecord(
                        train_dir / tif.stem / f"{pid}.tfrecord", arr, meta)
                else:
                    raise ValueError(
                        f"Unknown export_format '{export_format}' (npy | tfrecord)")
                records.append({
                    "patch_id": pid, "scene": tif.stem,
                    "spatial_block_id": block,
                    # POSIX separators so the index stays portable to
                    # Linux/macOS training environments
                    "cog_path": Path(cog_path).as_posix(),
                    "train_path": Path(train_path).as_posix(),
                    "invalid_frac": round(invalid, 4),
                })

    _assign_splits(records, cfg.get("split", {}))

    index_file.parent.mkdir(parents=True, exist_ok=True)
    with open(index_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "patch_id", "scene", "split", "spatial_block_id",
            "cog_path", "train_path", "invalid_frac"])
        writer.writeheader()
        writer.writerows(records)

    if logger:
        counts = {s: sum(1 for r in records if r["split"] == s) for s in SPLITS}
        blocks = len({r["spatial_block_id"] for r in records})
        logger.set_summary(scenes=len(interim), patches_accepted=len(records),
                           patches_skipped_invalid=skipped,
                           patches_skipped_field_coverage=skipped_field,
                           spatial_blocks=blocks, split_counts=counts,
                           index_file=str(index_file))
    return records
