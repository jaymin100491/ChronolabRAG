import pytest

from chronolab_rag.parsers.fhir_bundle import parse_fhir_bundle
from chronolab_rag.parsers.simple_json import parse_simple_json


def _glucose_observation(value: float, when: str, patient: str = "Patient/SYN-FHIR") -> dict:
    return {
        "resource": {
            "resourceType": "Observation",
            "subject": {"reference": patient},
            "code": {
                "text": "Glucose",
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "2345-7",
                        "display": "Glucose [Mass/volume] in Serum or Plasma",
                    }
                ],
            },
            "valueQuantity": {"value": value, "unit": "mg/dL"},
            "referenceRange": [{"low": {"value": 70}, "high": {"value": 99}}],
            "effectiveDateTime": when,
        }
    }


def test_fhir_bundle_parses_numeric_observations() -> None:
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "DiagnosticReport"}},
            _glucose_observation(90, "2024-01-01T08:00:00Z"),
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "2345-7"}]},
                    "valueString": "yellow",
                }
            },
            _glucose_observation(110, "2024-01-11T08:00:00Z"),
        ],
    }
    timeline = parse_fhir_bundle(bundle)
    assert timeline.patient_id == "SYN-FHIR"
    assert len(timeline.observations) == 2
    assert timeline.observations[1].value == 110
    assert timeline.observations[0].reference_low == 70


def test_fhir_bundle_rejects_mixed_patients() -> None:
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            _glucose_observation(90, "2024-01-01T08:00:00Z", "Patient/SYN-A"),
            _glucose_observation(91, "2024-02-01T08:00:00Z", "Patient/SYN-B"),
        ],
    }
    with pytest.raises(ValueError, match="more than one patient"):
        parse_fhir_bundle(bundle)


def test_simple_json_array_and_object() -> None:
    rows = [
        {
            "patient_id": "SYN-JSON",
            "loinc_code": "2345-7",
            "test_name": "Glucose",
            "value": 90,
            "unit": "mg/dL",
            "reference_low": 70,
            "reference_high": 99,
            "timestamp": "2024-01-01T08:00:00+00:00",
        }
    ]
    from_array = parse_simple_json(rows)
    from_object = parse_simple_json({"patient_id": "SYN-JSON", "observations": rows})
    assert from_array.patient_id == "SYN-JSON"
    assert from_object.observations[0].value == 90


def test_simple_json_rejects_mixed_patients() -> None:
    rows = [
        {
            "patient_id": "SYN-A",
            "loinc_code": "2345-7",
            "test_name": "Glucose",
            "value": 90,
            "unit": "mg/dL",
            "timestamp": "2024-01-01T00:00:00Z",
        },
        {
            "patient_id": "SYN-B",
            "loinc_code": "2345-7",
            "test_name": "Glucose",
            "value": 91,
            "unit": "mg/dL",
            "timestamp": "2024-02-01T00:00:00Z",
        },
    ]
    with pytest.raises(ValueError, match="more than one patient"):
        parse_simple_json(rows)
