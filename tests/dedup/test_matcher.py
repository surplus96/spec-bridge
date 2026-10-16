"""W4-5: duplicates by natural key, similar by maker and model name, always with evidence."""

import json
from typing import Any

import pytest

from spec_bridge.dedup.matcher import match
from spec_bridge.eval.dedup_scoring import REGISTRY as REGISTRY_DIR
from spec_bridge.eval.dedup_scoring import dev_labels, dev_registry
from spec_bridge.normalize.dictionary import dev_answers

REGISTRY, MAKERS = dev_registry()
LABELS = dev_labels()
ANSWERS = dev_answers()
MAKERS_RAW = json.loads((REGISTRY_DIR / "manufacturers.json").read_text())


def facts_of(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"attribute": f["attribute_id"], "value": f["value"]} for f in answer["facts"]]


def identity(maker: str, model: str) -> list[dict[str, Any]]:
    return [
        {"attribute": "maker", "value": maker},
        {"attribute": "model_designation", "value": model},
    ]


@pytest.mark.parametrize("answer", ANSWERS, ids=[a["input_id"] for a in ANSWERS])
def test_gold_identity_finds_the_labelled_products(answer: dict[str, Any]) -> None:
    found = match(answer["expected_class"], facts_of(answer), REGISTRY, MAKERS)
    labels = LABELS[answer["input_id"]]
    assert sorted(m.registry_id for m in found if m.relation == "duplicate") == sorted(
        labels["duplicate"]
    )
    assert sorted(m.registry_id for m in found if m.relation == "similar") == sorted(
        labels["similar"]
    )


def test_alias_and_spacing_still_make_a_duplicate() -> None:
    record = REGISTRY[0]
    maker = next(m for m in MAKERS_RAW if m["maker_id"] == record["maker_id"] and m["aliases"])
    model = record["model_designation"].replace("-", " ")
    found = match(record["class"], identity(maker["aliases"][0], model), REGISTRY, MAKERS)
    assert [(m.registry_id, m.relation) for m in found if m.relation == "duplicate"] == [
        (record["product_id"], "duplicate")
    ]


def test_other_classes_are_never_compared() -> None:
    record = REGISTRY[0]
    other = next(r["class"] for r in REGISTRY if r["class"] != record["class"])
    maker_name = next(m["name"] for m in MAKERS_RAW if m["maker_id"] == record["maker_id"])
    found = match(other, identity(maker_name, record["model_designation"]), REGISTRY, MAKERS)
    assert all(m.registry_id != record["product_id"] for m in found)


def test_every_judgement_carries_evidence() -> None:
    answer = next(a for a in ANSWERS if LABELS[a["input_id"]]["similar"])
    found = match(answer["expected_class"], facts_of(answer), REGISTRY, MAKERS)
    similar = next(m for m in found if m.relation == "similar")
    assert similar.evidence["same_maker"] and similar.evidence["name_score"] >= 60
    assert "differing_attributes" in similar.evidence


@pytest.mark.parametrize("facts", [[], identity("No Such Maker Works", "VX999-999")])
def test_no_identity_or_unknown_maker_matches_nothing(facts: list[dict[str, Any]]) -> None:
    assert match(REGISTRY[0]["class"], facts, REGISTRY, MAKERS) == []
