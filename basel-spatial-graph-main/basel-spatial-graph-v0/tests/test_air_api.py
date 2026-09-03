"""The run planner over HTTP."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.air.api import _prepared, router
from app.air.testing import CENTRE

from fastapi import FastAPI


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(scope="module")
def params():
    lon, lat = CENTRE
    return {"lon": lon, "lat": lat, "distance_m": 2000, "pace_min_per_km": 6.0}


def test_loops_endpoint_returns_candidates(client, params):
    response = client.get("/run/loops", params=params)
    assert response.status_code == 200
    body = response.json()
    assert body["loops"]
    assert body["network_coverage"]["segments_total"] > 0


def test_response_admits_when_the_air_field_is_synthetic(client, params):
    body = client.get("/run/loops", params=params).json()
    source = body["air_source"]
    if source["fixture"]:
        assert "not measurements" in source["warning"].lower()


def test_every_loop_carries_its_parameters_and_coverage(client, params):
    body = client.get("/run/loops", params={**params, "hour": 8}).json()
    for loop in body["loops"]:
        exposure = loop["exposure"]
        assert exposure["classification"] == "dynamic"
        assert exposure["parameters"]["hour"] == 8
        assert exposure["parameters"]["pace_min_per_km"] == 6.0
        assert 0.0 <= exposure["coverage"]["measured_share"] <= 1.0


def test_unmeasured_segments_reach_the_client_as_unmeasured(client, params):
    body = client.get("/run/loops", params=params).json()
    classes = {s["classification"] for loop in body["loops"] for s in loop["segments"]}
    assert classes <= {"measured", "unmeasured"}
    for loop in body["loops"]:
        for segment in loop["segments"]:
            if segment["classification"] == "unmeasured":
                assert segment["concentration"] is None
                assert segment["contribution"] == 0


def test_impossible_distance_explains_itself(client):
    lon, lat = CENTRE
    response = client.get("/run/loops", params={"lon": lon, "lat": lat, "distance_m": 24000})
    assert response.status_code == 404
    assert "distance" in response.json()["detail"].lower()


def test_out_of_range_pace_is_rejected(client, params):
    assert client.get("/run/loops", params={**params, "pace_min_per_km": 99}).status_code == 422


def test_gpx_endpoint_serves_a_downloadable_file(client, params):
    response = client.get("/run/gpx", params=params)
    assert response.status_code == 200
    assert "gpx" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    root = ET.fromstring(response.text)
    assert root.tag.endswith("gpx")
    assert root.findall(".//{http://www.topografix.com/GPX/1/1}trkpt")


def test_prepared_is_cached():
    assert _prepared() is _prepared()


# --- why this route: every clause has to come from a metric -----------------


class _FakeExposure:
    def __init__(self, no2, measured, share, segments=()):
        self.baseline_no2_mean = no2
        self.mean_concentration = measured
        self.measured_share = share
        self.segments = list(segments)


class _FakeSegment:
    def __init__(self, sid, no2, length):
        self.segment_id, self.baseline_no2, self.length_m = sid, no2, length


class _FakeCandidate:
    def __init__(self, distance_m, exposure):
        self.distance_m, self.exposure = distance_m, exposure


def test_a_tie_is_described_as_a_tie_not_as_a_decision():
    """A 0.1 ug/m3 margin must not be dressed up as avoiding something."""
    from app.air.api import _why_this_route

    chosen = _FakeCandidate(8000, _FakeExposure(16.7, 11.0, 0.5))
    rival = _FakeCandidate(8800, _FakeExposure(16.8, 11.2, 0.4))
    lines = _why_this_route(chosen, [rival], {})
    assert "barely matters" in lines[0]
    assert "avoids" not in lines[0].lower()


def test_a_real_gap_names_the_street_it_avoids():
    """The name must come from the network, never from invention."""
    from app.air.api import _why_this_route

    chosen = _FakeCandidate(9000, _FakeExposure(16.0, 11.0, 0.5))
    rival = _FakeCandidate(8000, _FakeExposure(17.0, 11.0, 0.5), )
    rival.exposure.segments = [_FakeSegment("a|b", 24.0, 300.0)]
    lines = _why_this_route(chosen, [rival], {"a|b": "Luzernerring"})
    assert "Luzernerring" in lines[0]
    assert "24.0 µg/m³" in lines[0]
    assert "1.0 km more distance" in lines[0]


def test_an_unnamed_street_is_not_given_a_name():
    """34% of the network has a name; the rest stays anonymous."""
    from app.air.api import _why_this_route

    chosen = _FakeCandidate(9000, _FakeExposure(16.0, 11.0, 0.5))
    rival = _FakeCandidate(8000, _FakeExposure(17.0, 11.0, 0.5))
    rival.exposure.segments = [_FakeSegment("a|b", 24.0, 300.0)]
    lines = _why_this_route(chosen, [rival], {})          # no names available
    assert "1.0 lower" in lines[0]
    assert "Avoids" not in lines[0]


def test_short_stretches_do_not_win_the_naming_contest():
    """One 12 m connector on a hot pixel is not the reason for a route."""
    from app.air.api import _worst_named_stretch

    exposure = _FakeExposure(20.0, None, 0.0, [
        _FakeSegment("a|b", 40.0, 12.0),        # hot but trivial
        _FakeSegment("c|d", 22.0, 400.0),       # the real arterial
    ])
    name, level, metres = _worst_named_stretch(
        exposure, {"a|b": "Gässlein", "c|d": "Luzernerring"}, set()
    )
    assert name == "Luzernerring"
    assert metres == 400


def test_an_unmeasured_route_says_so_rather_than_going_quiet():
    from app.air.api import _why_this_route

    chosen = _FakeCandidate(8000, _FakeExposure(16.0, None, 0.0))
    lines = _why_this_route(chosen, [], {})
    assert "not the same as clean" in lines[-1]


def test_choosing_a_worse_route_is_described_as_the_trade_it_is():
    """The reader can click any card. A worse one must not be called 'lowest'."""
    from app.air.api import _why_this_route

    chosen = _FakeCandidate(7350, _FakeExposure(17.2, 11.0, 0.5))
    better = _FakeCandidate(6550, _FakeExposure(16.6, 11.0, 0.5))
    lines = _why_this_route(chosen, [better], {})
    assert "lowest" not in lines[0]
    assert "0.6 higher than the best candidate" in lines[0]
    # The clause describes the better alternative, which is the shorter one here.
    assert "0.8 km shorter" in lines[0]
    assert "-" not in lines[0].replace("–", "")     # no negative numbers on screen


def test_no_explanation_ever_prints_a_negative_gap():
    from app.air.api import _why_this_route

    for mine, rival in ((17.2, 16.6), (16.6, 17.2), (17.0, 17.05)):
        lines = _why_this_route(
            _FakeCandidate(8000, _FakeExposure(mine, 11.0, 0.5)),
            [_FakeCandidate(8000, _FakeExposure(rival, 11.0, 0.5))], {},
        )
        assert "-0." not in lines[0], lines[0]


def test_the_distance_clause_describes_the_right_route():
    """Chosen 7.95 km vs best 6.55 km: the best candidate is the SHORTER one.

    Gaps are set clearly past MEANINGFUL_NO2_GAP rather than exactly on it —
    at the threshold the tie branch wins, which is the conservative answer.
    """
    from app.air.api import _why_this_route

    chosen = _FakeCandidate(7950, _FakeExposure(17.6, 11.0, 0.5))
    best = _FakeCandidate(6550, _FakeExposure(17.1, 11.0, 0.5))
    line = _why_this_route(chosen, [best], {})[0]
    assert "1.4 km shorter" in line, line

    # And the mirror image: a chosen route shorter than the better alternative.
    chosen = _FakeCandidate(6000, _FakeExposure(17.6, 11.0, 0.5))
    best = _FakeCandidate(8000, _FakeExposure(17.1, 11.0, 0.5))
    line = _why_this_route(chosen, [best], {})[0]
    assert "2.0 km longer" in line, line


def test_the_distance_clause_reads_as_english_in_both_branches():
    from app.air.api import _why_this_route

    names = {"a|b": "Feldbergstrasse"}
    rival = _FakeCandidate(8000, _FakeExposure(17.5, 11.0, 0.5))
    rival.exposure.segments = [_FakeSegment("a|b", 20.4, 300.0)]

    same = _why_this_route(_FakeCandidate(8000, _FakeExposure(17.1, 11.0, 0.5)),
                           [rival], names)[0]
    assert "at the same distance as the next-best candidate" in same
    assert "distance than" not in same

    longer = _why_this_route(_FakeCandidate(8600, _FakeExposure(17.1, 11.0, 0.5)),
                             [rival], names)[0]
    assert "for 0.6 km more distance than the next-best candidate" in longer
