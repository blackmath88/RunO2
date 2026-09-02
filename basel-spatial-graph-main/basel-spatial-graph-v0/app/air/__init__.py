"""Air-quality layer: mobile sensor readings joined to the walking network.

Built for the Hack am Rhein warm-up entry. Read-only with respect to the rest
of the application — nothing here modifies the graph, the accessibility engine
or the existing sources. It consumes a `StreetNetwork` and produces exposure
scores with per-segment provenance.
"""
from .model import AirReading, SegmentAir, Coverage, MEASURED, UNMEASURED, POLLUTANTS

__all__ = ["AirReading", "SegmentAir", "Coverage", "MEASURED", "UNMEASURED", "POLLUTANTS"]
