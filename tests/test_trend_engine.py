import pytest

from chronolab_rag.schemas import PatientLabTimeline
from chronolab_rag.temporal.trend_engine import compute_trends
from chronolab_rag.temporal.unit_normalizer import GLUCOSE_MGDL_PER_MMOLL, convert
from tests.conftest import observation


def test_delta_percent_velocity_and_status(rising_glucose: PatientLabTimeline) -> None:
    trend = compute_trends(rising_glucose)[0]
    assert trend.delta == pytest.approx(30)
    assert trend.percent_change == pytest.approx(37.5)
    assert trend.velocity_per_day == pytest.approx(3)
    assert trend.status_transition == "Normal->High"
    assert trend.normalized_unit == "mg/dL"
    assert trend.baseline_value == pytest.approx(80)
    assert trend.latest_value == pytest.approx(110)
    assert trend.observation_count == 2


def test_unit_flip_uses_the_aligned_scale() -> None:
    mmol = convert(95, "mg/dL", "mmol/L", loinc_code="2345-7")
    low = convert(70, "mg/dL", "mmol/L", loinc_code="2345-7")
    high = convert(99, "mg/dL", "mmol/L", loinc_code="2345-7")
    timeline = PatientLabTimeline(
        patient_id="SYN-FLIP",
        observations=[
            observation(90, 1),
            observation(
                mmol,
                11,
                unit="mmol/L",
                reference_low=low,
                reference_high=high,
                loinc_code="14749-6",
            ),
        ],
    )
    trend = compute_trends(timeline)[0]
    assert trend.delta == pytest.approx(5)
    assert trend.normalized_unit == "mg/dL"
    assert trend.loinc_code == "2345-7"
    assert trend.latest_value == pytest.approx(95)
    assert mmol * GLUCOSE_MGDL_PER_MMOLL == pytest.approx(95)


def test_single_visit_has_no_change() -> None:
    timeline = PatientLabTimeline(patient_id="SYN-ONE", observations=[observation(88, 1)])
    trend = compute_trends(timeline)[0]
    assert trend.delta == 0
    assert trend.percent_change == 0
    assert trend.velocity_per_day == 0
    assert trend.status_transition == "Normal->Normal"


def test_low_to_normal_creatinine() -> None:
    timeline = PatientLabTimeline(
        patient_id="SYN-CREAT",
        observations=[
            observation(
                0.4,
                1,
                loinc_code="2160-0",
                test_name="Creatinine",
                reference_low=0.6,
                reference_high=1.3,
            ),
            observation(
                0.8,
                11,
                loinc_code="2160-0",
                test_name="Creatinine",
                reference_low=0.6,
                reference_high=1.3,
            ),
        ],
    )
    trend = compute_trends(timeline)[0]
    assert trend.status_transition == "Low->Normal"
    assert trend.percent_change == pytest.approx(100)


def test_zero_baseline_percent_is_defined() -> None:
    timeline = PatientLabTimeline(
        patient_id="SYN-ZERO",
        observations=[
            observation(0, 1, loinc_code="2089-1", test_name="LDL Cholesterol", reference_low=0, reference_high=100),
            observation(10, 11, loinc_code="2089-1", test_name="LDL Cholesterol", reference_low=0, reference_high=100),
        ],
    )
    trend = compute_trends(timeline)[0]
    assert trend.percent_change == 0
    assert trend.delta == pytest.approx(10)


def test_empty_timeline() -> None:
    assert compute_trends(PatientLabTimeline(patient_id="SYN-EMPTY", observations=[])) == []
