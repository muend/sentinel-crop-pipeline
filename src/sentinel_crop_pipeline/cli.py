"""CLI entry point. Stages run independently:

    python -m sentinel_crop_pipeline.cli discover   --config config/default.yaml
    python -m sentinel_crop_pipeline.cli download   --config config/default.yaml [--yes]
    python -m sentinel_crop_pipeline.cli preprocess --config config/default.yaml
    python -m sentinel_crop_pipeline.cli patch      --config config/default.yaml
    python -m sentinel_crop_pipeline.cli label      --config config/default.yaml
    python -m sentinel_crop_pipeline.cli run-all    --config config/default.yaml [--yes]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sentinel_crop_pipeline.utils.config import all_bands, load_config, load_crop_calendar
from sentinel_crop_pipeline.utils.env import load_dotenv
from sentinel_crop_pipeline.utils.geo import load_aoi
from sentinel_crop_pipeline.utils.run_logger import RunLogger

CATALOG_FILE = Path("data/catalog/scenes.json")


def _download_field_crops(provider, scene, aoi, bands: list[str], out_dir: str | Path,
                          fields_path: str | Path, resolution_m: int, assume_yes: bool) -> list[Path]:
    """Download into temporary storage; persist only validated per-field COGs."""
    from sentinel_crop_pipeline.preprocessing.field_mask import load_fields, write_field_crop

    features = load_fields(fields_path)
    field_ids = [(f.get("properties") or {}).get("field_id", "") for f in features]
    if any(not isinstance(fid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", fid) for fid in field_ids):
        raise ValueError("Field-only downloads require safe nonempty field_id values")
    if len(set(field_ids)) != len(field_ids):
        raise ValueError("Field-only downloads require unique field_id values")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", scene.id) or scene.id in (".", ".."):
        raise ValueError("Unsafe scene id for field crop filenames")
    paths = []
    with TemporaryDirectory(prefix="sentinel_field_download_") as directory:
        source = provider.download(scene, aoi, bands, directory,
                                   resolution_m=resolution_m, assume_yes=assume_yes)
        for fid in field_ids:
            target = Path(out_dir) / f"{scene.id}_{fid}.tif"
            write_field_crop(source, target, fields_path, fid)
            paths.append(target)
    return paths


def _setup(args):
    load_dotenv()
    cfg = load_config(args.config)
    log_cfg = cfg.get("logging", {})
    return cfg, log_cfg.get("dir", "logs"), log_cfg.get("level", "INFO")


def cmd_discover(args) -> int:
    cfg, log_dir, level = _setup(args)
    logger = RunLogger("discover", log_dir, level)
    from sentinel_crop_pipeline.discovery.judge import get_judge
    from sentinel_crop_pipeline.discovery.providers import get_provider
    from sentinel_crop_pipeline.discovery.scene_selector import SceneSelector

    aoi = load_aoi(cfg["aoi"]["path"])
    provider = get_provider(cfg)
    calendar = load_crop_calendar(cfg["time"].get("crop_calendar",
                                                  "config/crop_calendar.yaml"))
    judge = get_judge(cfg)
    selector = SceneSelector(cfg, calendar, provider, judge=judge)

    logger.event("searching", provider=provider.name,
                 start=cfg["time"]["start"], end=cfg["time"]["end"])
    scenes = provider.search(
        aoi, cfg["time"]["start"], cfg["time"]["end"],
        max_cloud_cover=float(cfg["search"].get("max_cloud_cover_pct", 20)))
    logger.event("search done", found=len(scenes))

    accepted, results, manual_review = [], [], 0
    for scene in scenes:
        res = selector.should_include(scene, aoi, skip_scl=args.skip_scl)
        # footprint goes into the audit log so map views need no extra lookup
        results.append({**res.to_dict(), "geometry": scene.geometry})
        manual_review += res.needs_manual_review
        logger.event("selection", scene=scene.id, accepted=res.accepted,
                     needs_manual_review=res.needs_manual_review,
                     reasons=res.reasons)
        if res.accepted:
            accepted.append(scene)

    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(json.dumps([s.to_dict() for s in accepted],
                                       indent=2, default=str))
    selection_log = Path(log_dir) / "selection_results.json"
    selection_log.write_text(json.dumps(results, indent=2, default=str))

    logger.set_summary(found=len(scenes), accepted=len(accepted),
                       rejected=len(scenes) - len(accepted),
                       needs_manual_review=manual_review,
                       catalog=str(CATALOG_FILE), selection_log=str(selection_log))
    logger.finish()
    return 0


def cmd_download(args) -> int:
    cfg, log_dir, level = _setup(args)
    logger = RunLogger("download", log_dir, level)
    from sentinel_crop_pipeline.discovery.providers import get_provider
    from sentinel_crop_pipeline.discovery.providers.base import Scene

    if not CATALOG_FILE.exists():
        logger.warning("no catalog found; run `discover` first")
        return 1
    scenes = [Scene.from_dict(d) for d in json.loads(CATALOG_FILE.read_text())]
    aoi = load_aoi(cfg["aoi"]["path"])
    provider = get_provider(cfg)
    bands = all_bands(cfg)
    dl = cfg.get("download", {})
    method = dl.get("method", "process_api")
    out_dir = dl.get("out_dir", "data/raw")
    field_only = bool(dl.get("field_only", False))
    fields_path = cfg.get("preprocessing", {}).get("field_mask_path")
    if field_only and (method != "process_api" or not fields_path):
        raise ValueError("download.field_only requires process_api and preprocessing.field_mask_path")

    # Report total estimate before touching the network for data.
    if method == "process_api" and hasattr(provider, "estimate_size_mb"):
        per_scene = provider.estimate_size_mb(aoi, len(bands),
                                              int(dl.get("resolution_m", 10)))
        total = per_scene * len(scenes)
        logger.event("size estimate", scenes=len(scenes),
                     per_scene_mb=round(per_scene, 1), total_mb=round(total, 1))
        if total > float(dl.get("max_auto_size_mb", 200)) and not args.yes:
            logger.warning(
                f"estimated total {total:.0f} MB exceeds max_auto_size_mb; "
                "re-run with --yes to confirm")
            return 1

    done = 0
    field_crops = 0
    for scene in scenes:
        if field_only:
            paths = _download_field_crops(provider, scene, aoi, bands, out_dir, fields_path,
                                          int(dl.get("resolution_m", 10)), args.yes)
            done += 1
            field_crops += len(paths)
            for path in paths:
                logger.event("downloaded field crop", scene=scene.id, path=str(path))
            continue
        if method == "process_api":
            path = provider.download(scene, aoi, bands, out_dir,
                                     resolution_m=int(dl.get("resolution_m", 10)),
                                     assume_yes=args.yes)
        elif method == "odata":
            path = provider.download_odata(scene, out_dir, assume_yes=args.yes)
        else:
            raise ValueError(f"Unknown download.method '{method}'")
        done += 1
        logger.event("downloaded", scene=scene.id, path=str(path))

    logger.set_summary(scenes=len(scenes), downloaded=done, field_crops=field_crops, out_dir=out_dir)
    logger.finish()
    return 0


def cmd_preprocess(args) -> int:
    cfg, log_dir, level = _setup(args)
    logger = RunLogger("preprocess", log_dir, level)
    from sentinel_crop_pipeline.preprocessing.pipeline import run_preprocess

    outputs = run_preprocess(cfg, logger)
    if not outputs:
        logger.warning("no raw scenes found; run `download` first")
    logger.finish()
    return 0 if outputs else 1


def cmd_patch(args) -> int:
    cfg, log_dir, level = _setup(args)
    logger = RunLogger("patch", log_dir, level)
    from sentinel_crop_pipeline.patching.tiler import run_patching

    records = run_patching(cfg, logger)
    if not records:
        logger.warning("no patches produced; check data/interim and thresholds")
    logger.finish()
    return 0 if records else 1


def cmd_label(args) -> int:
    cfg, log_dir, level = _setup(args)
    logger = RunLogger("label", log_dir, level)
    from sentinel_crop_pipeline.labeling.base import LabelSourceError
    from sentinel_crop_pipeline.labeling.rasterize import run_labeling

    try:
        records = run_labeling(cfg, logger)
    except LabelSourceError as exc:
        logger.warning(str(exc))
        logger.finish()
        return 1
    logger.finish()
    return 0 if records else 1


def cmd_run_all(args) -> int:
    for step in (cmd_discover, cmd_download, cmd_preprocess, cmd_patch):
        rc = step(args)
        if rc != 0:
            return rc
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel-crop-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("discover", cmd_discover), ("download", cmd_download),
                     ("preprocess", cmd_preprocess), ("patch", cmd_patch),
                     ("label", cmd_label), ("run-all", cmd_run_all)):
        p = sub.add_parser(name)
        p.add_argument("--config", default="config/default.yaml")
        p.add_argument("--yes", action="store_true",
                       help="confirm downloads above the size threshold")
        p.add_argument("--skip-scl", action="store_true",
                       help="skip the per-scene SCL pixel check (no network)")
        p.set_defaults(fn=fn)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
