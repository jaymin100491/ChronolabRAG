from chronolab_rag.retrieval.loinc_kb import load_monographs
from chronolab_rag.retrieval.retriever import BM25Retriever, retrieve_for_timeline
from chronolab_rag.schemas import PatientLabTimeline
from tests.conftest import observation


def test_knowledge_base_covers_twelve_tests() -> None:
    monographs = load_monographs()
    assert len(monographs) == 12
    assert {item.source_id for item in monographs} >= {"REF-GLUCOSE", "REF-ALT", "REF-AST"}


def test_exact_loinc_and_alias_lookup() -> None:
    retriever = BM25Retriever()
    alt = retriever.for_loinc("1742-6")
    glucose = retriever.for_loinc("14749-6")
    assert alt is not None and alt.source_id == "REF-ALT"
    assert glucose is not None and glucose.loinc_code == "2345-7"


def test_bm25_ranks_the_blood_sugar_note_first() -> None:
    hits = BM25Retriever().search("blood sugar", k=3)
    assert hits[0].source_id == "REF-GLUCOSE"


def test_timeline_retrieval_uses_the_loinc_code() -> None:
    timeline = PatientLabTimeline(
        patient_id="SYN-RET",
        observations=[observation(20, 1, loinc_code="1920-8", test_name="AST", reference_low=10, reference_high=40)],
    )
    references = retrieve_for_timeline(timeline)
    assert [item.source_id for item in references] == ["REF-AST"]
