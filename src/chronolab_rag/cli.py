"""Command line for offline explanations and benchmark scoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from chronolab_rag.pipeline import explain_path

app = typer.Typer(no_args_is_help=True, help="Unit-normalized lab trends and cited explanations.")


@app.command("explain")
def explain_command(
    input_path: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Timeline JSON or FHIR Bundle."),
    ],
    provider: Annotated[str, typer.Option("--provider", help="mock, openai, anthropic, or ollama.")] = "mock",
    model: Annotated[Optional[str], typer.Option("--model", help="Model name for a live provider.")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", help="Write the audit JSON here.")] = None,
) -> None:
    """Explain one synthetic timeline and print the safety audit."""

    try:
        result = explain_path(input_path, provider=provider, model=model)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    rendered = json.dumps(result.model_dump(mode="json"), indent=2)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(rendered)


@app.command("benchmark")
def benchmark_command(
    dataset: Annotated[
        Path,
        typer.Option("--dataset", help="JSONL file of synthetic timelines."),
    ] = Path("benchmark/sample_cases.jsonl"),
    provider: Annotated[str, typer.Option("--provider")] = "mock",
) -> None:
    """Score numeric fidelity, citation precision, and readability."""

    if not dataset.exists():
        typer.echo(f"Dataset not found: {dataset}", err=True)
        raise typer.Exit(code=2)
    try:
        report = _evaluate_dataset(dataset, provider)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(json.dumps(report, indent=2))


def _evaluate_dataset(dataset: Path, provider: str) -> dict[str, object]:
    """Load ``benchmark.metrics`` from the repo that contains the dataset."""

    roots = [Path.cwd(), dataset.resolve().parent.parent]
    for root in roots:
        if (root / "benchmark" / "metrics.py").exists():
            root_text = str(root)
            if root_text not in sys.path:
                sys.path.insert(0, root_text)
            break
    from benchmark.metrics import evaluate_dataset

    report: dict[str, object] = evaluate_dataset(dataset, provider=provider)
    return report


def main() -> None:
    app()


if __name__ == "__main__":
    main()
