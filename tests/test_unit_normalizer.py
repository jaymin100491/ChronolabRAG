import pytest

from chronolab_rag.temporal.unit_normalizer import (
    CHOLESTEROL_MGDL_PER_MMOLL,
    CREATININE_UMOLL_PER_MGDL,
    GLUCOSE_MGDL_PER_MMOLL,
    HBA1C_INTERCEPT,
    HBA1C_SLOPE,
    HEMOGLOBIN_GL_PER_GDL,
    TRIGLYCERIDE_MGDL_PER_MMOLL,
    UnitConversionError,
    convert,
    list_panels,
    normalize_observation,
)
from tests.conftest import observation


def test_twelve_panels_are_registered() -> None:
    assert len(list_panels()) == 12


@pytest.mark.parametrize("panel", list_panels(), ids=lambda panel: panel.key)
def test_non_canonical_units_round_trip(panel) -> None:
    for unit in panel.converters:
        if unit == panel.canonical_unit:
            continue
        canonical = convert(25.0, unit, panel.canonical_unit, loinc_code=panel.canonical_loinc)
        restored = convert(canonical, panel.canonical_unit, unit, loinc_code=panel.canonical_loinc)
        assert restored == pytest.approx(25.0)


def test_glucose_molar_factor() -> None:
    assert convert(10, "mmol/L", "mg/dL", test_name="Glucose") == pytest.approx(
        10 * GLUCOSE_MGDL_PER_MMOLL
    )
    assert convert(180.182, "mg/dL", "mmol/L", loinc_code="2345-7") == pytest.approx(10)


def test_hba1c_ifcc_equation() -> None:
    expected = (6.5 - HBA1C_INTERCEPT) * HBA1C_SLOPE
    assert convert(6.5, "%", "mmol/mol", test_name="HbA1c") == pytest.approx(expected)
    assert convert(expected, "mmol/mol", "%", loinc_code="59261-8") == pytest.approx(6.5)


def test_creatinine_hemoglobin_and_lipids() -> None:
    assert convert(1, "mg/dL", "umol/L", test_name="Creatinine") == pytest.approx(
        CREATININE_UMOLL_PER_MGDL
    )
    assert convert(14, "g/dL", "g/L", test_name="Hemoglobin") == pytest.approx(
        14 * HEMOGLOBIN_GL_PER_GDL
    )
    assert convert(100, "mg/dL", "mmol/L", test_name="LDL Cholesterol") == pytest.approx(
        100 / CHOLESTEROL_MGDL_PER_MMOLL
    )
    assert convert(150, "mg/dL", "mmol/L", test_name="Triglycerides") == pytest.approx(
        150 / TRIGLYCERIDE_MGDL_PER_MMOLL
    )


def test_identity_units() -> None:
    assert convert(2.5, "uIU/mL", "mIU/L", test_name="TSH") == pytest.approx(2.5)
    assert convert(8, "10^3/uL", "10*9/L", test_name="WBC") == pytest.approx(8)
    assert convert(30, "U/L", "IU/L", test_name="ALT") == pytest.approx(30)
    assert convert(90, "mL/min/{1.73_m2}", "mL/min/1.73m2", test_name="eGFR") == pytest.approx(90)


def test_ambiguous_mass_to_molar_conversion_requires_a_test() -> None:
    with pytest.raises(UnitConversionError):
        convert(100, "mg/dL", "mmol/L")


def test_normalize_observation_converts_the_reference_range() -> None:
    raw = observation(
        5.5,
        1,
        unit="mmol/L",
        reference_low=70 / GLUCOSE_MGDL_PER_MMOLL,
        reference_high=99 / GLUCOSE_MGDL_PER_MMOLL,
    )
    normalized = normalize_observation(raw)
    assert normalized.unit == "mg/dL"
    assert normalized.value == pytest.approx(5.5 * GLUCOSE_MGDL_PER_MMOLL)
    assert normalized.reference_low == pytest.approx(70)
    assert normalized.reference_high == pytest.approx(99)


def test_unknown_unit_is_rejected() -> None:
    with pytest.raises(UnitConversionError):
        convert(1, "furlongs", "mg/dL", test_name="Glucose")
