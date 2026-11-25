"""Inline Synthea FHIR bundles and MIMIC-IV CSV rows for the external loaders."""

import json
from pathlib import Path

import pytest

from benchmark.metrics import load_cases
from benchmark.prepare_external_data import default_output, main, prepare_synthea
from chronolab_rag.parsers.fhir_bundle import parse_fhir_bundle
from chronolab_rag.parsers.mimic_loader import load_mimic_directory, load_mimic_timelines
from chronolab_rag.pipeline import timeline_from_payload
from chronolab_rag.temporal.unit_normalizer import GLUCOSE_MGDL_PER_MMOLL

_LABEVENTS = """\
subject_id,hadm_id,itemid,charttime,value,valuenum,valueuom,ref_range_lower,ref_range_upper
1001,10,50809,2180-01-01 08:00:00,90,90,mg/dL,,
1001,10,50912,2180-01-01 08:00:00,1.0,1.0,mg/dL,0.5,1.1
1001,10,50809,2180-02-01 08:00:00,110,110,mg/dL,,
1001,11,50912,2180-04-01 08:00:00,1.2,1.2,mg/dL,0.5,1.1
1001,11,99999,2180-04-02 08:00:00,4,4,mEq/L,,
1002,20,50809,2180-03-01 08:00:00,95,95,mg/dL,,
1003,30,50809,2180-01-01 08:00:00,80,80,apples,,
1003,30,50809,2180-02-01 08:00:00,81,81,apples,,
"""

_LABITEMS = """\
itemid,label,fluid,category,loinc_code
50809,Glucose,Blood,Chemistry,2345-7
50912,Creatinine,Blood,Chemistry,2160-0
99999,Potassium,Blood,Chemistry,2823-3
"""

_PREMAPPED = """\
subject_id,charttime,loinc_code,label,valuenum,valueuom,ref_range_lower,ref_range_upper
7,2180-01-01 00:00:00,718-7,Hemoglobin,13.0,g/dL,,
7,2180-06-01 00:00:00,718-7,Hemoglobin,14.2,g/dL,,
8,2180-01-01 00:00:00,1234-5,Other,1,mg/dL,,
8,2180-02-01 00:00:00,1234-5,Other,2,mg/dL,,
"""


def _coding(code: str, display: str, system: str = "http://loinc.org") -> dict:
    return {"system": system, "code": code, "display": display}


def _observation(
    code: str,
    value: object,
    when: str,
    *,
    patient: str = "Patient/synth-1",
    unit: str = "mg/dL",
    display: str = "Glucose",
    system: str = "http://loinc.org",
    reference: list | None = None,
    value_key: str = "valueQuantity",
) -> dict:
    resource: dict = {
        "resourceType": "Observation",
        "status": "final",
        "subject": {"reference": patient},
        "code": {"text": display, "coding": [_coding(code, display, system)]},
        "effectiveDateTime": when,
    }
    if value_key == "valueQuantity":
        resource["valueQuantity"] = {"value": value, "unit": unit, "code": unit}
    else:
        resource[value_key] = value
    if reference is not None:
        resource["referenceRange"] = reference
    return {"fullUrl": f"urn:uuid:{code}-{when}", "resource": resource, "request": {"method": "POST", "url": "Observation"}}


def _synthea_bundle() -> dict:
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "synth-1",
                    "name": [{"family": "Example", "given": ["A"]}],
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "enc-1",
                    "subject": {"reference": "Patient/synth-1"},
                    "period": {"start": "2020-01-01T08:00:00Z"},
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "code": {"text": "Prediabetes"},
                    "subject": {"reference": "Patient/synth-1"},
                }
            },
            _observation("2339-0", 5.0, "2020-01-01T08:00:00Z", unit="mmol/L", display="Glucose"),
            _observation("8302-2", 170, "2020-01-01T08:05:00Z", unit="cm", display="Body Height"),
            _observation(
                "2345-7",
                "yellow",
                "2020-01-01T08:06:00Z",
                value_key="valueString",
                display="Glucose",
            ),
            _observation("2345-7", 110, "2020-06-01T08:00:00Z", display="Glucose"),
            _observation("1742-6", 22, "2020-06-01T08:10:00Z", unit="U/L", display="ALT"),
            _observation(
                "2160-0",
                1.1,
                "2020-06-01T08:20:00Z",
                unit="mg/dL",
                display="Creatinine",
                reference=[{"low": {"value": 0.4}, "high": {"value": 1.2}}],
            ),
        ],
    }


def test_synthea_bundle_keeps_supported_numeric_labs_and_fills_ranges() -> None:
    timeline = parse_fhir_bundle(_synthea_bundle())
    assert timeline.patient_id == "synth-1"
    codes = [item.loinc_code for item in timeline.observations]
    assert codes == ["2339-0", "2345-7", "1742-6", "2160-0"]
    glucose = timeline.observations[0]
    assert glucose.value == 5.0
    assert glucose.unit == "mmol/L"
    assert glucose.reference_low == pytest.approx(70 / GLUCOSE_MGDL_PER_MMOLL)
    assert glucose.reference_high == pytest.approx(99 / GLUCOSE_MGDL_PER_MMOLL)
    assert timeline.observations[1].reference_low == 70
    assert timeline.observations[1].reference_high == 99
    assert timeline.observations[2].reference_low == 7
    assert timeline.observations[2].reference_high == 56
    creatinine = timeline.observations[3]
    assert creatinine.reference_low == 0.4
    assert creatinine.reference_high == 1.2


def test_mimic_join_groups_by_subject_and_requires_two_results(tmp_path: Path) -> None:
    (tmp_path / "labevents.csv").write_text(_LABEVENTS, encoding="utf-8")
    (tmp_path / "d_labitems.csv").write_text(_LABITEMS, encoding="utf-8")
    timelines = load_mimic_directory(tmp_path)
    assert [item.patient_id for item in timelines] == ["1001"]
    observations = timelines[0].observations
    assert [(item.loinc_code, item.value, item.timestamp.month) for item in observations] == [
        ("2345-7", 90.0, 1),
        ("2160-0", 1.0, 1),
        ("2345-7", 110.0, 2),
        ("2160-0", 1.2, 4),
    ]
    assert observations[0].test_name == "Glucose"
    assert observations[0].reference_low == 70
    assert observations[0].reference_high == 99
    assert observations[1].reference_low == 0.5
    assert observations[1].reference_high == 1.1


def test_mimic_pre_mapped_loinc_does_not_need_a_dictionary(tmp_path: Path) -> None:
    labevents = tmp_path / "labevents.csv"
    labevents.write_text(_PREMAPPED, encoding="utf-8")
    timelines = load_mimic_timelines(labevents)
    assert len(timelines) == 1
    assert timelines[0].patient_id == "7"
    assert [item.value for item in timelines[0].observations] == [13.0, 14.2]
    assert timelines[0].observations[0].reference_low == 12.0
    assert timelines[0].observations[0].reference_high == 17.5


def test_prepare_synthea_writes_benchmark_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "synthea_1k"
    source.mkdir()
    (source / "Patient_A.json").write_text(json.dumps(_synthea_bundle()), encoding="utf-8")
    (source / "not-a-bundle.json").write_text(json.dumps({"resourceType": "Patient"}), encoding="utf-8")
    single = _synthea_bundle()
    single["entry"] = [
        entry
        for entry in single["entry"]
        if entry["resource"].get("resourceType") != "Observation"
        or entry["resource"]["code"]["coding"][0]["code"] == "1742-6"
    ]
    (source / "fhir" / "lonely.json").parent.mkdir()
    (source / "fhir" / "lonely.json").write_text(json.dumps(single), encoding="utf-8")
    output = tmp_path / "external_synthea.jsonl"
    assert prepare_synthea(source, output) == 1
    cases = load_cases(output)
    timeline = timeline_from_payload(cases[0])
    assert timeline.patient_id == "synth-1"
    assert [item.loinc_code for item in timeline.observations] == [
        "2339-0",
        "2345-7",
        "1742-6",
        "2160-0",
    ]
    assert set(cases[0]["observations"][0]) >= {
        "loinc_code",
        "test_name",
        "value",
        "unit",
        "reference_low",
        "reference_high",
        "timestamp",
    }


def test_prepare_cli_accepts_synthea_and_mimic_dirs(tmp_path: Path) -> None:
    synthea = tmp_path / "synthea_1k"
    synthea.mkdir()
    (synthea / "bundle.json").write_text(json.dumps(_synthea_bundle()), encoding="utf-8")
    synthea_out = tmp_path / "external_synthea.jsonl"
    assert main(["--synthea-dir", str(synthea), "--output", str(synthea_out)]) == 0
    assert load_cases(synthea_out)[0]["patient_id"] == "synth-1"

    mimic = tmp_path / "mimic_iv"
    mimic.mkdir()
    (mimic / "labevents.csv").write_text(_LABEVENTS, encoding="utf-8")
    (mimic / "d_labitems.csv").write_text(_LABITEMS, encoding="utf-8")
    mimic_out = tmp_path / "external_mimic.jsonl"
    assert main(["--mimic-dir", str(mimic), "--output", str(mimic_out)]) == 0
    assert load_cases(mimic_out)[0]["patient_id"] == "1001"
    assert main(["--synthea-dir", str(tmp_path / "missing")]) == 2


def test_default_external_jsonl_names() -> None:
    assert default_output("synthea").name == "external_synthea.jsonl"
    assert default_output("mimic").name == "external_mimic.jsonl"
