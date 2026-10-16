"""W1 DoD: gold records are representable by the generated candidate schema."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from spec_bridge.ontology.gold import v2_to_candidate_input
from spec_bridge.ontology.loader import Ontology
from spec_bridge.ontology.schema import build_candidate_model
from tests.conftest import ROOT, candidate_from_answer, dev_ids, load_dev_answer

HANDWRITTEN = ROOT / "data/eval/handwritten"
LEGACY_TEXT_VISCOSITY = pytest.mark.xfail(
    strict=True,
    reason="gold v2 keeps viscosity as legacy text; structuring needs a versioned gold migration",
)


def load_v2(doc_id: str) -> dict[str, Any]:
    answer: dict[str, Any] = yaml.safe_load((HANDWRITTEN / f"{doc_id}.answer.yaml").read_text())
    return answer


def validate_v2(onto: Ontology, doc_id: str) -> Any:
    answer = load_v2(doc_id)
    model = build_candidate_model(onto, answer["expected_class"])
    return model.model_validate(v2_to_candidate_input(answer))


def test_handwritten_pump_validates(onto: Ontology) -> None:
    """The original W1 DoD: one handwritten gold record against the generated schema."""
    candidate = validate_v2(onto, "HW-PUMP-001")
    assert (
        candidate.attributes.capacity[0].value
        == load_v2("HW-PUMP-001")["attributes"]["capacity"]["value"]
    )


@pytest.mark.parametrize(
    "doc_id",
    [
        "HW-2S-001",
        "HW-4S-001",
        "HW-COMP-001",
        pytest.param("HW-SEP-001", marks=LEGACY_TEXT_VISCOSITY),
        "HW-TC-001",
    ],
)
def test_other_handwritten_records(onto: Ontology, doc_id: str) -> None:
    validate_v2(onto, doc_id)


def test_conditional_values_become_separate_facts() -> None:
    converted = v2_to_candidate_input(load_v2("HW-SEP-001"))
    assert len(converted["attributes"]["rated_throughput"]) == 2


def test_evaluator_metadata_is_dropped() -> None:
    converted = v2_to_candidate_input(load_v2("HW-2S-001"))
    for facts in converted["attributes"].values():
        for fact in facts:
            assert "expected_status" not in fact
            assert "match_tolerance_rel" not in fact


@pytest.mark.parametrize("input_id", dev_ids())
def test_dev_gold_validates(onto: Ontology, input_id: str) -> None:
    candidate_from_answer(onto, load_dev_answer(input_id))


def test_handwritten_files_exist() -> None:
    assert len(list(Path(HANDWRITTEN).glob("HW-*.answer.yaml"))) == 6


def test_conditional_values_keep_their_own_context() -> None:
    """L3: sibling facts keep their condition/occurrences and inherit basis/scope."""
    entry = load_v2("HW-SEP-001")["attributes"]["rated_throughput"]
    extra = entry["conditional_values"][0]
    first, second = v2_to_candidate_input(load_v2("HW-SEP-001"))["attributes"]["rated_throughput"]
    assert first["basis"] == second["basis"] == {"rating": entry["rating_basis"]}
    assert first["scope"] == second["scope"] == entry.get("scope", "unknown")
    assert (first["value"], first["condition"]) == (entry["value"], entry["condition"])
    assert (second["value"], second["condition"]) == (extra["value"], extra["condition"])
    assert [o["raw_text"] for o in second["occurrences"]] == [
        o["raw_text"] for o in extra["occurrences"]
    ]
