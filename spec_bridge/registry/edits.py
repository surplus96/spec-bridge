"""Human edits (W5-2, S1): a reviewer changes, adds or removes a value before registering.

An edit goes through the same deterministic normalizer as extracted values, so a wrong
unit or a malformed number becomes an unresolved value and the validator reports it
(E2/E3/REVIEW) instead of the edit being trusted. Every fact must keep a place in the
document (the validator and the candidate model require an occurrence, NFR-07):
- set: the corrected value keeps the occurrences where the original was read;
- add: the reviewer points at the document block the value was read from.
A value that is nowhere in the document cannot be added (D-063 note in the W5 report).

Context (basis, condition, scope) is not edited in W5: a corrected fact keeps its
context; a value from an unresolved row or a new block gets the empty context.
"""

from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError

from spec_bridge.normalize.values import NormalizationError, Normalizer
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.ontology.schema import build_candidate_model
from spec_bridge.parse.blocks import ParsedDocument

NO_SCOPE = "main_equipment"  # what the extractor writes for "no scope" (scope_token)


class FactEdit(StrictModel):
    op: Literal["set", "add", "remove"]
    target: Literal["fact", "unresolved"] | None = None  # set / remove
    index: int | None = None  # position in the current facts or unresolved list
    attribute: str | None = None  # add
    block: int | None = None  # add: the document block the value was read from
    value_text: str | None = None  # set / add
    unit_text: str | None = None
    reason: Annotated[str, Field(min_length=1)]


class EditRejected(ValueError):
    """The edit does not fit the job (bad index, attribute of another class, ...)."""


def _pick(edit: FactEdit, facts: list[Any], unresolved: list[Any]) -> dict[str, Any]:
    rows = facts if edit.target == "fact" else unresolved
    if edit.target is None or edit.index is None or not 0 <= edit.index < len(rows):
        raise EditRejected(f"{edit.op}: no {edit.target or 'target'} at index {edit.index}")
    row: dict[str, Any] = rows[edit.index]
    return row


def _read(
    onto: Ontology,
    normalizer: Normalizer,
    class_id: str,
    attribute: str,
    edit: FactEdit,
    context: dict[str, Any],
    occurrences: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(fact, None) or (None, unresolved row): the normalizer decides, as for extraction."""
    if not edit.value_text:
        raise EditRejected(f"{edit.op}: a value is required")
    try:
        value, unit = normalizer.value(attribute, edit.value_text, edit.unit_text)
    except NormalizationError as error:
        row = {
            "attribute": attribute,
            "value_text": edit.value_text,
            "unit_text": edit.unit_text,
            "reason": error.reason,
            "occurrence": occurrences[0],
        }
        return None, row
    fact = {"attribute": attribute, "value": value, "unit": unit, **context}
    fact["occurrences"] = occurrences
    body = {k: v for k, v in fact.items() if k != "attribute"}
    try:
        build_candidate_model(onto, class_id).model_validate({"attributes": {attribute: [body]}})
    except ValidationError as error:
        raise EditRejected(f"{attribute}: the value does not fit the attribute") from error
    return fact, None


def apply_edit(
    onto: Ontology,
    normalizer: Normalizer,
    document: ParsedDocument,
    class_id: str,
    facts: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    edit: FactEdit,
    edit_id: str,
    at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Apply one edit; return the new facts, the new unresolved rows and the HumanEdit row
    (previous value, new value, reason, time). The inputs are not changed."""
    facts, unresolved = list(facts), list(unresolved)
    empty = {"basis": {}, "condition": {}, "scope": NO_SCOPE}
    before: dict[str, Any] | None = None
    if edit.op == "remove":
        before = _pick(edit, facts, unresolved)
        (facts if edit.target == "fact" else unresolved).remove(before)
        attribute, fact, row = before["attribute"], None, None
    elif edit.op == "set":
        before = _pick(edit, facts, unresolved)
        attribute = before["attribute"]
        if edit.target == "fact":
            context = {k: before[k] for k in ("basis", "condition", "scope")}
            occurrences = before["occurrences"]  # every place the old value was read
        else:
            context, occurrences = empty, [before["occurrence"]]
        fact, row = _read(onto, normalizer, class_id, attribute, edit, context, occurrences)
        (facts if edit.target == "fact" else unresolved).remove(before)
    else:  # add
        if edit.attribute not in onto.attributes_of(class_id):
            raise EditRejected(f"add: {edit.attribute!r} is not an attribute of {class_id}")
        if edit.block is None or not 0 <= edit.block < len(document.blocks):
            raise EditRejected("add: point at the document block the value was read from")
        attribute = edit.attribute
        occurrence = {
            "source_document_id": document.document_id,
            "raw_text": edit.value_text or "",
            "label_text": None,
            "unit_text": edit.unit_text,
            "location": document.blocks[edit.block].location.model_dump(exclude_none=True),
        }
        fact, row = _read(onto, normalizer, class_id, attribute, edit, empty, [occurrence])
    if fact is not None:
        facts.append(fact)
    if row is not None:
        unresolved.append(row)
    record = {
        "edit_id": edit_id,
        "op": edit.op,
        "attribute": attribute,
        "before": before,
        "after": fact or row,
        "outcome": "removed" if edit.op == "remove" else ("fact" if fact else "unresolved"),
        "reason": edit.reason,
        "at": at,
    }
    return facts, unresolved, record
