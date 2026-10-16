"""W6-0: the scorer reads the split it is asked for (dev or test), and nothing else.

These tests use only the document ids of the test split (from the case plan), never the
content of its answers (D-020: the helper does not read test answers before W6-4).
"""

import pytest

from spec_bridge.eval.dedup_scoring import split_labels, split_registry
from spec_bridge.normalize.dictionary import dev_answers, split_answers
from spec_bridge.rag.knowledge import documents_by_split

PLAN = documents_by_split()


@pytest.mark.parametrize("split", ["dev", "test"])
def test_each_split_reads_its_own_answers_labels_and_registry(split: str) -> None:
    ids = {i for i, d in PLAN.items() if d["split"] == split}
    assert {a["input_id"] for a in split_answers(split)} == ids
    assert set(split_labels(split)) == ids
    records, _ = split_registry(split)
    other = "test" if split == "dev" else "dev"
    other_ids = {r["product_id"] for r in split_registry(other)[0]}
    assert records and not ({r["product_id"] for r in records} & other_ids)


def test_dev_answers_are_the_dev_split() -> None:
    assert dev_answers() == split_answers("dev")


def test_an_unknown_split_is_refused() -> None:
    with pytest.raises(ValueError, match="split"):
        split_answers("train")


def test_the_knowledge_base_holds_no_test_family() -> None:
    """Review Focus 2: test documents are judged with development cases only."""
    from spec_bridge.rag.knowledge import load_kb

    test_families = {d["family_id"] for d in PLAN.values() if d["split"] == "test"}
    kb = load_kb()
    assert kb and all(e.split == "dev" for e in kb)
    assert not {e.family_id for e in kb} & test_families
