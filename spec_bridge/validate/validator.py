"""Deterministic registration validator (W4-3, FR-09): E1-E5 and readiness.

Input: one document's normalized facts and the values the normalizer left unresolved.
Output: findings, the required attributes still missing and whether the record is ready.
Nothing here asks a model; every rule reads the ontology (plan 5-1).
"""

from collections import defaultdict
from typing import Any, Literal

from spec_bridge.eval.scoring import fact_key
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.ontology.policy import Presence, missing_required, presence_status
from spec_bridge.ontology.schema import build_candidate_model
from spec_bridge.validate.findings import (
    ONTOLOGY_REF,
    RULE_KINDS,
    Code,
    Finding,
    code_for_unresolved,
)

Status = Literal["ready", "needs_review"]


class Validation(StrictModel):
    findings: list[Finding]
    missing_required: list[str]
    presence: Presence | Literal["unknown_class"]
    status: Status


def _candidate(onto: Ontology, class_id: str, facts: list[dict[str, Any]]) -> Any:
    by_attribute: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        by_attribute[fact["attribute"]].append({k: v for k, v in fact.items() if k != "attribute"})
    return build_candidate_model(onto, class_id).model_validate({"attributes": by_attribute})


def _required_rule(onto: Ontology, class_id: str, attribute: str) -> str:
    """Which rule kind makes an attribute required (for the finding's rule_ref)."""
    chain = [*reversed(onto.ancestors(class_id)), class_id]
    for name in chain:
        cls = onto.classes[name]
        if attribute in cls.required_all:
            return f"classes/{name}/required_all"
        if any(attribute in group for group in cls.required_any_groups):
            return f"classes/{name}/required_any_groups"
        if any(
            attribute in rule.required_all or any(attribute in g for g in rule.required_any_groups)
            for rule in cls.conditional_required
        ):
            return f"classes/{name}/conditional_required"
    return f"classes/{class_id}/required_all"


def _allowed(onto: Ontology, class_id: str) -> dict[str, list[str]]:
    allowed: dict[str, list[str]] = {}
    for name in [*reversed(onto.ancestors(class_id)), class_id]:
        allowed |= onto.classes[name].allowed_values
    return allowed


def validate(
    onto: Ontology,
    class_id: str,
    facts: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> Validation:
    if class_id not in onto.classes:  # unknown class: no rules apply, a person decides
        return Validation(
            findings=[], missing_required=[], presence="unknown_class", status="needs_review"
        )
    findings: list[Finding] = []

    # E2 / E3 / REVIEW: values the normalizer would not read without guessing.
    grouped: dict[tuple[Code, str], list[dict[str, Any]]] = defaultdict(list)
    for item in unresolved:
        code = code_for_unresolved(item["reason"])
        grouped[(code, item["attribute"])].append(item["occurrence"])
    for (code, attribute), occurrences in sorted(grouped.items()):
        findings.append(
            Finding(
                code=code,
                attribute_ids=[attribute],
                occurrences=occurrences,
                rule_ref=f"{ONTOLOGY_REF}#attributes/{attribute}/{RULE_KINDS[code]}",
                reason=f"value left unresolved: {code}",
            )
        )
    invalid = {attribute for code, attribute in grouped if code in ("E2", "E3")}

    # E1: required and absent; an attribute present only as E2/E3 keeps that code (D-015).
    candidate = _candidate(onto, class_id, facts)  # facts are schema-checked upstream
    missing = missing_required(onto, class_id, candidate)
    for attribute in missing:
        if attribute in invalid:
            continue
        findings.append(
            Finding(
                code="E1",
                attribute_ids=[attribute],
                occurrences=[],
                rule_ref=f"{ONTOLOGY_REF}#{_required_rule(onto, class_id, attribute)}",
                reason="required attribute not found in the document",
            )
        )

    # E4: a stated value outside the class's synthetic allowed list (the fact is kept).
    for attribute, allowed in sorted(_allowed(onto, class_id).items()):
        for fact in (f for f in facts if f["attribute"] == attribute):
            values = fact["value"] if isinstance(fact["value"], list) else [fact["value"]]
            if any(v not in allowed for v in values):
                findings.append(
                    Finding(
                        code="E4",
                        attribute_ids=[attribute],
                        occurrences=fact["occurrences"],
                        rule_ref=f"{ONTOLOGY_REF}#classes/{class_id}/allowed_values",
                        reason=f"value outside the allowed list {allowed}",
                    )
                )

    # E5: different values under the same basis, condition and scope (other contexts are
    # separate facts, not conflicts).
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        key = fact_key(fact["attribute"], fact["basis"], fact["condition"], fact["scope"])
        by_key[key].append(fact)
    for group in by_key.values():
        if len(group) > 1:
            findings.append(
                Finding(
                    code="E5",
                    attribute_ids=[group[0]["attribute"]],
                    occurrences=[o for fact in group for o in fact["occurrences"]],
                    rule_ref="data/synth/answer-contract.yaml#issue/E5",
                    reason=f"{len(group)} different values in one context",
                )
            )

    presence = presence_status(onto, class_id, candidate)
    status: Status = "ready" if not findings and presence == "present" else "needs_review"
    return Validation(findings=findings, missing_required=missing, presence=presence, status=status)
