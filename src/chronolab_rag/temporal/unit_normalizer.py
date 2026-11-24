"""Deterministic unit conversion for twelve common laboratory panels.

Factors are public clinical constants:

- glucose: 18.0182 mg/dL per mmol/L
- creatinine: 88.4 umol/L per mg/dL
- cholesterol (LDL and HDL): 38.67 mg/dL per mmol/L
- triglycerides: 88.57 mg/dL per mmol/L
- hemoglobin: 10 g/L per g/dL
- HbA1c NGSP/IFCC: mmol/mol = (percent - 2.15) x 10.929

Reference intervals on each panel are illustrative teaching bands for synthetic
data. They are not diagnostic cutoffs.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from chronolab_rag.schemas import LabObservation

GLUCOSE_MGDL_PER_MMOLL = 18.0182
CREATININE_UMOLL_PER_MGDL = 88.4
CHOLESTEROL_MGDL_PER_MMOLL = 38.67
TRIGLYCERIDE_MGDL_PER_MMOLL = 88.57
HBA1C_SLOPE = 10.929
HBA1C_INTERCEPT = 2.15
HEMOGLOBIN_GL_PER_GDL = 10.0


class UnitConversionError(ValueError):
    """Raised when a value cannot be placed on a single unit scale."""


@dataclass(frozen=True)
class UnitConverter:
    to_canonical: Callable[[float], float]
    from_canonical: Callable[[float], float]


@dataclass(frozen=True)
class Panel:
    key: str
    test_name: str
    canonical_loinc: str
    loinc_codes: tuple[str, ...]
    canonical_unit: str
    reference_low: float
    reference_high: float
    aliases: tuple[str, ...]
    converters: dict[str, UnitConverter]


def _identity(value: float) -> float:
    return value


_IDENTITY = UnitConverter(_identity, _identity)


def _scale(to_canonical_factor: float) -> UnitConverter:
    factor = to_canonical_factor

    def to_canonical(value: float) -> float:
        return value * factor

    def from_canonical(value: float) -> float:
        return value / factor

    return UnitConverter(to_canonical, from_canonical)


def _hba1c_mmol_mol() -> UnitConverter:
    def to_percent(value: float) -> float:
        return value / HBA1C_SLOPE + HBA1C_INTERCEPT

    def from_percent(value: float) -> float:
        return (value - HBA1C_INTERCEPT) * HBA1C_SLOPE

    return UnitConverter(to_percent, from_percent)


_UNIT_ALIASES = {
    "mg/dl": "mg/dL",
    "mmol/l": "mmol/L",
    "g/dl": "g/dL",
    "g/l": "g/L",
    "uiu/ml": "uIU/mL",
    "uu/ml": "uIU/mL",
    "miu/l": "mIU/L",
    "miu/ml": "mIU/L",
    "%": "%",
    "percent": "%",
    "mmol/mol": "mmol/mol",
    "umol/l": "umol/L",
    "10*3/ul": "10^3/uL",
    "10^3/ul": "10^3/uL",
    "10e3/ul": "10^3/uL",
    "10**3/ul": "10^3/uL",
    "x10^3/ul": "10^3/uL",
    "k/ul": "10^3/uL",
    "thou/ul": "10^3/uL",
    "10*9/l": "10^9/L",
    "10^9/l": "10^9/L",
    "10e9/l": "10^9/L",
    "u/l": "U/L",
    "iu/l": "IU/L",
    "ml/min/1.73m2": "mL/min/1.73m2",
    "ml/min/1.73m^2": "mL/min/1.73m2",
    "ml/min/{1.73_m2}": "mL/min/1.73m2",
}


def canonicalize_unit_label(unit: str) -> str:
    """Fold common spellings onto one label. The numeric scale is unchanged."""

    compact = re.sub(r"\s+", "", unit.strip())
    compact = compact.replace("µ", "u").replace("μ", "u")
    key = compact.lower()
    if key not in _UNIT_ALIASES:
        raise UnitConversionError(f"Unsupported unit: {unit}")
    return _UNIT_ALIASES[key]


def _panel(
    key: str,
    test_name: str,
    canonical_loinc: str,
    loinc_codes: tuple[str, ...],
    canonical_unit: str,
    reference_low: float,
    reference_high: float,
    aliases: tuple[str, ...],
    converters: dict[str, UnitConverter],
) -> Panel:
    return Panel(
        key=key,
        test_name=test_name,
        canonical_loinc=canonical_loinc,
        loinc_codes=loinc_codes,
        canonical_unit=canonical_unit,
        reference_low=reference_low,
        reference_high=reference_high,
        aliases=aliases,
        converters=converters,
    )


def _build_panels() -> tuple[Panel, ...]:
    return (
        _panel(
            "glucose",
            "Glucose",
            "2345-7",
            ("2345-7", "2339-0", "14749-6"),
            "mg/dL",
            70.0,
            99.0,
            ("glucose", "fasting glucose", "blood glucose"),
            {"mg/dL": _IDENTITY, "mmol/L": _scale(GLUCOSE_MGDL_PER_MMOLL)},
        ),
        _panel(
            "hba1c",
            "HbA1c",
            "4548-4",
            ("4548-4", "59261-8"),
            "%",
            4.0,
            5.6,
            ("hba1c", "hemoglobin a1c", "a1c", "glycated hemoglobin"),
            {"%": _IDENTITY, "mmol/mol": _hba1c_mmol_mol()},
        ),
        _panel(
            "creatinine",
            "Creatinine",
            "2160-0",
            ("2160-0", "14682-9"),
            "mg/dL",
            0.6,
            1.3,
            ("creatinine",),
            {"mg/dL": _IDENTITY, "umol/L": _scale(1.0 / CREATININE_UMOLL_PER_MGDL)},
        ),
        _panel(
            "egfr",
            "eGFR",
            "33914-3",
            ("33914-3",),
            "mL/min/1.73m2",
            60.0,
            120.0,
            ("egfr", "estimated glomerular filtration rate", "gfr"),
            {"mL/min/1.73m2": _IDENTITY},
        ),
        _panel(
            "ldl",
            "LDL Cholesterol",
            "2089-1",
            ("2089-1", "13457-7"),
            "mg/dL",
            0.0,
            100.0,
            ("ldl", "ldl cholesterol", "ldl-c"),
            {"mg/dL": _IDENTITY, "mmol/L": _scale(CHOLESTEROL_MGDL_PER_MMOLL)},
        ),
        _panel(
            "hdl",
            "HDL Cholesterol",
            "2085-9",
            ("2085-9",),
            "mg/dL",
            40.0,
            60.0,
            ("hdl", "hdl cholesterol", "hdl-c"),
            {"mg/dL": _IDENTITY, "mmol/L": _scale(CHOLESTEROL_MGDL_PER_MMOLL)},
        ),
        _panel(
            "triglycerides",
            "Triglycerides",
            "2571-8",
            ("2571-8", "14927-8"),
            "mg/dL",
            0.0,
            150.0,
            ("triglycerides", "triglyceride", "trigs"),
            {"mg/dL": _IDENTITY, "mmol/L": _scale(TRIGLYCERIDE_MGDL_PER_MMOLL)},
        ),
        _panel(
            "tsh",
            "TSH",
            "3016-3",
            ("3016-3",),
            "uIU/mL",
            0.4,
            4.0,
            ("tsh", "thyroid stimulating hormone", "thyrotropin"),
            {"uIU/mL": _IDENTITY, "mIU/L": _IDENTITY},
        ),
        _panel(
            "hemoglobin",
            "Hemoglobin",
            "718-7",
            ("718-7",),
            "g/dL",
            12.0,
            17.5,
            ("hemoglobin", "hgb", "hb"),
            {"g/dL": _IDENTITY, "g/L": _scale(1.0 / HEMOGLOBIN_GL_PER_GDL)},
        ),
        _panel(
            "wbc",
            "WBC",
            "6690-2",
            ("6690-2",),
            "10^3/uL",
            4.5,
            11.0,
            ("wbc", "white blood cell", "white blood cells", "leukocytes"),
            {"10^3/uL": _IDENTITY, "10^9/L": _IDENTITY},
        ),
        _panel(
            "alt",
            "ALT",
            "1742-6",
            ("1742-6",),
            "U/L",
            7.0,
            56.0,
            ("alt", "alanine aminotransferase", "sgpt"),
            {"U/L": _IDENTITY, "IU/L": _IDENTITY},
        ),
        _panel(
            "ast",
            "AST",
            "1920-8",
            ("1920-8",),
            "U/L",
            10.0,
            40.0,
            ("ast", "aspartate aminotransferase", "sgot"),
            {"U/L": _IDENTITY, "IU/L": _IDENTITY},
        ),
    )


PANELS: tuple[Panel, ...] = _build_panels()
_BY_LOINC: dict[str, Panel] = {}
for _panel_item in PANELS:
    for _code in _panel_item.loinc_codes:
        _BY_LOINC[_code] = _panel_item


def list_panels() -> tuple[Panel, ...]:
    return PANELS


def resolve_panel(loinc_code: str | None, test_name: str | None = None) -> Panel:
    if loinc_code and loinc_code in _BY_LOINC:
        return _BY_LOINC[loinc_code]
    if test_name:
        matched = _match_name(test_name)
        if matched is not None:
            return matched
    raise UnitConversionError(
        f"Unknown lab panel for loinc={loinc_code!r} test_name={test_name!r}"
    )


def _match_name(test_name: str) -> Panel | None:
    lowered = test_name.strip().lower()
    best: Panel | None = None
    best_length = -1
    for panel in PANELS:
        for alias in panel.aliases:
            if alias == lowered or re.search(rf"\b{re.escape(alias)}\b", lowered):
                if len(alias) > best_length:
                    best = panel
                    best_length = len(alias)
    return best


def convert(
    value: float,
    from_unit: str,
    to_unit: str,
    *,
    loinc_code: str | None = None,
    test_name: str | None = None,
) -> float:
    """Convert ``value`` between two units of the same panel."""

    source = canonicalize_unit_label(from_unit)
    target = canonicalize_unit_label(to_unit)
    if loinc_code or test_name:
        panel = resolve_panel(loinc_code, test_name)
        return _convert(panel, value, source, target)

    candidates = [
        panel
        for panel in PANELS
        if source in panel.converters and target in panel.converters
    ]
    if not candidates:
        raise UnitConversionError(f"Unsupported conversion from {from_unit} to {to_unit}")
    converted = [_convert(panel, value, source, target) for panel in candidates]
    first = converted[0]
    if all(abs(item - first) <= 1e-9 for item in converted[1:]):
        return first
    raise UnitConversionError(
        "Ambiguous conversion. Provide loinc_code or test_name so the molar factor is known."
    )


def _convert(panel: Panel, value: float, source: str, target: str) -> float:
    if source not in panel.converters or target not in panel.converters:
        raise UnitConversionError(
            f"Cannot convert {panel.test_name} from {source} to {target}"
        )
    canonical = panel.converters[source].to_canonical(value)
    return panel.converters[target].from_canonical(canonical)


def normalize_observation(observation: LabObservation) -> LabObservation:
    """Return a copy of ``observation`` expressed in the panel's canonical unit."""

    panel = resolve_panel(observation.loinc_code, observation.test_name)
    source = canonicalize_unit_label(observation.unit)
    return observation.model_copy(
        update={
            "test_name": panel.test_name,
            "value": _convert(panel, observation.value, source, panel.canonical_unit),
            "unit": panel.canonical_unit,
            "reference_low": _convert_bound(panel, observation.reference_low, source),
            "reference_high": _convert_bound(panel, observation.reference_high, source),
        }
    )


def _convert_bound(panel: Panel, bound: float | None, source: str) -> float | None:
    if bound is None:
        return None
    return _convert(panel, bound, source, panel.canonical_unit)
