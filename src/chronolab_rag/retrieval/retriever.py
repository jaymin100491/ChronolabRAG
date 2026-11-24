"""In-memory BM25 retrieval over the bundled teaching notes.

There is no vector database. Exact LOINC matches are returned first. BM25 ranks
free-text queries against the same local notes.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from chronolab_rag.retrieval.loinc_kb import Monograph, load_monographs
from chronolab_rag.schemas import PatientLabTimeline, RetrievedReference

_TOKEN = re.compile(r"[a-z0-9]+")
_K1 = 1.5
_B = 0.75


class BM25Retriever:
    """Small Okapi BM25 index over the twelve bundled monographs."""

    def __init__(self, monographs: tuple[Monograph, ...] | None = None) -> None:
        self._monographs = monographs if monographs is not None else load_monographs()
        self._by_loinc: dict[str, Monograph] = {}
        self._tokens: list[list[str]] = []
        for monograph in self._monographs:
            self._by_loinc[monograph.loinc_code] = monograph
            for alias in monograph.alias_loinc_codes:
                self._by_loinc[alias] = monograph
            self._tokens.append(_tokenize(monograph.search_text()))
        self._doc_lengths = [len(tokens) for tokens in self._tokens]
        self._avg_length = (
            sum(self._doc_lengths) / len(self._doc_lengths) if self._doc_lengths else 0.0
        )
        document_frequency: Counter[str] = Counter()
        for tokens in self._tokens:
            document_frequency.update(set(tokens))
        self._document_frequency = document_frequency
        self._count = len(self._monographs)

    def for_loinc(self, loinc_code: str) -> RetrievedReference | None:
        monograph = self._by_loinc.get(loinc_code)
        if monograph is None:
            return None
        return _to_reference(monograph)

    def search(self, query: str, k: int = 5) -> list[RetrievedReference]:
        query_tokens = _tokenize(query)
        if not query_tokens or self._count == 0:
            return []
        scored = [
            (self._score(query_tokens, index), index) for index in range(self._count)
        ]
        scored = [item for item in scored if item[0] > 0]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [_to_reference(self._monographs[index]) for _, index in scored[:k]]

    def _score(self, query_tokens: list[str], index: int) -> float:
        counts = Counter(self._tokens[index])
        length = self._doc_lengths[index] or 1
        score = 0.0
        for token in query_tokens:
            if token not in counts:
                continue
            frequency = counts[token]
            containing = self._document_frequency[token]
            idf = math.log(1 + (self._count - containing + 0.5) / (containing + 0.5))
            denominator = frequency + _K1 * (1 - _B + _B * length / (self._avg_length or 1))
            score += idf * (frequency * (_K1 + 1)) / denominator
        return score


def retrieve_for_timeline(
    timeline: PatientLabTimeline,
    retriever: BM25Retriever | None = None,
) -> list[RetrievedReference]:
    """Return the teaching note for every known LOINC code in the timeline."""

    index = retriever or BM25Retriever()
    references: list[RetrievedReference] = []
    seen: set[str] = set()
    for observation in timeline.observations:
        reference = index.for_loinc(observation.loinc_code)
        if reference is not None and reference.source_id not in seen:
            references.append(reference)
            seen.add(reference.source_id)
    if references:
        return references
    query = " ".join(observation.test_name for observation in timeline.observations)
    return index.search(query, k=3)


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _to_reference(monograph: Monograph) -> RetrievedReference:
    return RetrievedReference(
        source_id=monograph.source_id,
        loinc_code=monograph.loinc_code,
        title=monograph.title,
        snippet=monograph.snippet,
    )
