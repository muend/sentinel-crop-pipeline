import numpy as np
import pytest
from shapely.geometry import box, mapping

from src.discovery.providers.base import Scene
from src.discovery.scene_selector import SceneSelector

AOI = box(26.65, 38.25, 26.85, 38.36)
CALENDAR = {"tomato": {"sowing": "04-15", "harvest": "09-30"},
            "wheat": {"sowing": "11-01", "harvest": "06-30"}}


def make_scene(scene_id="S2A_TEST", dt="2025-06-15T09:00:00Z", cloud=5.0,
               footprint=box(26.0, 38.0, 27.5, 39.0)):
    return Scene(id=scene_id, provider="cdse", datetime=dt, cloud_cover=cloud,
                 geometry=mapping(footprint))


def test_accepts_good_scene(base_cfg):
    sel = SceneSelector(base_cfg, CALENDAR)
    res = sel.should_include(make_scene(), AOI)
    assert res.accepted
    assert res.checks["scl_stats"]["passed"]  # provider None -> skipped, passes


def test_rejects_cloudy_scene(base_cfg):
    sel = SceneSelector(base_cfg, CALENDAR)
    res = sel.should_include(make_scene(cloud=55.0), AOI)
    assert not res.accepted
    assert any("cloud_metadata" in r for r in res.reasons)


def test_missing_cloud_metadata_defers_to_scl(base_cfg):
    sel = SceneSelector(base_cfg, CALENDAR)
    ok, note = sel.check_cloud_metadata(make_scene(cloud=None))
    assert ok and "deferred" in note


def test_rejects_out_of_window_date(base_cfg):
    base_cfg["time"]["crop"] = "tomato"
    sel = SceneSelector(base_cfg, CALENDAR)
    res = sel.should_include(make_scene(dt="2025-10-20T09:00:00Z"), AOI)
    assert not res.accepted
    assert any("date_window" in r for r in res.reasons)


def test_winter_crop_window_crosses_year(base_cfg):
    base_cfg["time"] = {"start": "2024-11-01", "end": "2025-06-30", "crop": "wheat"}
    sel = SceneSelector(base_cfg, CALENDAR)
    ok, _ = sel.check_date(make_scene(dt="2025-02-10T09:00:00Z"))
    assert ok


def test_unknown_crop_raises(base_cfg):
    base_cfg["time"]["crop"] = "durian"
    sel = SceneSelector(base_cfg, CALENDAR)
    with pytest.raises(ValueError, match="durian"):
        sel.date_windows()


def test_rejects_low_overlap(base_cfg):
    sel = SceneSelector(base_cfg, CALENDAR)
    off_scene = make_scene(footprint=box(28.0, 39.0, 29.0, 40.0))
    res = sel.should_include(off_scene, AOI)
    assert not res.accepted
    assert any("aoi_overlap" in r for r in res.reasons)


def test_scl_pixel_check_rejects(base_cfg):
    class FakeProvider:
        def get_scl_mask(self, scene, aoi, resolution_m=20):
            scl = np.full((10, 10), 4, dtype=np.uint8)
            scl[:5] = 9  # 50% cloud
            return scl

    sel = SceneSelector(base_cfg, CALENDAR, provider=FakeProvider())
    res = sel.should_include(make_scene(), AOI)
    assert not res.accepted
    assert any("scl_stats" in r for r in res.reasons)


def test_selection_result_serializable(base_cfg):
    import json
    sel = SceneSelector(base_cfg, CALENDAR)
    res = sel.should_include(make_scene(), AOI)
    json.dumps(res.to_dict())
