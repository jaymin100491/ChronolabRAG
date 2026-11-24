# chronolab-rag

`chronolab-rag` turns a multi-visit laboratory timeline into a unit-aligned trend and a short plain-language explanation. The trend math runs before any model call. After the text is written, a deterministic checker rejects numbers that were not in the data, sentences with no citation, and citations that were not retrieved.

This is a teaching toolkit. It uses synthetic patients and illustrative reference ranges. It is not a medical device, and it does not give a diagnosis or a treatment recommendation.

LOINC is a registered trademark of Regenstrief Institute, Inc. The codes in this repository are public identifiers. The teaching notes are original short descriptions written for this project.

## Install

Python 3.11 or newer:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

LiteLLM is optional. `--provider mock` runs with no API key and no network.

```bash
pip install -e ".[llm]"
```

## Quick start

```bash
chronolab explain examples/synthetic_glucose.json --provider mock
```

That file is two synthetic fasting glucose results, 90 mg/dL then 110 mg/dL. The command prints a `VerifiedExplanation`: the summary, the citation ids, whether the safety audit passed, any flags, and a Flesch-Kincaid grade.

Score the bundled synthetic set:

```bash
python benchmark/generate_synthetic.py
chronolab benchmark --dataset benchmark/sample_cases.jsonl --provider mock
```

`benchmark/sample_cases.jsonl` holds 50 synthetic timelines. The generator rebuilds that file. Cases include a unit change between visits (for example mg/dL, then mmol/L), values sitting on the edge of the reference range, and a short-interval spike.

## Pipeline

1. **Parse.** `parsers/simple_json.py` reads a JSON object or array. `parsers/fhir_bundle.py` reads a FHIR R4 `Bundle` of numeric `Observation` resources.
2. **Normalize.** `temporal/unit_normalizer.py` converts 12 common panels onto one unit. Glucose, creatinine, LDL, HDL, triglycerides, and hemoglobin use a constant factor. HbA1c uses the NGSP/IFCC equation `mmol/mol = (percent - 2.15) x 10.929`. TSH, WBC, ALT, AST, and eGFR accept equivalent unit labels.
3. **Trend.** `temporal/trend_engine.py` computes delta, percent change, change per day, and the reference-range transition (`Normal->High` and the other combinations). Low, Normal, and High mean below, inside, or above the supplied interval.
4. **Retrieve.** `retrieval/retriever.py` loads the local JSON notes and returns the monograph for each LOINC code. Free-text search uses an in-memory BM25 index. There is no vector database.
5. **Explain.** `generation/explainer.py` calls OpenAI, Anthropic, or Ollama when a provider is selected. `mock` fills a template from the trend metrics.
6. **Verify.** `generation/safety_verifier.py` checks numbers, citations, and reading grade.

Live providers:

```bash
chronolab explain examples/synthetic_glucose.json --provider openai
chronolab explain examples/synthetic_glucose.json --provider anthropic
chronolab explain examples/synthetic_glucose.json --provider ollama
```

Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for the hosted models. Ollama uses `OLLAMA_HOST` (default `http://127.0.0.1:11434`). If LiteLLM is installed it is used first; otherwise the library calls the provider HTTP API.

## Safety audit

A summary passes only when all three checks pass:

- Every number matches a trend field or an input result, including the unit-normalized value, within normal rounding to two decimals.
- Every sentence that states a result, a change, or a test name ends with a `[source_id]` that was retrieved for this timeline.
- The Flesch-Kincaid grade is reported on `reading_grade_level`.

`numeric_hallucination`, `missing_citation`, and `unknown_citation` flags set `safety_audit_passed` to false. The process still prints the audit so a caller can inspect the flags.

## Tests

```bash
pytest
```

The suite covers unit conversion, trend math, FHIR parsing, retrieval, hallucination detection, and a full mock run of the 50 synthetic cases.

## Layout

```text
src/chronolab_rag/
  schemas.py
  parsers/
  temporal/
  retrieval/
  generation/
  cli.py
benchmark/
examples/
tests/
```
