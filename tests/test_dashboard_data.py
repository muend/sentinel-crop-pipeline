"""Dashboard data loaders. No Streamlit needed - src/dashboard/data.py is
plain file parsing."""

import json

from src.dashboard import data as d


def test_parse_note_pct():
    assert d.parse_note_pct("cloud_cover=8.4% (limit 20%)") == 8.4
    assert d.parse_note_pct("scl_invalid=49.1% (limit 30%)") == 49.1
    assert d.parse_note_pct("no percentage here") is None
    assert d.parse_note_pct(None) is None


def test_scene_status():
    assert d.scene_status({"accepted": False}) == "rejected"
    assert d.scene_status({"accepted": True,
                           "needs_manual_review": True}) == "needs_manual_review"
    assert d.scene_status({"accepted": True,
                           "needs_manual_review": False}) == "accepted"


def test_scene_date():
    sid = "S2A_MSIL2A_20250602T085721_N0511_R007_T35SMC_20250602T130429"
    assert d.scene_date(sid) == "2025-06-02"
    assert d.scene_date("garbage") == ""


def test_selection_table_flattens_checks():
    rows = d.selection_table([{
        "scene_id": "S2A_MSIL2A_20250602T085721_N0511_R007_T35SMC_20250602T130429",
        "accepted": True, "needs_manual_review": True,
        "checks": {
            "cloud_metadata": {"passed": True, "note": "cloud_cover=1.8% (limit 20%)"},
            "aoi_overlap": {"passed": True, "note": "aoi_overlap=100.0% (min 60%)"},
            "scl_stats": {"passed": True, "note": "scl_invalid=0.0% (limit 30%)"},
        },
        "reasons": [], "ai_verdict": None, "ai_confidence": None,
    }])
    assert rows[0]["status"] == "needs_manual_review"
    assert rows[0]["cloud_pct"] == 1.8
    assert rows[0]["aoi_overlap_pct"] == 100.0
    assert rows[0]["scl_invalid_pct"] == 0.0
    assert rows[0]["date"] == "2025-06-02"


def test_loaders_tolerate_missing_files(tmp_path):
    assert d.load_selection_results(tmp_path) == []
    assert d.load_index(tmp_path / "index.csv") == []
    assert d.load_run_logs(tmp_path) == []
    assert d.load_catalog_geometries(tmp_path / "scenes.json") == {}
    assert d.load_class_map(tmp_path) == {}


def test_load_run_logs_newest_first_and_skips_bad_json(tmp_path):
    (tmp_path / "run_discover_20260101T000000.json").write_text(json.dumps(
        {"stage": "discover", "started": "a", "finished": "b", "summary": {"found": 3}}))
    (tmp_path / "run_patch_20260201T000000.json").write_text(json.dumps(
        {"stage": "patch", "started": "c", "finished": "d", "summary": {}}))
    (tmp_path / "run_broken_20260301T000000.json").write_text("{not json")
    logs = d.load_run_logs(tmp_path)
    assert [r["stage"] for r in logs] == ["patch", "discover"]
    assert logs[1]["summary"] == {"found": 3}
