# Air data viability

| | |
|---|---|
| Dataset | 100113 |
| Title | Feinstaubmessungen auf BVB-Trams |
| Source | Open Data Basel-Stadt |
| Licence | CC BY 4.0 |
| Retrieved | 2026-09-03T18:57:33+00:00 |
| Publisher last update | 2026-01-28T10:16:46.763000+00:00 |
| Sensor class | low-cost mobile microsensor |

Pollutant: `pm25`

**Route recommendation viable:** False
**Hour-of-day control viable:** True

## spatial

```json
{
  "basis": "hour 8",
  "segments_compared": 3311,
  "p10": 4.72,
  "p90": 15.07,
  "between_street_gap": 10.35,
  "typical_within_street_spread": 19.13,
  "ratio": 0.54,
  "passes": false,
  "threshold": 1.5
}
```

## temporal

```json
{
  "segments_compared": 3242,
  "morning_hour": 8,
  "evening_hour": 17,
  "rank_correlation": 0.453,
  "disagreement": 0.273,
  "passes": true,
  "threshold": 0.25,
  "interpretation": "Rankings change by hour \u2014 an hour-of-day control is justified."
}
```

## coverage

```json
{
  "segments_total": 19258,
  "segments_measured": 4700,
  "segments_unmeasured": 14558,
  "segment_share": 0.2441,
  "length_share": 0.192,
  "network_length_km": 884.11,
  "note": "Sensors ride on trams, so coverage follows the tram network. Unmeasured streets are shown as unmeasured, never as clean."
}
```

## resolution

```json
{
  "citywide_background": {
    "bins": 2735,
    "bin_definition": "one date, one clock hour, whole fleet",
    "p10": 1.73,
    "median": 7.45,
    "p90": 26.34,
    "note": "Day-to-day variation moves every street together. It is removed from both sides of the comparison below."
  },
  "signal_street_contrast": {
    "basis": "hour 8",
    "segments_compared": 3311,
    "median_gap_between_two_streets": 0.51,
    "unit": "ug/m3 (enhancement over citywide level)"
  },
  "noise_sensor_disagreement": {
    "cells_compared": 11570,
    "cell_definition": "one segment, one date, one clock hour",
    "median_gap_between_two_sensors": 1.41,
    "p90_gap": 8.19,
    "unit": "ug/m3",
    "systematic_offsets": [
      {
        "pair": "228 - 237",
        "comparisons": 3893,
        "median_offset": -0.81
      },
      {
        "pair": "234 - 235",
        "comparisons": 2122,
        "median_offset": 2.33
      },
      {
        "pair": "227 - 237",
        "comparisons": 1561,
        "median_offset": -1.7
      },
      {
        "pair": "227 - 228",
        "comparisons": 1452,
        "median_offset": -0.28
      },
      {
        "pair": "234 - 237",
        "comparisons": 906,
        "median_offset": -1.07
      },
      {
        "pair": "228 - 234",
        "comparisons": 780,
        "median_offset": -0.74
      },
      {
        "pair": "228 - 235",
        "comparisons": 776,
        "median_offset": 0.65
      },
      {
        "pair": "227 - 234",
        "comparisons": 687,
        "median_offset": -1.08
      },
      {
        "pair": "235 - 237",
        "comparisons": 664,
        "median_offset": -3.08
      },
      {
        "pair": "227 - 235",
        "comparisons": 502,
        "median_offset": 4.18
      }
    ]
  },
  "signal_to_noise_ratio": 0.36,
  "passes": false,
  "threshold": 1.0,
  "interpretation": "Two sensors on the same street in the same hour disagree by as much as two different streets do. Ranking routes by these values ranks noise. More trams would add coverage, not resolution \u2014 only calibration against reference instruments would."
}
```

## measurement window

```json
{
  "readings_per_month": {
    "2019-12": 196875,
    "2020-01": 193861,
    "2020-02": 150915,
    "2020-03": 72072
  },
  "readings_total": 613723,
  "readings_after_2020_03_16": 23078,
  "fraction_after_2020_03_16": 0.03760328356603875,
  "stationary_sensors_excluded": [
    236,
    240
  ]
}
```
