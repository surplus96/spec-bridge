"""W5-6 review: explanations in words (approved fixes 1-3)."""

from spec_bridge.ontology.loader import load_ontology
from spec_bridge.registry.explain import explain_unresolved, place_of, shown_value
from tests.conftest import ONTOLOGY

ONTO = load_ontology(ONTOLOGY)


def test_the_unit_is_shown_once() -> None:
    assert shown_value("5230.4 kg", "kg") == "5230.4 kg"
    assert shown_value("5230.4", "(kg)") == "5230.4 kg"
    assert shown_value("12", None) == "12"


def test_a_dimension_mismatch_names_both_dimensions_from_the_ontology() -> None:
    attribute = next(a for a, d in ONTO.attributes.items() if d.dimension == "volume_flow")
    unit = next(u for u in ONTO.units if u == "kg")
    row = {"attribute": attribute, "value_text": "1", "unit_text": unit, "reason": "dimension"}
    text = explain_unresolved(ONTO, row)
    canonical = ONTO.attributes[attribute].canonical_unit
    assert "질량" in text and "부피 유량" in text and f"({canonical})" in text


def test_places_read_like_a_person_would_say_them() -> None:
    pdf = {"pdf_page": 1, "bbox": [1.0, 2.0, 3.0, 4.0], "section": "Specifications"}
    assert place_of(pdf, "Throughput") == "1쪽 · Specifications · 라벨 Throughput"
    assert place_of({"table": 1, "row": 2, "column": 3}) == "표 1 2행 3열"
    assert place_of({"sheet": "Spec", "cell_ref": "B13"}) == "시트 Spec · 셀 B13"


def test_context_reasons_keep_real_axes_and_drop_invented_ones() -> None:
    from spec_bridge.registry.explain import explain_context_reason

    axis = next(iter(ONTO.vocabularies.basis))
    real = explain_context_reason(ONTO, f"basis.{axis}: evidence not in the line")
    assert real == f"기준 {axis} — 모델의 근거 구절이 원문 줄에 없음"
    assert explain_context_reason(ONTO, "scope: phrase not in the remarks") == (
        "범위 — 범위 구절이 비고에 없음"
    )
    assert explain_context_reason(ONTO, "basis.capacity_invented: not in the vocabulary") is None
    assert explain_context_reason(ONTO, "basis: not an object") is None
