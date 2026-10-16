"""Required-attribute presence from the ontology (project synthetic policy).

Scope (D-022): this module only checks whether required attributes are present.
Whether critical basis/condition/scope values are known, and E4/E5 judgements,
belong to the W4 registration-readiness validator.
"""

from typing import Any, Literal

from pydantic import BaseModel

from spec_bridge.ontology.definitions import ConditionalRule, Ontology

Presence = Literal["present", "missing", "undetermined"]


def present(candidate: BaseModel) -> dict[str, list[Any]]:
    """Attribute ID -> values that carry a fact (empty lists dropped)."""
    attrs = candidate.model_dump()["attributes"]
    return {k: [f["value"] for f in facts] for k, facts in attrs.items() if facts}


def applies(rule: ConditionalRule, values: dict[str, list[Any]]) -> bool:
    return all(expected in values.get(key, []) for key, expected in rule.when.items())


def missing_required(onto: Ontology, class_id: str, candidate: BaseModel) -> list[str]:
    cls = onto.classes[class_id]
    values = present(candidate)
    required = set(cls.required_all)
    groups = list(cls.required_any_groups)
    for rule in cls.conditional_required:
        if applies(rule, values):
            required.update(rule.required_all)
            groups += rule.required_any_groups
    missing = required - values.keys()
    for group in groups:
        if not values.keys() & set(group):
            missing.update(group)
    return sorted(missing)


def presence_status(onto: Ontology, class_id: str, candidate: BaseModel) -> Presence:
    """present: required attributes found; missing: some absent;
    undetermined: a conditional rule's branch value is unknown (e.g. unlisted pump type)."""
    if missing_required(onto, class_id, candidate):
        return "missing"
    values = present(candidate)
    rules = onto.classes[class_id].conditional_required
    for key in {k for rule in rules for k in rule.when}:
        known = {rule.when[key] for rule in rules if key in rule.when}
        if not set(values.get(key, [])) & known:
            return "undetermined"
    return "present"
