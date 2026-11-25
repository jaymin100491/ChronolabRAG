"""Load the bundled public LOINC teaching notes and default intervals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from chronolab_rag.temporal.unit_normalizer import UnitConversionError, canonicalize_unit_label, convert

_DATA_PATH = Path(__file__).resolve().parent / "data" / "loinc_references.json"


@dataclass(frozen=True)
class Monograph:
    source_id: str
    loinc_code: str
    alias_loinc_codes: tuple[str, ...]
    title: str
    snippet: str

    def search_text(self) -> str:
        aliases = " ".join(self.alias_loinc_codes)
        return f"{self.title} {self.snippet} {self.loinc_code} {aliases} {self.source_id}"


@dataclass(frozen=True)
class ReferenceInterval:
    """Teaching interval stored beside a monograph, in ``unit``."""

    low: float
    high: float
    unit: str


def load_monographs() -> tuple[Monograph, ...]:
    monographs = []
    for row in _payload():
        monographs.append(
            Monograph(
                source_id=row["source_id"],
                loinc_code=row["loinc_code"],
                alias_loinc_codes=tuple(row.get("alias_loinc_codes") or ()),
                title=row["title"],
                snippet=row["snippet"],
            )
        )
    return tuple(monographs)


def default_reference_interval(loinc_code: str) -> ReferenceInterval | None:
    """Return the teaching interval for a canonical code or one of its aliases."""

    return _interval_index().get(loinc_code)


def reference_bounds(
    loinc_code: str,
    unit: str,
    low: float | None,
    high: float | None,
) -> tuple[float | None, float | None]:
    """Keep a supplied interval, or fill both bounds from the teaching notes.

    Defaults are stored in the monograph unit and converted onto ``unit``.
    A partial supplied interval is left unchanged.
    """

    if low is not None or high is not None:
        return low, high
    interval = default_reference_interval(loinc_code)
    if interval is None:
        return None, None
    try:
        observed = canonicalize_unit_label(unit)
        canonical = canonicalize_unit_label(interval.unit)
    except UnitConversionError:
        return None, None
    if observed == canonical:
        return interval.low, interval.high
    try:
        return (
            convert(interval.low, interval.unit, unit, loinc_code=loinc_code),
            convert(interval.high, interval.unit, unit, loinc_code=loinc_code),
        )
    except UnitConversionError:
        return None, None


def _payload() -> list[dict[str, object]]:
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("loinc_references.json must be a list")
    return payload


@lru_cache(maxsize=1)
def _interval_index() -> dict[str, ReferenceInterval]:
    index: dict[str, ReferenceInterval] = {}
    for row in _payload():
        low_raw = row.get("reference_low")
        high_raw = row.get("reference_high")
        unit_raw = row.get("reference_unit")
        if isinstance(low_raw, bool) or isinstance(high_raw, bool):
            continue
        if not isinstance(low_raw, (int, float)) or not isinstance(high_raw, (int, float)):
            continue
        if not isinstance(unit_raw, str) or not unit_raw.strip():
            continue
        interval = ReferenceInterval(low=float(low_raw), high=float(high_raw), unit=unit_raw)
        index[str(row["loinc_code"])] = interval
        aliases = row.get("alias_loinc_codes") or []
        if isinstance(aliases, list):
            for alias in aliases:
                index[str(alias)] = interval
    return index
