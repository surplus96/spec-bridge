"""Rule baseline R (W3-7): dev label dictionary + line layout, no LLM.

A table line reads `label | value | unit | remarks`; a text line reads
`label — value unit (remarks)`. The label must be in the dev dictionary; remarks
(basis, conditions, scope) are not interpreted, so R reports the default context.
Values go through the same deterministic normalizer as mode C.
"""

import re
from typing import Any

from spec_bridge.extract.extractor import Extraction, RawObservation
from spec_bridge.extract.prompt_input import group_lines
from spec_bridge.normalize.dictionary import label_key
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.parse.blocks import Block, ParsedDocument

SEPARATOR = " — "
REMARKS = re.compile(r"\s*\([^()]*\)\s*$")
EMPTY = {"", "—", "-"}


def read_line(
    onto: Ontology, line: list[Block], labels: dict[str, str]
) -> tuple[str, Block, str, str, str | None] | None:
    """(attribute, value block, label, value text, unit text) or None."""
    if len(line) > 1:  # table row
        label = line[0].text.strip()
        attribute = labels.get(label_key(label))
        if attribute is None:
            return None
        unit = line[2].text.strip() if len(line) > 2 else ""
        return attribute, line[1], label, line[1].text.strip(), None if unit in EMPTY else unit
    block = line[0]
    label, separator, rest = block.text.partition(SEPARATOR)
    attribute = labels.get(label_key(label)) if separator else None
    if attribute is None:
        return None
    value = REMARKS.sub("", rest).strip()
    if onto.attributes[attribute].canonical_unit is None or " " not in value:
        return attribute, block, label.strip(), value, None
    number, unit = value.rsplit(" ", 1)
    return attribute, block, label.strip(), number, unit


def rule_extract(
    onto: Ontology, document: ParsedDocument, class_id: str, labels: dict[str, str]
) -> Extraction:
    result = Extraction(document_id=document.document_id, class_id=class_id, mode="R")
    attributes = set(onto.attributes_of(class_id)) if class_id in onto.classes else set()
    for line in group_lines(document):
        found = read_line(onto, line, labels)
        if found is None or found[0] not in attributes:
            continue
        attribute, block, label, value, unit = found
        occurrence: dict[str, Any] = {
            "source_document_id": document.document_id,
            "raw_text": value,
            "label_text": label,
            "unit_text": unit,
            "location": block.location.model_dump(exclude_none=True),
        }
        result.raw.append(
            RawObservation(
                attribute=attribute,
                value_text=value,
                unit_text=unit,
                basis={},
                condition={},
                scope="main_equipment",
                occurrence=occurrence,
            )
        )
    return result
