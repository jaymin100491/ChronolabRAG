"""Deterministic trend math. This module never calls a language model."""

from __future__ import annotations

import math
from datetime import datetime

from chronolab_rag.schemas import LabObservation, PatientLabTimeline, TrendMetric
from chronolab_rag.temporal.unit_normalizer import Panel, normalize_observation, resolve_panel

_SECONDS_PER_DAY = 86400.0


def compute_trends(timeline: PatientLabTimeline) -> list[TrendMetric]:
    """Compare the earliest and latest normalized result for each panel."""

    grouped: dict[str, list[LabObservation]] = {}
    panels: dict[str, Panel] = {}
    for observation in timeline.observations:
        panel = resolve_panel(observation.loinc_code, observation.test_name)
        grouped.setdefault(panel.key, []).append(normalize_observation(observation))
        panels[panel.key] = panel

    metrics = [_metric(panels[key], series) for key, series in grouped.items()]
    metrics.sort(key=lambda metric: metric.test_name)
    return metrics


def _metric(panel: Panel, series: list[LabObservation]) -> TrendMetric:
    ordered = sorted(series, key=lambda observation: observation.timestamp)
    baseline = ordered[0]
    latest = ordered[-1]
    delta = latest.value - baseline.value
    percent_change = 0.0 if baseline.value == 0 else (delta / baseline.value) * 100.0
    elapsed_days = _elapsed_days(baseline.timestamp, latest.timestamp)
    velocity = delta / elapsed_days if elapsed_days > 0 else 0.0
    baseline_low, baseline_high = _range(panel, baseline)
    latest_low, latest_high = _range(panel, latest)
    baseline_status = classify_status(baseline.value, baseline_low, baseline_high)
    latest_status = classify_status(latest.value, latest_low, latest_high)
    return TrendMetric(
        loinc_code=panel.canonical_loinc,
        test_name=panel.test_name,
        delta=delta,
        percent_change=percent_change,
        velocity_per_day=velocity,
        status_transition=f"{baseline_status}->{latest_status}",
        normalized_unit=panel.canonical_unit,
        baseline_value=baseline.value,
        latest_value=latest.value,
        baseline_status=baseline_status,
        latest_status=latest_status,
        observation_count=len(ordered),
        reference_low=latest_low,
        reference_high=latest_high,
    )


def classify_status(value: float, low: float | None, high: float | None) -> str:
    """Label a value against an inclusive reference interval."""

    if low is not None and _below(value, low):
        return "Low"
    if high is not None and _above(value, high):
        return "High"
    if low is None and high is None:
        return "Unknown"
    return "Normal"


def _below(value: float, bound: float) -> bool:
    return value < bound and not math.isclose(value, bound, rel_tol=1e-9, abs_tol=1e-6)


def _above(value: float, bound: float) -> bool:
    return value > bound and not math.isclose(value, bound, rel_tol=1e-9, abs_tol=1e-6)


def _range(panel: Panel, observation: LabObservation) -> tuple[float | None, float | None]:
    low = observation.reference_low if observation.reference_low is not None else panel.reference_low
    high = observation.reference_high if observation.reference_high is not None else panel.reference_high
    return low, high


def _elapsed_days(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / _SECONDS_PER_DAY
