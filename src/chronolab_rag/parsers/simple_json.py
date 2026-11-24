"""Parse plain JSON timelines into ``PatientLabTimeline``."""

from __future__ import annotations

import json
from typing import Any

from chronolab_rag.schemas import LabObservation, PatientLabTimeline

_OBSERVATION_FIELDS = {
    "loinc_code",
    "test_name",
    "value",
    "unit",
    "reference_low",
    "reference_high",
    "timestamp",
}


def parse_simple_json(payload: Any, *, patient_id: str | None = None) -> PatientLabTimeline:
    """Parse a timeline object or a JSON array of lab rows.

    Array rows may include ``patient_id``. Every row in one call must belong to
    the same patient. A bare array without ids uses ``patient_id`` or ``"unknown"``.
    """

    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict) and "observations" in payload:
        resolved_id = str(patient_id or payload.get("patient_id") or "unknown")
        observations = [_observation(row) for row in payload["observations"]]
        return PatientLabTimeline(patient_id=resolved_id, observations=observations)
    if isinstance(payload, list):
        return _from_rows(payload, patient_id)
    raise ValueError("Expected a JSON object with observations or a JSON array of lab rows")


def _from_rows(rows: list[Any], patient_id: str | None) -> PatientLabTimeline:
    found_ids: list[str] = []
    observations: list[LabObservation] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each lab row must be a JSON object")
        if row.get("patient_id"):
            found_ids.append(str(row["patient_id"]))
        observations.append(_observation(row))
    unique_ids = list(dict.fromkeys(found_ids))
    if len(unique_ids) > 1:
        raise ValueError("JSON array contains more than one patient_id")
    if patient_id:
        resolved_id = patient_id
    elif unique_ids:
        resolved_id = unique_ids[0]
    else:
        resolved_id = "unknown"
    return PatientLabTimeline(patient_id=resolved_id, observations=observations)


def _observation(row: dict[str, Any]) -> LabObservation:
    if not isinstance(row, dict):
        raise ValueError("Each lab row must be a JSON object")
    data = {key: value for key, value in row.items() if key in _OBSERVATION_FIELDS}
    return LabObservation.model_validate(data)
