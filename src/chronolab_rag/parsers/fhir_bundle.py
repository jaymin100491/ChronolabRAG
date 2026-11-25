"""Parse a single-patient HL7 FHIR R4 Bundle of Observation resources.

Synthea exports are multi-resource Bundles. Non-laboratory entries, qualitative
results, and LOINC codes outside the unit normalizer are skipped. A missing
reference range is filled from the teaching intervals in ``loinc_references.json``.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from chronolab_rag.retrieval.loinc_kb import reference_bounds
from chronolab_rag.schemas import LabObservation, PatientLabTimeline
from chronolab_rag.temporal.unit_normalizer import (
    UnitConversionError,
    canonicalize_unit_label,
    supported_loinc_codes,
)


def parse_fhir_bundle(payload: Any) -> PatientLabTimeline:
    """Convert a FHIR R4 Bundle of numeric Observations into a timeline.

    Qualitative observations, unsupported LOINC codes, and entries that are not
    Observations are skipped. A bundle that mixes more than one patient is rejected.
    """

    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict) or payload.get("resourceType") != "Bundle":
        raise ValueError("Expected a FHIR R4 Bundle")

    observations: list[LabObservation] = []
    patient_ids: list[str] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource") or {}
        if not isinstance(resource, dict):
            continue
        parsed = _observation(resource)
        if parsed is None:
            continue
        observation, patient_id = parsed
        observations.append(observation)
        if patient_id:
            patient_ids.append(patient_id)

    unique_ids = list(dict.fromkeys(patient_ids))
    if len(unique_ids) > 1:
        raise ValueError("Bundle contains observations for more than one patient")
    patient_id = unique_ids[0] if unique_ids else "unknown"
    return PatientLabTimeline(patient_id=patient_id, observations=observations)


def _observation(resource: dict[str, Any]) -> tuple[LabObservation, str | None] | None:
    if resource.get("resourceType") != "Observation":
        return None
    quantity = resource.get("valueQuantity")
    if not isinstance(quantity, dict):
        return None
    value = _finite_number(quantity.get("value"))
    if value is None:
        return None
    matched = _matching_loinc(resource.get("code") or {})
    if matched is None:
        return None
    loinc_code, display = matched
    unit = quantity.get("unit") or quantity.get("code")
    if not isinstance(unit, str) or not unit.strip():
        return None
    unit = unit.strip()
    try:
        canonicalize_unit_label(unit)
    except UnitConversionError:
        return None
    low, high = _reference_range(resource.get("referenceRange"))
    low, high = reference_bounds(loinc_code, unit, low, high)
    timestamp = _timestamp(resource)
    if timestamp is None:
        return None
    code = resource.get("code") or {}
    test_name = code.get("text") if isinstance(code, dict) else None
    test_name = test_name or display or loinc_code
    try:
        observation = LabObservation(
            loinc_code=loinc_code,
            test_name=str(test_name),
            value=value,
            unit=unit,
            reference_low=low,
            reference_high=high,
            timestamp=timestamp,
        )
    except ValidationError:
        return None
    return observation, _patient_id(resource.get("subject") or {})


def _matching_loinc(code: Any) -> tuple[str, str | None] | None:
    if not isinstance(code, dict):
        return None
    supported = supported_loinc_codes()
    loinc_hits: list[tuple[str, str | None]] = []
    other_hits: list[tuple[str, str | None]] = []
    for coding in code.get("coding") or []:
        if not isinstance(coding, dict):
            continue
        token = str(coding.get("code") or "").strip()
        if token not in supported:
            continue
        display = coding.get("display")
        display_text = str(display) if display else None
        system = str(coding.get("system") or "").lower()
        if "loinc" in system:
            loinc_hits.append((token, display_text))
        else:
            other_hits.append((token, display_text))
    if loinc_hits:
        return loinc_hits[0]
    if other_hits:
        return other_hits[0]
    return None


def _reference_range(ranges: Any) -> tuple[float | None, float | None]:
    if not isinstance(ranges, list) or not ranges:
        return None, None
    first = ranges[0] if isinstance(ranges[0], dict) else {}
    low = (first.get("low") or {}) if isinstance(first, dict) else {}
    high = (first.get("high") or {}) if isinstance(first, dict) else {}
    low_value = _finite_number(low.get("value") if isinstance(low, dict) else None)
    high_value = _finite_number(high.get("value") if isinstance(high, dict) else None)
    return low_value, high_value


def _timestamp(resource: dict[str, Any]) -> datetime | None:
    raw = resource.get("effectiveDateTime") or resource.get("issued")
    if raw is None:
        period = resource.get("effectivePeriod") or {}
        raw = period.get("start") if isinstance(period, dict) else None
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _patient_id(subject: Any) -> str | None:
    if not isinstance(subject, dict):
        return None
    reference = subject.get("reference")
    if reference:
        return str(reference).rstrip("/").split("/")[-1]
    identifier = subject.get("identifier") or {}
    if not isinstance(identifier, dict):
        return None
    value = identifier.get("value")
    return str(value) if value else None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number
