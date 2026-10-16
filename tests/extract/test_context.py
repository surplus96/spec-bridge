"""W4-1 context questions (D-039): ontology descriptions, hidden contract defaults,
optional versus required-with-"none" context fields."""

from typing import Any

import pytest

from spec_bridge.extract.extractor import CONTEXT_GUIDE, extract, scope_token
from spec_bridge.extract.schemas import HIDDEN, NONE, ContextStyle, extraction_schema
from spec_bridge.ontology.loader import Ontology
from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from tests.extract.test_extractor import ANSWER, INPUT_ID, PATH, b_item, numeric_attribute
from tests.llm.fakes import FakeProvider
from tests.parse.goldmatch import dev_documents

STYLES: list[ContextStyle] = ["optional", "required_none"]


@pytest.fixture(scope="module")
def document() -> ParsedDocument:
    return parse_document(PATH, INPUT_ID)


def items(onto: Ontology, mode: Any, style: ContextStyle) -> list[dict[str, Any]]:
    schema = extraction_schema(onto, ANSWER["expected_class"], mode, style)
    return list(schema["properties"]["facts"]["items"]["anyOf"])


def enums(item: dict[str, Any]) -> list[list[str]]:
    context = [item["properties"]["basis"], item["properties"]["condition"]]
    return [p["enum"] for c in context for p in c["properties"].values() if "enum" in p]


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("mode", ["B", "C"])
def test_contract_defaults_are_never_offered(
    onto: Ontology, mode: Any, style: ContextStyle
) -> None:
    for item in items(onto, mode, style):
        assert all(not HIDDEN & set(values) for values in enums(item))


def test_optional_style_does_not_require_context(onto: Ontology) -> None:
    for item in items(onto, "C", "optional"):
        assert not {"basis", "condition", "scope"} & set(item["required"])
        assert all(NONE not in values for values in enums(item))


def test_required_style_offers_none_everywhere(onto: Ontology) -> None:
    for item in items(onto, "C", "required_none"):
        assert {"basis", "condition", "scope"} <= set(item["required"])
        assert all(values[-1] == NONE for values in enums(item))


def test_ontology_descriptions_reach_the_schema(onto: Ontology) -> None:
    described = onto.vocabularies.descriptions
    assert described is not None
    item = items(onto, "C", "required_none")[0]
    for axis, texts in described.basis.items():
        text = item["properties"]["basis"]["properties"][axis]["description"]
        assert all(sentence in text for sentence in texts.values())
    assert item["properties"]["scope"]["description"] == described.scope["required_none"]


@pytest.mark.parametrize("style", STYLES)
def test_prompt_states_the_context_style(
    onto: Ontology, document: ParsedDocument, style: ContextStyle
) -> None:
    provider = FakeProvider([{"facts": []}])
    extract(onto, document, ANSWER["expected_class"], provider, "C", style)
    assert CONTEXT_GUIDE[style] in provider.prompts[0]["user"]


def test_none_means_no_context(onto: Ontology, document: ParsedDocument) -> None:
    item = b_item(document, numeric_attribute())
    c_item = {k: v for k, v in item.items() if k not in ("value", "unit", "raw_text")}
    c_item |= {"value_text": item["raw_text"], "unit_text": item["unit"]}
    c_item |= {"basis": {"rating": NONE}, "condition": {"rating_point": NONE}, "scope": NONE}
    provider = FakeProvider([{"facts": [c_item]}])
    result = extract(onto, document, ANSWER["expected_class"], provider, "C", "required_none")
    raw = result.raw[0]
    assert (raw.basis, raw.condition, raw.scope) == ({}, {}, "main_equipment")
    assert scope_token("None") == "main_equipment"


def test_no_prompt_wording_is_copied_from_dev_documents(onto: Ontology) -> None:
    """CP-S3 L6: descriptions and guides come from the ontology, not development text."""
    described = onto.vocabularies.descriptions
    assert described is not None
    sentences = [
        *(t for texts in described.basis.values() for t in texts.values()),
        *(t for texts in described.condition.values() for t in texts.values()),
        *described.scope.values(),
        *CONTEXT_GUIDE.values(),
    ]
    texts = [
        block.text.casefold()
        for input_id, path, _ in dev_documents("xlsx") + dev_documents("docx")
        for block in parse_document(path, input_id).blocks
    ]
    copied = [s for s in sentences if any(s.casefold() in t for t in texts)]
    assert copied == []
