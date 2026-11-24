"""Score numeric fidelity, citation precision, and readability."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chronolab_rag.generation.safety_verifier import audit_details  # noqa: E402
from chronolab_rag.pipeline import explain_payload, timeline_from_payload  # noqa: E402
from chronolab_rag.retrieval.retriever import retrieve_for_timeline  # noqa: E402
from chronolab_rag.temporal.trend_engine import compute_trends  # noqa: E402


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def evaluate_cases(cases: list[dict[str, Any]], provider: str = "mock") -> dict[str, Any]:
    """Explain each case and aggregate the safety-audit counts."""

    extracted = 0
    matched = 0
    mentions = 0
    valid_mentions = 0
    grades: list[float] = []
    passed = 0
    failures: list[dict[str, Any]] = []
    for case in cases:
        result = explain_payload(case, provider=provider)
        timeline = timeline_from_payload(case)
        details = audit_details(
            result.summary_text,
            timeline,
            compute_trends(timeline),
            retrieve_for_timeline(timeline),
        )
        extracted += int(details["extracted_numbers"])
        matched += int(details["matched_numbers"])
        mentions += int(details["citation_mentions"])
        valid_mentions += int(details["valid_citation_mentions"])
        grades.append(float(details["reading_grade_level"]))
        if result.safety_audit_passed:
            passed += 1
        else:
            failures.append(
                {
                    "patient_id": case.get("patient_id"),
                    "flags": result.audit_flags,
                    "summary": result.summary_text[:500],
                }
            )
    total = len(cases)
    return {
        "cases": total,
        "numeric_fidelity": _ratio(matched, extracted),
        "citation_precision": _ratio(valid_mentions, mentions),
        "mean_reading_grade_level": round(sum(grades) / len(grades), 2) if grades else 0.0,
        "audit_pass_rate": _ratio(passed, total),
        "failures": failures,
    }


def evaluate_dataset(path: Path, provider: str = "mock") -> dict[str, Any]:
    return evaluate_cases(load_cases(path), provider=provider)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)


def main() -> None:
    dataset = Path(__file__).resolve().parent / "sample_cases.jsonl"
    print(json.dumps(evaluate_dataset(dataset, provider="mock"), indent=2))


if __name__ == "__main__":
    main()
