from datetime import datetime, timezone

import pytest

from chronolab_rag.schemas import LabObservation, PatientLabTimeline


def observation(
    value: float,
    day: int,
    *,
    loinc_code: str = "2345-7",
    test_name: str = "Glucose",
    unit: str = "mg/dL",
    reference_low: float | None = 70,
    reference_high: float | None = 99,
    month: int = 1,
) -> LabObservation:
    return LabObservation(
        loinc_code=loinc_code,
        test_name=test_name,
        value=value,
        unit=unit,
        reference_low=reference_low,
        reference_high=reference_high,
        timestamp=datetime(2024, month, day, 8, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def rising_glucose() -> PatientLabTimeline:
    return PatientLabTimeline(
        patient_id="SYN-GLUCOSE",
        observations=[observation(80, 1), observation(110, 11)],
    )
