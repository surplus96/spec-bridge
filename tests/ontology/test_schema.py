import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from spec_bridge.ontology.loader import Ontology
from spec_bridge.ontology.schema import build_candidate_model, export_json_schemas
from tests.conftest import load_dev_answer, to_facts


def candidate(onto: Ontology, class_id: str, attrs: dict[str, Any]) -> Any:
    return build_candidate_model(onto, class_id).model_validate({"attributes": attrs})


def first_fact(input_id: str, attribute: str) -> tuple[str, dict[str, Any]]:
    answer = load_dev_answer(input_id)
    return answer["expected_class"], to_facts(answer, attribute)[0]


def test_two_viscosity_conditions_are_two_valid_facts(onto: Ontology) -> None:
    answer = load_dev_answer("SYN-032")
    facts = to_facts(answer, "rated_throughput")
    result = candidate(onto, answer["expected_class"], {"rated_throughput": facts})
    assert len(result.attributes.rated_throughput) == 2


def test_unknown_condition_key_rejected(onto: Ontology) -> None:
    class_id, fact = first_fact("SYN-032", "rated_throughput")
    fact["condition"]["humidity"] = "high"
    with pytest.raises(ValidationError, match="humidity"):
        candidate(onto, class_id, {"rated_throughput": [fact]})


def test_basis_token_outside_vocabulary_rejected(onto: Ontology) -> None:
    class_id, fact = first_fact("SYN-032", "rated_throughput")
    fact["basis"]["rating"] = "guessed"
    with pytest.raises(ValidationError):
        candidate(onto, class_id, {"rated_throughput": [fact]})


def test_reversed_range_rejected(onto: Ontology) -> None:
    class_id, fact = first_fact("SYN-017", "applicable_engine_power")
    fact["value"] = {"min": fact["value"]["max"], "max": fact["value"]["min"]}
    with pytest.raises(ValidationError, match="minimum"):
        candidate(onto, class_id, {"applicable_engine_power": [fact]})


def test_non_canonical_unit_rejected(onto: Ontology) -> None:
    class_id, fact = first_fact("SYN-032", "rated_throughput")
    fact["unit"] = "m3/h"
    with pytest.raises(ValidationError):
        candidate(onto, class_id, {"rated_throughput": [fact]})


def test_boolean_is_not_a_number(onto: Ontology) -> None:
    class_id, fact = first_fact("SYN-032", "rated_throughput")
    fact["value"] = True
    with pytest.raises(ValidationError):
        candidate(onto, class_id, {"rated_throughput": [fact]})


def test_zero_and_false_are_values(onto: Ontology) -> None:
    class_id, cleaning = first_fact("SYN-032", "self_cleaning")
    _, throughput = first_fact("SYN-032", "rated_throughput")
    cleaning["value"], throughput["value"] = False, 0
    result = candidate(
        onto, class_id, {"self_cleaning": [cleaning], "rated_throughput": [throughput]}
    )
    assert result.attributes.self_cleaning[0].value is False


def test_fact_needs_an_occurrence(onto: Ontology) -> None:
    class_id, fact = first_fact("SYN-032", "rated_throughput")
    fact["occurrences"] = []
    with pytest.raises(ValidationError):
        candidate(onto, class_id, {"rated_throughput": [fact]})


def test_exports_one_schema_per_leaf_class(onto: Ontology, tmp_path: Path) -> None:
    paths = export_json_schemas(onto, tmp_path)
    assert len(paths) == 6
    schema = json.loads(paths[0].read_text())
    assert "attributes" in schema["properties"]
