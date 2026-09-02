from __future__ import annotations

import json
from pathlib import Path

from app.air.attribute import attribute_readings
from app.air.sources.basel_tram import (
    BaselTramAirSource,
    MOBILE_SENSOR_EXCLUSIONS,
)
from app.air.testing import fixture_network


FIXTURE = Path(__file__).parent / "fixtures" / "basel_tram_100113_sample.json"


def test_real_api_schema_parses_without_network(monkeypatch):
    monkeypatch.setattr("app.air.sources.basel_tram.fetch_dataset_metadata", lambda _: {})
    readings = BaselTramAirSource(FIXTURE).readings()
    assert len(readings) == 50
    assert all(set(r.values) == {"pm25", "pm10"} for r in readings)
    assert all(7.4 < r.lon < 7.8 and 47.4 < r.lat < 47.7 for r in readings)


def test_utc_timestamp_is_converted_to_basel_cet(monkeypatch):
    monkeypatch.setattr("app.air.sources.basel_tram.fetch_dataset_metadata", lambda _: {})
    reading = BaselTramAirSource(FIXTURE, max_rows=1).readings()[0]
    assert reading.timestamp.utcoffset().total_seconds() == 3600
    assert reading.hour == 0  # 2020-01-20 23:03 UTC -> 2020-01-21 00:03 CET


def test_malformed_records_are_skipped_not_defaulted(tmp_path, monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    payload["results"][:3] = [
        {**payload["results"][0], "time": "not-a-time"},
        {**payload["results"][1], "longitude": None},
        {**payload["results"][2], "pm25": None, "pm10": None},
    ]
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr("app.air.sources.basel_tram.fetch_dataset_metadata", lambda _: {})
    source = BaselTramAirSource(path)
    readings = source.readings()
    assert source.skipped == 3
    assert len(readings) == 47


def test_stationary_sensors_never_reach_attribution(tmp_path, monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    baseline = BaselTramAirSource(FIXTURE).readings()
    for sensor in MOBILE_SENSOR_EXCLUSIONS:
        payload["results"].append({**payload["results"][0], "sensornr": sensor})
    path = tmp_path / "with_stationary.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr("app.air.sources.basel_tram.fetch_dataset_metadata", lambda _: {})
    readings = BaselTramAirSource(path).readings()
    assert not ({int(r.sensor_id) for r in readings} & MOBILE_SENSOR_EXCLUSIONS)
    baseline_segments, _ = attribute_readings(fixture_network(), baseline)
    segments, _ = attribute_readings(fixture_network(), readings)
    assert {
        sid: (segment.reading_count, segment.median)
        for sid, segment in segments.items()
    } == {
        sid: (segment.reading_count, segment.median)
        for sid, segment in baseline_segments.items()
    }
