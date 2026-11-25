"""Load MIMIC-IV laboratory tables into patient timelines.

``labevents.csv`` may already contain ``loinc_code``. Otherwise it is joined to
``d_labitems.csv`` on ``itemid``. Rows are grouped by ``subject_id`` and sorted
by ``charttime``. A patient is kept when one supported test appears at least twice.
"""

from __future__ import annotations

import csv
import gzip
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, TextIO

from pydantic import ValidationError

from chronolab_rag.retrieval.loinc_kb import reference_bounds
from chronolab_rag.schemas import LabObservation, PatientLabTimeline
from chronolab_rag.temporal.unit_normalizer import (
    UnitConversionError,
    canonicalize_unit_label,
    resolve_panel,
    supported_loinc_codes,
)


def load_mimic_directory(directory: Path) -> list[PatientLabTimeline]:
    """Read ``labevents.csv`` and optional ``d_labitems.csv`` from ``directory``."""

    if not directory.is_dir():
        raise FileNotFoundError(f"MIMIC directory not found: {directory}")
    labevents = _find_table(directory, "labevents")
    if labevents is None:
        raise FileNotFoundError(f"labevents.csv not found in {directory}")
    return load_mimic_timelines(labevents, _find_table(directory, "d_labitems"))


def load_mimic_timelines(
    labevents: Path,
    labitems: Path | None = None,
) -> list[PatientLabTimeline]:
    """Join lab events to LOINC codes and return repeat-test timelines."""

    item_map = _load_item_map(labitems) if labitems is not None else {}
    grouped: dict[str, list[LabObservation]] = defaultdict(list)
    supported = supported_loinc_codes()
    with _open_text(labevents) as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = _normalize_row(raw)
            observation = _observation(row, item_map, supported)
            subject_id = row.get("subject_id", "")
            if observation is None or not subject_id:
                continue
            grouped[subject_id].append(observation)
    timelines = [
        PatientLabTimeline(patient_id=subject_id, observations=observations)
        for subject_id, observations in grouped.items()
    ]
    return timelines_with_repeated_tests(timelines)


def timelines_with_repeated_tests(
    timelines: Iterable[PatientLabTimeline],
) -> list[PatientLabTimeline]:
    """Keep patients who have at least one test measured twice.

    Alias LOINC codes for one panel, such as glucose ``2339-0`` and ``2345-7``,
    count as the same test. Observations are sorted by time. A patient whose
    every supported test appears only once is dropped.
    """

    kept: list[PatientLabTimeline] = []
    for timeline in timelines:
        grouped: dict[str, list[LabObservation]] = defaultdict(list)
        for observation in timeline.observations:
            panel = resolve_panel(observation.loinc_code, observation.test_name)
            grouped[panel.key].append(observation)
        if not any(len(series) >= 2 for series in grouped.values()):
            continue
        observations = sorted(timeline.observations, key=lambda observation: observation.timestamp)
        kept.append(
            PatientLabTimeline(patient_id=timeline.patient_id, observations=observations)
        )
    kept.sort(key=_patient_sort_key)
    return kept


def _observation(
    row: dict[str, str],
    item_map: dict[str, tuple[str, str]],
    supported: frozenset[str],
) -> LabObservation | None:
    loinc_code = row.get("loinc_code", "")
    label = row.get("label", "")
    if not loinc_code:
        mapped = item_map.get(row.get("itemid", ""))
        if mapped is None:
            return None
        loinc_code, mapped_label = mapped
        label = label or mapped_label
    if loinc_code not in supported:
        return None
    value = _finite_number(row.get("valuenum") or row.get("value"))
    if value is None:
        return None
    unit = row.get("valueuom") or row.get("unit") or ""
    if not unit:
        return None
    try:
        canonicalize_unit_label(unit)
        panel = resolve_panel(loinc_code)
    except UnitConversionError:
        return None
    timestamp = _charttime(row.get("charttime", ""))
    if timestamp is None:
        return None
    low = _finite_number(row.get("ref_range_lower"))
    high = _finite_number(row.get("ref_range_upper"))
    low, high = reference_bounds(loinc_code, unit, low, high)
    try:
        return LabObservation(
            loinc_code=loinc_code,
            test_name=label or panel.test_name,
            value=value,
            unit=unit,
            reference_low=low,
            reference_high=high,
            timestamp=timestamp,
        )
    except ValidationError:
        return None


def _load_item_map(path: Path) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    with _open_text(path) as handle:
        for raw in csv.DictReader(handle):
            row = _normalize_row(raw)
            itemid = row.get("itemid", "")
            loinc_code = row.get("loinc_code", "")
            if itemid and loinc_code:
                mapping[itemid] = (loinc_code, row.get("label", ""))
    return mapping


def _find_table(directory: Path, stem: str) -> Path | None:
    expected = {f"{stem}.csv", f"{stem}.csv.gz"}
    for name in expected:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    for path in directory.iterdir():
        if path.is_file() and path.name.lower() in expected:
            return path
    return None


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("r", encoding="utf-8-sig", newline="")


def _normalize_row(raw: dict[str, str | None]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        if key is None:
            continue
        text = "" if value is None else str(value).strip()
        normalized[key.strip().lower().lstrip("\ufeff")] = text
    return normalized


def _charttime(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    text = text.replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _finite_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _patient_sort_key(timeline: PatientLabTimeline) -> tuple[int, int, str]:
    if timeline.patient_id.isdigit():
        return (0, int(timeline.patient_id), timeline.patient_id)
    return (1, 0, timeline.patient_id)
