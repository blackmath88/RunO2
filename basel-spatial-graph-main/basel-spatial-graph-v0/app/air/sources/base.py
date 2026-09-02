"""Contract every air-reading provider implements.

Same shape as the street, service and transit source contracts: a provider
returns `AirReading` objects carrying their own provenance, and nothing
downstream knows or cares whether they came from a CSV export, an API or a
hand-written fixture.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from ..model import AirReading

LIVE = "live"
FIXTURE = "fixture"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_air_provenance(
    *,
    mode: str,
    source: str,
    dataset: str,
    dataset_title: Optional[str] = None,
    source_url: Optional[str] = None,
    license: Optional[str] = None,
    retrieved_at: Optional[str] = None,
    sensor_class: Optional[str] = None,
    **extra,
) -> dict:
    """One provenance shape for every air source, so the UI can trust fields."""
    record = {
        "mode": mode,
        "fixture": mode == FIXTURE,
        "source": source,
        "dataset": dataset,
        "dataset_title": dataset_title,
        "source_url": source_url,
        "license": license,
        "retrieved_at": retrieved_at or utc_now_iso(),
        "sensor_class": sensor_class,
    }
    record.update(extra)
    return record


class AirSource(ABC):
    """Returns air readings for a bounding box."""

    #: Set by subclasses; surfaced in every provenance record.
    mode: str = FIXTURE

    @abstractmethod
    def readings(self) -> List[AirReading]:
        """All readings this source can supply, each with provenance attached."""

    def error_band(self, pollutant: str) -> Optional[float]:
        """Published deviation of this sensor class against reference instruments.

        Returns None when unknown — which is different from zero, and the
        interface renders the difference.
        """
        return None
