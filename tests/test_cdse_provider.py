import pytest
from shapely.geometry import box, mapping

from src.discovery.providers.base import ProviderError
from src.discovery.providers.cdse import (MAX_PROCESS_DIM, CdseProvider,
                                          _evalscript, _tile_grid)

AOI = box(26.65, 38.25, 26.85, 38.36)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse(self.pages.pop(0))


def feature(fid, cloud=5.0, ptype="S2MSI2A", dt="2025-06-15T09:00:00Z"):
    return {
        "id": fid,
        "geometry": mapping(box(26.0, 38.0, 27.5, 39.0)),
        "properties": {"datetime": dt, "eo:cloud_cover": cloud,
                       "product:type": ptype},
    }


def test_search_filters_cloud_and_product_type(base_cfg):
    page = {"features": [feature("ok", cloud=10),
                         feature("cloudy", cloud=80),
                         feature("l1c", cloud=5, ptype="S2MSI1C")],
            "links": []}
    provider = CdseProvider(base_cfg, session=FakeSession([page]))
    scenes = provider.search(AOI, "2025-04-01", "2025-10-31", max_cloud_cover=20)
    assert [s.id for s in scenes] == ["ok"]
    assert scenes[0].cloud_cover == 10


def test_search_follows_pagination(base_cfg):
    page1 = {"features": [feature("a")],
             "links": [{"rel": "next", "href": "http://x/search",
                        "body": {"token": "next-page"}}]}
    page2 = {"features": [feature("b")], "links": []}
    session = FakeSession([page1, page2])
    provider = CdseProvider(base_cfg, session=session)
    scenes = provider.search(AOI, "2025-04-01", "2025-10-31")
    assert [s.id for s in scenes] == ["a", "b"]
    assert len(session.calls) == 2


def test_download_requires_credentials(base_cfg, monkeypatch, tmp_path):
    monkeypatch.delenv("CDSE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CDSE_CLIENT_SECRET", raising=False)
    provider = CdseProvider(base_cfg, session=FakeSession([]))
    from tests.test_scene_selector import make_scene
    with pytest.raises(ProviderError, match="CDSE_CLIENT_ID"):
        provider.download(make_scene(), AOI, ["B02"], tmp_path)


def test_download_size_guard(base_cfg, monkeypatch, tmp_path):
    base_cfg["download"]["max_auto_size_mb"] = 0.001
    provider = CdseProvider(base_cfg, session=FakeSession([]))
    monkeypatch.setattr(provider, "_get_token", lambda: "tok")
    from tests.test_scene_selector import make_scene
    with pytest.raises(ProviderError, match="max_auto_size_mb"):
        provider.download(make_scene(), AOI, ["B02", "B03", "B04", "B08"], tmp_path)


def test_evalscript_contains_bands():
    script = _evalscript(["B02", "B08"])
    for token in ('"B02"', '"B08"', '"SCL"', "s.B02", "s.SCL"):
        assert token in script
    assert "bands: 3" in script


def test_tile_grid_single_tile_when_small():
    assert _tile_grid(2000, 1000) == [(0, 0, 2000, 1000)]


def test_tile_grid_splits_and_covers():
    tiles = _tile_grid(3060, 2660)   # interim Urla AOI scale at 10 m
    assert len(tiles) == 4
    for _, _, w, h in tiles:
        assert w <= MAX_PROCESS_DIM and h <= MAX_PROCESS_DIM
    # exact coverage, no gaps/overlaps
    assert sum(w * h for _, _, w, h in tiles) == 3060 * 2660
    assert {(c, r) for c, r, _, _ in tiles} == {(0, 0), (1530, 0),
                                                (0, 1330), (1530, 1330)}


def test_utm_bbox_dims_match_grid(base_cfg):
    provider = CdseProvider(base_cfg, session=FakeSession([]))
    epsg, bbox, width, height = provider._utm_bbox(AOI, 10)
    assert epsg == 32635
    assert round((bbox[2] - bbox[0]) / 10) == width
    assert round((bbox[3] - bbox[1]) / 10) == height


def test_retry_then_fail(base_cfg, monkeypatch):
    class FlakySession:
        def __init__(self):
            self.n = 0

        def request(self, method, url, **kwargs):
            self.n += 1
            return FakeResponse({"err": True}, status_code=503)

    monkeypatch.setattr("time.sleep", lambda s: None)
    provider = CdseProvider(base_cfg, session=FlakySession())
    with pytest.raises(ProviderError, match="503"):
        provider._request("GET", "http://x", retries=2)
    assert provider.session.n == 3
