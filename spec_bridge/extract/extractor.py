"""Extraction (W3-4, FR-07): the model reports values and the line they are on; code
attaches the parser position, keeps every occurrence and rejects ungrounded values.

Modes: A free JSON (no schema), B schema with model-normalized values, C schema with
values as written (normalized by W3-5). An LlmError never escapes: the document is
marked failed and its gold facts count as misses.
"""

import json
import re
from typing import Any, Literal

from pydantic import ValidationError

from spec_bridge.extract.prompt_input import has_token, render_lines
from spec_bridge.extract.schemas import NONE, ContextStyle, extraction_schema
from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.ontology.schema import build_candidate_model
from spec_bridge.parse.blocks import Block, ParsedDocument

Mode = Literal["A", "B", "C"]
Config = Literal["R", "A", "B", "C", "E"]  # R: rule baseline (spec_bridge/extract/rules.py)
Reason = Literal[
    "unknown_attribute",
    "unknown_line",
    "not_in_line",
    "ambiguous_in_line",
    "schema",
    "not_an_object",
]

SYSTEM = (
    "You extract technical data about the main product from a marine equipment "
    "specification. Report every occurrence of every value, including repeats. Copy text "
    "exactly as written. For 'line' give the line id (for example L9) that holds the value. "
    "Never invent values that are not in the lines."
)


class RawObservation(StrictModel):
    """A grounded value as written (mode C); W3-5 normalizes it into a fact."""

    attribute: str
    value_text: str
    unit_text: str | None
    basis: dict[str, str]
    condition: dict[str, Any]
    scope: str
    occurrence: dict[str, Any]


class Rejected(StrictModel):
    attribute: str
    text: str
    line: str
    reason: Reason


class Extraction(StrictModel):
    document_id: str
    class_id: str
    mode: Config
    facts: list[dict[str, Any]] = []
    raw: list[RawObservation] = []
    rejected: list[Rejected] = []
    llm_failed: bool = False
    error: str | None = None
    reply: dict[str, Any] | None = None  # the model's JSON as returned, kept for diagnosis


def scope_token(text: str | None) -> str:
    """'for complete pump unit with motor and base' -> 'complete_pump_unit_with_motor_and_base'."""
    words = re.sub(r"^\s*for\s+", "", (text or "").strip().lower())
    token = re.sub(r"[^a-z0-9]+", "_", words).strip("_")
    return "main_equipment" if token in ("", NONE) else token


def _ground(
    lines: list[list[Block]], line_id: str, text: str
) -> tuple[Block | None, Reason | None]:
    number = line_id.strip().upper().removeprefix("L")
    if not number.isdigit() or not 1 <= int(number) <= len(lines):
        return None, "unknown_line"
    hits = [b for b in lines[int(number) - 1] if has_token(b.text, text.strip())]
    if not hits:
        return None, "not_in_line"
    if len(hits) > 1:
        return None, "ambiguous_in_line"
    return hits[0], None


def _occurrence(
    document: ParsedDocument, block: Block, text: str, item: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source_document_id": document.document_id,
        "raw_text": text.strip(),
        "label_text": item.get("label"),
        "unit_text": item.get("unit_text"),
        "location": block.location.model_dump(exclude_none=True),
    }


def merge_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same attribute, value and context -> one fact with several occurrences."""
    merged: dict[str, dict[str, Any]] = {}
    for fact in facts:
        key = json.dumps(
            {k: fact[k] for k in ("attribute", "value", "unit", "basis", "condition", "scope")},
            sort_keys=True,
        )
        if key in merged:
            merged[key]["occurrences"] += fact["occurrences"]
        else:
            merged[key] = fact
    return list(merged.values())


def extract(
    onto: Ontology,
    document: ParsedDocument,
    class_id: str,
    provider: JsonProvider,
    mode: Mode,
    context: ContextStyle = "required_none",
) -> Extraction:
    text, lines = render_lines(document)
    result = Extraction(document_id=document.document_id, class_id=class_id, mode=mode)
    attributes = onto.attributes_of(class_id)
    try:
        reply = provider.complete_json(
            system=SYSTEM,
            user=_prompt(onto, class_id, mode, text, context),
            schema=None if mode == "A" else extraction_schema(onto, class_id, mode, context),
            task=f"extract-{mode}",
        )
    except LlmError as error:
        result.llm_failed, result.error = True, error.reason
        return result
    result.reply = reply
    items = _items_from_free_json(reply, attributes) if mode == "A" else reply.get("facts", [])
    facts: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):  # off the schema (no strict output): skip it only
            result.rejected.append(
                Rejected(attribute="", text=str(item), line="", reason="not_an_object")
            )
            continue
        attribute = str(item.get("attribute", ""))
        evidence = str(item.get("value_text" if mode == "C" else "raw_text", "")) or str(
            item.get("value", "")
        )
        line_id = str(item.get("line", ""))
        if attribute not in attributes:
            result.rejected.append(
                Rejected(
                    attribute=attribute, text=evidence, line=line_id, reason="unknown_attribute"
                )
            )
            continue
        block, reason = _ground(lines, line_id, evidence)
        if block is None:
            assert reason is not None
            result.rejected.append(
                Rejected(attribute=attribute, text=evidence, line=line_id, reason=reason)
            )
            continue
        occurrence = _occurrence(document, block, evidence, item)
        basis = {k: v for k, v in (item.get("basis") or {}).items() if v and v != NONE}
        condition = {
            k: v for k, v in (item.get("condition") or {}).items() if v not in (None, "", NONE)
        }
        scope = scope_token(item.get("scope"))
        if mode == "C":
            result.raw.append(
                RawObservation(
                    attribute=attribute,
                    value_text=str(item["value_text"]),
                    unit_text=item.get("unit_text") or None,
                    basis=basis,
                    condition=condition,
                    scope=scope,
                    occurrence=occurrence,
                )
            )
            continue
        facts.append(
            {
                "attribute": attribute,
                "value": item.get("value"),
                "unit": item.get("unit"),
                "basis": basis,
                "condition": condition,
                "scope": scope,
                "occurrences": [occurrence],
            }
        )
    merged = merge_facts(facts)
    # Mode A is the schema-free baseline: its facts go to scoring unvalidated (D-025 item 3).
    result.facts = merged if mode == "A" else validate_facts(onto, class_id, merged, result)
    return result


def validate_facts(
    onto: Ontology, class_id: str, facts: list[dict[str, Any]], result: Extraction
) -> list[dict[str, Any]]:
    """Keep facts the W1 candidate model accepts; others are schema rejections."""
    model = build_candidate_model(onto, class_id)
    kept = []
    for fact in facts:
        body = {k: v for k, v in fact.items() if k != "attribute"}
        try:
            model.model_validate({"attributes": {fact["attribute"]: [body]}})
        except ValidationError:
            occurrence = fact["occurrences"][0]
            result.rejected.append(
                Rejected(
                    attribute=fact["attribute"],
                    text=occurrence["raw_text"],
                    line="",
                    reason="schema",
                )
            )
            continue
        kept.append(fact)
    return kept


def _items_from_free_json(reply: dict[str, Any], attributes: list[str]) -> list[dict[str, Any]]:
    """Mode A: free keys count only when they equal an attribute id (casefold)."""
    by_name = {a.casefold(): a for a in attributes}
    values = reply.get("attributes") if isinstance(reply.get("attributes"), dict) else {}
    lines = reply.get("lines") if isinstance(reply.get("lines"), dict) else {}
    items = []
    for name, value in (values or {}).items():
        attribute = by_name.get(str(name).casefold(), str(name))
        items.append(
            {
                "attribute": attribute,
                "value": value,
                "unit": None,
                "raw_text": str(value),
                "line": str((lines or {}).get(name, "")),
            }
        )
    return items


FIELD_GUIDE = {
    "B": (
        "Fields: 'value' is the value converted to the attribute's canonical unit and type; "
        "'raw_text' is only the value exactly as written in its cell or after its label, "
        "without the label, the unit or the conditions; 'unit' is the canonical unit."
    ),
    "C": (
        "Fields: 'value_text' is only the value exactly as written in its cell or after its "
        "label, without the label, the unit or the conditions; 'unit_text' is the unit exactly "
        "as written (null if none). Do not convert."
    ),
}


CONTEXT_GUIDE = {
    "optional": "basis, condition and scope describe the value only when the document states them.",
    "required_none": (
        "Always give basis, condition and scope for every value; choose 'none' where the "
        "document states nothing. Field descriptions explain each token."
    ),
}


def _prompt(
    onto: Ontology, class_id: str, mode: Mode, text: str, context: ContextStyle = "required_none"
) -> str:
    if mode == "A":
        return (
            "Extract the product information as JSON with keys 'attributes' (name -> value) "
            "and 'lines' (name -> line id).\n\nDocument lines:\n" + text
        )
    attrs = "\n".join(f"- {a}" for a in onto.attributes_of(class_id))
    common = (
        "'label' is the row or line label; 'line' is the line id holding the value; "
        + CONTEXT_GUIDE[context]
    )
    return (
        f"Product class: {class_id}\nAttributes:\n{attrs}\n{FIELD_GUIDE[mode]} {common}"
        f"\n\nDocument lines:\n{text}"
    )
