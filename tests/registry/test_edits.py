"""W5-2: human edits go through the deterministic normalizer and keep a document place."""

from typing import Any

import pytest

from spec_bridge.extract.extractor import scope_token
from spec_bridge.extract.schemas import units_of_dimension
from spec_bridge.normalize.dictionary import load_dictionary
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.pipeline import process_document
from spec_bridge.registry.edits import EditRejected, FactEdit, apply_edit
from spec_bridge.service import normalizer_for
from tests.api.test_app import DOC_ID, PATH, service_with
from tests.conftest import ONTOLOGY
from tests.test_pipeline import replies

ONTO = load_ontology(ONTOLOGY)
NORMALIZER = normalizer_for(ONTO, "dev", load_dictionary())
DOCUMENT = parse_document(PATH, DOC_ID)


def facts() -> tuple[str, list[dict[str, Any]]]:
    s = service_with(replies())
    result = process_document(
        PATH,
        DOC_ID,
        onto=s.onto,
        normalizer=s.normalizer,
        provider=s.provider,
        rag=s.rag,
        registry=s.registry,
        makers=s.makers,
    )
    return result.class_id, result.facts


def run(class_id: str, rows: list[dict[str, Any]], **change: Any) -> Any:
    edit = FactEdit(reason="test", **change)
    return apply_edit(ONTO, NORMALIZER, DOCUMENT, class_id, rows, [], edit, "J-E1", "t")


def test_set_keeps_the_context_and_the_places_it_was_read() -> None:
    class_id, rows = facts()
    before = rows[0]
    text = str(before["value"] + 1)
    new, unresolved, record = run(
        class_id, rows, op="set", target="fact", index=0, value_text=text, unit_text=before["unit"]
    )
    assert unresolved == [] and rows == [before]  # the input is not changed
    assert new[0]["value"] == before["value"] + 1
    assert new[0]["occurrences"] == before["occurrences"]
    assert {k: new[0][k] for k in ("basis", "condition", "scope")} == {
        k: before[k] for k in ("basis", "condition", "scope")
    }
    assert record["before"] == before and record["after"] == new[0]
    assert record["outcome"] == "fact" and record["reason"] == "test"


def test_a_wrong_unit_is_left_unresolved_for_the_validator() -> None:
    class_id, rows = facts()
    new, unresolved, record = run(
        class_id, rows, op="set", target="fact", index=0, value_text="1", unit_text="kg"
    )
    assert new == [] and unresolved[0]["reason"] == "dimension"
    assert unresolved[0]["occurrence"] == rows[0]["occurrences"][0]
    assert record["outcome"] == "unresolved"


def test_remove_records_the_old_value() -> None:
    class_id, rows = facts()
    new, _, record = run(class_id, rows, op="remove", target="fact", index=0)
    assert new == [] and record["before"] == rows[0] and record["after"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"op": "remove", "target": "fact", "index": 5},
        {"op": "set", "target": "fact", "index": 0},  # no value
        {"op": "add", "attribute": "head", "block": 0, "value_text": "1"},  # not this class
        {"op": "add", "attribute": "rated_speed", "value_text": "1"},  # no document place
    ],
)
def test_edits_that_do_not_fit_are_refused(change: dict[str, Any]) -> None:
    class_id, rows = facts()
    with pytest.raises(EditRejected):
        run(class_id, rows, **change)


# context (D-100) -----------------------------------------------------------------------
VOCAB = ONTO.vocabularies
RATING = VOCAB.basis["rating"][0]  # tokens come from the ontology, not from memory (H3)
POINT = next(k for k, c in VOCAB.condition.items() if c.kind == "token")
POINT_TOKEN = VOCAB.condition[POINT].values[0]
FREQUENCY = next(k for k, c in VOCAB.condition.items() if c.kind == "quantity")


def context(class_id: str, rows: list[dict[str, Any]], axis: str, text: str | None) -> Any:
    return run(class_id, rows, op="context", target="fact", index=0, axis=axis, value_text=text)


def scope_phrase() -> str:
    """A 'for …' phrase that the test document really holds."""
    text = next(b.text for b in DOCUMENT.blocks if "; for " in b.text)
    return text.split("; ", 1)[1]


def test_a_basis_token_from_the_vocabulary_is_set_and_recorded() -> None:
    class_id, rows = facts()
    before = rows[0]
    new, unresolved, record = context(class_id, rows, "basis.rating", RATING)
    assert unresolved == [] and rows == [before]  # the input is not changed
    assert new[0]["basis"] == {**before["basis"], "rating": RATING}
    assert new[0]["value"] == before["value"] and new[0]["occurrences"] == before["occurrences"]
    assert record["op"] == "context" and record["axis"] == "basis.rating"
    assert record["before"] == before and record["after"] == new[0]
    assert record["outcome"] == "fact"


def test_a_condition_token_and_a_quantity_go_through_the_normalizer() -> None:
    class_id, rows = facts()
    new, _, _ = context(class_id, rows, f"condition.{POINT}", POINT_TOKEN)
    assert new[0]["condition"][POINT] == POINT_TOKEN
    unit = units_of_dimension(ONTO, VOCAB.condition[FREQUENCY].dimension or "")[0]
    new, _, _ = context(class_id, rows, f"condition.{FREQUENCY}", f"50 {unit}")
    assert new[0]["condition"][FREQUENCY] == {"value": 50, "unit": unit}


def test_clearing_an_axis_removes_it() -> None:
    class_id, rows = facts()
    with_rating, _, _ = context(class_id, rows, "basis.rating", RATING)
    cleared, _, _ = context(class_id, with_rating, "basis.rating", None)
    assert "rating" not in cleared[0]["basis"]
    unknown, _, _ = context(class_id, with_rating, "basis.rating", "unknown")
    assert unknown[0]["basis"] == cleared[0]["basis"]


def test_a_scope_phrase_must_be_in_the_document() -> None:
    class_id, rows = facts()
    phrase = scope_phrase()
    new, _, _ = context(class_id, rows, "scope", phrase.upper())  # case does not matter
    assert new[0]["scope"] == scope_token(phrase)
    with pytest.raises(EditRejected, match="not in the document"):
        context(class_id, rows, "scope", "for a phrase nowhere in the sheet")
    none, _, _ = context(class_id, rows, "scope", "")
    assert none[0]["scope"] == "main_equipment"


@pytest.mark.parametrize(
    ("axis", "text"),
    [
        ("basis.rating", "a word outside the vocabulary"),
        ("basis.no_such_axis", "x"),
        ("condition.no_such_axis", "x"),
        (f"condition.{FREQUENCY}", "fifty"),  # not a quantity
        (f"condition.{FREQUENCY}", "50 kg"),  # wrong dimension
        ("value", "1"),  # not a context axis
        (None, "x"),
    ],
)
def test_context_edits_that_do_not_fit_are_refused(axis: str | None, text: str) -> None:
    class_id, rows = facts()
    with pytest.raises(EditRejected):
        context(class_id, rows, axis, text)  # type: ignore[arg-type]


def test_a_context_edit_that_changes_nothing_or_copies_another_fact_is_refused() -> None:
    class_id, rows = facts()
    with pytest.raises(EditRejected, match="nothing changed"):
        context(class_id, rows, "scope", rows[0]["scope"].replace("_", " "))
    twin = {**rows[0], "basis": {"rating": RATING}}
    with pytest.raises(EditRejected, match="same as another fact"):
        context(class_id, [rows[0], twin], "basis.rating", RATING)


def test_context_is_edited_on_facts_only() -> None:
    class_id, rows = facts()
    row = {"attribute": "rated_power", "value_text": "x", "unit_text": None, "reason": "parse"}
    with pytest.raises(EditRejected):
        apply_edit(
            ONTO,
            NORMALIZER,
            DOCUMENT,
            class_id,
            rows,
            [row | {"occurrence": rows[0]["occurrences"][0]}],
            FactEdit(op="context", target="unresolved", index=0, axis="scope", reason="t"),
            "J-E1",
            "t",
        )
