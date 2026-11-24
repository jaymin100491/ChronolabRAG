import json
from pathlib import Path

from typer.testing import CliRunner

from benchmark.generate_synthetic import build_cases
from benchmark.metrics import evaluate_cases
from chronolab_rag.cli import app

ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_generator_covers_unit_flips_and_spikes() -> None:
    cases = build_cases()
    assert len(cases) == 50
    assert {case["patient_id"] for case in cases} == {f"SYN-{index:03d}" for index in range(1, 51)}
    flipped = 0
    spiked = 0
    for case in cases:
        units = {row["unit"] for row in case["observations"]}
        values = [row["value"] for row in case["observations"]]
        if len(units) > 1:
            flipped += 1
        if max(values) > min(values) * 1.4:
            spiked += 1
    assert flipped >= 8
    assert spiked >= 8


def test_mock_benchmark_is_numerically_faithful() -> None:
    report = evaluate_cases(build_cases(), provider="mock")
    assert report["audit_pass_rate"] == 1, report["failures"]
    assert report["numeric_fidelity"] == 1, report["failures"]
    assert report["citation_precision"] == 1, report["failures"]
    assert report["cases"] == 50


def test_explain_command_on_the_example() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["explain", str(ROOT / "examples" / "synthetic_glucose.json"), "--provider", "mock"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["safety_audit_passed"] is True
    assert payload["citations"] == ["REF-GLUCOSE"]


def test_benchmark_command(tmp_path: Path) -> None:
    dataset = tmp_path / "sample_cases.jsonl"
    lines = [json.dumps(case, separators=(",", ":")) for case in build_cases(n=2)]
    dataset.write_text("\n".join(lines) + "\n", encoding="utf-8")
    repo_benchmark = ROOT / "benchmark"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["benchmark", "--dataset", str(dataset), "--provider", "mock"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["cases"] == 2
    assert payload["audit_pass_rate"] == 1
    assert repo_benchmark.joinpath("metrics.py").exists()
