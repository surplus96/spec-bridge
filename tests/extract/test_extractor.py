from typing import Any

import pytest

from spec_bridge.eval.locations import same_place
from spec_bridge.extract.extractor import Extraction, extract, scope_token
from spec_bridge.extract.prompt_input import render_lines
from spec_bridge.extract.schemas import extraction_schema
from spec_bridge.llm.provider import LlmError
from spec_bridge.ontology.loader import Ontology
from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from tests.llm.fakes import FakeProvider
from tests.parse.goldmatch import dev_documents

INPUT_ID, PATH, ANSWER = dev_documents("docx")[0]


@pytest.fixture(scope="module")
def document() -> ParsedDocument:
    return parse_document(PATH, INPUT_ID)


def gold_fact(attribute: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """A gold fact of this dev document and its first observation."""
    fact = next(f for f in ANSWER["facts"] if f["attribute_id"] == attribute)
    obs = next(
        o for o in ANSWER["observations"] if o["observation_id"] == fact["observation_ids"][0]
    )
    return fact, obs


def line_of(document: ParsedDocument, obs: dict[str, Any]) -> str:
    _, lines = render_lines(document)
    number = next(
        n for n, line in enumerate(lines, 1) if any(same_place(obs["location"], b) for b in line)
    )
    return f"L{number}"


def b_item(document: ParsedDocument, attribute: str) -> dict[str, Any]:
    fact, obs = gold_fact(attribute)
    item = {
        "attribute": attribute,
        "value": fact["value"],
        "unit": fact["unit"],
        "raw_text": obs["raw_text"],
        "basis": fact["basis"],
        "condition": fact["condition"],
        "scope": fact["scope"].replace("_", " "),
        "line": line_of(document, obs),
    }
    return item


def run(onto: Ontology, document: ParsedDocument, mode: str, facts: list[Any]) -> Extraction:
    reply = {"facts": facts} if mode != "A" else facts[0]
    return extract(onto, document, ANSWER["expected_class"], FakeProvider([reply]), mode)  # type: ignore[arg-type]


def numeric_attribute() -> str:
    return str(
        next(
            f["attribute_id"]
            for f in ANSWER["facts"]
            if isinstance(f["value"], (int, float)) and not isinstance(f["value"], bool)
        )
    )


def test_b_fact_gets_the_parser_location(onto: Ontology, document: ParsedDocument) -> None:
    attribute = numeric_attribute()
    result = run(onto, document, "B", [b_item(document, attribute)])
    _, obs = gold_fact(attribute)
    assert len(result.facts) == 1 and not result.rejected
    location = result.facts[0]["occurrences"][0]["location"]
    block = next(b for b in document.blocks if b.location.model_dump(exclude_none=True) == location)
    assert same_place(obs["location"], block)


@pytest.mark.parametrize(
    "override, reason",
    [
        ({"line": "L999"}, "unknown_line"),
        ({"raw_text": "987654321"}, "not_in_line"),
        ({"attribute": "warp_drive"}, "unknown_attribute"),
    ],
)
def test_ungrounded_values_are_rejected_not_facts(
    onto: Ontology, document: ParsedDocument, override: dict[str, Any], reason: str
) -> None:
    result = run(onto, document, "B", [b_item(document, numeric_attribute()) | override])
    assert result.facts == [] and [r.reason for r in result.rejected] == [reason]


def test_wrong_type_in_b_is_a_schema_rejection(onto: Ontology, document: ParsedDocument) -> None:
    item = b_item(document, numeric_attribute()) | {"value": "not a number"}
    result = run(onto, document, "B", [item])
    assert result.facts == [] and result.rejected[0].reason == "schema"


def test_two_values_in_one_context_stay_two_facts(onto: Ontology, document: ParsedDocument) -> None:
    """Different values are never merged (E5 keeps the conflicting set).

    Grounding checks the cited raw_text, not the model's normalized value: a mode-B value
    that differs from its raw text survives here and is caught only by scoring (CP-S3 note).
    """
    first = b_item(document, numeric_attribute())
    second = first | {"value": first["value"] + 1}
    result = run(onto, document, "B", [first, second])
    assert sorted(f["value"] for f in result.facts) == [first["value"], first["value"] + 1]


def test_repeated_identical_value_is_one_fact(onto: Ontology, document: ParsedDocument) -> None:
    item = b_item(document, numeric_attribute())
    result = run(onto, document, "B", [item, dict(item)])
    assert len(result.facts) == 1 and len(result.facts[0]["occurrences"]) == 2


def test_mode_c_keeps_text_as_written(onto: Ontology, document: ParsedDocument) -> None:
    item = b_item(document, numeric_attribute())
    c_item = {k: v for k, v in item.items() if k not in ("value", "unit", "raw_text")}
    c_item |= {"value_text": item["raw_text"], "unit_text": item["unit"]}
    result = run(onto, document, "C", [c_item])
    assert result.facts == [] and len(result.raw) == 1
    assert result.raw[0].value_text == item["raw_text"]


def test_mode_a_maps_only_exact_attribute_ids(onto: Ontology, document: ParsedDocument) -> None:
    attribute = numeric_attribute()
    item = b_item(document, attribute)
    reply = {
        "attributes": {attribute.upper(): item["raw_text"], "Bore size": "1"},
        "lines": {attribute.upper(): item["line"]},
    }
    result = run(onto, document, "A", [reply])
    assert [f["attribute"] for f in result.facts] == [attribute]
    assert [r.reason for r in result.rejected] == ["unknown_attribute"]


def test_llm_failure_marks_the_document(onto: Ontology, document: ParsedDocument) -> None:
    provider = FakeProvider([LlmError("extract-B", "timeout")])
    result = extract(onto, document, ANSWER["expected_class"], provider, "B")
    assert result.llm_failed and result.error == "timeout" and result.facts == []


@pytest.mark.parametrize("mode", ["B", "C"])
def test_context_fields_are_required_but_may_be_empty(onto: Ontology, mode: Any) -> None:
    schema = extraction_schema(onto, ANSWER["expected_class"], mode)
    for item in schema["properties"]["facts"]["items"]["anyOf"]:
        assert {"basis", "condition", "scope"} <= set(item["required"])
        assert "required" not in item["properties"]["basis"]
        assert "required" not in item["properties"]["condition"]


def test_schema_offers_only_class_attributes(onto: Ontology) -> None:
    schema = extraction_schema(onto, ANSWER["expected_class"], "C")
    items = schema["properties"]["facts"]["items"]["anyOf"]
    names = [i["properties"]["attribute"]["enum"][0] for i in items]
    assert names == onto.attributes_of(ANSWER["expected_class"])
    assert all(i["properties"]["value_text"] == {"type": "string"} for i in items)


@pytest.mark.parametrize(
    "text, token",
    [
        ("for complete pump unit with motor and base", "complete_pump_unit_with_motor_and_base"),
        ("main pump", "main_pump"),
        (None, "main_equipment"),
        ("", "main_equipment"),
    ],
)
def test_scope_token(text: str | None, token: str) -> None:
    assert scope_token(text) == token


def test_an_item_off_the_schema_is_rejected_not_a_crash(
    onto: Ontology, document: ParsedDocument
) -> None:
    """D-067 residual (W6-0): a provider without strict output may put a string or a list
    where an item object belongs; that item is rejected and the rest is still read."""
    item = b_item(document, numeric_attribute())
    c_item = {k: v for k, v in item.items() if k not in ("value", "unit", "raw_text")}
    c_item |= {"value_text": item["raw_text"], "unit_text": item["unit"]}
    result = run(onto, document, "C", ["bore 210 mm", ["x"], c_item])
    assert len(result.raw) == 1
    assert [r.reason for r in result.rejected] == ["not_an_object", "not_an_object"]
    assert [r.text for r in result.rejected] == ["bore 210 mm", "['x']"]
