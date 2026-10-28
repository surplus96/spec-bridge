"""BOM candidate suggestion (D-112): the evaluated C configuration on one pending row."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.bom.reader import BomRow
from spec_bridge.bom.suggest import suggest
from spec_bridge.llm.provider import LlmError
from spec_bridge.ontology.loader import Ontology
from spec_bridge.registry.store import RegistryStore
from tests.bom.test_bom import answer, store_for
from tests.llm.fakes import FakeProvider


@pytest.fixture
def dev(tmp_path: Path, onto: Ontology) -> Iterator[RegistryStore]:
    s = store_for(tmp_path, onto, "dev", relations=False)
    yield s
    s.close()


PUMP = answer("BOM-001")["items"][1]
ROOT = answer("BOM-001")["root_product_id"]


def row(maker: str, model: str = PUMP["model_designation"]) -> BomRow:
    return BomRow(component=PUMP["class"], model=model, maker=maker, quantity=1, line=10)


def misspelt(store: RegistryStore) -> str:
    name = str(store.identities()[0]["maker_name"])
    return name[:-2] + name[-1] + name[-2]


def test_a_verified_choice_is_suggested(dev: RegistryStore, onto: Ontology) -> None:
    provider = FakeProvider([{"product_id": PUMP["product_id"], "reason": "same maker"}])
    result = suggest(dev, onto, provider, row(misspelt(dev)), ROOT)
    assert result.product_id == PUMP["product_id"] and result.rejected is None
    prompt = provider.prompts[0]
    assert PUMP["product_id"] in prompt["schema"]["properties"]["product_id"]["enum"]
    assert "Solved rows" not in prompt["user"]  # C: candidates only, no examples


class FirstCandidate:
    """Chooses the first shown candidate, as the local model did on rows without a model."""

    def complete_json(self, *, schema: dict[str, Any] | None, **_: Any) -> dict[str, Any]:
        assert schema is not None
        return {"product_id": schema["properties"]["product_id"]["enum"][0], "reason": "closest"}


def test_a_choice_that_fails_verification_is_not_suggested(
    dev: RegistryStore, onto: Ontology
) -> None:
    result = suggest(dev, onto, FirstCandidate(), row(misspelt(dev), model="—"), ROOT)
    assert result.product_id is None and result.model_answer is not None
    assert result.rejected and "model cell" in result.rejected


def test_the_root_is_never_suggested(dev: RegistryStore, onto: Ontology) -> None:
    provider = FakeProvider([{"product_id": ROOT, "reason": "x"}])
    root_model = next(p["model_designation"] for p in dev.identities() if p["product_id"] == ROOT)
    root_class = dev.product_class(ROOT) or ""
    bom_row = BomRow(component=root_class, model=root_model, maker="x", quantity=1, line=9)
    result = suggest(dev, onto, provider, bom_row, ROOT)
    assert result.product_id is None


@pytest.mark.parametrize("failure", [LlmError("g5_bom_row", "timeout"), ConnectionError("down")])
def test_a_model_failure_is_no_suggestion_with_the_reason(
    failure: Exception, dev: RegistryStore, onto: Ontology
) -> None:
    result = suggest(dev, onto, FakeProvider([failure]), row(misspelt(dev)), ROOT)
    assert result.product_id is None and result.unavailable


def test_maker_aliases_come_from_the_store(dev: RegistryStore) -> None:
    names = dev.maker_aliases()
    assert names and all(isinstance(v, list) for v in names.values())
    assert all(p["maker_name"] not in names[p["maker_id"]] for p in dev.identities())


def test_no_other_registered_product_is_no_suggestion(onto: Ontology) -> None:
    """A registry with only the BOM root has nothing to choose from: say so, ask no model."""
    from spec_bridge.bom.suggest import suggest_from

    only_root = [{"product_id": ROOT, "class_id": "x", "model_designation": "x"}]
    result = suggest_from(only_root, {}, onto, FakeProvider([]), row("x"), ROOT)
    assert result.product_id is None and result.rejected == "no other registered product"
