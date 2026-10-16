"""W4-R R2: retrievers rank sensibly, never return the excluded family, and stay stable."""

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from spec_bridge.rag.knowledge import KbExample, Qualifiers
from spec_bridge.rag.retrieval import (
    KbBM25Retriever,
    KbDenseRetriever,
    KbHybridRetriever,
    KbRetriever,
    examples_of,
    for_query,
    tokens,
)

LINES = [
    (
        "A:1",
        "FAM-A",
        "rated_power",
        "Engine (kWm) | 3746.4 | kW | continuous rating; at R1; engine shaft",
    ),
    ("A:2", "FAM-A", "dry_weight", "Dry weight | 31755.2 | kg | dry; for engine without generator"),
    (
        "B:1",
        "FAM-B",
        "rated_power",
        "Power [kW] | 17346.0 | kW | at MCR; rating point R1; for engine shaft",
    ),
    ("B:2", "FAM-B", "dry_weight", "Dry mass — 389400.0 kg (dry condition; main engine)"),
    ("C:1", "FAM-C", "capacity", "Flow | 95.67 | m3/h | nominal rating; at 50 Hz; main pump"),
]
KB = [
    KbExample(
        example_id=i,
        doc_id=i.split(":")[0],
        family_id=fam,
        split="dev",
        attribute=attr,
        label_text=None,
        line_text=text,
        parent_text=f"Line: {text}",
        qualifiers=Qualifiers(),
        evidence={},
    )
    for i, fam, attr, text in LINES
]
BY_ID = {e.example_id: e for e in KB}


def retrievers() -> dict[str, KbRetriever]:
    lexical = KbBM25Retriever(KB, k=3)
    semantic = KbDenseRetriever(KB, DeterministicFakeEmbedding(size=32), k=3)
    return {
        "bm25": lexical,
        "dense": semantic,
        "hybrid": KbHybridRetriever(lexical=lexical, semantic=semantic, k=3),
    }


@pytest.mark.parametrize("kind", ["bm25", "dense", "hybrid"])
def test_excluded_family_never_comes_back(kind: str) -> None:
    retriever = for_query(retrievers()[kind], "FAM-A")
    found = examples_of(retriever.invoke("at R1; engine shaft"), BY_ID)
    assert found and all(e.family_id != "FAM-A" for e in found)


def test_bm25_ranks_exact_symbols_first() -> None:
    found = examples_of(retrievers()["bm25"].invoke("rating point R1"), BY_ID)
    assert found[0].example_id == "B:1"


def test_hybrid_fuses_without_duplicates_and_keeps_k() -> None:
    found = retrievers()["hybrid"].invoke("dry weight for engine")
    ids = [d.metadata["example_id"] for d in found]
    assert len(ids) == len(set(ids)) <= 3


@pytest.mark.parametrize("kind", ["bm25", "dense", "hybrid"])
def test_empty_query_returns_nothing(kind: str) -> None:
    assert retrievers()[kind].invoke("   ") == []


def test_bm25_without_overlap_returns_nothing() -> None:
    assert retrievers()["bm25"].invoke("zzz qqq") == []


@pytest.mark.parametrize("kind", ["bm25", "dense", "hybrid"])
def test_same_query_same_order(kind: str) -> None:
    retriever = retrievers()[kind]
    first = [d.metadata["example_id"] for d in retriever.invoke("dry condition")]
    assert first == [d.metadata["example_id"] for d in retriever.invoke("dry condition")]


def test_for_query_does_not_change_the_shared_retriever() -> None:
    shared = retrievers()["bm25"]
    for_query(shared, "FAM-B").invoke("R1")
    assert shared.exclude_family is None


def test_tokens_keep_symbols_together() -> None:
    assert tokens("4-stroke, per TC unit; at R1; 17220.6 kW") == [
        "4-stroke",
        "per",
        "tc",
        "unit",
        "at",
        "r1",
        "17220.6",
        "kw",
    ]
