"""Build per-class candidate models and JSON Schema from the ontology (FR-02)."""

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, create_model

from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import (
    Dimensions,
    NumericRange,
    Occurrence,
    Quantity,
    ReferenceQuantity,
    StrictModel,
    Text,
)

UniqueTexts = Annotated[list[Text], Field(min_length=1)]

VALUE_TYPES: dict[str, Any] = {
    "string": Text,
    "number": float,
    "integer": int,
    "boolean": bool,
    "string_set": UniqueTexts,
    "range": NumericRange,
    "dimensions": Dimensions,
}


def one_of(values: list[str]) -> Any:
    """Literal type built from ontology tokens."""
    return Literal[tuple(values)]


def camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def build_basis_model(onto: Ontology) -> type[BaseModel]:
    fields: dict[str, Any] = {
        key: (one_of(values), "unknown") for key, values in onto.vocabularies.basis.items()
    }
    return create_model("Basis", __base__=StrictModel, **fields)


def build_condition_model(onto: Ontology) -> type[BaseModel]:
    kinds: dict[str, Any] = {"quantity": Quantity, "reference_quantity": ReferenceQuantity}
    fields: dict[str, Any] = {}
    for key, cond in onto.vocabularies.condition.items():
        kind = one_of(cond.values) if cond.kind == "token" else kinds[cond.kind]
        fields[key] = (kind | None, None)
    return create_model("Condition", __base__=StrictModel, **fields)


def build_fact_model(
    onto: Ontology,
    attr_id: str,
    basis: type[BaseModel],
    condition: type[BaseModel],
    *,
    registered: bool = False,
) -> type[BaseModel]:
    attr = onto.attributes[attr_id]
    names = attr.datatype if isinstance(attr.datatype, list) else [attr.datatype]
    value: Any = VALUE_TYPES[names[0]]
    for name in names[1:]:
        value = value | VALUE_TYPES[name]
    unit: Any = None if attr.canonical_unit is None else one_of([attr.canonical_unit])
    fields: dict[str, Any] = {
        "value": (value, ...),
        "unit": (unit, ...),
        "basis": (basis, Field(default_factory=basis)),
        "condition": (condition, Field(default_factory=condition)),
        "scope": (Text, "unknown"),
    }
    if not registered:
        fields["occurrences"] = (list[Occurrence], Field(min_length=1))
    prefix = "Registered" if registered else ""
    return create_model(f"{prefix}{camel(attr_id)}Fact", __base__=StrictModel, **fields)


def build_candidate_model(
    onto: Ontology, class_id: str, *, registered: bool = False
) -> type[BaseModel]:
    """Extraction candidate (facts need occurrences) or registered record (no occurrences)."""
    basis = build_basis_model(onto)
    condition = build_condition_model(onto)
    fields: dict[str, Any] = {}
    for attr_id in onto.attributes_of(class_id):
        fact = build_fact_model(onto, attr_id, basis, condition, registered=registered)
        fields[attr_id] = (list[fact], Field(default_factory=list))  # type: ignore[valid-type]
    attributes = create_model(f"{class_id}Attributes", __base__=StrictModel, **fields)
    return create_model(
        f"{class_id}Candidate",
        __base__=StrictModel,
        class_id=(one_of([class_id]), class_id),
        attributes=(attributes, ...),
    )


def export_json_schemas(onto: Ontology, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for class_id, cls in onto.classes.items():
        if cls.abstract:
            continue
        schema = build_candidate_model(onto, class_id).model_json_schema()
        path = out_dir / f"{class_id}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        paths.append(path)
    return paths
