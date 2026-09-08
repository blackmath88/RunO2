"""Tests for the air-quality layer.

The load-bearing assertions are the ones about *not knowing*: an unmeasured
segment must never acquire a value, must never be ranked as clean, and must
carry its share into every result derived from it.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.air.attribute import attribute_from_source, attribute_readings, segment_id
from app.air.exposure import DEFAULT_PACE_MIN_PER_KM, duration_minutes, score_path
from app.air.gpx import NAMESPACE, route_to_gpx
from app.air.loops import generate_loops
from app.air.model import MEASURED, UNMEASURED, AirReading, SegmentAir
from app.air.sources.fixture_source import FixtureAirSource
from app.air.testing import CENTRE, fixture_network
from app.air.viability import run as run_viability


@pytest.fixture(scope="module")
def network():
    return fixture_network()


@pytest.fixture(scope="module")
def attributed(network):
    return attribute_from_source(network, FixtureAirSource(days=1))


# --- attribution ----------------------------------------------------------

def test_every_segment_appears_even_without_readings(network, attributed):
    segments, coverage = attributed
    assert len(segments) == network.number_of_edges()
    assert coverage.segments_total == network.number_of_edges()


def test_unmeasured_segments_have_no_value(attributed):
    segments, _ = attributed
    unmeasured = [s for s in segments.values() if s.reading_count == 0]
    assert unmeasured, "fixture should leave part of the grid unmeasured"
    for segment in unmeasured:
        assert segment.median is None
        assert segment.classification == UNMEASURED
        assert segment.known is False


def test_coverage_is_reported_not_assumed(attributed):
    _, coverage = attributed
    payload = coverage.as_dict()
    assert 0.0 < payload["segment_share"] < 1.0
    assert payload["segments_measured"] + payload["segments_unmeasured"] == payload["segments_total"]


def test_segment_id_is_order_independent():
    assert segment_id("a", "b") == segment_id("b", "a")


def test_hourly_medians_need_enough_readings(network):
    source = FixtureAirSource(days=1)
    segments, _ = attribute_readings(network, source.readings()[:20], pollutant="pm25")
    measured = [s for s in segments.values() if s.reading_count > 0]
    for segment in measured:
        for hour, value in segment.by_hour.items():
            assert value is not None


# --- provenance -----------------------------------------------------------

def test_provenance_record_names_its_class(attributed):
    segments, _ = attributed
    measured = next(s for s in segments.values() if s.known)
    record = measured.as_provenance()
    assert record["classification"] == MEASURED
    assert record["reading_count"] > 0
    assert record["unit"] == "ug/m3"
    assert "explanation" in record


def test_unmeasured_provenance_says_unknown_not_zero(attributed):
    segments, _ = attributed
    unmeasured = next(s for s in segments.values() if not s.known)
    record = unmeasured.as_provenance()
    assert record["classification"] == UNMEASURED
    assert "median" not in record
    assert "unknown" in record["explanation"].lower()


def test_error_band_absent_when_unknown():
    segment = SegmentAir(segment_id="x", pollutant="pm25", median=10.0, p90=12.0,
                         reading_count=5, error_band=None)
    assert "error_band" not in segment.as_provenance()


# --- exposure -------------------------------------------------------------

def _measured_path(network, segments, length=8):
    """A path along a row that actually has readings on it."""
    rows = sorted({int(sid.split("|")[0][1:].split("_")[0]) for sid, s in segments.items() if s.known})
    for row in rows:
        path = [f"n{row}_{c}" for c in range(length)]
        if all(network.has_edge(a, b) for a, b in zip(path, path[1:])):
            if any(segments[segment_id(a, b)].known for a, b in zip(path, path[1:])):
                return path
    raise AssertionError("fixture has no measured row")


def test_exposure_scales_with_pace(network, attributed):
    segments, _ = attributed
    path = _measured_path(network, segments)
    slow = score_path(network, path, segments, pace_min_per_km=7.0)
    fast = score_path(network, path, segments, pace_min_per_km=5.0)
    assert slow.total > fast.total
    assert slow.minutes > fast.minutes
    assert slow.distance_m == pytest.approx(fast.distance_m)


def test_unmeasured_contributes_nothing_but_is_counted(network, attributed):
    segments, _ = attributed
    path = [f"n{r}_3" for r in range(9)]
    result = score_path(network, path, segments)
    unmeasured = [s for s in result.segments if s.classification == UNMEASURED]
    assert all(s.contribution == 0.0 for s in unmeasured)
    if unmeasured:
        assert result.measured_share < 1.0
        assert result.as_dict()["coverage"]["unmeasured_share"] > 0


def test_dynamic_result_carries_its_parameters(network, attributed):
    segments, _ = attributed
    path = [f"n5_{c}" for c in range(6)]
    payload = score_path(network, path, segments, pace_min_per_km=5.5, hour=8).as_dict()
    assert payload["classification"] == "dynamic"
    assert payload["parameters"]["pace_min_per_km"] == 5.5
    assert payload["parameters"]["hour"] == 8


def test_mean_concentration_uses_measured_part_only(network, attributed):
    segments, _ = attributed
    path = [f"n{r}_3" for r in range(9)]
    result = score_path(network, path, segments)
    mean = result.mean_concentration
    if mean is not None:
        measured = [s.concentration for s in result.segments if s.classification == MEASURED]
        assert min(measured) <= mean <= max(measured)


def test_duration_arithmetic():
    assert duration_minutes(5000, 6.0) == pytest.approx(30.0)


# --- loops ----------------------------------------------------------------

def test_loops_start_and_end_at_the_same_node(network, attributed):
    segments, _ = attributed
    loops = generate_loops(network, segments, lon=CENTRE[0], lat=CENTRE[1], target_m=2000)
    assert loops
    for loop in loops:
        assert loop.nodes[0] == loop.nodes[-1]


def test_loops_respect_the_distance_target(network, attributed):
    segments, _ = attributed
    target = 2500
    loops = generate_loops(network, segments, lon=CENTRE[0], lat=CENTRE[1], target_m=target)
    for loop in loops:
        assert abs(loop.distance_m - target) / target <= 0.25


def test_loops_are_ranked_cleanest_first(network, attributed):
    segments, _ = attributed
    loops = generate_loops(network, segments, lon=CENTRE[0], lat=CENTRE[1], target_m=2000, hour=8)
    means = [l.exposure.mean_concentration for l in loops if l.exposure.mean_concentration]
    assert means == sorted(means)


def test_an_unmeasured_loop_cannot_win_by_being_unknown(network, attributed):
    segments, _ = attributed
    loops = generate_loops(network, segments, lon=CENTRE[0], lat=CENTRE[1], target_m=2000)
    if len(loops) > 1:
        best = loops[0]
        assert best.exposure.mean_concentration is not None


# --- gpx ------------------------------------------------------------------

def test_gpx_is_wellformed_and_importable(network, attributed):
    segments, _ = attributed
    loops = generate_loops(network, segments, lon=CENTRE[0], lat=CENTRE[1], target_m=2000)
    loop = loops[0]
    xml = route_to_gpx(loop.coordinates(network), loop.exposure)
    root = ET.fromstring(xml)
    assert root.tag.endswith("gpx")
    points = root.findall(".//{http://www.topografix.com/GPX/1/1}trkpt")
    assert len(points) == len(loop.nodes)
    for point in points:
        assert -90 <= float(point.get("lat")) <= 90
        assert -180 <= float(point.get("lon")) <= 180


def test_gpx_carries_provenance_in_extensions(network, attributed):
    segments, _ = attributed
    loops = generate_loops(network, segments, lon=CENTRE[0], lat=CENTRE[1], target_m=2000, hour=8)
    loop = loops[0]
    xml = route_to_gpx(loop.coordinates(network), loop.exposure)
    root = ET.fromstring(xml)
    classes = {e.text for e in root.iter(f"{{{NAMESPACE}}}classification")}
    assert classes & {MEASURED, UNMEASURED, "dynamic"}
    shares = root.findall(f".//{{{NAMESPACE}}}unmeasured_share")
    assert shares and float(shares[0].text) >= 0.0


def test_gpx_never_invents_a_concentration_for_unmeasured_points(network, attributed):
    segments, _ = attributed
    path = [f"n{r}_3" for r in range(9)]
    exposure = score_path(network, path, segments)
    coords = [[network.nodes[n]["lon"], network.nodes[n]["lat"]] for n in path]
    root = ET.fromstring(route_to_gpx(coords, exposure))
    for point in root.iter("{http://www.topografix.com/GPX/1/1}trkpt"):
        classification = point.find(f".//{{{NAMESPACE}}}classification")
        concentration = point.find(f".//{{{NAMESPACE}}}concentration")
        if classification is not None and classification.text == UNMEASURED:
            assert concentration is None


# --- viability gate -------------------------------------------------------

def test_viability_detects_the_signal_built_into_the_fixture(network):
    verdict = run_viability(network, FixtureAirSource(days=2))
    assert verdict["spatial"] is not None
    assert verdict["spatial"]["passes"] is True
    assert verdict["temporal"]["passes"] is True
    assert verdict["route_recommendation_viable"] is True


def test_viability_reports_rather_than_raises_on_thin_data(network):
    class Thin(FixtureAirSource):
        def readings(self):
            return super().readings()[:5]

    verdict = run_viability(network, Thin())
    assert verdict["spatial"] is None or verdict["spatial"]["passes"] in (True, False)
    assert verdict["coverage"]["segments_total"] > 0


# --- resolution: signal against the instrument's own disagreement -----------


def test_background_removal_leaves_the_street_and_drops_the_weather():
    """Enhancement is a reading minus what the whole fleet saw that hour."""
    from datetime import datetime, timezone

    from app.air.noise import as_enhancement, citywide_background

    when = datetime(2020, 1, 5, 8, tzinfo=timezone.utc)
    readings = [
        AirReading(lon=7.58, lat=47.55, timestamp=when, values={"pm25": v},
                   sensor_id="a")
        for v in [10.0] * 40
    ] + [
        AirReading(lon=7.59, lat=47.56, timestamp=when, values={"pm25": 18.0},
                   sensor_id="b")
    ]
    background = citywide_background(readings)
    assert background[(when.date(), 8)] == 10.0
    enhanced = as_enhancement(readings, background)
    assert enhanced[-1].values["pm25"] == 8.0      # 18 above a citywide 10
    assert enhanced[0].values["pm25"] == 0.0


def test_hours_without_enough_readings_get_no_background_and_are_dropped():
    """A background from three readings would be noise pretending to be a level."""
    from datetime import datetime, timezone

    from app.air.noise import as_enhancement, citywide_background

    when = datetime(2020, 1, 5, 3, tzinfo=timezone.utc)
    thin = [
        AirReading(lon=7.58, lat=47.55, timestamp=when, values={"pm25": 12.0},
                   sensor_id="a")
        for _ in range(3)
    ]
    background = citywide_background(thin)
    assert background == {}
    assert as_enhancement(thin, background) == []


def test_disagreement_is_undetermined_when_no_street_saw_two_sensors(network):
    """One sensor per street means the instruments were never compared."""
    from app.air.noise import signal_to_noise

    verdict = signal_to_noise(network, FixtureAirSource(days=2).readings())
    assert verdict["noise_sensor_disagreement"]["median_gap_between_two_sensors"] is None
    assert verdict["passes"] is None
    assert "undetermined" in verdict["interpretation"]


def test_an_undetermined_resolution_gate_does_not_condemn_the_dataset(network):
    """Unknown is not bad — the same rule the unmeasured class follows."""
    verdict = run_viability(network, FixtureAirSource(days=2))
    assert verdict["resolution"]["passes"] is None
    assert verdict["route_recommendation_viable"] is True


def test_two_sensors_disagreeing_on_one_street_is_measured_as_noise(network):
    """Same segment, same hour, two sensors, a known 6 ug/m3 apart."""
    from datetime import datetime, timezone

    from app.air.noise import sensor_disagreement

    # On the midpoint of a real edge, which is what attribution matches against.
    u, v = next(iter(network.edges()))
    lon = (network.nodes[u]["lon"] + network.nodes[v]["lon"]) / 2
    lat = (network.nodes[u]["lat"] + network.nodes[v]["lat"]) / 2
    when = datetime(2020, 1, 5, 8, tzinfo=timezone.utc)
    readings = []
    for sensor, value in (("a", 8.0), ("b", 14.0)):
        readings += [
            AirReading(lon=lon, lat=lat, timestamp=when, values={"pm25": value},
                       sensor_id=sensor)
            for _ in range(5)
        ]
    result = sensor_disagreement(network, readings)
    assert result["cells_compared"] >= 1
    assert result["median_gap_between_two_sensors"] == 6.0


# --- the modelled baseline: separate from measurement, never merged with it ---


@pytest.fixture
def baseline():
    from app.air.baseline import AirBaseline

    if not AirBaseline.available():
        pytest.skip("federal baseline not prepared; run `python -m app.air.baseline --prepare`")
    return AirBaseline()


def test_baseline_covers_effectively_the_whole_basel_network(baseline):
    """The point of the modelled layer: it is everywhere the measurements are not."""
    from app.air.attribute import _segment_midpoints
    from app.street_sources import load_network

    try:
        network = load_network("walk", source="osmnx")
    except Exception:
        pytest.skip("prepared Basel network not present")
    ids, xs, ys, _ = _segment_midpoints(network)
    values = baseline.sample(xs, ys, "no2")
    covered = sum(v is not None for v in values)
    assert covered / len(ids) > 0.95


def test_baseline_declares_itself_modelled_and_annual(baseline):
    """Modelled data must never arrive looking like a measurement."""
    provenance = baseline.provenance("no2")
    assert provenance["classification"] == "modelled"
    assert provenance["temporal_resolution"] == "annual mean"
    assert "not a measurement" in provenance["explanation"].lower()
    assert provenance["attribution"]
    assert provenance["resolution_m"] == 20


def test_baseline_outside_the_clip_is_none_not_zero(baseline):
    """Off the edge of Basel is unknown, in the same way an unmeasured street is."""
    assert baseline.sample([0.0], [0.0], "no2") == [None]


def test_modelled_and_measured_travel_in_separate_fields(network, attributed):
    """The two must be distinguishable at every level of the response."""
    segments, _ = attributed
    nodes = list(network.nodes())[:6]
    fake_baseline = {segment_id(u, v): 22.0 for u, v in zip(nodes, nodes[1:])}
    exposure = score_path(network, nodes, segments, baseline=fake_baseline)
    body = exposure.as_dict()
    assert body["baseline"]["classification"] == "modelled"
    assert body["baseline"]["pollutant"] == "no2"
    assert body["baseline"]["mean"] == 22.0
    # The measured total is untouched by the presence of a model.
    assert body["classification"] == "dynamic"
    assert body["pollutant"] == "pm25"
    for segment in exposure.segments:
        row = segment.as_dict()
        assert "concentration" in row and "baseline_no2" in row
        assert row["baseline_no2"] == 22.0


def test_a_route_with_no_baseline_behaves_exactly_as_before(network, attributed):
    """The modelled layer is additive; without it nothing changes."""
    segments, _ = attributed
    nodes = list(network.nodes())[:6]
    body = score_path(network, nodes, segments).as_dict()
    assert body["baseline"]["mean"] is None
    assert body["baseline"]["share_of_route"] == 0.0
