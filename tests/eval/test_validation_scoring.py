"""W4-4: G3 validation scoring against the dev gold issues (answer contract issue_match)."""

from typing import Any

import pytest

from spec_bridge.eval.scoring import Prediction
from spec_bridge.eval.validation_scoring import (
    aggregate_validation,
    rule_kind,
    score_validation,
    validate_predictions,
)
from spec_bridge.normalize.dictionary import dev_answers, load_dictionary
from spec_bridge.normalize.values import Normalizer, Unresolved
from spec_bridge.ontology.loader import Ontology, load_ontology
from spec_bridge.service import normalizer_for
from spec_bridge.validate.findings import Finding
from tests.conftest import ONTOLOGY, to_location
from tests.normalize.test_values import raw_from

ANSWERS = dev_answers()
WITH_ISSUES = [a for a in ANSWERS if a["issues"]]


def gold_findings(answer: dict[str, Any]) -> list[Finding]:
    observations = {o["observation_id"]: o for o in answer["observations"]}
    return [
        Finding(
            code=issue["code"],
            attribute_ids=issue["attribute_ids"],
            occurrences=[
                {"location": to_location(observations[oid]["location"])}
                for oid in issue["observation_ids"]
            ],
            rule_ref=issue["rule_ref"],
            reason="gold",
        )
        for issue in answer["issues"]
    ]


def test_gold_findings_score_one() -> None:
    scores = [score_validation(a, gold_findings(a)) for a in ANSWERS]
    metrics = aggregate_validation(scores)
    assert metrics.micro.recall == metrics.micro.precision == 1.0
    assert metrics.false_findings_on_clean == 0 and metrics.failed_documents == []
    assert metrics.clean_documents == len(ANSWERS) - len(WITH_ISSUES)


def test_a_missed_issue_is_a_false_negative_of_its_code() -> None:
    answer = WITH_ISSUES[0]
    score = score_validation(answer, gold_findings(answer)[1:])
    code = answer["issues"][0]["code"]
    assert score.by_code[code].fn == 1 and score.by_code[code].fp == 0


def test_a_finding_on_a_clean_document_is_counted() -> None:
    clean = next(a for a in ANSWERS if not a["issues"])
    extra = Finding(
        code="E4", attribute_ids=["x"], occurrences=[], rule_ref="r/allowed_values", reason="t"
    )
    metrics = aggregate_validation([score_validation(clean, [extra])])
    assert metrics.false_findings_on_clean == 1 and metrics.by_code["E4"].fp == 1


@pytest.mark.parametrize(
    "change",
    [
        {"attribute_ids": ["not_this_one"]},
        {"rule_ref": "ontology/ontology.yaml#somewhere/else"},
        {"occurrences": [{"location": {"paragraph": 999}}]},
    ],
)
def test_wrong_attribute_rule_or_place_does_not_match(change: dict[str, Any]) -> None:
    answer = next(a for a in WITH_ISSUES if a["issues"][0]["code"] in ("E2", "E3", "E4", "E5"))
    finding = gold_findings(answer)[0].model_copy(update=change)
    score = score_validation(answer, [finding])
    code = answer["issues"][0]["code"]
    assert (score.by_code[code].tp, score.by_code[code].fp, score.by_code[code].fn) == (0, 1, 1)


def test_review_is_counted_apart_and_failure_misses_everything() -> None:
    answer = WITH_ISSUES[0]
    review = Finding(code="REVIEW", attribute_ids=["x"], occurrences=[], rule_ref="r", reason="t")
    score = score_validation(answer, [*gold_findings(answer), review])
    assert score.review == 1 and sum(c.fp for c in score.by_code.values()) == 0
    failed = score_validation(answer, None)
    assert failed.failed and sum(c.fn for c in failed.by_code.values()) == len(answer["issues"])


def test_rule_kind_treats_dataset_allowed_values_alike() -> None:
    assert rule_kind("x/classes/A/attribute_definitions/application/dataset_allowed_values") == (
        rule_kind("ontology/ontology.yaml#classes/A/allowed_values")
    )


@pytest.fixture(scope="module")
def onto() -> Ontology:
    return load_ontology(ONTOLOGY)


@pytest.fixture(scope="module")
def normalizer(onto: Ontology) -> Normalizer:
    return normalizer_for(onto, "dev", load_dictionary())


def gold_prediction(answer: dict[str, Any], normalizer: Normalizer) -> Prediction:
    """What a perfect pipeline would hand the validator for this document."""
    observations = {o["observation_id"]: o for o in answer["observations"]}

    def occurrence(oid: str) -> dict[str, Any]:
        obs = observations[oid]
        return {
            "source_document_id": answer["input_id"],
            "raw_text": obs["raw_text"],
            "label_text": obs["label_text"],
            "unit_text": obs["unit_text"],
            "location": to_location(obs["location"]),
        }

    facts = [
        {k: f[k] for k in ("value", "unit", "basis", "condition", "scope")}
        | {
            "attribute": f["attribute_id"],
            "occurrences": [occurrence(i) for i in f["observation_ids"]],
        }
        for f in answer["facts"]
    ]
    unresolved = []
    for obs in answer["observations"]:
        if obs["interpretation"] in ("invalid_unit", "invalid_shape"):
            raw = raw_from(obs, None).model_copy(
                update={"occurrence": occurrence(obs["observation_id"])}
            )
            got = normalizer.fact(raw)
            assert isinstance(got, Unresolved)
            unresolved.append(got.model_dump())
    return Prediction(
        document_id=answer["input_id"],
        class_id=answer["expected_class"],
        facts=facts,
        unresolved=unresolved,
    )


def test_validator_on_a_perfect_pipeline_scores_one(onto: Ontology, normalizer: Normalizer) -> None:
    predictions = {a["input_id"]: gold_prediction(a, normalizer) for a in ANSWERS}
    _, metrics = validate_predictions(onto, ANSWERS, predictions)
    assert metrics.micro.recall == metrics.micro.precision == 1.0
    assert metrics.false_findings_on_clean == 0
