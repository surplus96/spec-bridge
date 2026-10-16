"""W4-5: G4 scoring over all (document, product) pairs of the gold class."""

from spec_bridge.eval.dedup_scoring import (
    aggregate_dedup,
    confusion_of,
    dev_registry,
    evaluate_dedup,
)
from spec_bridge.eval.scoring import Prediction
from spec_bridge.normalize.dictionary import dev_answers

ANSWERS = dev_answers()


def gold_prediction(answer: dict) -> Prediction:  # type: ignore[type-arg]
    facts = [
        {
            "attribute": f["attribute_id"],
            "value": f["value"],
            "unit": f["unit"],
            "basis": f["basis"],
            "condition": f["condition"],
            "scope": f["scope"],
            "occurrences": [],
        }
        for f in answer["facts"]
    ]
    return Prediction(
        document_id=answer["input_id"], class_id=answer["expected_class"], facts=facts
    )


def test_gold_identity_scores_one_and_counts_every_pair() -> None:
    metrics = evaluate_dedup(ANSWERS, {a["input_id"]: gold_prediction(a) for a in ANSWERS})
    assert metrics.labelled.precision == metrics.labelled.recall == 1.0
    registry, _ = dev_registry()
    per_class = {c: sum(r["class"] == c for r in registry) for c in {r["class"] for r in registry}}
    assert metrics.pairs == sum(per_class[a["expected_class"]] for a in ANSWERS)


def test_failed_documents_miss_their_labelled_pairs() -> None:
    metrics = evaluate_dedup(ANSWERS, {})
    assert metrics.labelled.tp == 0 and metrics.labelled.fn > 0
    assert metrics.confusion["new"]["new"] == sum(metrics.confusion["new"].values())


def test_a_product_named_outside_the_gold_class_is_a_false_positive() -> None:
    registry, _ = dev_registry()
    answer = ANSWERS[0]
    outside = next(r["product_id"] for r in registry if r["class"] != answer["expected_class"])
    table = confusion_of(answer, {outside: "similar"}, registry, {"duplicate": [], "similar": []})
    assert aggregate_dedup([table]).similar.fp == 1
