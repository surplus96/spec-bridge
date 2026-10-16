"""W4-R R1: the knowledge base is dev-only, complete, faithful to the gold and stable."""

from pathlib import Path
from typing import Any

import pytest

from spec_bridge.eval.scoring import CONTEXT_DEFAULTS
from spec_bridge.extract.extractor import scope_token
from spec_bridge.normalize.dictionary import dev_answers, load_dictionary
from spec_bridge.normalize.values import Normalizer
from spec_bridge.ontology.loader import Ontology, load_ontology
from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.rag.knowledge import (
    KbExample,
    build_kb,
    definitions,
    documents_by_split,
    load_kb,
    save_kb,
)
from spec_bridge.service import normalizer_for
from tests.conftest import ONTOLOGY
from tests.parse.goldmatch import dev_documents

FAST = dev_documents("xlsx") + dev_documents("docx")
ANSWERS = {a["input_id"]: a for a in dev_answers()}


def parsed(rows: list[tuple[str, Path, Any]]) -> dict[str, ParsedDocument]:
    return {i: parse_document(p, i) for i, p, _ in rows}


@pytest.fixture(scope="module")
def fast_kb() -> list[KbExample]:
    return build_kb([a for i, _, a in FAST], parsed(FAST))


@pytest.fixture(scope="module")
def normalizer() -> Normalizer:
    onto = load_ontology(ONTOLOGY)
    return normalizer_for(onto, "dev", load_dictionary())


def gold_fact(example: KbExample) -> dict[str, Any]:
    oid = example.example_id.split(":")[1]
    answer = ANSWERS[example.doc_id]
    return next(f for f in answer["facts"] if oid in f["observation_ids"])


def test_other_splits_are_refused() -> None:
    test_id = next(i for i, d in documents_by_split().items() if d["split"] == "test")
    with pytest.raises(ValueError, match="dev split"):
        build_kb([{"input_id": test_id, "observations": [], "facts": []}], {})


def test_examples_are_dev_with_a_family(fast_kb: list[KbExample]) -> None:
    assert fast_kb and all(e.split == "dev" and e.family_id for e in fast_kb)


def test_qualifiers_normalize_back_to_the_gold(
    fast_kb: list[KbExample], normalizer: Normalizer
) -> None:
    for example in fast_kb:
        fact = gold_fact(example)
        q = example.qualifiers
        basis = {k: v for k, v in fact["basis"].items() if CONTEXT_DEFAULTS.get(k) != v}
        assert q.basis == basis, example.example_id
        assert normalizer.condition(q.condition) == fact["condition"], example.example_id
        assert scope_token(q.scope) == fact["scope"], example.example_id


def test_evidence_is_quoted_from_the_line(fast_kb: list[KbExample]) -> None:
    for example in fast_kb:
        assert all(span in example.line_text for span in example.evidence.values())


def test_parent_shows_the_table_header(fast_kb: list[KbExample]) -> None:
    rows = [e for e in fast_kb if " | " in e.line_text]
    assert rows and all("Table header: " in e.parent_text for e in rows)
    assert all(e.parent_text.endswith(f"Line: {e.line_text}") for e in fast_kb)


def test_save_is_stable(fast_kb: list[KbExample], tmp_path: Path) -> None:
    first = save_kb(fast_kb, tmp_path / "a.jsonl")
    second = save_kb(list(reversed(fast_kb)), tmp_path / "b.jsonl")
    assert first == second
    assert load_kb(tmp_path / "a.jsonl") == sorted(fast_kb, key=lambda e: e.example_id)


def test_definitions_come_from_the_ontology(onto: Ontology) -> None:
    described = onto.vocabularies.descriptions
    assert described is not None
    rows = definitions(onto)
    assert len({r.definition_id for r in rows}) == len(rows)
    texts = {r.text for r in rows}
    assert all(t in texts for table in described.basis.values() for t in table.values())


@pytest.mark.docling
def test_every_dev_fact_becomes_an_example() -> None:
    rows = dev_documents("xlsx") + dev_documents("docx") + dev_documents("pdf")
    kb = build_kb(list(ANSWERS.values()), parsed(rows))
    covered = {(e.doc_id, f["fact_id"]) for e in kb for f in [gold_fact(e)]}
    facts = {(a["input_id"], f["fact_id"]) for a in ANSWERS.values() for f in a["facts"]}
    assert covered == facts
    empty = {"basis": {}, "condition": {}, "scope": ""}
    with_context = {
        (e.doc_id, gold_fact(e)["fact_id"]) for e in kb if e.qualifiers.model_dump() != empty
    }
    assert len(with_context) == 98  # dev facts with stated basis/condition/scope (D-042)
