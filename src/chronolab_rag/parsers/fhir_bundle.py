"""Parse a single-patient HL7 FHIR R4 Bundle of Observation resources."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from chronolab_rag.schemas import LabObservation, PatientLabTimeline


def parse_fhir_bundle(payload: Any) -> PatientLabTimeline:
    """Convert a FHIR R4 Bundle of numeric Observations into a timeline.

    Qualitative observations and entries that are not Observations are skipped.
    A bundle that mixes more than one patient is rejected.
    """

    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict) or payload.get("resourceType") != "Bundle":
        raise ValueError("Expected a FHIR R4 Bundle")

    observations: list[LabObservation] = []
    patient_ids: list[str] = []
    for entry in payload.get("entry") or []:
        resource = (entry or {}).get("resource") or {}
        if resource.get("resourceType") != "Observation":
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
    quantity = resource.get("valueQuantity")
    if not isinstance(quantity, dict) or quantity.get("value") is None:
        return None
    loinc_code, display = _loinc(resource.get("code") or {})
    if loinc_code is None:
        raise ValueError("Numeric Observation is missing a LOINC code")
    low, high = _reference_range(resource.get("referenceRange"))
    timestamp = _timestamp(resource)
    test_name = (resource.get("code") or {}).get("text") or display or loinc_code
    unit = quantity.get("unit") or quantity.get("code")
    if not unit:
        raise ValueError(f"Observation {loinc_code} is missing a unit")
    observation = LabObservation(
        loinc_code=loinc_code,
        test_name=str(test_name),
        value=float(quantity["value"]),
        unit=str(unit),
        reference_low=low,
        reference_high=high,
        timestamp=timestamp,
    )
    return observation, _patient_id(resource.get("subject") or {})


def _loinc(code: dict[str, Any]) -> tuple[str | None, str | None]:
    for coding in code.get("coding") or []:
        system = str(coding.get("system") or "")
        if "loinc.org" in system.lower():
            return str(coding.get("code")), coding.get("display")
    return None, None


def _reference_range(ranges: Any) -> tuple[float | None, float | None]:
    if not ranges:
        return None, None
    first = ranges[0] or {}
    low = (first.get("low") or {}).get("value")
    high = (first.get("high") or {}).get("value")
    return (float(low) if low is not None else None, float(high) if high is not None else None)


def _timestamp(resource: dict[str, Any]) -> datetime:
    raw = resource.get("effectiveDateTime") or resource.get("issued")
    if raw is None:
        period = resource.get("effectivePeriod") or {}
        raw = period.get("start")
    if not raw:
        raise ValueError("Observation is missing effectiveDateTime")
    text = str(raw).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _patient_id(subject: dict[str, Any]) -> str | None:
    reference = subject.get("reference")
    if reference:
        return str(reference).rstrip("/").split("/")[-1]
    identifier = subject.get("identifier") or {}
    value = identifier.get("value")
    return str(value) if value else None
