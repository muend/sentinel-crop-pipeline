"""Two-layer scene selection.

Layer 1: deterministic rules - cloud metadata threshold, crop-calendar date
window, AOI overlap, pixel-based SCL statistics. Always available, no API key.

Layer 2: optional vision-LLM review (SceneJudge plugin). Graceful degradation:
if the judge is disabled (judge_provider: none), unavailable (missing key/SDK)
or errors out (429, timeout), the scene is flagged needs_manual_review=True
and the layer-1 decision stands - the pipeline never stops on judge failures.

Every decision is returned as a SelectionResult and logged for auditability.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from shapely.geometry import shape

from sentinel_crop_pipeline.preprocessing.scl_mask import DEFAULT_INVALID_CLASSES, invalid_fraction
from sentinel_crop_pipeline.utils.geo import overlap_pct
from .providers.base import Scene

log = logging.getLogger("selector")


@dataclass
class SelectionResult:
    scene_id: str
    accepted: bool
    checks: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    ai_verdict: str | None = None
    ai_confidence: float | None = None
    needs_manual_review: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class SceneSelector:
    def __init__(self, config: dict, crop_calendar: dict | None = None,
                 provider=None, judge=None):
        self.cfg = config
        self.calendar = crop_calendar or {}
        self.provider = provider  # needed for the SCL pixel check and previews
        self.judge = judge        # SceneJudge or None

    # -- layer 1 -----------------------------------------------------------

    def check_cloud_metadata(self, scene: Scene) -> tuple[bool, str]:
        limit = float(self.cfg["search"].get("max_cloud_cover_pct", 20))
        if scene.cloud_cover is None:
            # No metadata: pass here, rely on the SCL pixel check.
            return True, "cloud metadata missing, deferred to SCL check"
        ok = scene.cloud_cover <= limit
        return ok, f"cloud_cover={scene.cloud_cover:.1f}% (limit {limit:.0f}%)"

    def date_windows(self) -> list[tuple[date, date]]:
        """Windows from the crop calendar, clipped to the configured range."""
        start = date.fromisoformat(str(self.cfg["time"]["start"]))
        end = date.fromisoformat(str(self.cfg["time"]["end"]))
        crop = self.cfg["time"].get("crop")
        if not crop:
            return [(start, end)]
        cal = self.calendar.get(crop)
        if cal is None:
            raise ValueError(
                f"Crop '{crop}' not found in crop calendar "
                f"(available: {sorted(self.calendar)})")
        sow_m, sow_d = (int(x) for x in str(cal["sowing"]).split("-"))
        har_m, har_d = (int(x) for x in str(cal["harvest"]).split("-"))
        windows = []
        for year in range(start.year - 1, end.year + 1):
            w0 = date(year, sow_m, sow_d)
            # Harvest before sowing (month-day) means the window crosses new year.
            w1 = (date(year, har_m, har_d) if (har_m, har_d) >= (sow_m, sow_d)
                  else date(year + 1, har_m, har_d))
            w0c, w1c = max(w0, start), min(w1, end)
            if w0c <= w1c:
                windows.append((w0c, w1c))
        return windows

    def check_date(self, scene: Scene) -> tuple[bool, str]:
        d = datetime.fromisoformat(scene.datetime.replace("Z", "+00:00")).date()
        windows = self.date_windows()
        for w0, w1 in windows:
            if w0 <= d <= w1:
                return True, f"{d} in window {w0}..{w1}"
        return False, f"{d} outside crop windows {[(str(a), str(b)) for a, b in windows]}"

    def check_overlap(self, scene: Scene, aoi_geom) -> tuple[bool, str]:
        min_pct = float(self.cfg["aoi"].get("min_scene_overlap_pct", 60))
        pct = overlap_pct(aoi_geom, shape(scene.geometry))
        return pct >= min_pct, f"aoi_overlap={pct:.1f}% (min {min_pct:.0f}%)"

    def check_scl(self, scene: Scene, aoi_geom) -> tuple[bool, str]:
        """Pixel-based invalid fraction from the actual SCL band over the AOI.

        Scene-level cloud metadata can be misleading for a small AOI inside a
        large tile, so this check reads real pixels.
        """
        scl_cfg = self.cfg.get("scl_filter", {})
        if not scl_cfg.get("enabled", True):
            return True, "scl check disabled in config"
        if self.provider is None:
            return True, "no provider bound, scl check skipped"
        scl = self.provider.get_scl_mask(scene, aoi_geom)
        classes = tuple(scl_cfg.get("invalid_classes", DEFAULT_INVALID_CLASSES))
        frac = invalid_fraction(scl, classes)
        limit = float(scl_cfg.get("max_invalid_pct", 30)) / 100.0
        return frac <= limit, f"scl_invalid={frac * 100:.1f}% (limit {limit * 100:.0f}%)"

    # -- layer 2 -----------------------------------------------------------

    def _get_preview(self, scene: Scene, aoi_geom) -> bytes | None:
        if self.provider is not None and hasattr(self.provider, "get_preview"):
            return self.provider.get_preview(scene, aoi_geom)
        return None

    def ai_review(self, scene: Scene, aoi_geom) -> dict:
        """Run the configured judge. Returns a dict with either a verdict or
        needs_manual_review=True; never raises."""
        provider_name = str(self.cfg.get("ai_review", {})
                            .get("judge_provider", "none")).lower()
        if provider_name in ("", "none"):
            return {"needs_manual_review": True,
                    "reason": "ai review disabled (judge_provider: none)"}
        if self.judge is None:
            return {"needs_manual_review": True,
                    "reason": f"judge '{provider_name}' unavailable "
                              "(missing API key or SDK)"}
        try:
            preview = self._get_preview(scene, aoi_geom)
            res = self.judge.evaluate(scene, preview)
        except Exception as exc:
            log.warning("judge failed for %s: %s", scene.id, exc)
            return {"needs_manual_review": True, "reason": f"judge error: {exc}"}
        if res.needs_manual_review or res.accept is None:
            return {"needs_manual_review": True, "reason": res.reason}
        return {"verdict": "accept" if res.accept else "reject",
                "confidence": res.confidence, "reason": res.reason}

    # -- combined ------------------------------------------------------------

    def should_include(self, scene: Scene, aoi_geom,
                       skip_scl: bool = False) -> SelectionResult:
        result = SelectionResult(scene_id=scene.id, accepted=True)
        cheap_checks = [
            ("cloud_metadata", lambda: self.check_cloud_metadata(scene)),
            ("date_window", lambda: self.check_date(scene)),
            ("aoi_overlap", lambda: self.check_overlap(scene, aoi_geom)),
        ]
        for name, fn in cheap_checks:
            ok, note = fn()
            result.checks[name] = {"passed": ok, "note": note}
            if not ok:
                result.accepted = False
                result.reasons.append(f"{name}: {note}")

        # SCL check costs a network call; only run it if still a candidate.
        if result.accepted and not skip_scl:
            ok, note = self.check_scl(scene, aoi_geom)
            result.checks["scl_stats"] = {"passed": ok, "note": note}
            if not ok:
                result.accepted = False
                result.reasons.append(f"scl_stats: {note}")

        # Layer 2 only for scenes that passed layer 1.
        if result.accepted:
            outcome = self.ai_review(scene, aoi_geom)
            if outcome.get("needs_manual_review"):
                result.needs_manual_review = True
                result.checks["ai_review"] = {"passed": True,
                                              "note": outcome["reason"]}
            else:
                result.ai_verdict = outcome["verdict"]
                result.ai_confidence = outcome["confidence"]
                rejected = outcome["verdict"] == "reject"
                result.checks["ai_review"] = {"passed": not rejected,
                                              "note": outcome["reason"]}
                min_conf = float(self.cfg.get("ai_review", {})
                                 .get("min_confidence", 0.6))
                if rejected and outcome["confidence"] >= min_conf:
                    result.accepted = False
                    result.reasons.append(f"ai_review: {outcome['reason']}")
                elif rejected:
                    # Low-confidence reject: keep the scene but ask a human.
                    result.needs_manual_review = True
        return result
