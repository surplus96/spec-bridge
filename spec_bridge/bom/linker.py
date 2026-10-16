"""Link a BOM to the registry (D-101): deterministic, no model.

- The root (Root model + Manufacturer) must be a registered product, else the BOM is
  refused: a new product comes in through its spec sheet, not from a BOM line.
- Each row is identified by maker and model (aliases count). It waits for review
  ("pending") when the product is unknown, when the row's component is not the product's
  class (or a parent class), or when it is the root itself.
- Found rows are "new" or "existing" (already a has_component of the root). Relations
  the root has but the BOM does not list are reported in `not_in_bom`, never removed.
- A reviewer may resolve a pending row by picking a registered product of the row's
  class (D-103). The pick keeps its reason and is marked `decided_by: reviewer`, apart
  from what the rule found. A pick for a row the rule found, or of another class, is
  refused.
- has_component means supply-scope inclusion (D-014): compatibility is not judged.
"""

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import Field

from spec_bridge.bom.reader import BomDocument, BomError, BomRow
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.store import RegistryStore

RELATION = "has_component"


class Pick(StrictModel):
    """A reviewer's product for a pending row (D-103)."""

    line: int
    product_id: str
    reason: Annotated[str, Field(min_length=1)]


class RowResult(StrictModel):
    row: BomRow
    status: Literal["new", "existing", "pending"]
    product_id: str | None = None
    reason: str | None = None  # why a row waits for review, or the reviewer's reason
    decided_by: Literal["rule", "reviewer"] = "rule"


class BomPlan(StrictModel):
    file_name: str
    root_id: str
    rows: list[RowResult]
    not_in_bom: list[str]  # has_component targets of the root that the BOM does not list


def _classes(onto: Ontology, class_id: str) -> list[str]:
    """The class and its parents: a row's component may name any of them."""
    return [class_id, *onto.ancestors(class_id)] if class_id in onto.classes else [class_id]


def candidates(store: RegistryStore, onto: Ontology, row: BomRow) -> list[dict[str, Any]]:
    """Registered products a reviewer may pick for the row: those of the row's class."""
    fitting = [c for c in onto.classes if row.component in _classes(onto, c)]
    return store.products_in_classes(fitting)


def _picked(
    store: RegistryStore,
    onto: Ontology,
    found: RowResult,
    pick: Pick,
    root_id: str,
    existing: list[str],
) -> RowResult:
    if found.status != "pending":
        raise BomError(f"line {pick.line}: the row is already identified as {found.product_id}")
    class_id = store.product_class(pick.product_id)
    if class_id is None:
        raise BomError(f"line {pick.line}: {pick.product_id} is not in the registry")
    if pick.product_id == root_id or found.row.component not in _classes(onto, class_id):
        raise BomError(
            f"line {pick.line}: {pick.product_id} is a {class_id}, the row says "
            f"{found.row.component}"
        )
    status: Literal["new", "existing"] = "existing" if pick.product_id in existing else "new"
    return RowResult(
        row=found.row,
        status=status,
        product_id=pick.product_id,
        reason=pick.reason,
        decided_by="reviewer",
    )


def _row(
    store: RegistryStore, onto: Ontology, row: BomRow, root_id: str, existing: list[str]
) -> RowResult:
    product_id = store.find_by_identity(row.maker, row.model)
    if product_id is None:
        why = f"{row.maker} {row.model} is not in the registry (register it from its spec sheet)"
        return RowResult(row=row, status="pending", reason=why)
    if product_id == root_id:
        return RowResult(row=row, status="pending", reason="the root cannot be its own component")
    class_id = store.product_class(product_id) or ""
    if row.component not in _classes(onto, class_id):
        why = f"the row says {row.component}, but {product_id} is a {class_id} (class mismatch)"
        return RowResult(row=row, status="pending", reason=why)
    status: Literal["new", "existing"] = "existing" if product_id in existing else "new"
    return RowResult(row=row, status=status, product_id=product_id)


def plan(
    store: RegistryStore, onto: Ontology, bom: BomDocument, picks: list[Pick] | None = None
) -> BomPlan:
    """What applying the BOM would do, with the reviewer's picks. Writes nothing."""
    root_id = store.find_by_identity(bom.root_maker, bom.root_model)
    if root_id is None:
        raise BomError(
            f"root {bom.root_maker} {bom.root_model} is not in the registry; "
            "register it from its spec sheet first"
        )
    existing = store.relations_of(root_id, RELATION)
    rows = [_row(store, onto, row, root_id, existing) for row in bom.rows]
    lines = [r.row.line for r in rows]
    for pick in picks or []:
        if pick.line not in lines:
            raise BomError(f"line {pick.line}: no such row in the BOM")
        at = lines.index(pick.line)
        rows[at] = _picked(store, onto, rows[at], pick, root_id, existing)
    listed = {r.product_id for r in rows if r.product_id}
    return BomPlan(
        file_name=bom.file_name,
        root_id=root_id,
        rows=rows,
        not_in_bom=sorted(set(existing) - listed),
    )


def summary(result: BomPlan) -> dict[str, Any]:
    """The plan as the reviewer reads it (and as the event keeps it): every row, quantity
    included, with its outcome."""
    return {
        "bom_file": result.file_name,
        "root_id": result.root_id,
        "rows": [
            {
                **r.row.model_dump(),
                "status": r.status,
                "product_id": r.product_id,
                "reason": r.reason,
                "decided_by": r.decided_by,
            }
            for r in result.rows
        ],
        "not_in_bom": result.not_in_bom,
    }


def plan_key(result: BomPlan) -> str:
    """A fingerprint of what applying would do: a preview whose key no longer matches the
    current plan is out of date (D-103)."""
    rows = [(r.row.line, r.status, r.product_id, r.decided_by) for r in result.rows]
    body = json.dumps([result.root_id, rows, result.not_in_bom], sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def apply(
    store: RegistryStore, result: BomPlan, actor: str, extra: dict[str, Any] | None = None
) -> int:
    """Add the new relations; returns how many were added (0 writes nothing). `extra`
    (the uploaded file's id and hash) is kept with the event."""
    new = [r.product_id for r in result.rows if r.status == "new" and r.product_id]
    if not new:
        return 0
    return store.add_components(result.root_id, new, actor, summary(result) | (extra or {}))
