"""Explanation generation and the post-generation safety audit."""

from chronolab_rag.generation.explainer import generate_summary, render_mock_summary
from chronolab_rag.generation.safety_verifier import (
    audit_details,
    extract_numbers,
    flesch_kincaid_grade,
    verify_summary,
)

__all__ = [
    "audit_details",
    "extract_numbers",
    "flesch_kincaid_grade",
    "generate_summary",
    "render_mock_summary",
    "verify_summary",
]
