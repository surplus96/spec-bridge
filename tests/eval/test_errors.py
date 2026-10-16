"""W6-5: each missed or extra fact key gets exactly one cause, and the counts add up.

Values come from a development answer (H3: no domain numbers written here); each test
changes one predicted fact and checks the cause it is given.
"""

from typing import Any

from spec_bridge.eval.errors import document_errors, summary
from spec_bridge.eval.scoring import Prediction, score_document
from spec_bridge.normalize.dictionary import dev_answers

ANSWER = dev_answers()[0]
TEXT = "\n".join(o["raw_text"] for o in ANSWER["observations"])


def _facts() -> list[dict[str, Any]]:
    return [
        {
            "attribute": f["attribute_id"],
            "value": f["value"],
            "unit": f["unit"],
            "basis": dict(f["basis"]),
            "condition": dict(f["condition"]),
            "scope": f["scope"],
        }
        for f in ANSWER["facts"]
    ]


def _prediction(facts: list[dict[str, Any]], **extra: Any) -> Prediction:
    return Prediction(
        document_id=ANSWER["input_id"],
        class_id=ANSWER["expected_class"],
        facts=facts,
        **extra,
    )


def _numeric_index(facts: list[dict[str, Any]]) -> int:
    return next(
        i for i, f in enumerate(facts) if isinstance(f["value"], (int, float)) and f["unit"]
    )


def _causes(prediction: Prediction | None, text: str = TEXT) -> list[str]:
    return [e.cause for e in document_errors(ANSWER, prediction, text).facts]


def test_the_answer_itself_has_no_errors() -> None:
    assert _causes(_prediction(_facts())) == []


def test_a_wrong_value_under_the_same_key_is_a_value_error() -> None:
    facts = _facts()
    i = _numeric_index(facts)
    facts[i] = facts[i] | {"value": facts[i]["value"] + 1}
    assert _causes(_prediction(facts)) == ["value"]


def test_the_right_value_with_another_scope_is_a_context_error() -> None:
    facts = _facts()
    i = _numeric_index(facts)
    facts[i] = facts[i] | {"scope": "a_scope_no_answer_uses"}
    assert _causes(_prediction(facts)) == ["context"]


def test_the_right_value_under_another_attribute_is_an_attribute_error() -> None:
    facts = _facts()
    i = _numeric_index(facts)
    facts[i] = facts[i] | {"attribute": "an_attribute_no_answer_uses"}
    assert _causes(_prediction(facts)) == ["attribute"]


def test_a_missing_fact_is_not_extracted_when_the_text_holds_it() -> None:
    facts = _facts()
    del facts[_numeric_index(facts)]
    assert _causes(_prediction(facts)) == ["not_extracted"]
    assert _causes(_prediction(facts), text="") == ["parse"]


def test_a_missing_fact_the_run_grounded_but_did_not_normalize_is_unresolved() -> None:
    facts = _facts()
    gone = facts.pop(_numeric_index(facts))
    unresolved = [{"attribute": gone["attribute"], "occurrence": {"raw_text": "x"}}]
    assert _causes(_prediction(facts, unresolved=unresolved)) == ["unresolved"]


def test_an_unexplained_prediction_is_extra() -> None:
    facts = [*_facts(), {**_facts()[0], "attribute": "an_attribute_no_answer_uses"}]
    assert _causes(_prediction(facts)) == ["extra"]


def test_counts_match_the_scorer_and_a_wrong_class_is_reported() -> None:
    facts = _facts()
    i = _numeric_index(facts)
    facts[i] = facts[i] | {"scope": "a_scope_no_answer_uses"}
    del facts[0 if i else 1]
    prediction = _prediction(facts).model_copy(update={"class_id": "unknown"})
    report = summary([document_errors(ANSWER, prediction, TEXT)])
    score = score_document(ANSWER, prediction)
    assert report["fn"] == sum(c.fn for c in score.facts.values())
    assert report["fp"] == sum(c.fp for c in score.facts.values())
    assert report["wrong_class"] == [ANSWER["input_id"]]


def test_a_failed_document_misses_every_gold_key() -> None:
    gold_keys = sum(c.fn for c in score_document(ANSWER, None).facts.values())
    for prediction in (None, _prediction(_facts(), failure="not_parsed")):
        causes = _causes(prediction)
        assert len(causes) == gold_keys
        assert set(causes) <= {"not_extracted", "parse"}
