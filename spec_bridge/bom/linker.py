"""Link a BOM to the registry (D-101): deterministic, no model.

- The root (Root model + Manufacturer) must be a registered product, else the BOM is
  refused: a new product comes in through its spec sheet, not from a BOM line.
- Each row is identified by maker and model (aliases count). It waits for review
  ("pending") when the product is unknown, when the row's component is not the product's
  class (or a parent class), or when it is the root itself.
- Found rows are "new" or "existing" (already a has_component of the root). Relations
  the root has but the BOM does not list are reported in `not_in_bom`, never removed.
- When the maker and model cells are not an exact registered identity, the model cell is
  searched (D-108): a run of 1-3 of its words that, without separators, equals a
  registered model links the row only if the maker cell names that product's maker and
  exactly one product fits. A model that matches but a maker written another way, an
  "or equal" row, a row without a model and a model of several products all wait for
  review with the reason; nothing is linked on resemblance.
- A reviewer may resolve a pending row by picking a registered product of the row's
  class (D-103). The pick keeps its reason and is marked `decided_by: reviewer`, apart
  from what the rule found. A pick for a row the rule found, or of another class, is
  refused.
- has_component means supply-scope inclusion (D-014): compatibility is not judged.
"""

import hashlib
import json
import re
from typing import Annotated, Any, Literal

from pydantic import Field

from spec_bridge.bom.reader import BomDocument, BomError, BomRow
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.store import RegistryStore

RELATION = "has_component"
MIN_KEY = 4  # a shorter model code could match a fragment of an unrelated cell
NO_MODEL = re.compile(r"[\s\-—–/.]*")  # the model cell holds no code at all
OR_EQUAL = re.compile(r"\bor\s+(?:an\s+)?(?:equal|equivalent)\b", re.I)


def search_key(text: str) -> str:
    """'VX-021/002' -> 'VX021002': letters and digits only, for searching a cell."""
    return re.sub(r"[^0-9A-Z]", "", text.upper())


def _spans(cell: str) -> set[str]:
    """Search keys of every run of 1-3 consecutive words of the cell."""
    words = [w for w in re.split(r"[\s,;()]+", cell) if w]
    runs = (words[i : i + n] for n in (1, 2, 3) for i in range(len(words) - n + 1))
    return {k for run in runs if len(k := search_key("".join(run))) >= MIN_KEY}


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


def _found(
    store: RegistryStore,
    onto: Ontology,
    row: BomRow,
    product_id: str,
    root_id: str,
    existing: list[str],
) -> RowResult:
    """A product the rule identified: still refused if it is the root or another class."""
    if product_id == root_id:
        return RowResult(row=row, status="pending", reason="the root cannot be its own component")
    class_id = store.product_class(product_id) or ""
    if row.component not in _classes(onto, class_id):
        why = f"the row says {row.component}, but {product_id} is a {class_id} (class mismatch)"
        return RowResult(row=row, status="pending", reason=why)
    status: Literal["new", "existing"] = "existing" if product_id in existing else "new"
    return RowResult(row=row, status=status, product_id=product_id)


def _searched(store: RegistryStore, row: BomRow, index: list[dict[str, Any]]) -> str:
    """The product the model cell names, or why the row waits (a sentence, not an id)."""
    if NO_MODEL.fullmatch(row.model):
        return f"no model in the row (only {row.maker}): the product cannot be told"
    spans = _spans(row.model)
    matches = [p for p in index if search_key(p["model_designation"]) in spans]
    if not matches:
        return f"{row.maker} {row.model} is not in the registry (register it from its spec sheet)"
    ids = ", ".join(p["product_id"] for p in matches)
    if OR_EQUAL.search(row.model):
        return f"'or equal': the supplied product may differ from {ids}; pick it if it is"
    maker_id = store.resolve_maker(row.maker)
    same = [p for p in matches if p["maker_id"] == maker_id]
    if len(same) == 1:
        return str(same[0]["product_id"])
    if len(same) > 1:
        return f"the model fits several products ({ids}); pick the right one"
    makers = ", ".join(sorted({str(p["maker_name"]) for p in matches}))
    if maker_id is None:
        return (
            f"the model matches {ids} ({makers}), but the maker {row.maker!r} is not a known "
            "name of it; pick the product if it is the same maker"
        )
    return f"the model matches {ids} of another maker ({makers}); check the maker"


def _row(
    store: RegistryStore,
    onto: Ontology,
    row: BomRow,
    root_id: str,
    existing: list[str],
    index: list[dict[str, Any]],
) -> RowResult:
    exact = store.find_by_identity(row.maker, row.model)
    if exact is not None:
        return _found(store, onto, row, exact, root_id, existing)
    found = _searched(store, row, index)
    if found in {p["product_id"] for p in index}:
        return _found(store, onto, row, found, root_id, existing)
    return RowResult(row=row, status="pending", reason=found)


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
    index = store.identities()
    rows = [_row(store, onto, row, root_id, existing, index) for row in bom.rows]
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
