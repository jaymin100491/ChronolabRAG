"""Convert Synthea FHIR bundles or MIMIC-IV lab tables into benchmark JSONL.

Examples
--------
python benchmark/prepare_external_data.py --synthea-dir data/external/synthea_1k
python benchmark/prepare_external_data.py --mimic-dir data/external/mimic_iv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chronolab_rag.parsers.fhir_bundle import parse_fhir_bundle  # noqa: E402
from chronolab_rag.parsers.mimic_loader import (  # noqa: E402
    load_mimic_directory,
    timelines_with_repeated_tests,
)
from chronolab_rag.schemas import PatientLabTimeline  # noqa: E402

BENCHMARK_DIR = Path(__file__).resolve().parent


def default_output(kind: str) -> Path:
    """Return the JSONL path used for a Synthea or MIMIC extract."""

    if kind == "synthea":
        return BENCHMARK_DIR / "external_synthea.jsonl"
    if kind == "mimic":
        return BENCHMARK_DIR / "external_mimic.jsonl"
    raise ValueError(f"Unknown dataset kind: {kind}")


def prepare_synthea(source: Path, output: Path) -> int:
    """Write multi-visit Synthea timelines to ``output`` and return the count."""

    if not source.is_dir():
        raise FileNotFoundError(f"Synthea directory not found: {source}")
    timelines: list[PatientLabTimeline] = []
    for path in sorted(source.rglob("*.json")):
        timeline = _timeline_from_bundle(path)
        if timeline is not None:
            timelines.append(timeline)
    kept = timelines_with_repeated_tests(timelines)
    write_timelines(output, kept)
    return len(kept)


def prepare_mimic(source: Path, output: Path) -> int:
    """Write multi-visit MIMIC-IV timelines to ``output`` and return the count."""

    kept = load_mimic_directory(source)
    write_timelines(output, kept)
    return len(kept)


def write_timelines(path: Path, timelines: list[PatientLabTimeline]) -> None:
    """Write timelines in the same JSONL shape as ``sample_cases.jsonl``."""

    lines = [
        json.dumps(timeline.model_dump(mode="json"), separators=(",", ":"))
        for timeline in timelines
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Synthea or MIMIC-IV extracts into chronolab benchmark JSONL."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--synthea-dir",
        type=Path,
        help="Directory of Synthea FHIR R4 Bundle JSON files, such as data/external/synthea_1k.",
    )
    source.add_argument(
        "--mimic-dir",
        type=Path,
        help="Directory containing MIMIC-IV labevents.csv, such as data/external/mimic_iv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSONL destination. Defaults to benchmark/external_synthea.jsonl or benchmark/external_mimic.jsonl.",
    )
    args = parser.parse_args(argv)
    try:
        if args.synthea_dir is not None:
            destination = args.output or default_output("synthea")
            count = prepare_synthea(args.synthea_dir, destination)
        else:
            destination = args.output or default_output("mimic")
            count = prepare_mimic(args.mimic_dir, destination)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Wrote {count} timelines to {destination}")
    return 0


def _timeline_from_bundle(path: Path) -> PatientLabTimeline | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("resourceType") != "Bundle":
        return None
    try:
        return parse_fhir_bundle(payload)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
