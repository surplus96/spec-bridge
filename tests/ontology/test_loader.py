from pathlib import Path
from typing import Any

import pytest

from spec_bridge.ontology.loader import Ontology, OntologyError, load_ontology
from tests.conftest import write_yaml


def reject(tmp_path: Path, raw: dict[str, Any], match: str) -> None:
    with pytest.raises(OntologyError, match=match):
        load_ontology(write_yaml(tmp_path, raw))


def test_leaf_class_inherits_parent_attributes(onto: Ontology) -> None:
    attrs = onto.attributes_of("Pump")
    assert "maker" in attrs and "medium" in attrs and "capacity" in attrs


def test_ancestors_are_ordered_from_parent(onto: Ontology) -> None:
    assert onto.ancestors("Pump") == ["FluidMachinery", "Equipment"]


def test_rejects_unknown_parent(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["classes"]["Pump"]["parent"] = "Machinery"
    reject(tmp_path, raw, "parent")


def test_rejects_inheritance_cycle(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["classes"]["Equipment"]["parent"] = "Pump"
    reject(tmp_path, raw, "cycle")


def test_rejects_required_attribute_not_on_class(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["classes"]["Pump"]["required_all"].append("rated_power")
    reject(tmp_path, raw, "rated_power")


def test_rejects_conditional_rule_on_unknown_attribute(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["classes"]["Pump"]["conditional_required"][0]["required_all"] = ["suction_head"]
    reject(tmp_path, raw, "suction_head")


def test_rejects_undefined_unit(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["attributes"]["head"]["canonical_unit"] = "ft"
    reject(tmp_path, raw, "ft")


def test_rejects_unit_with_wrong_dimension(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["attributes"]["capacity"]["canonical_unit"] = "kW"
    reject(tmp_path, raw, "capacity")


def test_rejects_alias_on_two_attributes(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["label_aliases"].append({**raw["label_aliases"][0], "attribute": "head"})
    reject(tmp_path, raw, "alias")


def test_rejects_sourced_alias_without_source(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["label_aliases"][0]["origin"] = "sourced"
    del raw["label_aliases"][0]["source"]
    reject(tmp_path, raw, "source")


def test_six_leaf_classes(onto: Ontology) -> None:
    leaves = {c for c, d in onto.classes.items() if not d.abstract}
    assert leaves == {
        "TwoStrokeMainEngine",
        "FourStrokeEngine",
        "Pump",
        "AirCompressor",
        "Separator",
        "Turbocharger",
    }


def test_rejects_allowed_values_on_foreign_attribute(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["classes"]["Pump"]["allowed_values"] = {"application": ["fuel_oil"]}
    reject(tmp_path, raw, "application")


def test_generic_weight_alias_is_never_dry_weight(onto: Ontology) -> None:
    for alias in onto.label_aliases:
        if "weight" in alias.label.casefold() and "dry" not in alias.label.casefold():
            assert alias.attribute != "dry_weight", alias.label


def test_synthetic_alias_needs_no_source(tmp_path: Path, raw: dict[str, Any]) -> None:
    alias = raw["label_aliases"][0]
    alias["origin"] = "synthetic"
    del alias["source"], alias["location"]
    load_ontology(write_yaml(tmp_path, raw))


def test_rejects_sourced_alias_without_location(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["label_aliases"][0]["origin"] = "sourced"
    del raw["label_aliases"][0]["location"]
    reject(tmp_path, raw, "location")


def test_synthetic_alias_cannot_claim_verification(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["label_aliases"][0].update(origin="synthetic", verified_by="reviewer")
    reject(tmp_path, raw, "verified_by")


def test_no_sourced_alias_is_left_unverified(onto: Ontology) -> None:
    """CP-S1 gate: sourced real-world items need the user's verified_by (H3)."""
    pending = [a.label for a in onto.label_aliases if a.origin == "sourced" and not a.verified_by]
    assert pending == []


def test_context_descriptions_load(onto: Ontology) -> None:
    described = onto.vocabularies.descriptions
    assert described is not None and described.origin == "synthetic"
    assert described.verified_by is None  # only the user verifies (H3)


@pytest.mark.parametrize("where", ["basis", "condition"])
def test_rejects_description_of_unknown_token(
    tmp_path: Path, raw: dict[str, Any], where: str
) -> None:
    axis = next(iter(raw["vocabularies"]["descriptions"][where]))
    raw["vocabularies"]["descriptions"][where][axis]["not_a_token"] = "text"
    reject(tmp_path, raw, "unknown tokens")


def test_rejects_description_of_unknown_axis(tmp_path: Path, raw: dict[str, Any]) -> None:
    raw["vocabularies"]["descriptions"]["basis"]["not_an_axis"] = {"_": "text"}
    reject(tmp_path, raw, "unknown basis")
