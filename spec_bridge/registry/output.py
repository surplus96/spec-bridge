"""Standard registration result (W4-6, FR-11): one JSON document per processed file.

It carries the class, the normalized facts with their source locations, the values left
unresolved, the validation findings, the duplicate/similar judgements and where the result
came from. The class facts are checked with the ontology's candidate model (FR-02); the
whole document is checked with this model's JSON Schema (exported by `export_schema`).
"""

import json
from pathlib import Path
from typing import Any, Literal

from spec_bridge.dedup.matcher import Match
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.ontology.schema import build_candidate_model
from spec_bridge.validate.validator import Validation

SCHEMA_VERSION = 1
Status = Literal["ready", "needs_review"]


class RegistrationResult(StrictModel):
    schema_version: Literal[1] = 1  # SCHEMA_VERSION
    document_id: str
    file_name: str | None = None
    class_id: str  # a leaf class or "unknown"
    class_candidates: list[str] = []
    facts: list[
        dict[str, Any]
    ] = []  # candidate facts: attribute, value, unit, context, occurrences
    unresolved: list[dict[str, Any]] = []
    validation: Validation
    matches: list[Match] = []
    status: Status
    failure: str | None = None  # parse or model failure: nothing extracted, a person decides
    provenance: dict[str, Any] = {}


def decide_status(validation: Validation, matches: list[Match], failure: str | None) -> Status:
    """Ready only with no failure, a ready validation and no duplicate in the registry."""
    duplicate = any(m.relation == "duplicate" for m in matches)
    if failure is None and validation.status == "ready" and not duplicate:
        return "ready"
    return "needs_review"


def check_result(onto: Ontology, result: RegistrationResult) -> None:
    """Raise if the facts break the class's candidate model or the document its schema."""
    if result.class_id in onto.classes:
        by_attribute: dict[str, list[dict[str, Any]]] = {}
        for fact in result.facts:
            body = {k: v for k, v in fact.items() if k != "attribute"}
            by_attribute.setdefault(fact["attribute"], []).append(body)
        build_candidate_model(onto, result.class_id).model_validate({"attributes": by_attribute})
    RegistrationResult.model_validate_json(result.model_dump_json())


def export_schema(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = RegistrationResult.model_json_schema()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    return path


if __name__ == "__main__":  # uv run python -m spec_bridge.registry.output
    print(
        export_schema(
            Path(__file__).resolve().parents[2] / "var/schemas/registration-result.schema.json"
        )
    )
