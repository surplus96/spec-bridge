import copy
import json
from typing import Any

import pytest

from spec_bridge.eval.scoring import (
    Prediction,
    fact_key,
    score_document,
    score_split,
    values_match,
)
from spec_bridge.normalize.dictionary import dev_answers
from tests.conftest import to_location

DEV_ANSWERS = dev_answers()


def perfect(answer: dict[str, Any]) -> Prediction:
    """The gold answer written as a prediction (facts, occurrences, unresolved)."""
    observations = {o["observation_id"]: o for o in answer["observations"]}

    def occurrence(oid: str) -> dict[str, Any]:
        obs = observations[oid]
        return {"raw_text": obs["raw_text"], "location": to_location(obs["location"])}

    facts = [
        {k: f[k] for k in ("value", "unit", "basis", "condition", "scope")}
        | {
            "attribute": f["attribute_id"],
            "occurrences": [occurrence(i) for i in f["observation_ids"]],
        }
        for f in answer["facts"]
    ]
    used = {i for f in answer["facts"] for i in f["observation_ids"]}
    unresolved = [
        {"attribute": o["attribute_id"], "occurrence": occurrence(o["observation_id"])}
        for o in answer["observations"]
        if o["observation_id"] not in used and o["attribute_id"] is not None
    ]
    return Prediction(
        document_id=answer["input_id"],
        class_id=answer["expected_class"],
        facts=facts,
        unresolved=unresolved,
    )


def gold_keys(answers: list[dict[str, Any]]) -> int:
    return sum(
        len({fact_key(f["attribute_id"], f["basis"], f["condition"], f["scope"]) for f in facts})
        for facts in (a["facts"] for a in answers)
    )


def test_gold_as_prediction_scores_one_on_every_channel() -> None:
    _, metrics = score_split(DEV_ANSWERS, {a["input_id"]: perfect(a) for a in DEV_ANSWERS})
    assert metrics.class_top1 == metrics.class_top3 == 1.0 and metrics.class_unknown == 0
    assert (metrics.facts_micro.precision, metrics.facts_micro.recall) == (1.0, 1.0)
    assert metrics.facts_macro_f1_attribute == metrics.facts_macro_f1_class == 1.0
    assert metrics.observation_recall == 1.0 and metrics.failed_documents == []


def test_denominators_come_from_the_answer_files() -> None:
    _, metrics = score_split(DEV_ANSWERS, {})
    observations = [o for a in DEV_ANSWERS for o in a["observations"]]
    assert metrics.documents == len(DEV_ANSWERS)
    assert metrics.facts_micro.fn == gold_keys(DEV_ANSWERS)
    assert metrics.observations_total + metrics.observations_unattributed == len(observations)
    invalid = [o for o in observations if o["interpretation"] in ("invalid_unit", "invalid_shape")]
    assert metrics.observations_invalid == len(invalid)


def test_missing_and_failed_documents_stay_in_the_inventory() -> None:
    answer = DEV_ANSWERS[0]
    failed = perfect(answer).model_copy(update={"failure": "llm_timeout"})
    scores, metrics = score_split(DEV_ANSWERS[:2], {answer["input_id"]: failed})
    assert metrics.failed_documents == [a["input_id"] for a in DEV_ANSWERS[:2]]
    assert metrics.facts_micro.tp == 0 and metrics.facts_micro.fn == gold_keys(DEV_ANSWERS[:2])
    by_id = {s.document_id: s for s in scores}
    assert by_id[answer["input_id"]].predicted_class == answer["expected_class"]  # D-031
    assert by_id[DEV_ANSWERS[1]["input_id"]].predicted_class == "unknown"


def test_one_missing_fact_lowers_recall_only() -> None:
    answer = DEV_ANSWERS[0]
    prediction = perfect(answer)
    prediction.facts.pop()
    _, metrics = score_split([answer], {answer["input_id"]: prediction})
    assert metrics.facts_micro.precision == 1.0 and metrics.facts_micro.fn == 1


def test_same_value_under_another_condition_does_not_match() -> None:
    answer = DEV_ANSWERS[0]
    prediction = perfect(answer)
    prediction.facts[0]["condition"] = {"frequency": {"value": 60, "unit": "Hz"}}
    score = score_document(answer, prediction)
    attribute = prediction.facts[0]["attribute"]
    assert (score.facts[attribute].fp, score.facts[attribute].fn) == (1, 1)


def e5_answer() -> dict[str, Any]:
    for answer in DEV_ANSWERS:
        if any(i["code"] == "E5" for i in answer["issues"]):
            return answer
    raise LookupError("no dev E5 document")


def test_e5_needs_the_whole_conflicting_set() -> None:
    answer = e5_answer()
    attribute = next(i for i in answer["issues"] if i["code"] == "E5")["attribute_ids"][0]
    prediction = perfect(answer)
    first = next(i for i, f in enumerate(prediction.facts) if f["attribute"] == attribute)
    prediction.facts.pop(first)
    score = score_document(answer, prediction)
    assert (score.facts[attribute].tp, score.facts[attribute].fp, score.facts[attribute].fn) == (
        0,
        1,
        1,
    )
    assert score_document(answer, perfect(answer)).facts[attribute].tp == 1


def test_hallucinated_fact_is_a_false_positive() -> None:
    answer = DEV_ANSWERS[0]
    prediction = perfect(answer)
    extra = copy.deepcopy(prediction.facts[0]) | {"scope": "invented_scope"}
    prediction.facts.append(extra)
    score = score_document(answer, prediction)
    assert score.facts[extra["attribute"]].fp == 1


def test_wrong_location_is_not_retrieved() -> None:
    answer = DEV_ANSWERS[0]
    prediction = perfect(answer)
    for fact in prediction.facts:
        for occurrence in fact["occurrences"]:
            occurrence["raw_text"] = "not the value"
    score = score_document(answer, prediction)
    assert score.observations_found < score.observations_total
    assert score.facts == score_document(answer, perfect(answer)).facts


@pytest.mark.parametrize(
    "gold, predicted, same",
    [
        (650, 650.0000005, True),
        (650, 650.01, False),
        (["a", "b"], ["b", "a"], True),
        (["a", "b"], ["a"], False),
        ({"min": 1, "max": 2}, {"min": 1, "max": 2.0}, True),
        ({"length": 1, "width": None}, {"length": 1}, False),
        (True, 1, False),
        ("650", 650, False),
    ],
)
def test_values_match(gold: Any, predicted: Any, same: bool) -> None:
    assert values_match(gold, predicted) is same


def test_context_defaults_equal_an_unstated_basis() -> None:
    stated = fact_key("x", {"pressure": "not_applicable"}, {"frequency": {"value": 50.0}}, "s")
    assert stated == fact_key("x", {}, {"frequency": {"value": 50}}, "s")
    assert fact_key("x", {"pressure": "gauge"}, {}, "s") != fact_key("x", {}, {}, "s")


def test_attributes_outside_the_gold_do_not_change_macro_f1() -> None:
    answer = DEV_ANSWERS[0]
    prediction = perfect(answer)
    _, before = score_split([answer], {answer["input_id"]: prediction})
    extra = copy.deepcopy(prediction.facts[0]) | {"attribute": "not_in_any_answer"}
    prediction.facts.append(extra)
    _, after = score_split([answer], {answer["input_id"]: prediction})
    assert after.facts_macro_f1_attribute == before.facts_macro_f1_attribute == 1.0
    assert after.facts_fp_outside_gold == 1 and after.facts_micro.fp == 1


@pytest.mark.parametrize("scope", [None, "", "main_equipment"])
def test_scope_default_is_applied_by_the_scorer(scope: str | None) -> None:
    assert fact_key("x", {}, {}, scope) == fact_key("x", {}, {}, "main_equipment")


def test_top3_looks_at_three_classes_only() -> None:
    answer = DEV_ANSWERS[0]
    others = sorted({a["expected_class"] for a in DEV_ANSWERS} - {answer["expected_class"]})
    chosen, first, second = others[:3]
    fourth = answer["expected_class"]
    prediction = perfect(answer).model_copy(
        update={"class_id": chosen, "class_candidates": [chosen, first, second, fourth]}
    )
    assert not score_document(answer, prediction).top3_hit
    prediction.class_candidates = [chosen, first, fourth]
    assert score_document(answer, prediction).top3_hit


def test_occurrence_precision_counts_occurrences_off_the_gold() -> None:
    answer = DEV_ANSWERS[0]
    _, clean = score_split([answer], {answer["input_id"]: perfect(answer)})
    assert clean.occurrence_precision == 1.0
    prediction = perfect(answer)
    prediction.facts[0]["occurrences"][0]["raw_text"] = "not the value"
    _, noisy = score_split([answer], {answer["input_id"]: prediction})
    assert noisy.occurrences_matched == noisy.occurrences_predicted - 1


def test_metrics_are_json_serializable() -> None:
    _, metrics = score_split(DEV_ANSWERS[:1], {})
    assert json.loads(metrics.model_dump_json())["documents"] == 1


def test_context_channel_splits_the_keys() -> None:
    _, metrics = score_split(DEV_ANSWERS, {a["input_id"]: perfect(a) for a in DEV_ANSWERS})
    assert metrics.context_tp == metrics.context_keys > 0 and metrics.context_fp == 0
    assert metrics.plain_tp == metrics.plain_keys
    assert metrics.context_keys + metrics.plain_keys == gold_keys(DEV_ANSWERS)


def test_invented_context_is_counted() -> None:
    answer = next(a for a in DEV_ANSWERS if any(f["scope"] == "main_equipment" for f in a["facts"]))
    prediction = perfect(answer)
    fact = next(f for f in prediction.facts if f["scope"] == "main_equipment")
    fact["scope"] = "invented_scope"
    score = score_document(answer, prediction)
    assert score.context_fp == 1
