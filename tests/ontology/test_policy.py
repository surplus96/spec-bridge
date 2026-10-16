from typing import Any

import pytest
from pydantic import ValidationError

from spec_bridge.ontology.loader import Ontology
from spec_bridge.ontology.policy import missing_required, presence_status
from tests.conftest import candidate_from_answer, dev_ids, first_dev_answer, load_dev_answer


def without(answer: dict[str, Any], *attributes: str) -> dict[str, Any]:
    kept = [f for f in answer["facts"] if f["attribute_id"] not in attributes]
    return answer | {"facts": kept}


@pytest.mark.parametrize("input_id", dev_ids())
def test_matches_gold_missing_required(onto: Ontology, input_id: str) -> None:
    answer = load_dev_answer(input_id)
    candidate = candidate_from_answer(onto, answer)
    expected = answer["missing_required"]
    assert missing_required(onto, answer["expected_class"], candidate) == expected


def test_clean_document_has_required_presence(onto: Ontology) -> None:
    answer = first_dev_answer("Pump", "head")
    assert presence_status(onto, "Pump", candidate_from_answer(onto, answer)) == "present"


def test_any_group_lists_every_member(onto: Ontology) -> None:
    compressor = first_dev_answer("AirCompressor", "max_pressure")
    answer = without(compressor, "max_pressure", "working_pressure")
    candidate = candidate_from_answer(onto, answer)
    expected = ["max_pressure", "working_pressure"]
    assert missing_required(onto, "AirCompressor", candidate) == expected


def test_unknown_pump_type_is_undetermined_not_missing(onto: Ontology) -> None:
    answer = without(first_dev_answer("Pump", "head"), "head")
    for fact in answer["facts"]:
        if fact["attribute_id"] == "pump_type":
            fact["value"] = "unlisted_type_for_test"
    candidate = candidate_from_answer(onto, answer)
    assert missing_required(onto, "Pump", candidate) == []
    assert presence_status(onto, "Pump", candidate) == "undetermined"


def test_empty_string_cannot_satisfy_required(onto: Ontology) -> None:
    answer = first_dev_answer("Pump", "head")
    for fact in answer["facts"]:
        if fact["attribute_id"] == "pump_type":
            fact["value"] = ""
    with pytest.raises(ValidationError):
        candidate_from_answer(onto, answer)


def test_presence_check_does_not_judge_context(onto: Ontology) -> None:
    """D-022: unknown critical basis/condition is a W4 readiness review, not this check."""
    answer = first_dev_answer("AirCompressor", "max_pressure")
    for fact in answer["facts"]:
        fact["basis"], fact["condition"], fact["scope"] = {}, {}, "unknown"
    assert presence_status(onto, "AirCompressor", candidate_from_answer(onto, answer)) == "present"
