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
