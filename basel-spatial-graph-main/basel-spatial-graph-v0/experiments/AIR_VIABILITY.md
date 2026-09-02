# Air data viability

Pollutant: `pm25`

**Route recommendation viable:** True
**Hour-of-day control viable:** True

## spatial

```json
{
  "basis": "hour 8",
  "segments_compared": 33,
  "p10": 12.46,
  "p90": 18.57,
  "between_street_gap": 6.11,
  "typical_within_street_spread": 0.11,
  "ratio": 53.86,
  "passes": true,
  "threshold": 1.5
}
```

## temporal

```json
{
  "segments_compared": 33,
  "morning_hour": 8,
  "evening_hour": 17,
  "rank_correlation": -0.993,
  "disagreement": 0.996,
  "passes": true,
  "threshold": 0.25,
  "interpretation": "Rankings change by hour \u2014 an hour-of-day control is justified."
}
```

## coverage

```json
{
  "segments_total": 218,
  "segments_measured": 33,
  "segments_unmeasured": 185,
  "segment_share": 0.1514,
  "length_share": 0.1423,
  "network_length_km": 63.46,
  "note": "Sensors ride on trams, so coverage follows the tram network. Unmeasured streets are shown as unmeasured, never as clean."
}
```
