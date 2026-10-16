"""Duplicate and similar products (W4-5, FR-10): one document against the registry.

1. Blocking: only registered products of the same class are compared.
2. Natural key: same maker (registered name or alias) and same model key -> duplicate.
3. Otherwise, a registered product of the same maker whose model designation is close
   (rapidfuzz ratio of the model keys) -> similar.
Each judgement carries its evidence: the identity comparison, the name score and the
attributes whose values differ. No model is asked (plan 5-1); maker aliases come only from
the registry's manufacturers file (H3).
"""

from typing import Any, Literal

from rapidfuzz import fuzz

from spec_bridge.eval.scoring import values_match
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.identity import MakerIndex, model_key

NAME_THRESHOLD = 60.0  # fixed on the dev split (D-056); similar pairs score 62.5 and above

Relation = Literal["duplicate", "similar"]


class Match(StrictModel):
    registry_id: str
    relation: Relation
    evidence: dict[str, Any]


def _first(facts: list[dict[str, Any]], attribute: str) -> Any:
    return next((f["value"] for f in facts if f["attribute"] == attribute), None)


def differing_attributes(facts: list[dict[str, Any]], record: dict[str, Any]) -> list[str]:
    """Attributes both sides state whose values differ (any context)."""
    differs = []
    for attribute, registered in sorted(record["attributes"].items()):
        ours = [f["value"] for f in facts if f["attribute"] == attribute]
        theirs = [r["value"] for r in registered]
        if ours and theirs and not any(values_match(t, o) for t in theirs for o in ours):
            differs.append(attribute)
    return differs


def match(
    class_id: str,
    facts: list[dict[str, Any]],
    registry: list[dict[str, Any]],
    makers: MakerIndex,
    *,
    name_threshold: float = NAME_THRESHOLD,
) -> list[Match]:
    maker_text, model_text = _first(facts, "maker"), _first(facts, "model_designation")
    if not isinstance(maker_text, str) or not isinstance(model_text, str):
        return []  # no identity, no comparison: a person decides (needs_review upstream)
    maker_id, key = makers.resolve(maker_text), model_key(model_text)
    found = []
    for record in registry:
        if record["class"] != class_id:
            continue
        same_maker = maker_id is not None and maker_id == record["maker_id"]
        their_key = model_key(record["model_designation"])
        identity = {
            "maker_id": maker_id,
            "same_maker": same_maker,
            "model_key": key,
            "registered_model_key": their_key,
        }
        if same_maker and key == their_key:
            found.append(
                Match(registry_id=record["product_id"], relation="duplicate", evidence=identity)
            )
            continue
        score = fuzz.ratio(key, their_key)
        if same_maker and score >= name_threshold:
            found.append(
                Match(
                    registry_id=record["product_id"],
                    relation="similar",
                    evidence=identity
                    | {
                        "name_score": score,
                        "differing_attributes": differing_attributes(facts, record),
                    },
                )
            )
    return found
