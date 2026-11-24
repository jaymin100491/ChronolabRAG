"""Plain-language trend explanations.

``provider="mock"`` renders a deterministic template and does not call a model.
OpenAI, Anthropic, and Ollama go through LiteLLM when it is installed, and
otherwise through a small HTTP adapter.
"""

from __future__ import annotations

import json
import math
import os
import urllib.request
from typing import Any

from chronolab_rag.schemas import PatientLabTimeline, RetrievedReference, TrendMetric

SYSTEM_PROMPT = (
    "You explain laboratory trends in plain language for a general reader. "
    "Use only numbers that appear in the trend metrics or the observations. "
    "Every sentence that states a result, a change, or what a test means must end "
    "with a citation in square brackets using only the supplied source ids. "
    "Low, Normal, and High mean below, inside, or above the supplied reference range. "
    "They are not a diagnosis. Do not recommend treatment."
)

_PROSE_UNITS = {
    "mg/dL": "mg/dL",
    "mmol/L": "mmol/L",
    "g/dL": "g/dL",
    "g/L": "g/L",
    "%": "%",
    "mmol/mol": "mmol/mol",
    "umol/L": "umol/L",
    "uIU/mL": "uIU/mL",
    "mIU/L": "mIU/L",
    "10^3/uL": "thousand per uL",
    "10^9/L": "billion per L",
    "U/L": "U/L",
    "IU/L": "IU/L",
    "mL/min/1.73m2": "mL/min",
}

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "ollama": "llama3.2",
}


def generate_summary(
    timeline: PatientLabTimeline,
    trends: list[TrendMetric],
    references: list[RetrievedReference],
    *,
    provider: str = "mock",
    model: str | None = None,
) -> str:
    """Build a cited plain-language summary for one timeline."""

    selected = provider.lower().strip()
    if selected == "mock":
        return render_mock_summary(trends, references)
    if selected not in _DEFAULT_MODELS:
        raise ValueError("provider must be one of: mock, openai, anthropic, ollama")
    prompt = _user_prompt(timeline, trends, references)
    return _complete(selected, model, prompt).strip()


def render_mock_summary(
    trends: list[TrendMetric],
    references: list[RetrievedReference],
) -> str:
    """Offline summary whose numbers come only from ``trends``."""

    if not trends:
        return "No numeric results were found in this timeline."
    blocks = [_trend_block(trend, _reference_for(trend, references)) for trend in trends]
    return " ".join(blocks)


def format_number(value: float) -> str:
    rounded = round(float(value), 2)
    if math.isclose(rounded, round(rounded), abs_tol=1e-9):
        return str(int(round(rounded)))
    text = f"{rounded:.2f}"
    return text[:-1] if text.endswith("0") else text


def _trend_block(trend: TrendMetric, reference: RetrievedReference | None) -> str:
    cite = f"[{reference.source_id}]" if reference is not None else ""
    unit = _PROSE_UNITS.get(trend.normalized_unit, trend.normalized_unit)
    start, end = trend.status_transition.split("->")
    sentences = [
        _cited(
            f"{trend.test_name} moved from {format_number(trend.baseline_value)} {unit} "
            f"to {format_number(trend.latest_value)} {unit}",
            cite,
        ),
        _cited(
            f"The change was {format_number(trend.delta)} {unit}, "
            f"which is {format_number(trend.percent_change)} percent",
            cite,
        ),
        _cited(
            f"The rate of change was {format_number(trend.velocity_per_day)} {unit} per day",
            cite,
        ),
        _cited(f"The status moved from {start} to {end}", cite),
        _cited(
            "High here means above the supplied reference range, and Low means below it",
            cite,
        ),
    ]
    if trend.reference_low is not None and trend.reference_high is not None:
        sentences.append(
            _cited(
                "The reference range used here is "
                f"{format_number(trend.reference_low)} to {format_number(trend.reference_high)} {unit}",
                cite,
            )
        )
    if reference is not None:
        sentences.append(
            _cited(f"{reference.title} is the teaching note used for this result", cite)
        )
    return " ".join(sentences)


def _cited(text: str, cite: str) -> str:
    """Keep the citation in the same sentence as the claim."""

    suffix = f" {cite}" if cite else ""
    return f"{text.strip()}{suffix}."


def _reference_for(
    trend: TrendMetric,
    references: list[RetrievedReference],
) -> RetrievedReference | None:
    for reference in references:
        if reference.loinc_code == trend.loinc_code:
            return reference
    return references[0] if references else None


def _user_prompt(
    timeline: PatientLabTimeline,
    trends: list[TrendMetric],
    references: list[RetrievedReference],
) -> str:
    payload = {
        "patient_id": timeline.patient_id,
        "observations": [item.model_dump(mode="json") for item in timeline.observations],
        "trends": [item.model_dump(mode="json") for item in trends],
        "references": [item.model_dump(mode="json") for item in references],
    }
    return (
        "Write a short plain-language trend summary from this JSON. "
        "Do not invent numbers. Cite the matching source_id on every sentence.\n"
        + json.dumps(payload, indent=2)
    )


def _complete(provider: str, model: str | None, prompt: str) -> str:
    resolved = model or _DEFAULT_MODELS[provider]
    try:
        import litellm
    except ImportError:
        litellm = None
    if litellm is not None:
        response = litellm.completion(
            model=_litellm_model(provider, resolved),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        return content or ""
    return _http_complete(provider, resolved, prompt)


def _litellm_model(provider: str, model: str) -> str:
    if provider == "ollama" and "/" not in model:
        return f"ollama/{model}"
    if provider == "anthropic" and "/" not in model:
        return f"anthropic/{model}"
    return model


def _http_complete(provider: str, model: str, prompt: str) -> str:
    if provider == "openai":
        return _openai(model, prompt)
    if provider == "anthropic":
        return _anthropic(model, prompt)
    if provider == "ollama":
        return _ollama(model, prompt)
    raise ValueError(f"Unsupported provider: {provider}")


def _openai(model: str, prompt: str) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is not set. Use --provider mock to run offline.")
    payload = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
    )
    return str(payload["choices"][0]["message"]["content"])


def _anthropic(model: str, prompt: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY is not set. Use --provider mock to run offline.")
    payload = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        {
            "model": model,
            "max_tokens": 800,
            "temperature": 0,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return str(payload["content"][0]["text"])


def _ollama(model: str, prompt: str) -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    payload = _post_json(
        f"{host}/api/chat",
        {"Content-Type": "application/json"},
        {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
    )
    return str(payload["message"]["content"])


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        parsed: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return parsed
