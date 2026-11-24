"""Wire parsing, trend math, retrieval, explanation, and the safety audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chronolab_rag.generation.explainer import generate_summary
from chronolab_rag.generation.safety_verifier import verify_summary
from chronolab_rag.parsers.fhir_bundle import parse_fhir_bundle
from chronolab_rag.parsers.simple_json import parse_simple_json
from chronolab_rag.retrieval.retriever import retrieve_for_timeline
from chronolab_rag.schemas import PatientLabTimeline, VerifiedExplanation
from chronolab_rag.temporal.trend_engine import compute_trends


def explain_timeline(
    timeline: PatientLabTimeline,
    *,
    provider: str = "mock",
    model: str | None = None,
) -> VerifiedExplanation:
    """Run the full offline-capable explanation pipeline for one timeline."""

    trends = compute_trends(timeline)
    references = retrieve_for_timeline(timeline)
    summary = generate_summary(
        timeline,
        trends,
        references,
        provider=provider,
        model=model,
    )
    return verify_summary(summary, timeline, trends, references)


def explain_payload(
    payload: Any,
    *,
    provider: str = "mock",
    model: str | None = None,
) -> VerifiedExplanation:
    """Explain a dict, JSON string, timeline object, or FHIR Bundle."""

    return explain_timeline(timeline_from_payload(payload), provider=provider, model=model)


def explain_path(
    path: Path,
    *,
    provider: str = "mock",
    model: str | None = None,
) -> VerifiedExplanation:
    """Explain the JSON file at ``path``."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return explain_payload(payload, provider=provider, model=model)


def timeline_from_payload(payload: Any) -> PatientLabTimeline:
    if isinstance(payload, PatientLabTimeline):
        return payload
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict) and payload.get("resourceType") == "Bundle":
        return parse_fhir_bundle(payload)
    return parse_simple_json(payload)
