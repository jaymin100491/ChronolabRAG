from chronolab_rag.generation.explainer import render_mock_summary
from chronolab_rag.generation.safety_verifier import (
    extract_numbers,
    flesch_kincaid_grade,
    verify_summary,
)
from chronolab_rag.pipeline import explain_timeline
from chronolab_rag.retrieval.retriever import retrieve_for_timeline
from chronolab_rag.schemas import PatientLabTimeline
from chronolab_rag.temporal.trend_engine import compute_trends


def _audit(timeline: PatientLabTimeline, summary: str):
    return verify_summary(
        summary,
        timeline,
        compute_trends(timeline),
        retrieve_for_timeline(timeline),
    )


def test_mock_explanation_passes_the_audit(rising_glucose: PatientLabTimeline) -> None:
    verified = explain_timeline(rising_glucose, provider="mock")
    assert verified.safety_audit_passed, verified.audit_flags
    assert verified.citations == ["REF-GLUCOSE"]
    assert "30" in verified.summary_text
    assert "37.5" in verified.summary_text
    assert isinstance(verified.reading_grade_level, float)


def test_invented_number_is_flagged(rising_glucose: PatientLabTimeline) -> None:
    summary = render_mock_summary(compute_trends(rising_glucose), retrieve_for_timeline(rising_glucose))
    poisoned = summary + " The extra value was 999 mg/dL [REF-GLUCOSE]."
    verified = _audit(rising_glucose, poisoned)
    assert verified.safety_audit_passed is False
    assert any(flag.startswith("numeric_hallucination:999") for flag in verified.audit_flags)


def test_missing_citation_is_flagged(rising_glucose: PatientLabTimeline) -> None:
    summary = render_mock_summary(compute_trends(rising_glucose), retrieve_for_timeline(rising_glucose))
    stripped = summary.replace("[REF-GLUCOSE]", "")
    verified = _audit(rising_glucose, stripped)
    assert any(flag.startswith("missing_citation:") for flag in verified.audit_flags)


def test_unknown_citation_is_flagged(rising_glucose: PatientLabTimeline) -> None:
    summary = render_mock_summary(compute_trends(rising_glucose), retrieve_for_timeline(rising_glucose))
    swapped = summary.replace("[REF-GLUCOSE]", "[NOT-A-SOURCE]")
    verified = _audit(rising_glucose, swapped)
    assert any(flag.startswith("unknown_citation:NOT-A-SOURCE") for flag in verified.audit_flags)


def test_dates_are_not_treated_as_results() -> None:
    assert extract_numbers("On 2024-01-02 the value was 5.5 percent.") == [5.5]


def test_reading_grade_is_numeric() -> None:
    grade = flesch_kincaid_grade("The cat sat. The dog ran.")
    assert isinstance(grade, float)
