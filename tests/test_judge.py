"""Layer-2 judge tests: verdicts and graceful degradation."""

import pytest
from shapely.geometry import box

from sentinel_crop_pipeline.discovery.judge import (JudgeResult, SceneJudge, get_judge,
                                 parse_verdict, with_backoff)
from sentinel_crop_pipeline.discovery.scene_selector import SceneSelector
from tests.test_scene_selector import AOI, make_scene


class FakeJudge(SceneJudge):
    name = "fake"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def evaluate(self, scene, preview_image):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _selector(base_cfg, judge_provider="gemini", judge=None):
    base_cfg["ai_review"]["judge_provider"] = judge_provider
    return SceneSelector(base_cfg, {}, provider=None, judge=judge)


# -- graceful degradation: three scenarios ----------------------------------

def test_judge_provider_none_flags_manual_review(base_cfg):
    sel = _selector(base_cfg, judge_provider="none")
    res = sel.should_include(make_scene(), AOI)
    assert res.accepted                       # layer-1 decision stands
    assert res.needs_manual_review
    assert "disabled" in res.checks["ai_review"]["note"]


def test_missing_api_key_flags_manual_review(base_cfg, monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    base_cfg["ai_review"]["judge_provider"] = "gemini"
    judge = get_judge(base_cfg)               # no key -> None, no exception
    assert judge is None
    sel = _selector(base_cfg, judge=judge)
    res = sel.should_include(make_scene(), AOI)
    assert res.accepted
    assert res.needs_manual_review
    assert "unavailable" in res.checks["ai_review"]["note"]


def test_judge_api_error_flags_manual_review(base_cfg):
    judge = FakeJudge(error=RuntimeError("429 RESOURCE_EXHAUSTED"))
    sel = _selector(base_cfg, judge=judge)
    res = sel.should_include(make_scene(), AOI)
    assert res.accepted                       # pipeline continues on layer 1
    assert res.needs_manual_review
    assert "429" in res.checks["ai_review"]["note"]


# -- verdicts -----------------------------------------------------------------

def test_confident_reject_drops_scene(base_cfg):
    judge = FakeJudge(JudgeResult(False, 0.9, "heavy haze over AOI", "fake"))
    sel = _selector(base_cfg, judge=judge)
    res = sel.should_include(make_scene(), AOI)
    assert not res.accepted
    assert res.ai_verdict == "reject"
    assert any("haze" in r for r in res.reasons)


def test_low_confidence_reject_keeps_scene_for_review(base_cfg):
    judge = FakeJudge(JudgeResult(False, 0.3, "maybe haze", "fake"))
    sel = _selector(base_cfg, judge=judge)
    res = sel.should_include(make_scene(), AOI)
    assert res.accepted
    assert res.needs_manual_review


def test_accept_verdict_recorded(base_cfg):
    judge = FakeJudge(JudgeResult(True, 0.85, "clear scene", "fake"))
    sel = _selector(base_cfg, judge=judge)
    res = sel.should_include(make_scene(), AOI)
    assert res.accepted and not res.needs_manual_review
    assert res.ai_verdict == "accept"
    assert res.ai_confidence == 0.85


def test_judge_skipped_for_layer1_rejects(base_cfg):
    judge = FakeJudge(JudgeResult(True, 0.9, "clear", "fake"))
    sel = _selector(base_cfg, judge=judge)
    res = sel.should_include(make_scene(cloud=90.0), AOI)
    assert not res.accepted
    assert judge.calls == 0                   # no wasted API calls


# -- helpers ------------------------------------------------------------------

def test_parse_verdict_valid():
    r = parse_verdict('noise {"accept": true, "confidence": 0.8, '
                      '"reason": "ok"} trailing', "fake")
    assert r.accept is True and r.confidence == 0.8 and not r.needs_manual_review


def test_parse_verdict_garbage():
    r = parse_verdict("I think this scene looks fine.", "fake")
    assert r.accept is None and r.needs_manual_review


def test_with_backoff_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("429")
        return "ok"

    assert with_backoff(flaky, retries=3) == "ok"
    assert len(attempts) == 3


def test_get_judge_unknown_provider(base_cfg):
    base_cfg["ai_review"]["judge_provider"] = "gpt9"
    with pytest.raises(ValueError, match="gpt9"):
        get_judge(base_cfg)
