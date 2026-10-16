"""Values that did not become a standard term (W6-5 보완 1, D-091).

The normalizer turns a written value into the dictionary's term when it knows the
spelling, and otherwise keeps the text as written (`Normalizer._token`). A kept text is
not an error the validator can see unless the class has an allowed list (E4). So the
review shows it to the reviewer, who either corrects it to a term or confirms it as
written. Nothing is changed here, and no term is guessed.

The terms are the dictionary's (master data, H3). Attributes with an allowed list are
left to E4 (the validator's own lookup is reused so the two cannot drift); maker and
model have their own checks and no dictionary terms.
"""

from typing import Any

from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.validate.validator import _allowed

Enums = dict[str, dict[str, str]]  # attribute -> written form (casefolded) -> term


class TermNote(StrictModel):
    key: str  # what the reviewer acknowledges: TERM|attribute|value
    fact_index: int
    attribute: str
    value: str  # the item as written
    known: list[str]  # the dictionary's terms for the attribute
    message: str


def _items(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, str)]


def _message(attribute: str, value: str, known: list[str]) -> str:
    return (
        f"{attribute} '{value}' — 표준 용어로 바뀌지 않은 값. "
        f"사전 용어: {', '.join(known)}. 용어로 고치거나 적힌 그대로 확인하세요"
    )


def term_notes(
    onto: Ontology, class_id: str, facts: list[dict[str, Any]], enums: Enums
) -> list[TermNote]:
    allowed = _allowed(onto, class_id) if class_id in onto.classes else {}
    notes: list[TermNote] = []
    for index, fact in enumerate(facts):
        attribute = fact["attribute"]
        if attribute not in enums or attribute in allowed:
            continue
        known = sorted(set(enums[attribute].values()))
        notes += [
            TermNote(
                key=f"TERM|{attribute}|{item}",
                fact_index=index,
                attribute=attribute,
                value=item,
                known=known,
                message=_message(attribute, item, known),
            )
            for item in _items(fact["value"])
            if item not in known
        ]
    return notes
