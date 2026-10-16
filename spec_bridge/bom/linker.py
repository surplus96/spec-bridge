"""Link a BOM to the registry (D-101): deterministic, no model.

- The root (Root model + Manufacturer) must be a registered product, else the BOM is
  refused: a new product comes in through its spec sheet, not from a BOM line.
- Each row is identified by maker and model (aliases count). It waits for review
  ("pending") when the product is unknown, when the row's component is not the product's
  class (or a parent class), or when it is the root itself.
- Found rows are "new" or "existing" (already a has_component of the root). Relations
  the root has but the BOM does not list are reported in `not_in_bom`, never removed.
- has_component means supply-scope inclusion (D-014): compatibility is not judged.
"""

from typing import Any, Literal

from spec_bridge.bom.reader import BomDocument, BomError, BomRow
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.store import RegistryStore

RELATION = "has_component"


class RowResult(StrictModel):
    row: BomRow
    status: Literal["new", "existing", "pending"]
    product_id: str | None = None
    reason: str | None = None  # why a row waits for review


class BomPlan(StrictModel):
    file_name: str
    root_id: str
    rows: list[RowResult]
    not_in_bom: list[str]  # has_component targets of the root that the BOM does not list


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
    classes = [class_id, *onto.ancestors(class_id)] if class_id in onto.classes else [class_id]
    if row.component not in classes:
        why = f"the row says {row.component}, but {product_id} is a {class_id} (class mismatch)"
        return RowResult(row=row, status="pending", reason=why)
    status: Literal["new", "existing"] = "existing" if product_id in existing else "new"
    return RowResult(row=row, status=status, product_id=product_id)


def plan(store: RegistryStore, onto: Ontology, bom: BomDocument) -> BomPlan:
    """What applying the BOM would do. Writes nothing."""
    root_id = store.find_by_identity(bom.root_maker, bom.root_model)
    if root_id is None:
        raise BomError(
            f"root {bom.root_maker} {bom.root_model} is not in the registry; "
            "register it from its spec sheet first"
        )
    existing = store.relations_of(root_id, RELATION)
    rows = [_row(store, onto, row, root_id, existing) for row in bom.rows]
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
            }
            for r in result.rows
        ],
        "not_in_bom": result.not_in_bom,
    }


def apply(store: RegistryStore, result: BomPlan, actor: str) -> int:
    """Add the new relations; returns how many were added (0 writes nothing)."""
    new = [r.product_id for r in result.rows if r.status == "new" and r.product_id]
    if not new:
        return 0
    return store.add_components(result.root_id, new, actor, summary(result))
