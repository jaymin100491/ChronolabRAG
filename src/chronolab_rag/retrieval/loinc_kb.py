"""Load the bundled public LOINC teaching notes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "data" / "loinc_references.json"


@dataclass(frozen=True)
class Monograph:
    source_id: str
    loinc_code: str
    alias_loinc_codes: tuple[str, ...]
    title: str
    snippet: str

    def search_text(self) -> str:
        aliases = " ".join(self.alias_loinc_codes)
        return f"{self.title} {self.snippet} {self.loinc_code} {aliases} {self.source_id}"


def load_monographs() -> tuple[Monograph, ...]:
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    monographs = []
    for row in payload:
        monographs.append(
            Monograph(
                source_id=row["source_id"],
                loinc_code=row["loinc_code"],
                alias_loinc_codes=tuple(row.get("alias_loinc_codes") or ()),
                title=row["title"],
                snippet=row["snippet"],
            )
        )
    return tuple(monographs)
