from pathlib import Path
from typing import Any

import pytest

from spec_bridge.extract.classifier import UNKNOWN, classify, keyword_scores
from spec_bridge.llm.provider import LlmError
from spec_bridge.ontology.loader import Ontology
from spec_bridge.parse.blocks import Block, ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from tests.llm.fakes import FakeProvider
from tests.parse.goldmatch import dev_documents

# Dev documents whose body names another class (applicable engine, component, feed pump).
MIXED = {
    "SYN-003",
    "SYN-010",
    "SYN-017",
    "SYN-024",
    "SYN-029",
    "SYN-030",
    "SYN-032",
    "SYN-035",
    "SYN-037",
}
ROWS = [row for fmt in ("xlsx", "docx", "pdf") for row in dev_documents(fmt)]


def as_param(row: tuple[str, Path, dict[str, Any]]) -> Any:
    marks = [pytest.mark.docling] if row[1].suffix == ".pdf" else []
    return pytest.param(*row, marks=marks, id=row[0])


DEV = [as_param(row) for row in ROWS]
MIXED_DEV = [as_param(row) for row in ROWS if row[0] in MIXED]
_cache: dict[str, ParsedDocument] = {}


def parsed(input_id: str, path: Path) -> ParsedDocument:
    if input_id not in _cache:
        _cache[input_id] = parse_document(path, input_id)
    return _cache[input_id]


@pytest.mark.parametrize("input_id, path, answer", DEV)
def test_true_class_is_among_keyword_candidates(
    onto: Ontology, input_id: str, path: Path, answer: Any
) -> None:
    top3 = [s.class_id for s in keyword_scores(onto, parsed(input_id, path))[:3]]
    assert answer["expected_class"] in top3


@pytest.mark.parametrize("input_id, path, answer", MIXED_DEV)
def test_body_mentions_do_not_win(onto: Ontology, input_id: str, path: Path, answer: Any) -> None:
    prediction = classify(onto, parsed(input_id, path))
    assert prediction.chosen == answer["expected_class"]


def bare_document() -> ParsedDocument:
    block = Block.model_validate(
        {"kind": "paragraph", "text": "Rated output 120 kW", "location": {"paragraph": 1}}
    )
    return ParsedDocument(
        document_id="X-1", file_format="docx", sha256="0" * 64, parser="test", blocks=[block]
    )


def test_no_keyword_evidence_and_no_llm_is_unknown(onto: Ontology) -> None:
    prediction = classify(onto, bare_document())
    assert prediction.chosen == UNKNOWN and prediction.top_k == []


def test_llm_may_answer_unknown(onto: Ontology) -> None:
    provider = FakeProvider([{"product_class": UNKNOWN, "reason": "no product named"}])
    prediction = classify(onto, bare_document(), provider)
    assert (prediction.chosen, prediction.method) == (UNKNOWN, "llm")


def test_llm_answer_outside_candidates_is_an_error(onto: Ontology) -> None:
    input_id, path, _ = dev_documents("xlsx")[0]
    document = parsed(input_id, path)
    allowed = {s.class_id for s in keyword_scores(onto, document)[:3] if s.score > 0}
    outsider = next(c for c, d in onto.classes.items() if not d.abstract and c not in allowed)
    with pytest.raises(LlmError, match="not one of"):
        classify(onto, document, FakeProvider([{"product_class": outsider, "reason": "x"}]))


def test_llm_sees_only_candidates_and_unknown(onto: Ontology) -> None:
    input_id, path, answer = dev_documents("xlsx")[0]
    provider = FakeProvider([{"product_class": answer["expected_class"], "reason": "head"}])
    classify(onto, parsed(input_id, path), provider)
    enum = provider.prompts[0]["schema"]["properties"]["product_class"]["enum"]
    assert enum[-1] == UNKNOWN and answer["expected_class"] in enum and len(enum) <= 4
    assert input_id not in provider.prompts[0]["user"]
