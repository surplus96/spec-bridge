"""W5-7a: display labels name only what the ontology has, and cover every attribute."""

from pathlib import Path

import pytest

from spec_bridge.ontology.display import load_display_labels
from spec_bridge.ontology.loader import load_ontology
from tests.conftest import ONTOLOGY, ROOT

LABELS = ROOT / "ontology/display-labels.yaml"


def test_every_attribute_and_leaf_class_has_a_label() -> None:
    onto = load_ontology(ONTOLOGY)
    labels = load_display_labels(LABELS, onto)
    assert set(labels.attributes) == set(onto.attributes)
    assert {c for c, d in onto.classes.items() if not d.abstract} <= set(labels.classes)
    assert labels.origin == "synthetic" and labels.verified_by is None


def test_a_label_for_an_unknown_id_is_refused(tmp_path: Path) -> None:
    onto = load_ontology(ONTOLOGY)
    text = LABELS.read_text().replace("  bore: 실린더 내경", "  bore_typo: 실린더 내경")
    (tmp_path / "labels.yaml").write_text(text)
    with pytest.raises(ValueError, match="bore_typo"):
        load_display_labels(tmp_path / "labels.yaml", onto)
