"""Load ontology YAML and check cross-references (FR-01)."""

from collections import Counter
from pathlib import Path

import pint
import yaml
from pydantic import ValidationError

from spec_bridge.ontology.definitions import Ontology

__all__ = ["Ontology", "OntologyError", "load_ontology"]


class OntologyError(ValueError):
    """The ontology file is structurally invalid."""


def load_ontology(path: Path) -> Ontology:
    try:
        onto = Ontology.model_validate(yaml.safe_load(path.read_text()))
    except ValidationError as exc:
        raise OntologyError(str(exc)) from exc
    check_parents(onto)
    check_cycles(onto)  # ancestors()를 쓰는 검사보다 반드시 먼저
    check_requirements(onto)
    check_units(onto)
    check_aliases(onto)
    check_vocabularies(onto)
    return onto


def check_parents(onto: Ontology) -> None:
    for class_id, cls in onto.classes.items():
        if cls.parent is not None and cls.parent not in onto.classes:
            raise OntologyError(f"{class_id}: unknown parent {cls.parent}")


def check_cycles(onto: Ontology) -> None:
    for class_id in onto.classes:
        seen = {class_id}
        parent = onto.classes[class_id].parent
        while parent is not None:
            if parent in seen:
                raise OntologyError(f"{class_id}: inheritance cycle through {parent}")
            seen.add(parent)
            parent = onto.classes[parent].parent


def check_requirements(onto: Ontology) -> None:
    for class_id, cls in onto.classes.items():
        undefined = [a for a in cls.attributes if a not in onto.attributes]
        if undefined:
            raise OntologyError(f"{class_id}: undefined attributes {undefined}")
        allowed = set(onto.attributes_of(class_id))
        named = list(cls.required_all) + list(cls.allowed_values)
        named += [a for group in cls.required_any_groups for a in group]
        for rule in cls.conditional_required:
            named += list(rule.when)
            named += rule.required_all
            named += [a for group in rule.required_any_groups for a in group]
        unknown = sorted(set(named) - allowed)
        if unknown:
            raise OntologyError(f"{class_id}: requirement names unknown attributes {unknown}")


def check_aliases(onto: Ontology) -> None:
    for alias in onto.label_aliases:
        if alias.attribute not in onto.attributes:
            raise OntologyError(f"alias {alias.label!r}: unknown attribute {alias.attribute}")
        if alias.origin == "sourced" and (alias.source is None or alias.location is None):
            raise OntologyError(f"alias {alias.label!r}: sourced alias needs source and location")
        if alias.origin == "synthetic" and alias.verified_by is not None:
            raise OntologyError(f"alias {alias.label!r}: synthetic alias cannot carry verified_by")
    targets = Counter((alias.label.casefold(), alias.attribute) for alias in onto.label_aliases)
    labels = Counter(label for label, _ in targets)
    shared = sorted(label for label, count in labels.items() if count > 1)
    if shared:
        raise OntologyError(f"alias used for more than one attribute: {shared}")


def check_units(onto: Ontology) -> None:
    ureg = pint.UnitRegistry()
    for attr_id, attr in onto.attributes.items():
        if attr.dimension not in onto.dimensions:
            raise OntologyError(f"{attr_id}: unknown dimension {attr.dimension}")
        if attr.canonical_unit is None:
            continue
        if attr.canonical_unit not in onto.units:
            raise OntologyError(f"{attr_id}: undefined unit {attr.canonical_unit}")
        actual = ureg.parse_units(onto.units[attr.canonical_unit].pint).dimensionality
        expected = ureg.get_dimensionality(onto.dimensions[attr.dimension])
        if actual != expected:
            raise OntologyError(f"{attr_id}: {attr.canonical_unit} is not {attr.dimension}")


def check_vocabularies(onto: Ontology) -> None:
    for key, values in onto.vocabularies.basis.items():
        if "unknown" not in values:
            raise OntologyError(f"basis {key}: 'unknown' must be a listed value")
    for key, cond in onto.vocabularies.condition.items():
        if cond.kind == "token" and not cond.values:
            raise OntologyError(f"condition {key}: token kind needs values")
        if cond.kind != "token" and cond.dimension not in onto.dimensions:
            raise OntologyError(f"condition {key}: unknown dimension {cond.dimension}")

    check_descriptions(onto)


def check_descriptions(onto: Ontology) -> None:
    """Descriptions may only name axes and tokens the vocabulary has."""
    vocab, described = onto.vocabularies, onto.vocabularies.descriptions
    if described is None:
        return
    tokens = {key: set(values) for key, values in vocab.basis.items()}
    for where, texts in described.basis.items():
        _check_described("basis", where, texts, tokens)
    tokens = {key: set(cond.values) for key, cond in vocab.condition.items()}
    for where, texts in described.condition.items():
        _check_described("condition", where, texts, tokens)


def _check_described(
    kind: str, where: str, texts: dict[str, str], tokens: dict[str, set[str]]
) -> None:
    if where not in tokens:
        raise OntologyError(f"description for unknown {kind} {where!r}")
    unknown = set(texts) - tokens[where] - {"_"}
    if unknown:
        raise OntologyError(f"{kind} {where}: descriptions for unknown tokens {sorted(unknown)}")
