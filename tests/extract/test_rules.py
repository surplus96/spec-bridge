from typing import Any

import pytest

from spec_bridge.extract.prompt_input import has_token
from spec_bridge.extract.rules import read_line, rule_extract
from spec_bridge.normalize.dictionary import build_dev_dictionary, load_dictionary
from spec_bridge.ontology.loader import Ontology
from spec_bridge.parse.blocks import Block
from spec_bridge.parse.dispatch import parse_document
from tests.parse.goldmatch import dev_documents

LABELS: dict[str, str] = load_dictionary()["labels"]
FAST_DEV = dev_documents("xlsx") + dev_documents("docx")


def cell(text: str, column: int) -> Block:
    return Block.model_validate(
        {"kind": "table_cell", "text": text, "location": {"table": 1, "row": 2, "column": column}}
    )


def paragraph(text: str) -> Block:
    return Block.model_validate({"kind": "paragraph", "text": text, "location": {"paragraph": 3}})


def label_with_unit(onto: Ontology, with_unit: bool) -> tuple[str, str]:
    """A dev label whose attribute has (or lacks) a canonical unit."""
    for label, attribute in LABELS.items():
        if (onto.attributes[attribute].canonical_unit is not None) is with_unit:
            return label, attribute
    raise LookupError("no such dev label")


def test_table_row_reads_the_value_and_unit_cells(onto: Ontology) -> None:
    label, attribute = label_with_unit(onto, True)
    line = [cell(f"{label.upper()}:", 1), cell("12", 2), cell("u", 3), cell("remark", 4)]
    assert read_line(onto, line, LABELS) == (attribute, line[1], f"{label.upper()}:", "12", "u")


def test_dash_unit_cell_is_no_unit(onto: Ontology) -> None:
    label, _ = label_with_unit(onto, False)
    line = [cell(label, 1), cell("x", 2), cell("—", 3)]
    found = read_line(onto, line, LABELS)
    assert found is not None and found[4] is None


def test_text_line_drops_remarks_and_splits_the_unit(onto: Ontology) -> None:
    label, attribute = label_with_unit(onto, True)
    block = paragraph(f"{label} — 1 to 2 u (remark; for x)")
    assert read_line(onto, [block], LABELS) == (attribute, block, label, "1 to 2", "u")


def test_text_value_without_unit_keeps_its_words(onto: Ontology) -> None:
    label, attribute = label_with_unit(onto, False)
    block = paragraph(f"{label} — two words")
    assert read_line(onto, [block], LABELS) == (attribute, block, label, "two words", None)


@pytest.mark.parametrize(
    "line", [[cell("Parameter", 1), cell("Value", 2)], [paragraph("Not a label — 5 u")]]
)
def test_unknown_labels_are_skipped(onto: Ontology, line: list[Block]) -> None:
    assert read_line(onto, line, LABELS) is None


def test_conflicting_labels_are_rejected() -> None:
    def obs(attribute: str) -> dict[str, Any]:
        return {
            "attribute_id": attribute,
            "label_text": "Weight:",
            "raw_text": "1",
            "interpretation": "normalized",
        }

    with pytest.raises(ValueError, match="maps to"):
        build_dev_dictionary([{"input_id": "X", "observations": [obs("a"), obs("b")]}])


@pytest.mark.parametrize("input_id, path, answer", FAST_DEV, ids=[i for i, _, _ in FAST_DEV])
def test_rule_occurrences_are_grounded_and_in_class(
    onto: Ontology, input_id: str, path: Any, answer: dict[str, Any]
) -> None:
    document = parse_document(path, input_id)
    extraction = rule_extract(onto, document, answer["expected_class"], LABELS)
    attributes = set(onto.attributes_of(answer["expected_class"]))
    assert extraction.raw
    for raw in extraction.raw:
        blocks = [
            b
            for b in document.blocks
            if b.location.model_dump(exclude_none=True) == raw.occurrence["location"]
        ]
        assert raw.attribute in attributes
        assert len(blocks) == 1 and has_token(blocks[0].text, raw.value_text)


def test_unknown_class_extracts_nothing(onto: Ontology) -> None:
    input_id, path, _ = FAST_DEV[0]
    document = parse_document(path, input_id)
    assert rule_extract(onto, document, "unknown", LABELS).raw == []
