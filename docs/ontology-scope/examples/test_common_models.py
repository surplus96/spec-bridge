"""Structural checks use the documented synthetic examples, not real limits."""

import re
from pathlib import Path

import pytest
import yaml
from common_models import Dimensions, Fact, Location, NumericRange
from pydantic import ValidationError

DESIGN = Path(__file__).resolve().parents[1] / "schema-design.md"


@pytest.fixture
def example_facts() -> list[dict]:
    block = re.findall(r"```yaml\n(.*?)```", DESIGN.read_text(), re.S)[0]
    return yaml.safe_load(block)["attributes"]["rated_throughput"]


def test_distinct_conditions_and_repeated_evidence_survive_round_trip(example_facts):
    facts = [Fact.model_validate(value) for value in example_facts]
    assert facts[0].condition != facts[1].condition
    first = facts[0].model_copy(deep=True)
    extra = first.occurrences[0].model_copy(deep=True)
    extra.location = Location(section="3.1", paragraph=1)
    first.occurrences.append(extra)
    restored = Fact.model_validate_json(first.model_dump_json())
    assert restored == first
    assert len(restored.occurrences) == 2
    assert restored.value == facts[0].value


def test_unspecified_pressure_and_scope_stay_unknown(example_facts):
    fact = Fact.model_validate(example_facts[0])
    assert fact.basis.pressure == "unknown"
    assert Fact(value=False, unit=None, occurrences=fact.occurrences).value is False
    assert Fact(value=0, unit=None, occurrences=fact.occurrences).value == 0
    assert Fact(value=False, unit=None, occurrences=fact.occurrences).scope == "unknown"


@pytest.mark.parametrize(
    "change",
    [
        {"occurrences": []},
        {"condition": {"unregistered_condition": "anything"}},
        {"value": float("nan")},
        {"value": float("inf")},
    ],
)
def test_invalid_structure_is_rejected(example_facts, change):
    with pytest.raises(ValidationError):
        Fact.model_validate(example_facts[0] | change)


def test_numeric_string_is_preserved_until_attribute_schema_is_known(example_facts):
    fact = Fact.model_validate(example_facts[0] | {"value": "85"})
    assert isinstance(fact.value, str)


@pytest.mark.parametrize(
    "location", [{}, {"pdf_page": 0}, {"pdf_page": True}, {"row": 1}]
)
def test_ambiguous_or_invalid_position_is_rejected(location):
    with pytest.raises(ValidationError):
        Location.model_validate(location)


def test_partial_dimensions_and_range_order(example_facts):
    value = example_facts[0]["value"]
    assert Dimensions(length=value).width is None
    assert NumericRange(min=value, max=value).min == value
    with pytest.raises(ValidationError):
        Dimensions()
    with pytest.raises(ValidationError):
        NumericRange(min=value, max=example_facts[1]["value"])


def test_raw_whitespace_is_not_normalized(example_facts):
    data = example_facts[0]
    occurrence = data["occurrences"][0] | {"raw_text": "  original text  "}
    fact = Fact.model_validate(data | {"occurrences": [occurrence]})
    assert fact.occurrences[0].raw_text == "  original text  "
