"""Weather, pollen and terrain.

The network-facing functions are not exercised here — the suite never opens a
socket. What is tested is the arithmetic that turns a public elevation model
into a number someone will read off a screen, because that is where a plausible
lie is easiest to tell.
"""
from __future__ import annotations

import pytest

from app.air.conditions import (
    DERIVED, pollen_band, resample, smooth, terrain_profile, _bearing_name,
)


def test_pollen_bands_follow_the_published_thresholds():
    assert pollen_band(0) == "none"
    assert pollen_band(5) == "low"
    assert pollen_band(50) == "moderate"
    assert pollen_band(150) == "high"
    assert pollen_band(500) == "very high"
    assert pollen_band(None) is None


def test_wind_direction_is_named_from_degrees():
    assert _bearing_name(0) == "N"
    assert _bearing_name(90) == "E"
    assert _bearing_name(225) == "SW"
    assert _bearing_name(None) is None


def test_resampling_puts_points_at_a_fixed_spacing():
    """A route sampled unevenly would weight its own dense corners."""
    line = [[7.58, 47.55], [7.60, 47.55]]           # ~1.5 km due east
    points = resample(line, spacing_m=100.0)
    assert len(points) > 10
    gaps = [b[2] - a[2] for a, b in zip(points, points[1:])]
    assert all(abs(g - 100.0) < 1.0 for g in gaps[:-1])
    assert points[0][2] == 0.0
    assert points[-1][2] > points[0][2]


def test_smoothing_removes_the_sawtooth_a_90m_model_invents():
    """Alternating +/-5 m between 50 m samples is model noise, not a hill."""
    distances = [i * 50.0 for i in range(21)]
    spiky = [100.0 + (5.0 if i % 2 else -5.0) for i in range(21)]
    smoothed = smooth(spiky, distances, window_m=250.0)
    assert max(smoothed) - min(smoothed) < 3.0      # was 10.0 before smoothing


def test_grade_is_measured_over_a_window_not_between_two_samples():
    """The failure this guards: dividing DEM noise by 50 m to get 15%."""
    distances = [i * 50.0 for i in range(41)]
    spiky = [100.0 + (6.0 if i % 2 else -6.0) for i in range(41)]
    profile = terrain_profile(spiky, distances)
    assert profile["classification"] == DERIVED
    assert profile["max_grade_pct"] < 2.0
    assert "approximate" in profile["explanation"].lower()


def test_a_real_climb_still_shows_up():
    """Smoothing must not flatten terrain that is actually there."""
    distances = [i * 50.0 for i in range(41)]
    climb = [100.0 + i * 2.0 for i in range(41)]    # 2 m per 50 m = 4%
    profile = terrain_profile(climb, distances)
    # Slightly under the true 80 m: the smoothing window is truncated at both
    # ends of the route, which flattens the first and last 125 m of the ramp.
    assert profile["ascent_m"] == pytest.approx(80, abs=6)
    assert profile["descent_m"] == 0
    assert profile["max_grade_pct"] == pytest.approx(4.0, abs=0.3)


def test_a_loop_climbs_as_much_as_it_descends():
    distances = [i * 50.0 for i in range(41)]
    there_and_back = [100.0 + min(i, 40 - i) * 2.0 for i in range(41)]
    profile = terrain_profile(there_and_back, distances)
    assert profile["ascent_m"] == pytest.approx(profile["descent_m"], abs=2)


def test_too_few_points_reports_nothing_rather_than_zero():
    profile = terrain_profile([100.0], [0.0])
    assert profile["ascent_m"] is None
