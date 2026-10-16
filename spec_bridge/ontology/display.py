"""Screen names for ontology ids (W5-7a, D-074): ontology/display-labels.yaml.

Display only, origin synthetic: not model input, not part of any hash. Loading checks that
every key names something the ontology has, so a renamed attribute cannot keep a stale
label unnoticed.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from spec_bridge.ontology.definitions import Ontology


class DisplayLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: str
    verified_by: str | None = None
    classes: dict[str, str]
    attributes: dict[str, str]
    basis: dict[str, str]
    condition: dict[str, str]


def load_display_labels(path: Path, onto: Ontology) -> DisplayLabels:
    labels = DisplayLabels.model_validate(yaml.safe_load(path.read_text()))
    known = {
        "classes": set(onto.classes),
        "attributes": set(onto.attributes),
        "basis": set(onto.vocabularies.basis),
        "condition": set(onto.vocabularies.condition),
    }
    for group, ids in known.items():
        unknown = sorted(set(getattr(labels, group)) - ids)
        if unknown:
            raise ValueError(f"{path.name}: {group} not in the ontology: {unknown}")
    return labels
