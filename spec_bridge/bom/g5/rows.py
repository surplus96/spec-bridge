"""Synthetic BOM rows for the G5 follow-up (D-109).

Every registered product of a split becomes one row whose cells are written with the
notation patterns observed in that split's sources (the signed catalog, D-105/D-106);
NONE_ROWS more rows have no registered answer (no model, a driving machine named instead,
a model that is not registered). The transformations below are the project's own
synthetic rules (origin: synthetic); they only apply a pattern's description to the
synthetic makers and models, never a real maker name.

    uv run python -m spec_bridge.bom.g5.rows dev     # writes data/synth/bom-rows/dev.json

Answer rule (D-109): a row that holds a registered model and a way of writing that
product's maker has that product as its answer, whatever else the cells carry; the
others answer "none".
"""

import json
import random
import re
import sys
from pathlib import Path
from typing import Any, Literal

import yaml

from spec_bridge.bom.linker import search_key
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.store import ROOT

REGISTRY = ROOT / "data/synth/registry"
CATALOG = ROOT / "data/reference/bom-notation-patterns.yaml"
OUT = ROOT / "data/synth/bom-rows"
PATTERNS_BY_SOURCE_SPLIT = {  # D-109: the split follows the sources
    "dev": ("BOMSRC-01", "BOMSRC-02", "BOMSRC-03", "BOMSRC-04"),
    "test": ("BOMSRC-05", "BOMSRC-06", "BOMSRC-07", "BOMSRC-08"),
}
NONE_ROWS = {"dev": 30, "test": 20}
QUANTITY_PATTERNS = ("PAT-01", "PAT-02", "PAT-03", "PAT-12")
MAKER_PATTERNS = ("PAT-05", "PAT-06")
MODEL_PATTERNS = ("PAT-04", "PAT-09", "PAT-10", "PAT-11")
WORDS = {1: "One", 2: "Two"}

Kind = Literal["product", "no_model", "driver", "unregistered"]
Split = Literal["dev", "test"]


class RowCase(StrictModel):
    row_id: str
    split: Literal["dev", "test"]
    component: str  # the class the BOM row names
    model: str
    maker: str
    quantity_text: str
    quantity: int
    kind: Kind
    gold: str | None  # the answer: a registered product, or none
    patterns: list[str]

    @property
    def line(self) -> str:
        return (
            f"Component: {self.component} | Quantity: {self.quantity_text} | "
            f"Manufacturer: {self.maker} | Model: {self.model}"
        )


def registry_records(split: str) -> list[dict[str, Any]]:
    lines = (REGISTRY / f"{split}.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line]


def makers() -> dict[str, dict[str, Any]]:
    return {m["maker_id"]: m for m in json.loads((REGISTRY / "manufacturers.json").read_text())}


def allowed_patterns(split: str, catalog: Path = CATALOG) -> set[str]:
    """Signed patterns observed in at least one of the split's sources."""
    sources = set(PATTERNS_BY_SOURCE_SPLIT[split])
    patterns = yaml.safe_load(catalog.read_text())["patterns"]
    return {
        p["id"]
        for p in patterns
        if p.get("verified_by") and {r["source_id"] for r in p["source_refs"]} & sources
    }


# transformations (synthetic rules) ------------------------------------------------------
def _quantity(rng: random.Random, allowed: set[str], n: int) -> tuple[str, list[str]]:
    choices = [p for p in QUANTITY_PATTERNS if p in allowed]
    pattern = rng.choice(choices) if choices else None
    if pattern == "PAT-01":
        return rng.choice([f"{n} x", f"{n} ×", f"{n}x"]), [pattern]
    if pattern == "PAT-02":
        return f"({n})", [pattern]
    if pattern == "PAT-12":
        return rng.choice([WORDS[n], f"{WORDS[n]} ({n})"]), [pattern]
    return str(n), [pattern] if pattern else []


def _swap(text: str, rng: random.Random) -> str:
    """Two neighbouring letters swapped in the words after the maker code (a spelling
    variant); the code itself stays as written."""
    start = text.find(" ") + 1
    spots = [i for i in range(start, len(text) - 1) if text[i].isalpha() and text[i + 1].isalpha()]
    i = rng.choice(spots)
    return text[:i] + text[i + 1] + text[i] + text[i + 2 :]


def _maker(rng: random.Random, allowed: set[str], maker: dict[str, Any]) -> tuple[str, list[str]]:
    base = rng.choice([maker["name"], *maker.get("aliases", [])])
    options = [p for p in MAKER_PATTERNS if p in allowed] + [None]
    pattern = rng.choice(options)
    if pattern == "PAT-05":
        return rng.choice([base.upper(), base.split()[0]]), [pattern]  # capitals, or short form
    if pattern == "PAT-06":
        return _swap(base, rng), [pattern]
    return base, []


def _rating(record: dict[str, Any]) -> str:
    """A rating the registry holds for the product (values from data, not memory)."""
    for facts in record["attributes"].values():
        value, unit = facts[0]["value"], facts[0]["unit"]
        if isinstance(value, (int, float)) and unit:
            return f"{value} {unit}"
    return ""


def _model(
    rng: random.Random, allowed: set[str], model: str, record: dict[str, Any]
) -> tuple[str, list[str]]:
    options = [p for p in MODEL_PATTERNS if p in allowed]
    chosen = rng.sample(options, k=min(len(options), rng.choice([0, 1, 2])))
    text, used = model, []
    for pattern in sorted(chosen):
        if pattern == "PAT-11":
            text = text.replace("-", rng.choice(["/", " ", "."]))
        elif pattern == "PAT-04" and _rating(record):
            text = f"{text}, {_rating(record)}"
        elif pattern == "PAT-09":
            text = f"{text} S/No. {rng.randint(10000, 99999)}"
        elif pattern == "PAT-10":
            text = f"{text} or equal"
        else:
            continue
        used.append(pattern)
    return text, used


def _unregistered(rng: random.Random, model: str, taken: set[str]) -> str:
    """A model code of the same shape that no product of the split has."""
    while True:
        code = re.sub(r"\d", lambda _: str(rng.randint(0, 9)), model)
        if search_key(code) not in taken:
            return code


def _none_row(
    rng: random.Random,
    allowed: set[str],
    split: Split,
    records: list[dict[str, Any]],
    kind: Kind,
    index: int,
    taken: set[str],
) -> RowCase:
    record = rng.choice(records)
    maker = makers()[record["maker_id"]]
    maker_text, maker_used = _maker(rng, allowed, maker)
    quantity = rng.choice([1, 2])
    quantity_text, quantity_used = _quantity(rng, allowed, quantity)
    component, used = record["class"], []
    if kind == "no_model":
        model, used = "—", ["PAT-07"]
    elif kind == "driver":  # the row's component is another class, driven by this product
        others = sorted({r["class"] for r in records} - {record["class"]})
        component, model, used = (
            rng.choice(others),
            f"driven by {record['model_designation']}",
            ["PAT-08"],
        )
    else:
        model = _unregistered(rng, record["model_designation"], taken)
    return RowCase(
        row_id=f"{split}-N{index:03d}",
        split=split,
        component=component,
        model=model,
        maker=maker_text,
        quantity_text=quantity_text,
        quantity=quantity,
        kind=kind,
        gold=None,
        patterns=sorted(set(used + maker_used + quantity_used)),
    )


def generate(split: Split) -> list[RowCase]:
    rng = random.Random(f"g5-bom-rows-{split}")  # fixed seed per split
    allowed = allowed_patterns(split)
    records = registry_records(split)
    taken = {search_key(r["model_designation"]) for r in records}
    rows = []
    for i, record in enumerate(records):
        quantity = rng.choice([1, 2])
        quantity_text, q_used = _quantity(rng, allowed, quantity)
        maker_text, m_used = _maker(rng, allowed, makers()[record["maker_id"]])
        model_text, d_used = _model(rng, allowed, record["model_designation"], record)
        rows.append(
            RowCase(
                row_id=f"{split}-P{i:03d}",
                split=split,
                component=record["class"],
                model=model_text,
                maker=maker_text,
                quantity_text=quantity_text,
                quantity=quantity,
                kind="product",
                gold=record["product_id"],
                patterns=sorted(set(q_used + m_used + d_used)),
            )
        )
    optional: list[tuple[Kind, str]] = [("no_model", "PAT-07"), ("driver", "PAT-08")]
    kinds: list[Kind] = ["unregistered", *(k for k, p in optional if p in allowed)]
    for i in range(NONE_ROWS[split]):
        rows.append(_none_row(rng, allowed, split, records, kinds[i % len(kinds)], i, taken))
    return rows


def write(split: Split) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{split}.json"
    data = {
        "origin": "synthetic",
        "decision": "D-109",
        "split": split,
        "sources": list(PATTERNS_BY_SOURCE_SPLIT[split]),
        "rows": [r.model_dump() for r in generate(split)],
    }
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    return path


def load(split: str) -> list[RowCase]:
    data = json.loads((OUT / f"{split}.json").read_text())
    return [RowCase.model_validate(r) for r in data["rows"]]


if __name__ == "__main__":
    split = sys.argv[1]
    if split not in ("dev", "test"):
        raise SystemExit("usage: python -m spec_bridge.bom.g5.rows dev|test")
    print(write("dev" if split == "dev" else "test").relative_to(ROOT))
