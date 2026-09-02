# Air data viability

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
