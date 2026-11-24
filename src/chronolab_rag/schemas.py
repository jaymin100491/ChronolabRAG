"""Pydantic models for timelines, trend metrics, citations, and audited explanations."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

_STATUSES = ("Low", "Normal", "High", "Unknown")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class LabObservation(BaseModel):
    """One numeric laboratory result at a point in time."""

    model_config = ConfigDict(extra="ignore")

    loinc_code: str = Field(min_length=1)
    test_name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    reference_low: float | None = None
    reference_high: float | None = None
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

    @field_validator("value", "reference_low", "reference_high")
    @classmethod
    def finite_number(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("numeric fields must be finite")
        return value

    @field_validator("reference_high")
    @classmethod
    def high_is_not_below_low(cls, value: float | None, info) -> float | None:  # type: ignore[no-untyped-def]
        low = info.data.get("reference_low")
        if value is not None and low is not None and value < low:
            raise ValueError("reference_high must be greater than or equal to reference_low")
        return value


class PatientLabTimeline(BaseModel):
    """Synthetic multi-visit laboratory history for one patient."""

    model_config = ConfigDict(extra="ignore")

    patient_id: str = Field(min_length=1)
    observations: list[LabObservation]


class TrendMetric(BaseModel):
    """Deterministic trend computed before any language-model call."""

    model_config = ConfigDict(extra="ignore")

    loinc_code: str
    test_name: str
    delta: float
    percent_change: float
    velocity_per_day: float
    status_transition: str
    normalized_unit: str
    baseline_value: float
    latest_value: float
    baseline_status: str
    latest_status: str
    observation_count: int = Field(ge=1)
    reference_low: float | None = None
    reference_high: float | None = None

    @field_validator("status_transition")
    @classmethod
    def transition_uses_known_statuses(cls, value: str) -> str:
        parts = value.split("->")
        if len(parts) != 2 or parts[0] not in _STATUSES or parts[1] not in _STATUSES:
            raise ValueError("status_transition must look like Normal->High")
        return value


class RetrievedReference(BaseModel):
    """A public teaching monograph retrieved for a LOINC-coded test."""

    model_config = ConfigDict(extra="ignore")

    source_id: str
    loinc_code: str
    title: str
    snippet: str


class VerifiedExplanation(BaseModel):
    """Plain-language summary plus the deterministic safety audit."""

    model_config = ConfigDict(extra="ignore")

    summary_text: str
    citations: list[str]
    safety_audit_passed: bool
    audit_flags: list[str]
    reading_grade_level: float
