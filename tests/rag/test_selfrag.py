"""W4-R R5 (D-052): the Self-RAG support check can only remove context, never add it."""

from typing import Any

import pytest

from spec_bridge.llm.provider import LlmError
from spec_bridge.normalize.dictionary import load_dictionary
from spec_bridge.normalize.values import Normalizer
from spec_bridge.ontology.loader import Ontology, load_ontology
from spec_bridge.rag.knowledge import Qualifiers
from spec_bridge.rag.qualifiers import QualifierItem, QualifierResult, build_chain
from spec_bridge.rag.selfrag import check_support, support_prompt
from spec_bridge.service import normalizer_for
from tests.conftest import ONTOLOGY
from tests.llm.fakes import FakeProvider

LINE = "Overall dimensions (L × W × H) | 4700 × 2000 × 2760 | mm | engine without generator"
ITEM = QualifierItem(
    attribute="dimensions",
    value_text="4700 × 2000 × 2760",
    unit_text="mm",
    line_text=LINE,
    parent_text=f"Line: {LINE}",
)
RESULT = QualifierResult(
    qualifiers=Qualifiers(condition={"rating_point": "R1"}, scope="engine without generator"),
    evidence={"condition.rating_point": "engine", "scope": "engine without generator"},
    rejected=[],
    retrieved_ids=["X:1"],
)


def checked(reply: dict[str, Any] | Exception) -> tuple[QualifierResult, FakeProvider]:
    provider = FakeProvider([reply])
    return check_support(provider, ITEM, RESULT), provider


def test_unsupported_fields_are_dropped_and_remembered() -> None:
    result, _ = checked(
        {
            "checks": [
                {"field": "condition.rating_point", "supported": False},
                {"field": "scope", "supported": True},
            ]
        }
    )
    assert result.qualifiers == Qualifiers(scope="engine without generator")
    assert result.evidence == {"scope": "engine without generator"}
    assert result.rejected == ["condition.rating_point: not supported (self-check)"]
    assert result.before_check == RESULT.qualifiers


def test_the_check_cannot_add_fields() -> None:
    result, _ = checked({"checks": [{"field": "basis.weight", "supported": True}]})
    assert result.qualifiers == RESULT.qualifiers and result.rejected == []


def test_a_failed_check_keeps_the_verified_answer() -> None:
    result, _ = checked(LlmError("qualify-check", "timeout"))
    assert result.qualifiers == RESULT.qualifiers
    assert result.rejected == ["self-check: llm timeout"]


def test_nothing_to_check_means_no_call() -> None:
    empty = RESULT.model_copy(update={"qualifiers": Qualifiers(), "evidence": {}})
    provider = FakeProvider([])
    assert check_support(provider, ITEM, empty) == empty and provider.prompts == []


def test_prompt_lists_each_field_with_its_quote() -> None:
    prompt = support_prompt(ITEM, RESULT)
    assert 'condition.rating_point = R1 (quoted: "engine")' in prompt
    assert f"Line: {LINE}" in prompt


@pytest.fixture(scope="module")
def onto() -> Ontology:
    return load_ontology(ONTOLOGY)


@pytest.fixture(scope="module")
def normalizer(onto: Ontology) -> Normalizer:
    return normalizer_for(onto, "dev", load_dictionary())


def test_chain_runs_the_check_after_verification(onto: Ontology, normalizer: Normalizer) -> None:
    reply = {
        "condition": {"rating_point": {"value": "R1", "evidence": "engine"}},
        "scope": {"value": "engine without generator", "evidence": "engine without generator"},
    }
    check = {"checks": [{"field": "condition.rating_point", "supported": False}]}
    provider = FakeProvider([reply, check])
    chain = build_chain(onto, normalizer, provider, [], None, self_check=True)
    result = chain.invoke(ITEM)
    assert [p["task"] for p in provider.prompts] == ["qualify", "qualify-check"]
    assert result.qualifiers == Qualifiers(scope="engine without generator")
