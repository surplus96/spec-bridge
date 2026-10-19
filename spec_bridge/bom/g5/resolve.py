"""R, C and E for a BOM row (D-109).

- R: the deterministic linker (D-108) on the row's cells; a pending row answers none.
- C: the local model chooses among the BM25 top-10 registered products, or none.
- E: C plus three solved development rows found by BM25 + bge-m3 fused with RRF.

The answer schema lists only the candidates and "none", so the model cannot name a
product it was not shown; anything else is counted as none (D-109). Code then verifies
the choice (D-110): the chosen product's model code must be in the row's model cell and
its class must fit the row, else the answer is none. The model reads the maker; code
checks the model.
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from rank_bm25 import BM25Okapi

from spec_bridge.bom.g5.rows import RowCase
from spec_bridge.bom.linker import _classes, _row, _spans, search_key
from spec_bridge.bom.reader import BomRow
from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.registry.store import RegistryStore

CANDIDATES_K = 10
EXAMPLES_K = 3
RRF_K = 60  # as in the specification-context retrieval (D-043)
NONE = "none"

Embed = Callable[[list[str]], list[list[float]]]

SYSTEM = """You map one row of a bill of materials (BOM) to the registered product it names.
Answer with the product_id of exactly one candidate, or "none".
- A row names a candidate when it holds the candidate's whole model code and the maker is the
  candidate's maker. The model code may be written with other separators (space, slash, dot)
  and may carry ratings, a serial number or "or equal". The maker may be written in capitals,
  shortened or with letters swapped.
- Answer "none" when the row has no model, when the model belongs to a machine that drives the
  component rather than to the component itself, when no candidate has the row's model code,
  or when the component class does not fit the candidate.
- Never choose a candidate whose model code differs from the row's, even by one character."""


def _words(text: str) -> list[str]:
    """Lower-case words plus every 1-3 word run without separators: 'VX001/001' finds
    'vx001001' as well as 'vx001' and '001'."""
    return re.findall(r"[a-z0-9]+", text.casefold()) + [k.lower() for k in _spans(text)]


def product_text(product: dict[str, Any], aliases: Sequence[str]) -> str:
    return " ".join(
        [product["class_id"], product["maker_name"], *aliases, product["model_designation"]]
    )


@dataclass
class Candidates:
    """BM25 over the registered products of the split."""

    products: list[dict[str, Any]]
    aliases: dict[str, list[str]]
    _index: BM25Okapi = field(init=False)

    def __post_init__(self) -> None:
        texts = [product_text(p, self.aliases.get(p["maker_id"], [])) for p in self.products]
        self._index = BM25Okapi([_words(t) for t in texts])

    def top(self, line: str, k: int = CANDIDATES_K) -> list[dict[str, Any]]:
        scores = self._index.get_scores(_words(line))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        return [self.products[i] for i in order[:k]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass
class Examples:
    """Solved development rows, found by BM25 and dense search fused with RRF."""

    cases: list[RowCase]
    notes: dict[str, str]  # row_id -> why the answer is what it is
    embed: Embed
    _index: BM25Okapi = field(init=False)
    _vectors: list[list[float]] = field(init=False)

    def __post_init__(self) -> None:
        self._index = BM25Okapi([_words(c.line) for c in self.cases])
        self._vectors = self.embed([c.line for c in self.cases])

    def top(
        self, case: RowCase, leave_out: set[str] | None = None, k: int = EXAMPLES_K
    ) -> list[RowCase]:
        """Leaves out the row itself and every example whose answer is in `leave_out`: the
        runner passes the row's candidates (D-110; and on the development split the row's
        own product), so no example answers with a product the model is shown."""
        out = leave_out or set()
        allowed = [
            i for i, c in enumerate(self.cases) if c.row_id != case.row_id and c.gold not in out
        ]
        lexical = self._index.get_scores(_words(case.line))
        query = self.embed([case.line])[0]
        dense = {i: _cosine(query, self._vectors[i]) for i in allowed}
        fused: dict[int, float] = {}
        for ranking in (
            sorted(allowed, key=lambda i: (-lexical[i], i)),
            sorted(allowed, key=lambda i: (-dense[i], i)),
        ):
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
        order = sorted(fused, key=lambda i: (-fused[i], i))
        return [self.cases[i] for i in order[:k]]


def r_answer(
    store: RegistryStore, onto: Ontology, case: RowCase, index: list[dict[str, Any]]
) -> str | None:
    row = BomRow(
        component=case.component, model=case.model, maker=case.maker, quantity=case.quantity, line=1
    )
    result = _row(store, onto, row, root_id="", existing=[], index=index)
    return None if result.status == "pending" else result.product_id


def _candidate_line(p: dict[str, Any], aliases: Sequence[str]) -> str:
    names = " / ".join([p["maker_name"], *aliases])
    model = p["model_designation"]
    return f"{p['product_id']} | class {p['class_id']} | maker {names} | model {model}"


def prompt(
    case: RowCase,
    candidates: list[dict[str, Any]],
    aliases: dict[str, list[str]],
    examples: list[RowCase],
    notes: dict[str, str],
) -> str:
    parts = []
    if examples:
        parts.append("Solved rows (other products):")
        for ex in examples:
            parts.append(f"Row: {ex.line}\nAnswer: {ex.gold or NONE} - {notes.get(ex.row_id, '')}")
        parts.append("")
    parts.append("Candidates:")
    parts += [_candidate_line(p, aliases.get(p["maker_id"], [])) for p in candidates]
    parts.append(f"\nRow: {case.line}\nAnswer with one product_id from the candidates, or none.")
    return "\n".join(parts)


def schema(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [p["product_id"] for p in candidates] + [NONE]
    return {
        "type": "object",
        "properties": {"product_id": {"type": "string", "enum": ids}, "reason": {"type": "string"}},
        "required": ["product_id", "reason"],
    }


def llm_answer(
    provider: JsonProvider, user: str, candidates: list[dict[str, Any]]
) -> tuple[str | None, str]:
    """(answer, reason). A model failure or an answer outside the candidates is none."""
    try:
        reply = provider.complete_json(
            system=SYSTEM, user=user, schema=schema(candidates), task="g5_bom_row"
        )
    except LlmError as error:
        return None, f"llm: {error.reason}"
    chosen = reply.get("product_id")
    valid = {p["product_id"] for p in candidates}
    return (chosen if chosen in valid else None), str(reply.get("reason", ""))


def verify(onto: Ontology, case: RowCase, product: dict[str, Any]) -> str | None:
    """Why the model's choice is refused (D-110), or None when it stands."""
    if search_key(product["model_designation"]) not in _spans(case.model):
        return f"the row's model cell does not hold {product['model_designation']}"
    if case.component not in _classes(onto, product["class_id"]):
        return f"{product['product_id']} is a {product['class_id']}, the row says {case.component}"
    return None
