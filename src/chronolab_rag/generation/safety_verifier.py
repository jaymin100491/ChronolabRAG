"""Deterministic checks that run after a summary is written.

The verifier does three things:

1. Every number in the summary must match a trend metric or an input value.
2. Every clinical sentence must cite a source id that was actually retrieved.
3. The Flesch-Kincaid grade level is computed for the summary.
"""

from __future__ import annotations

import math
import re

from chronolab_rag.schemas import (
    PatientLabTimeline,
    RetrievedReference,
    TrendMetric,
    VerifiedExplanation,
)
from chronolab_rag.temporal.unit_normalizer import (
    UnitConversionError,
    list_panels,
    normalize_observation,
)

_DATE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?"
)
_CITATION = re.compile(r"\[([A-Za-z0-9_-]+)\]")
_NUMBER = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)%?")
_CLAIM = re.compile(
    r"\b(high|low|normal|increased|decreased|increase|decrease|rose|risen|fell|rising|falling|above|below|abnormal)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def verify_summary(
    summary_text: str,
    timeline: PatientLabTimeline,
    trends: list[TrendMetric],
    references: list[RetrievedReference],
) -> VerifiedExplanation:
    """Audit ``summary_text`` and return the explanation with flags."""

    details = audit_details(summary_text, timeline, trends, references)
    return VerifiedExplanation(
        summary_text=summary_text,
        citations=details["citations"],
        safety_audit_passed=not details["flags"],
        audit_flags=details["flags"],
        reading_grade_level=details["reading_grade_level"],
    )


def audit_details(
    summary_text: str,
    timeline: PatientLabTimeline,
    trends: list[TrendMetric],
    references: list[RetrievedReference],
) -> dict[str, object]:
    """Return numeric, citation, and readability details for one summary."""

    allowed_ids = {reference.source_id for reference in references}
    citations = _citations(summary_text)
    flags: list[str] = []
    allowed = _allowed_numbers(timeline, trends)
    extracted = extract_numbers(summary_text)
    matched = 0
    for number in extracted:
        if _matches(number, allowed):
            matched += 1
        else:
            flags.append(f"numeric_hallucination:{_show(number)}")
    test_names = [trend.test_name for trend in trends]
    for sentence in _sentences(summary_text):
        sentence_ids = _citations(sentence)
        if _needs_citation(sentence, test_names) and not sentence_ids:
            flags.append(f"missing_citation:{sentence[:80]}")
        for source_id in sentence_ids:
            if source_id not in allowed_ids:
                flags.append(f"unknown_citation:{source_id}")
    mentions = _CITATION.findall(summary_text)
    valid_mentions = sum(1 for source_id in mentions if source_id in allowed_ids)
    return {
        "citations": citations,
        "flags": flags,
        "extracted_numbers": len(extracted),
        "matched_numbers": matched,
        "citation_mentions": len(mentions),
        "valid_citation_mentions": valid_mentions,
        "reading_grade_level": flesch_kincaid_grade(summary_text),
    }


def extract_numbers(text: str) -> list[float]:
    """Pull measurement-like numbers out of prose, ignoring dates and citations."""

    cleaned = _DATE.sub(" ", text)
    cleaned = _CITATION.sub(" ", cleaned)
    for unit in _unit_labels():
        cleaned = re.sub(re.escape(unit), " ", cleaned, flags=re.IGNORECASE)
    return [float(match.group(1)) for match in _NUMBER.finditer(cleaned)]


def flesch_kincaid_grade(text: str) -> float:
    """US school-grade estimate. Very short text can score below zero."""

    words = re.findall(r"[A-Za-z0-9']+", text)
    if not words:
        return 0.0
    sentence_count = max(len(re.findall(r"[.!?]+", text)), 1)
    syllable_count = sum(_syllables(word) for word in words)
    grade = 0.39 * (len(words) / sentence_count) + 11.8 * (syllable_count / len(words)) - 15.59
    return round(grade, 2)


def _allowed_numbers(timeline: PatientLabTimeline, trends: list[TrendMetric]) -> list[float]:
    numbers: list[float] = []
    for observation in timeline.observations:
        numbers.extend(_finite(observation.value, observation.reference_low, observation.reference_high))
        try:
            normalized = normalize_observation(observation)
        except UnitConversionError:
            continue
        numbers.extend(
            _finite(normalized.value, normalized.reference_low, normalized.reference_high)
        )
    for trend in trends:
        numbers.extend(
            _finite(
                trend.delta,
                trend.percent_change,
                trend.velocity_per_day,
                trend.baseline_value,
                trend.latest_value,
                trend.reference_low,
                trend.reference_high,
                float(trend.observation_count),
            )
        )
    return numbers


def _finite(*values: float | None) -> list[float]:
    found: list[float] = []
    for value in values:
        if value is not None and math.isfinite(value):
            found.append(float(value))
            found.append(abs(float(value)))
    return found


def _matches(number: float, allowed: list[float]) -> bool:
    for candidate in allowed:
        targets = (
            candidate,
            round(candidate, 1),
            round(candidate, 2),
            round(candidate, 3),
        )
        if any(math.isclose(number, target, rel_tol=1e-9, abs_tol=1e-6) for target in targets):
            return True
    return False


def _needs_citation(sentence: str, test_names: list[str]) -> bool:
    if extract_numbers(sentence):
        return True
    if _CLAIM.search(sentence):
        return True
    lowered = sentence.lower()
    return any(re.search(rf"\b{re.escape(name.lower())}\b", lowered) for name in test_names)


def _sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return [part for part in _SENTENCE_SPLIT.split(stripped) if part.strip()]


def _citations(text: str) -> list[str]:
    found: list[str] = []
    for source_id in _CITATION.findall(text):
        if source_id not in found:
            found.append(source_id)
    return found


def _unit_labels() -> list[str]:
    labels: set[str] = set()
    for panel in list_panels():
        labels.add(panel.canonical_unit)
        labels.update(panel.converters)
    return sorted(labels, key=len, reverse=True)


def _syllables(word: str) -> int:
    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if not cleaned:
        return 1
    groups = re.findall(r"[aeiouy]+", cleaned)
    count = len(groups)
    if cleaned.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _show(number: float) -> str:
    if math.isclose(number, round(number), abs_tol=1e-9):
        return str(int(round(number)))
    return str(number)
