"""W5-2: human edits go through the deterministic normalizer and keep a document place."""

from typing import Any

import pytest

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
