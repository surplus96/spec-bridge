"""W4-2/3: the validator reproduces the dev answer contract's issues and readiness."""

from typing import Any

import pytest

from spec_bridge.normalize.dictionary import dev_answers, load_dictionary
from spec_bridge.normalize.values import Normalizer, Unresolved
from spec_bridge.ontology.loader import Ontology, load_ontology
from spec_bridge.service import normalizer_for
from spec_bridge.validate.findings import UNRESOLVED_CODES, code_for_unresolved
from spec_bridge.validate.validator import validate
from tests.conftest import ONTOLOGY
from tests.normalize.test_values import raw_from

ANSWERS = dev_answers()
INVALID = {"invalid_unit", "invalid_shape"}


@pytest.fixture(scope="module")
def onto() -> Ontology:
    return load_ontology(ONTOLOGY)


@pytest.fixture(scope="module")
def normalizer(onto: Ontology) -> Normalizer:
    return normalizer_for(onto, "dev", load_dictionary())


def gold_inputs(
    answer: dict[str, Any], normalizer: Normalizer
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Gold facts in pipeline form, and the gold E2/E3 observations as the normalizer
    leaves them (unresolved, with its reason)."""
    observations = {o["observation_id"]: o for o in answer["observations"]}
    facts = [
        {k: f[k] for k in ("value", "unit", "basis", "condition", "scope")}
        | {
            "attribute": f["attribute_id"],
            "occurrences": [
                {
                    "source_document_id": answer["input_id"],
                    "raw_text": observations[i]["raw_text"],
                    "location": {"paragraph": 1},
                }
                for i in f["observation_ids"]
            ],
        }
        for f in answer["facts"]
    ]
    unresolved = []
    for obs in answer["observations"]:
        if obs["interpretation"] in INVALID:
            got = normalizer.fact(raw_from(obs, None))
            assert isinstance(got, Unresolved)
            unresolved.append(got.model_dump())
    return facts, unresolved


def kind(rule_ref: str) -> str:
    last = rule_ref.rsplit("/", 1)[-1]
    return "allowed_values" if last.endswith("allowed_values") else last


@pytest.mark.parametrize("answer", ANSWERS, ids=[a["input_id"] for a in ANSWERS])
def test_gold_issues_are_reproduced(
    onto: Ontology, normalizer: Normalizer, answer: dict[str, Any]
) -> None:
    facts, unresolved = gold_inputs(answer, normalizer)
    result = validate(onto, answer["expected_class"], facts, unresolved)
    got = sorted((f.code, tuple(f.attribute_ids), kind(f.rule_ref)) for f in result.findings)
    want = sorted(
        (i["code"], tuple(i["attribute_ids"]), kind(i["rule_ref"])) for i in answer["issues"]
    )
    assert got == want
    assert result.missing_required == sorted(answer["missing_required"])
    assert (result.status == "ready") == (not answer["issues"])


def fact(
    attribute: str, value: Any, *, scope: str = "main_equipment", **context: Any
) -> dict[str, Any]:
    return {
        "attribute": attribute,
        "value": value,
        "unit": context.pop("unit", None),
        "basis": context.pop("basis", {}),
        "condition": context.pop("condition", {}),
        "scope": scope,
        "occurrences": [
            {"source_document_id": "X", "raw_text": str(value), "location": {"paragraph": 1}}
        ],
    }


def clean_answer(onto: Ontology, normalizer: Normalizer, cls: str) -> list[dict[str, Any]]:
    answer = next(a for a in ANSWERS if a["expected_class"] == cls and not a["issues"])
    return gold_inputs(answer, normalizer)[0]


def test_values_in_other_contexts_are_not_e5(onto: Ontology, normalizer: Normalizer) -> None:
    facts = clean_answer(onto, normalizer, "TwoStrokeMainEngine")
    power = next(f for f in facts if f["attribute"] == "rated_power")
    other = power | {"value": power["value"] + 1, "condition": {"rating_point": "R2"}}
    result = validate(onto, "TwoStrokeMainEngine", [*facts, other], [])
    assert not [f for f in result.findings if f.code == "E5"]
    same = power | {"value": power["value"] + 1}
    result = validate(onto, "TwoStrokeMainEngine", [*facts, same], [])
    assert [f.code for f in result.findings] == ["E5"]


def test_unknown_conditional_branch_is_undetermined_not_e1(
    onto: Ontology, normalizer: Normalizer
) -> None:
    facts = [f for f in clean_answer(onto, normalizer, "Pump") if f["attribute"] != "pump_type"]
    facts += [fact("pump_type", "not_a_listed_type")]
    facts = [
        f
        for f in facts
        if f["attribute"] not in ("head", "differential_pressure", "discharge_pressure")
    ]
    result = validate(onto, "Pump", facts, [])
    assert result.presence == "undetermined" and not [f for f in result.findings if f.code == "E1"]
    assert result.status == "needs_review"


def test_unknown_class_needs_review(onto: Ontology) -> None:
    result = validate(onto, "unknown", [], [])
    assert result.status == "needs_review" and result.findings == []


def test_every_normalizer_reason_has_a_code() -> None:
    from typing import get_args

    from spec_bridge.normalize.values import Reason

    assert set(UNRESOLVED_CODES) == set(get_args(Reason))
    assert code_for_unresolved("unknown_unit") == "REVIEW"
