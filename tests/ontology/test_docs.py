from spec_bridge.ontology.docs import OUTPUT, render_definition_markdown
from spec_bridge.ontology.loader import Ontology


def test_every_leaf_class_and_attribute_is_documented(onto: Ontology) -> None:
    text = render_definition_markdown(onto)
    for class_id, cls in onto.classes.items():
        if not cls.abstract:
            assert f"### {class_id}" in text
    for attr_id in onto.attributes:
        assert f"| {attr_id} |" in text


def test_rendering_is_deterministic(onto: Ontology) -> None:
    assert render_definition_markdown(onto) == render_definition_markdown(onto)


def test_unverified_sources_are_marked(onto: Ontology) -> None:
    text = render_definition_markdown(onto)
    unverified = [a for a in onto.label_aliases if a.verified_by is None]
    assert text.count("미검증") >= len(unverified)


def test_committed_document_matches_ontology(onto: Ontology) -> None:
    """The checked-in definition must be regenerated whenever the YAML changes."""
    assert OUTPUT.read_text() == render_definition_markdown(onto)


def test_alias_origin_is_shown(onto: Ontology) -> None:
    text = render_definition_markdown(onto)
    synthetic = [a for a in onto.label_aliases if a.origin == "synthetic"]
    assert text.count("| 합성 |") >= len(synthetic)
