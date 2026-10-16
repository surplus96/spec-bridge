import json
from typing import Any

import pytest

from spec_bridge.extract.extractor import Extraction, RawObservation
from spec_bridge.normalize.dictionary import build_dev_dictionary, dev_answers, load_dictionary
from spec_bridge.normalize.values import Normalizer, Unresolved, normalize_extraction, parse_number
from spec_bridge.ontology.loader import Ontology, load_ontology
from tests.conftest import ROOT, dev_ids

REGISTRY = ROOT / "data/synth/registry"
DEV_ANSWERS = dev_answers()
INVALID_REASONS = {
    "invalid_unit": {"dimension"},
    "invalid_shape": {"not_a_number", "not_integer", "reversed_range"},
}


@pytest.fixture(scope="module")
def normalizer() -> Normalizer:
    onto = load_ontology(ROOT / "ontology/ontology.yaml")
    makers = json.loads((REGISTRY / "manufacturers.json").read_text())
    models = [
        json.loads(line)["model_designation"]
        for line in (REGISTRY / "dev.jsonl").read_text().splitlines()
    ]
    return Normalizer(onto, load_dictionary(), makers, models)


def as_text(condition: dict[str, Any]) -> dict[str, Any]:
    """Gold condition objects written the way a document would show them."""
    text: dict[str, Any] = {}
    for key, value in condition.items():
        if isinstance(value, dict) and "reference_temperature" in value:
            ref = value["reference_temperature"]
            text[key] = f"{value['value']} {value['unit']} at {ref['value']} {ref['unit']}"
        elif isinstance(value, dict):
            text[key] = f"{value['value']} {value['unit']}"
        else:
            text[key] = value
    return text


def raw_from(obs: dict[str, Any], fact: dict[str, Any] | None) -> RawObservation:
    return RawObservation(
        attribute=obs["attribute_id"],
        value_text=obs["raw_text"],
        unit_text=obs["unit_text"],
        basis=fact["basis"] if fact else {},
        condition=as_text(fact["condition"]) if fact else {},
        scope=fact["scope"] if fact else "main_equipment",
        occurrence={},
    )


@pytest.mark.parametrize("answer", DEV_ANSWERS, ids=[a["input_id"] for a in DEV_ANSWERS])
def test_gold_observations_normalize_back_to_gold_facts(
    normalizer: Normalizer, answer: dict[str, Any]
) -> None:
    observations = {o["observation_id"]: o for o in answer["observations"]}
    wrong = []
    for fact in answer["facts"]:
        for oid in fact["observation_ids"]:
            got = normalizer.fact(raw_from(observations[oid], fact))
            want = {k: fact[k] for k in ("value", "unit", "condition")}
            if isinstance(got, Unresolved) or {k: got[k] for k in want} != want:
                wrong.append((oid, got))
    assert wrong == []


@pytest.mark.parametrize("answer", DEV_ANSWERS, ids=[a["input_id"] for a in DEV_ANSWERS])
def test_invalid_gold_observations_stay_unresolved(
    normalizer: Normalizer, answer: dict[str, Any]
) -> None:
    for obs in answer["observations"]:
        if obs["interpretation"] in INVALID_REASONS:
            got = normalizer.fact(raw_from(obs, None))
            assert isinstance(got, Unresolved), obs["observation_id"]
            assert got.reason in INVALID_REASONS[obs["interpretation"]]


def test_dictionary_is_built_from_dev_only() -> None:
    dictionary = load_dictionary()
    assert dictionary == build_dev_dictionary(DEV_ANSWERS)
    assert dictionary["source"]["documents"] == sorted(dev_ids())


def test_conflicting_display_forms_are_rejected() -> None:
    clash = {
        "input_id": "X",
        "observations": [
            {
                "attribute_id": "medium",
                "raw_text": "oil",
                "parsed_value": v,
                "interpretation": "normalized",
            }
            for v in ("heavy_fuel_oil", "lubricating_oil")
        ],
    }
    with pytest.raises(ValueError, match="maps to"):
        build_dev_dictionary([clash])


@pytest.mark.parametrize(
    "condition",
    [
        {"frequency": "50 kW"},
        {"viscosity": "380 cSt at 50 bar"},
        {"humidity": "dry"},
        {"rating_point": "R9"},
    ],
)
def test_condition_with_wrong_unit_or_word_is_unresolved(
    normalizer: Normalizer, condition: dict[str, Any]
) -> None:
    raw = RawObservation(
        attribute="bore",
        value_text="650",
        unit_text="mm",
        basis={},
        condition=condition,
        scope="main_equipment",
        occurrence={},
    )
    result = normalizer.fact(raw)
    assert isinstance(result, Unresolved) and result.reason == "condition"


@pytest.mark.parametrize(
    "unit, reason",
    [("bhp", "unknown_unit"), ("ton", "unknown_unit"), ("", "missing_unit"), ("kW", "dimension")],
)
def test_units_are_never_guessed(normalizer: Normalizer, unit: str, reason: str) -> None:
    raw = RawObservation(
        attribute="dry_weight",
        value_text="12",
        unit_text=unit,
        basis={},
        condition={},
        scope="main_equipment",
        occurrence={},
    )
    result = normalizer.fact(raw)
    assert isinstance(result, Unresolved) and result.reason == reason


def observation(attribute: str, value_text: str, unit_text: str | None) -> RawObservation:
    return RawObservation(
        attribute=attribute,
        value_text=value_text,
        unit_text=unit_text,
        basis={},
        condition={},
        scope="main_equipment",
        occurrence={},
    )


def test_unit_copied_into_the_value_is_split_off(normalizer: Normalizer) -> None:
    unit = normalizer.onto.attributes["dry_weight"].canonical_unit
    assert unit is not None
    for value_text, unit_text in [
        (f"12 {unit}", unit),
        (f"12 {unit}", f"({unit})"),
        ("12", f"({unit})"),
    ]:
        got = normalizer.fact(observation("dry_weight", value_text, unit_text))
        assert not isinstance(got, Unresolved) and (got["value"], got["unit"]) == (12, unit)


@pytest.mark.parametrize("unit_given", [False, True])
def test_unit_is_never_read_from_the_value_alone(normalizer: Normalizer, unit_given: bool) -> None:
    unit = normalizer.onto.attributes["dry_weight"].canonical_unit
    value_text, unit_text = (f"12{unit}", unit) if unit_given else (f"12 {unit}", None)
    got = normalizer.fact(observation("dry_weight", value_text, unit_text))
    assert isinstance(got, Unresolved) and got.reason == "not_a_number"


def test_unregistered_model_keeps_its_text(normalizer: Normalizer) -> None:
    value, _ = normalizer.value("model_designation", "ZZ-NEW 1", None)
    assert value == "ZZ-NEW 1"


@pytest.mark.parametrize("text, number", [("1,450", 1450), ("334845.0", 334845.0), ("30", 30)])
def test_parse_number(text: str, number: float) -> None:
    assert parse_number(text) == number and type(parse_number(text)) is type(number)


def test_extraction_is_normalized_merged_and_checked(
    onto: Ontology, normalizer: Normalizer
) -> None:
    answer = DEV_ANSWERS[0]
    fact = next(f for f in answer["facts"] if isinstance(f["value"], (int, float)))
    obs = next(o for o in answer["observations"] if o["observation_id"] in fact["observation_ids"])
    raw = raw_from(obs, fact).model_copy(
        update={
            "occurrence": {
                "source_document_id": answer["input_id"],
                "raw_text": obs["raw_text"],
                "location": {"paragraph": 1},
            }
        }
    )
    extraction = Extraction(
        document_id=answer["input_id"], class_id=answer["expected_class"], mode="C", raw=[raw, raw]
    )
    facts, unresolved = normalize_extraction(onto, extraction, normalizer)
    assert len(facts) == 1 and len(facts[0]["occurrences"]) == 2 and unresolved == []
