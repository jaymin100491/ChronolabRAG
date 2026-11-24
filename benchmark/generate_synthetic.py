"""Build 50 synthetic multi-visit timelines for the offline benchmark."""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chronolab_rag.temporal.unit_normalizer import Panel, convert, list_panels  # noqa: E402

_ORIGIN = datetime(2023, 1, 1, tzinfo=timezone.utc)


def build_cases(n: int = 50, seed: int = 42) -> list[dict[str, object]]:
    """Return ``n`` synthetic timelines.

    Cases rotate through five shapes: a stable series, a unit flip across
    visits, fluctuation around the top of the reference range, a rapid spike,
    and a steady decline. Every tenth-or-so case also carries a second test.
    """

    rng = random.Random(seed)
    panels = list_panels()
    cases: list[dict[str, object]] = []
    for index in range(n):
        primary = panels[index % len(panels)]
        selected = [primary]
        if index % 7 == 0:
            companion = panels[(index + 5) % len(panels)]
            if companion.key != primary.key:
                selected.append(companion)
        observations: list[dict[str, object]] = []
        for offset, panel in enumerate(selected):
            kind = index % 5 if offset == 0 else 0
            observations.extend(_series(rng, panel, index, kind))
        cases.append(
            {
                "patient_id": f"SYN-{index + 1:03d}",
                "observations": observations,
            }
        )
    return cases


def write_cases(path: Path, cases: list[dict[str, object]]) -> None:
    lines = [json.dumps(case, separators=(",", ":")) for case in cases]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _series(rng: random.Random, panel: Panel, index: int, kind: int) -> list[dict[str, object]]:
    visits = 4 + (index % 3)
    low = panel.reference_low
    high = panel.reference_high
    span = high - low
    alternate = _alternate_unit(panel) if kind == 1 else None
    rows: list[dict[str, object]] = []
    for visit in range(visits):
        value = _value(rng, kind, visit, visits, low, high, span)
        unit = panel.canonical_unit
        stored_low: float | None = low
        stored_high: float | None = high
        stored_value = value
        if alternate and visit >= visits // 2:
            unit = alternate
            stored_value = convert(
                value, panel.canonical_unit, alternate, loinc_code=panel.canonical_loinc
            )
            stored_low = convert(low, panel.canonical_unit, alternate, loinc_code=panel.canonical_loinc)
            stored_high = convert(
                high, panel.canonical_unit, alternate, loinc_code=panel.canonical_loinc
            )
        day = index * 3 + visit * 45
        if kind == 3 and visit == visits - 1:
            day = index * 3 + (visit - 1) * 45 + 2
        rows.append(
            {
                "loinc_code": panel.canonical_loinc,
                "test_name": panel.test_name,
                "value": round(stored_value, 4),
                "unit": unit,
                "reference_low": None if stored_low is None else round(stored_low, 4),
                "reference_high": None if stored_high is None else round(stored_high, 4),
                "timestamp": (_ORIGIN + timedelta(days=day)).isoformat(),
            }
        )
    return rows


def _value(
    rng: random.Random,
    kind: int,
    visit: int,
    visits: int,
    low: float,
    high: float,
    span: float,
) -> float:
    mid = (low + high) / 2
    if kind == 0:
        return mid + rng.uniform(-span * 0.05, span * 0.05)
    if kind == 1:
        progress = visit / max(visits - 1, 1)
        return low + span * (0.35 + 0.2 * progress)
    if kind == 2:
        return high + rng.uniform(-span * 0.04, span * 0.04)
    if kind == 3:
        if visit < visits - 1:
            return mid
        return high + span * 0.8
    progress = visit / max(visits - 1, 1)
    return high - span * (0.15 + 0.5 * progress)


def _alternate_unit(panel: Panel) -> str | None:
    changed: list[str] = []
    same: list[str] = []
    for unit in panel.converters:
        if unit == panel.canonical_unit:
            continue
        converted = convert(25.0, panel.canonical_unit, unit, loinc_code=panel.canonical_loinc)
        if math.isclose(converted, 25.0, rel_tol=1e-9, abs_tol=1e-9):
            same.append(unit)
        else:
            changed.append(unit)
    if changed:
        return changed[0]
    return same[0] if same else None


def main() -> None:
    destination = Path(__file__).resolve().parent / "sample_cases.jsonl"
    write_cases(destination, build_cases())
    print(f"Wrote 50 synthetic timelines to {destination}")


if __name__ == "__main__":
    main()
