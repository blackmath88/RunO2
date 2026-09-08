"""Every number on the page must still be true.

The interface and the documentation quote figures that were computed once from
613,723 readings and two national rasters. Nothing stops those numbers drifting
away from the artefacts they came from except this file, which reads the
evidence and checks the claims against it.

A failure here means a headline number is now a story rather than a result.
Regenerate the artefact or fix the wording — but do not adjust the assertion.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VIABILITY = ROOT / "experiments" / "AIR_VIABILITY_REAL.md"
CALIBRATION = ROOT / "experiments" / "sensor_calibration.json"
PAGE = ROOT / "app" / "static" / "run.html"
DATA_FIT = ROOT / "docs" / "DATA_FIT.md"


@pytest.fixture(scope="module")
def evidence():
    if not VIABILITY.exists():
        pytest.skip("real viability report not generated")
    text = VIABILITY.read_text(encoding="utf-8")
    blocks = dict(re.findall(r"## (\w+)\n\n```json\n(.*?)\n```", text, re.S))
    return {key: json.loads(body) for key, body in blocks.items()}


@pytest.fixture(scope="module")
def page():
    return PAGE.read_text(encoding="utf-8")


def test_the_evidence_still_says_the_gate_fails(evidence):
    """If this ever passes, the entire data story needs rewriting, not patching."""
    resolution = evidence["resolution"]
    assert resolution["passes"] is False
    assert resolution["signal_to_noise_ratio"] < 1.0


def test_the_headline_signal_and_noise_are_what_the_page_shows(evidence, page):
    signal = evidence["resolution"]["signal_street_contrast"]["median_gap_between_two_streets"]
    noise = evidence["resolution"]["noise_sensor_disagreement"]["median_gap_between_two_sensors"]
    ratio = evidence["resolution"]["signal_to_noise_ratio"]
    assert f"{signal}" in page, f"page no longer quotes the street contrast {signal}"
    assert f"{noise}" in page, f"page no longer quotes the sensor disagreement {noise}"
    assert f"{ratio}" in page, f"page no longer quotes the ratio {ratio}"


def test_the_page_does_not_overstate_how_much_worse_the_sensors_are(evidence, page):
    """'almost three times' has to keep matching the arithmetic."""
    signal = evidence["resolution"]["signal_street_contrast"]["median_gap_between_two_streets"]
    noise = evidence["resolution"]["noise_sensor_disagreement"]["median_gap_between_two_sensors"]
    assert 2.5 <= noise / signal < 3.0


def test_coverage_claims_match_the_report(evidence, page):
    share = evidence["coverage"]["length_share"]
    assert f"{share * 100:.1f}%" in page
    assert round(evidence["coverage"]["network_length_km"]) == 884


def test_temporal_gate_is_still_the_one_that_passes(evidence, page):
    assert evidence["temporal"]["passes"] is True
    assert f"{evidence['temporal']['disagreement']:.2f}" in page


def test_calibration_figures_on_the_page_match_the_run(page):
    if not CALIBRATION.exists():
        pytest.skip("calibration not run")
    payload = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    for site in payload["sites"]:
        assert f"{site['paired_hours']:,}" in page, f"{site['site']} paired hours"
        assert f"{site['mean_absolute_error_ug_m3']}" in page, f"{site['site']} MAE"
        assert f"{abs(site['median_bias_ug_m3'])}" in page, f"{site['site']} bias"


def test_the_underreporting_percentage_is_derived_not_asserted(page):
    """'32-37%' must follow from bias over reference median."""
    if not CALIBRATION.exists():
        pytest.skip("calibration not run")
    payload = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    shares = sorted(
        abs(s["median_bias_ug_m3"]) / s["reference_median_ug_m3"] * 100
        for s in payload["sites"]
    )
    claimed = re.search(r"under-report by (\d+)–(\d+)%", page)
    assert claimed, "the page no longer states an under-reporting range"
    low, high = int(claimed.group(1)), int(claimed.group(2))
    assert low == round(shares[0]) and high == round(shares[-1]), (
        f"page claims {low}-{high}%, evidence gives "
        f"{round(shares[0])}-{round(shares[-1])}%"
    )


def test_baseline_claims_match_the_committed_raster(page):
    """Coverage and street contrast of the federal layer, as shipped."""
    from app.air.attribute import _segment_midpoints
    from app.air.baseline import AirBaseline
    from app.air.noise import _median_pairwise_gap
    from app.street_sources import load_network

    if not AirBaseline.available():
        pytest.skip("federal baseline not prepared")
    # source="osmnx" pins past the suite's fixture mode to the committed
    # GraphML cache. It is a local file read; nothing opens a socket.
    try:
        network = load_network("walk", source="osmnx")
    except Exception:
        pytest.skip("prepared Basel network not present")
    ids, xs, ys, _ = _segment_midpoints(network)
    baseline = AirBaseline()
    for pollutant, expected_gap in (("no2", 3.00), ("pm25", 1.00)):
        values = [v for v in baseline.sample(xs, ys, pollutant) if v is not None]
        coverage = len(values) / len(ids) * 100
        assert f"{coverage:.1f}%" in page, (
            f"{pollutant} coverage is now {coverage:.1f}%, which the page does not quote"
        )
        gap = _median_pairwise_gap(values)
        assert gap == pytest.approx(expected_gap, abs=0.01)


def test_data_fit_and_the_page_do_not_contradict_each_other():
    """Two documents quoting the same study must quote it the same way."""
    if not DATA_FIT.exists():
        pytest.skip("DATA_FIT.md missing")
    fit = DATA_FIT.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    for figure in ("0.51", "1.41", "3.00", "99.5%", "19.2%"):
        assert figure in fit and figure in page, f"{figure} is not in both documents"
