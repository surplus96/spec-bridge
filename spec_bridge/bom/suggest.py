"""A suggested product for a pending BOM row (D-112), from the G5 result (D-111).

The configuration is the evaluated C: the local model chooses among the BM25 top-10
registered products, or none, and code keeps the choice only when the product's model
code is in the row's model cell and its class fits (D-110). Nothing is linked here: the
screen shows the suggestion and the reviewer confirms it as a pick (D-103), so the
relation is recorded as the reviewer's.

The evaluation code (spec_bridge.bom.g5) is frozen; this module calls it unchanged and
wraps a screen row as an evaluation row.
"""

from typing import Any

from spec_bridge.bom.g5.resolve import Candidates, llm_answer, prompt, verify
from spec_bridge.bom.g5.rows import RowCase
from spec_bridge.bom.reader import BomRow
from spec_bridge.llm.provider import JsonProvider
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.store import RegistryStore


class Suggestion(StrictModel):
    line: int
    product_id: str | None  # a verified product, or none
    model_answer: str | None = None  # what the model chose before verification
    reason: str = ""  # the model's reason
    rejected: str | None = None  # why code refused the model's choice
    unavailable: str | None = None  # the model could not be asked


def _as_case(row: BomRow) -> RowCase:
    """The screen row in the shape the evaluated configuration reads; no answer is known."""
    return RowCase(
        row_id=f"line-{row.line}",
        split="dev",  # unused by C: no examples are searched
        component=row.component,
        model=row.model,
        maker=row.maker,
        quantity_text=str(row.quantity),
        quantity=row.quantity,
        kind="product",
        gold=None,
        patterns=[],
    )


def suggest(
    store: RegistryStore, onto: Ontology, provider: JsonProvider, row: BomRow, root_id: str
) -> Suggestion:
    return suggest_from(store.identities(), store.maker_aliases(), onto, provider, row, root_id)


def suggest_from(
    products: list[dict[str, Any]],
    aliases: dict[str, list[str]],
    onto: Ontology,
    provider: JsonProvider,
    row: BomRow,
    root_id: str,
) -> Suggestion:
    """The same, from a copy of the registry: the caller reads it under its lock and the
    slow model call runs without holding it."""
    index = [p for p in products if p["product_id"] != root_id]
    if not index:  # nothing to choose from (and BM25 cannot index an empty list)
        return Suggestion(line=row.line, product_id=None, rejected="no other registered product")
    case = _as_case(row)
    top = Candidates(index, aliases).top(case.line)
    try:
        chosen, reason = llm_answer(provider, prompt(case, top, aliases, [], {}), top)
    except (ConnectionError, OSError) as error:  # the model server is down
        return Suggestion(line=row.line, product_id=None, unavailable=str(error))
    if reason.startswith("llm: "):
        return Suggestion(line=row.line, product_id=None, unavailable=reason)
    product = next((p for p in top if p["product_id"] == chosen), None)
    rejected = verify(onto, case, product) if product else None
    return Suggestion(
        line=row.line,
        product_id=None if rejected or product is None else chosen,
        model_answer=chosen,
        reason=reason,
        rejected=rejected,
    )
