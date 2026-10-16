"""W6-5 보완 1 (D-091): a value the dictionary did not turn into a standard term is shown
to the reviewer instead of being registered silently.

Terms come from the dictionary and allowed lists from the ontology (H3: no domain values
written here).
"""

from typing import Any

from spec_bridge.normalize.dictionary import load_dictionary
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.registry.terms import term_notes
from tests.conftest import ONTOLOGY

ONTO = load_ontology(ONTOLOGY)
ENUMS: dict[str, dict[str, str]] = load_dictionary()["enums"]


def _allowed(class_id: str, attribute: str) -> list[str]:
    allowed: list[str] = []
    for name in [*reversed(ONTO.ancestors(class_id)), class_id]:
        allowed = ONTO.classes[name].allowed_values.get(attribute, allowed)
    return allowed


def _case() -> tuple[str, str, str]:
    """A class, a string attribute of it with dictionary terms and no allowed list, and
    one of those terms."""
    for class_id in ONTO.classes:
        for attribute in ONTO.attributes_of(class_id):
            datatype = ONTO.attributes[attribute].datatype
            if attribute in ENUMS and datatype == "string" and not _allowed(class_id, attribute):
                return class_id, attribute, sorted(set(ENUMS[attribute].values()))[0]
    raise AssertionError("the dictionary has no such attribute")


CLASS, ATTRIBUTE, TERM = _case()


def _fact(attribute: str, value: Any) -> dict[str, Any]:
    return {"attribute": attribute, "value": value, "unit": None, "occurrences": []}


def test_a_standard_term_gives_no_note() -> None:
    assert term_notes(ONTO, CLASS, [_fact(ATTRIBUTE, TERM)], ENUMS) == []


def test_a_value_outside_the_terms_is_noted_with_the_terms_it_could_be() -> None:
    facts = [_fact("maker", "anything"), _fact(ATTRIBUTE, "Not A Listed Term")]
    (note,) = term_notes(ONTO, CLASS, facts, ENUMS)
    assert note.fact_index == 1 and note.attribute == ATTRIBUTE
    assert note.value == "Not A Listed Term"
    assert note.known == sorted(set(ENUMS[ATTRIBUTE].values()))
    assert note.key == f"TERM|{ATTRIBUTE}|Not A Listed Term"
    assert "표준 용어" in note.message and TERM in note.message


def test_each_unlisted_item_of_a_set_is_noted() -> None:
    attribute = next(a for a in ENUMS if ONTO.attributes[a].datatype == "string_set")
    class_id = next(c for c in ONTO.classes if attribute in ONTO.attributes_of(c))
    term = sorted(set(ENUMS[attribute].values()))[0]
    (note,) = term_notes(ONTO, class_id, [_fact(attribute, [term, "A / B"])], ENUMS)
    assert note.value == "A / B"


def test_an_attribute_with_an_allowed_list_is_left_to_the_validator() -> None:
    """E4 already reports values outside a class's allowed list."""
    class_id, attribute = next((c, a) for c in ONTO.classes for a in ENUMS if _allowed(c, a))
    assert term_notes(ONTO, class_id, [_fact(attribute, "Not A Listed Term")], ENUMS) == []


def test_an_attribute_without_dictionary_terms_is_not_checked() -> None:
    attribute = next(a for a in ONTO.attributes_of(CLASS) if a not in ENUMS and a != "maker")
    assert term_notes(ONTO, CLASS, [_fact(attribute, "free text")], ENUMS) == []
