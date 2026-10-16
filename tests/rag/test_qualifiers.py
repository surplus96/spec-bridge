"""W4-R R4: the qualifier chain verifies every field against the line (no invention)."""

from typing import Any

import pytest

from spec_bridge.llm.provider import LlmError
from spec_bridge.normalize.dictionary import load_dictionary
from spec_bridge.normalize.values import Normalizer
from spec_bridge.ontology.loader import Ontology, load_ontology
from spec_bridge.rag.knowledge import KbExample, Qualifiers
from spec_bridge.rag.qualifiers import (
    QualifierItem,
    build_chain,
    line_parts,
    qualifier_schema,
    query_of,
)
from spec_bridge.rag.retrieval import KbBM25Retriever
from spec_bridge.service import normalizer_for
from tests.conftest import ONTOLOGY
from tests.llm.fakes import FakeProvider

LINE = "Flow | 95.67 | m3/h | nominal rating; at 50 Hz; for main pump"
ITEM = QualifierItem(
    attribute="capacity",
    value_text="95.67",
    unit_text="m3/h",
    line_text=LINE,
    parent_text=f"Table header: Item | Value | Unit | Conditions\nLine: {LINE}",
    family_id="FAM-SELF",
)


def case(i: str, family: str, text: str, q: Qualifiers, ev: dict[str, str]) -> KbExample:
    return KbExample(
        example_id=i,
        doc_id=i.split(":")[0],
        family_id=family,
        split="dev",
        attribute="capacity",
        label_text=None,
        line_text=text,
        parent_text=f"Line: {text}",
        qualifiers=q,
        evidence=ev,
    )


KB = [
    case(
        "O:1",
        "FAM-OTHER",
        "Capacity | 120 | m3/h | nominal rating; at 60 Hz; for main pump",
        Qualifiers(
            basis={"rating": "nominal"}, condition={"frequency": "60 Hz"}, scope="main pump"
        ),
        {"basis.rating": "nominal rating", "condition.frequency": "60 Hz", "scope": "main pump"},
    ),
    case(
        "S:1",
        "FAM-SELF",
        "Flow | 95.67 | m3/h | nominal rating; at 50 Hz; for main pump",
        Qualifiers(basis={"rating": "nominal"}),
        {"basis.rating": "nominal rating"},
    ),
    # unrelated cases: a realistic corpus keeps BM25 weights positive for shared words
    case("F:1", "FAM-F1", "Dry weight | 5 | kg | dry; for main pump", Qualifiers(), {}),
    case("F:2", "FAM-F2", "Bore | 240 | mm | —", Qualifiers(), {}),
    case("F:3", "FAM-F3", "Stroke | 310 | mm | —", Qualifiers(), {}),
]


@pytest.fixture(scope="module")
def onto() -> Ontology:  # module scope: shared by the module-scoped normalizer
    return load_ontology(ONTOLOGY)


@pytest.fixture(scope="module")
def normalizer(onto: Ontology) -> Normalizer:
    return normalizer_for(onto, "dev", load_dictionary())


def ask(
    onto: Ontology, normalizer: Normalizer, reply: dict[str, Any] | Exception, *, rag: bool = True
) -> tuple[Any, FakeProvider]:
    provider = FakeProvider([reply])
    retriever = KbBM25Retriever(KB) if rag else None
    chain = build_chain(onto, normalizer, provider, KB, retriever)
    return chain.invoke(ITEM), provider


GOOD = {
    "basis": {"rating": {"value": "nominal", "evidence": "nominal rating"}},
    "condition": {"frequency": {"value": "50 Hz", "evidence": "at 50 Hz"}},
    "scope": {"value": "main pump", "evidence": "for main pump"},
}


def test_supported_fields_are_kept(onto: Ontology, normalizer: Normalizer) -> None:
    result, _ = ask(onto, normalizer, GOOD)
    assert result.qualifiers == Qualifiers(
        basis={"rating": "nominal"}, condition={"frequency": "50 Hz"}, scope="main pump"
    )
    assert result.rejected == [] and result.evidence["scope"] == "for main pump"


@pytest.mark.parametrize(
    "reply, reason",
    [
        (
            {"basis": {"rating": {"value": "nominal", "evidence": "rated nominally"}}},
            "basis.rating: evidence not in the line",
        ),
        ({"basis": {"rating": {"value": "nominal", "evidence": ""}}}, "basis.rating: no evidence"),
        (
            {"basis": {"rating": {"value": "unknown", "evidence": "nominal rating"}}},
            "basis.rating: not in the vocabulary",
        ),
        (
            {"condition": {"frequency": {"value": "60 Hz", "evidence": "at 50 Hz"}}},
            "condition.frequency: number not in the line",
        ),
        (
            {"condition": {"frequency": {"value": "50 kW", "evidence": "at 50 Hz"}}},
            "condition.frequency: wrong unit or form",
        ),
        ({"scope": {"value": "Flow", "evidence": "Flow"}}, "scope: phrase not in the remarks"),
    ],
)
def test_unsupported_fields_are_dropped(
    onto: Ontology, normalizer: Normalizer, reply: dict[str, Any], reason: str
) -> None:
    result, _ = ask(onto, normalizer, reply)
    assert result.qualifiers == Qualifiers() and result.rejected == [reason]


@pytest.mark.parametrize(
    "reply, reason",
    [
        ({"basis": {"rating": "nominal"}}, "basis.rating: not an object"),
        ({"condition": {"frequency": "50 Hz"}}, "condition.frequency: not an object"),
        ({"basis": "nominal"}, "basis: not an object"),
        ({"condition": ["50 Hz"]}, "condition: not an object"),
        ({"scope": "main pump"}, "scope: not an object"),
    ],
)
def test_a_reply_off_the_schema_is_rejected_not_a_crash(
    onto: Ontology, normalizer: Normalizer, reply: dict[str, Any], reason: str
) -> None:
    """A provider without strict structured output (cloud, strict=False) may answer a field
    as a bare string; the W5-4 cloud demo failed a whole job on that (D-067)."""
    result, _ = ask(onto, normalizer, reply)
    assert result.qualifiers == Qualifiers() and result.rejected == [reason]


def test_the_own_family_is_never_shown(onto: Ontology, normalizer: Normalizer) -> None:
    result, provider = ask(onto, normalizer, GOOD)
    prompt = provider.prompts[0]["user"]
    assert result.retrieved_ids[0] == "O:1" and "S:1" not in result.retrieved_ids
    assert "Solved case 1" in prompt and KB[1].line_text not in prompt.split("Now answer")[0]
    assert '"value": "60 Hz"' in prompt  # the case is shown with its answer


def test_without_retrieval_the_question_is_the_same(onto: Ontology, normalizer: Normalizer) -> None:
    result, provider = ask(onto, normalizer, GOOD, rag=False)
    assert "Solved cases: none" in provider.prompts[0]["user"]
    assert result.retrieved_ids == [] and result.qualifiers.scope == "main pump"


def test_model_failure_keeps_the_value_unqualified(onto: Ontology, normalizer: Normalizer) -> None:
    result, _ = ask(onto, normalizer, LlmError("qualify", "timeout"))
    assert result.qualifiers == Qualifiers() and result.rejected == ["llm: timeout"]


def test_schema_hides_contract_defaults_and_requires_evidence(onto: Ontology) -> None:
    schema = qualifier_schema(onto)
    rating = schema["properties"]["basis"]["properties"]["rating"]
    assert "unknown" not in rating["properties"]["value"]["enum"]
    assert rating["required"] == ["value", "evidence"] and "required" not in schema


def test_line_parts_and_query() -> None:
    assert line_parts(LINE) == ("Flow", "nominal rating; at 50 Hz; for main pump")
    assert line_parts("Dry mass — 5 kg (dry; main unit)") == ("Dry mass", "dry; main unit")
    nested = "FAD* — 125.52 m3/h (reference 20 degC; 1013 mbar(a); main compressor)"
    assert line_parts(nested)[1] == "reference 20 degC; 1013 mbar(a); main compressor"
    assert query_of(ITEM) == "Flow nominal rating; at 50 Hz; for main pump"


def test_an_axis_answered_with_no_value_is_not_a_proposal(
    onto: Ontology, normalizer: Normalizer
) -> None:
    """D-072: a provider without strict output lists every axis, most with null. A field
    with no value proposes nothing: it is neither kept nor rejected."""
    empty: dict[str, Any] = {"value": None, "evidence": None}
    reply = {
        "basis": {axis: empty for axis in onto.vocabularies.basis}
        | {"rating": {"value": "nominal", "evidence": "nominal rating"}},
        "condition": {"frequency": {"value": "none", "evidence": ""}, "medium": empty},
        "scope": GOOD["scope"],
    }
    result, _ = ask(onto, normalizer, reply)
    assert result.qualifiers == Qualifiers(basis={"rating": "nominal"}, scope="main pump")
    assert result.rejected == []
