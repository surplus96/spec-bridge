"""LLM output schemas for extraction modes B and C, generated from the ontology (W3-4).

B: the model normalizes (typed values, canonical unit, structured condition quantities).
C: the model copies the text as written; deterministic code normalizes later (W3-5).
Both cite a line id and choose basis/condition tokens from the ontology vocabulary.
"""

from typing import Any, Literal

import pint

from spec_bridge.ontology.definitions import Ontology

Mode = Literal["B", "C"]

VALUE_SCHEMAS: dict[str, dict[str, Any]] = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "integer": {"type": "integer"},
    "boolean": {"type": "boolean"},
    "string_set": {"type": "array", "items": {"type": "string"}},
    "range": {
        "type": "object",
        "properties": {"min": {"type": "number"}, "max": {"type": "number"}},
        "required": ["min", "max"],
    },
    "dimensions": {
        "type": "object",
        "properties": {
            axis: {"type": ["number", "null"]} for axis in ("length", "width", "height")
        },
        "required": ["length", "width", "height"],
    },
}


def units_of_dimension(onto: Ontology, dimension: str) -> list[str]:
    ureg = pint.UnitRegistry()
    target = ureg.get_dimensionality(onto.dimensions[dimension])
    return [
        u for u, spec in onto.units.items() if ureg.parse_units(spec.pint).dimensionality == target
    ]


def _quantity(onto: Ontology, dimension: str, with_reference: bool) -> dict[str, Any]:
    props: dict[str, Any] = {
        "value": {"type": "number"},
        "unit": {"type": "string", "enum": units_of_dimension(onto, dimension)},
    }
    if with_reference:
        props["reference_temperature"] = _quantity(onto, "temperature", False)
    return {"type": "object", "properties": props, "required": ["value", "unit"]}


# Context questions (W4-1, D-039). "optional": the model may leave basis, condition and
# scope out. "required_none": all three are required and "none" is an explicit choice, so
# the model decides the context for every value without being pushed to invent one.
ContextStyle = Literal["optional", "required_none"]
CONTEXT = ("basis", "condition", "scope")
NONE = "none"
# Contract context defaults mean "not stated"; the model says that by omission or "none",
# never by choosing these tokens (they could only produce keys no answer has, D-039).
HIDDEN = {"unknown", "not_applicable"}


def _described(prop: dict[str, Any], texts: dict[str, str], tokens: list[str]) -> dict[str, Any]:
    """Attach the ontology description of an axis and its tokens, if any."""
    parts = [texts["_"]] if "_" in texts else []
    named = [f"{t}: {texts[t]}" for t in tokens if t in texts]
    if named:
        parts.append("Tokens - " + "; ".join(named))
    return prop | {"description": " ".join(parts)} if parts else prop


def _context(
    onto: Ontology, mode: Mode, context: ContextStyle
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    vocab, extra = onto.vocabularies, [NONE] if context == "required_none" else []
    described = vocab.descriptions
    basis_props: dict[str, Any] = {}
    for axis, values in vocab.basis.items():
        tokens = [v for v in values if v not in HIDDEN]
        prop = {"type": "string", "enum": tokens + extra}
        texts = described.basis.get(axis, {}) if described else {}
        basis_props[axis] = _described(prop, texts, tokens)
    condition_props: dict[str, Any] = {}
    for key, cond in vocab.condition.items():
        tokens = [v for v in cond.values if v not in HIDDEN]
        if cond.kind == "token":
            prop = {"type": "string", "enum": tokens + extra}
        elif mode == "C":
            prop = {"type": "string"}  # e.g. "380 cSt at 50 degC" as written
        else:
            assert cond.dimension is not None
            prop = _quantity(onto, cond.dimension, cond.kind == "reference_quantity")
        texts = described.condition.get(key, {}) if described else {}
        condition_props[key] = _described(prop, texts, tokens)
    scope: dict[str, Any] = {"type": "string"}
    if described and context in described.scope:
        scope["description"] = described.scope[context]
    return (
        {"type": "object", "properties": basis_props},
        {"type": "object", "properties": condition_props},
        scope,
    )


def extraction_schema(
    onto: Ontology, class_id: str, mode: Mode, context: ContextStyle = "required_none"
) -> dict[str, Any]:
    basis, condition, scope = _context(onto, mode, context)
    common: dict[str, Any] = {
        "label": {"type": "string"},
        "basis": basis,
        "condition": condition,
        "scope": scope,
        "line": {"type": "string"},
    }
    asked = list(CONTEXT) if context == "required_none" else []
    items: list[dict[str, Any]] = []
    for attr_id in onto.attributes_of(class_id):
        attr = onto.attributes[attr_id]
        props: dict[str, Any] = {"attribute": {"type": "string", "enum": [attr_id]}, **common}
        if mode == "C":
            props["value_text"] = {"type": "string"}
            props["unit_text"] = {"type": ["string", "null"]}
            required = ["attribute", "value_text", "line", *asked]
        else:
            names = attr.datatype if isinstance(attr.datatype, list) else [attr.datatype]
            value = (
                VALUE_SCHEMAS[names[0]]
                if len(names) == 1
                else {"anyOf": [VALUE_SCHEMAS[n] for n in names]}
            )
            unit = (
                {"type": "null"}
                if attr.canonical_unit is None
                else {"type": "string", "enum": [attr.canonical_unit]}
            )
            props.update({"value": value, "unit": unit, "raw_text": {"type": "string"}})
            required = ["attribute", "value", "unit", "raw_text", "line", *asked]
        items.append({"type": "object", "properties": props, "required": required})
    return {
        "type": "object",
        "properties": {"facts": {"type": "array", "items": {"anyOf": items}}},
        "required": ["facts"],
    }
