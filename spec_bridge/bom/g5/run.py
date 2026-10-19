"""Run, score, compare and freeze the G5 follow-up (D-109).

    uv run python -m spec_bridge.bom.g5.run run dev R        # no model
    uv run python -m spec_bridge.bom.g5.run run dev C        # local exaone3.5:7.8b
    uv run python -m spec_bridge.bom.g5.run run dev E        # + bge-m3 examples
    uv run python -m spec_bridge.bom.g5.run compare <E dir> <R dir> <C dir>
    uv run python -m spec_bridge.bom.g5.run freeze write     # once, before the test split
    uv run python -m spec_bridge.bom.g5.run freeze verify

A test-split run is refused unless the freeze record matches the files (D-109). Each run
writes var/eval/g5/<split>-<config>-<time>/ with run.json, predictions.json, scores.json.
"""

import hashlib
import json
import random
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from spec_bridge.bom.g5.resolve import (
    CANDIDATES_K,
    EXAMPLES_K,
    Candidates,
    Embed,
    Examples,
    llm_answer,
    prompt,
    r_answer,
    verify,
)
from spec_bridge.bom.g5.rows import CATALOG, REGISTRY, RowCase, load, makers
from spec_bridge.llm.provider import DEFAULT_MODEL, JsonProvider
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.registry.store import ROOT, RegistryStore

RUNS = ROOT / "var/eval/g5"
FREEZE = ROOT / "var/eval/G5-FREEZE.json"
FROZEN_FILES = (
    "spec_bridge/bom/g5/rows.py",
    "spec_bridge/bom/g5/resolve.py",
    "spec_bridge/bom/g5/run.py",
    "spec_bridge/bom/linker.py",
    "spec_bridge/bom/reader.py",
    "data/synth/bom-rows/dev.json",
    "data/synth/bom-rows/test.json",
    "data/reference/bom-notation-patterns.yaml",
    "data/synth/registry/dev.jsonl",
    "data/synth/registry/test.jsonl",
    "data/synth/registry/manufacturers.json",
    "ontology/ontology.yaml",
)
EMBEDDING = "bge-m3"
BOOTSTRAP, SEED = 10_000, 7
# pre-registered (D-109): E - R accuracy low > 0; E wrong links <= 5% and <= R + 2 points;
# E - C accuracy low > 0
WRONG_LINK_MAX, WRONG_LINK_MARGIN = 0.05, 0.02
NOTES = {
    "no_model": "no model in the row",
    "driver": "the model is the driving machine's, not the component's",
    "unregistered": "no registered product has this model code",
}


# setup ------------------------------------------------------------------------------------
def store_for(split: str, onto: Ontology, folder: Path) -> RegistryStore:
    store = RegistryStore(folder / f"{split}.sqlite", onto)
    store.load_manufacturers(REGISTRY / "manufacturers.json")
    store.load_jsonl(REGISTRY / f"{split}.jsonl")
    return store


def aliases() -> dict[str, list[str]]:
    return {i: list(m.get("aliases", [])) for i, m in makers().items()}


def notes(cases: list[RowCase]) -> dict[str, str]:
    """Why each solved development row has its answer, in the catalog's pattern names."""
    names = {p["id"]: p["pattern_type"] for p in yaml.safe_load(CATALOG.read_text())["patterns"]}
    out = {}
    for c in cases:
        written = ", ".join(names.get(p, p) for p in c.patterns) or "plain"
        out[c.row_id] = NOTES.get(c.kind, f"the row names this product; written as {written}")
    return out


# freeze -------------------------------------------------------------------------------------
def file_hashes() -> dict[str, str]:
    return {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in FROZEN_FILES}


def write_freeze(model_digest: str | None, path: Path = FREEZE) -> Path:
    if path.exists():
        raise SystemExit(f"{path} exists; a freeze is written once (D-109)")
    record = {
        "frozen_at": datetime.now(UTC).isoformat(),
        "decision": "D-109",
        "model": DEFAULT_MODEL,
        "model_digest": model_digest,
        "embedding": EMBEDDING,
        "candidates_k": CANDIDATES_K,
        "examples_k": EXAMPLES_K,
        "files": file_hashes(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def verify_freeze(path: Path = FREEZE) -> list[str]:
    """Files whose hash differs from the freeze record (empty: unchanged)."""
    if not path.is_file():
        return ["no freeze record"]
    frozen = json.loads(path.read_text())["files"]
    now = file_hashes()
    return sorted(f for f in set(frozen) | set(now) if frozen.get(f) != now.get(f))


# run ----------------------------------------------------------------------------------------
def answers(
    split: str,
    config: str,
    provider: JsonProvider | None,
    embed: Embed | None,
    onto: Ontology,
) -> list[dict[str, Any]]:
    cases = load(split)
    with tempfile.TemporaryDirectory() as folder:
        store = store_for(split, onto, Path(folder))
        try:
            index = store.identities()  # id, class, maker id and name, model
            names = aliases()
            pool = Candidates(index, names)
            kb = load("dev") if config == "E" else []
            examples = Examples(kb, notes(kb), embed) if config == "E" and embed else None
            rows = []
            for case in cases:
                row: dict[str, Any] = {
                    "row_id": case.row_id,
                    "kind": case.kind,
                    "patterns": case.patterns,
                    "gold": case.gold,
                }
                if config == "R":
                    row["answer"], row["reason"] = r_answer(store, onto, case, index), ""
                else:
                    top = pool.top(case.line)
                    ids = {p["product_id"] for p in top}
                    row["in_top"] = case.gold in ids if case.gold else None
                    # examples never answer with a shown candidate (D-110); development
                    # rows also leave their own product out (D-109)
                    leave_out = ids | ({case.gold} if split == "dev" and case.gold else set())
                    shown = examples.top(case, leave_out) if examples else []
                    row["examples"] = [e.row_id for e in shown]
                    user = prompt(case, top, names, shown, notes(shown))
                    assert provider is not None
                    chosen, row["reason"] = llm_answer(provider, user, top)
                    product = next((p for p in top if p["product_id"] == chosen), None)
                    row["model_answer"] = chosen
                    row["rejected"] = verify(onto, case, product) if product else None
                    row["answer"] = None if row["rejected"] else chosen
                rows.append(row)
            return rows
        finally:
            store.close()


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def rates(subset: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(subset)
        right = sum(r["answer"] == r["gold"] for r in subset)
        wrong = sum(r["answer"] is not None and r["answer"] != r["gold"] for r in subset)
        pending = sum(r["answer"] is None for r in subset)
        return {
            "n": n,
            "accuracy": right / n if n else None,
            "wrong_link": wrong / n if n else None,
            "pending": pending / n if n else None,
        }

    hits = [r["in_top"] for r in rows if r.get("in_top") is not None]
    kinds = sorted({r["kind"] for r in rows})
    patterns = sorted({p for r in rows for p in r["patterns"]})
    return {
        **rates(rows),
        "candidates_recall": sum(hits) / len(hits) if hits else None,
        "by_kind": {k: rates([r for r in rows if r["kind"] == k]) for k in kinds},
        "by_pattern": {p: rates([r for r in rows if p in r["patterns"]]) for p in patterns},
    }


def run(
    split: str,
    config: str,
    provider: JsonProvider | None = None,
    embed: Embed | None = None,
    out: Path = RUNS,
) -> Path:
    if config not in ("R", "C", "E"):
        raise SystemExit(f"unknown configuration {config!r}")
    if split == "test" and (changed := verify_freeze()):
        raise SystemExit(f"test split refused: not frozen or changed since the freeze {changed}")
    onto = load_ontology(ROOT / "ontology/ontology.yaml")
    rows = answers(split, config, provider, embed, onto)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = out / f"{split}-{config}-{stamp}"
    folder.mkdir(parents=True)
    meta = {
        "split": split,
        "config": config,
        "at": stamp,
        "files": file_hashes(),
        "model": DEFAULT_MODEL if config != "R" else None,
        "model_digest": getattr(provider, "digest", None) if config != "R" else None,
        "embedding": EMBEDDING if config == "E" else None,
        "candidates_k": CANDIDATES_K,
        "examples_k": EXAMPLES_K if config == "E" else 0,
    }
    for name, data in (
        ("run.json", meta),
        ("predictions.json", rows),
        ("scores.json", score(rows)),
    ):
        (folder / name).write_text(
            json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
        )
    return folder


# compare ------------------------------------------------------------------------------------
def _paired(a: list[float], b: list[float]) -> dict[str, float]:
    """Mean of a - b with a 95% percentile interval over rows resampled together."""
    rng, n = random.Random(SEED), len(a)
    diffs = sorted(
        sum(a[i] - b[i] for i in idx) / n
        for idx in ([rng.randrange(n) for _ in range(n)] for _ in range(BOOTSTRAP))
    )
    return {
        "diff": sum(x - y for x, y in zip(a, b, strict=True)) / n,
        "low": diffs[int(0.025 * BOOTSTRAP)],
        "high": diffs[int(0.975 * BOOTSTRAP) - 1],
    }


def compare(e_dir: Path, r_dir: Path, c_dir: Path) -> dict[str, Any]:
    runs = {
        k: json.loads((d / "predictions.json").read_text())
        for k, d in (("E", e_dir), ("R", r_dir), ("C", c_dir))
    }
    splits = {json.loads((d / "run.json").read_text())["split"] for d in (e_dir, r_dir, c_dir)}
    if len(splits) != 1:
        raise SystemExit("the three runs must be of the same split")
    ids = [r["row_id"] for r in runs["E"]]
    if any([r["row_id"] for r in rows] != ids for rows in runs.values()):
        raise SystemExit("the runs must answer the same rows in the same order")
    right = {k: [float(r["answer"] == r["gold"]) for r in rows] for k, rows in runs.items()}
    wrong = {
        k: [float(r["answer"] is not None and r["answer"] != r["gold"]) for r in rows]
        for k, rows in runs.items()
    }
    a, c = _paired(right["E"], right["R"]), _paired(right["E"], right["C"])
    e_wrong, r_wrong = sum(wrong["E"]) / len(ids), sum(wrong["R"]) / len(ids)
    b = e_wrong <= WRONG_LINK_MAX and e_wrong - r_wrong <= WRONG_LINK_MARGIN
    return {
        "split": splits.pop(),
        "rows": len(ids),
        "a_e_minus_r_accuracy": a | {"pass": a["low"] > 0},
        "b_wrong_links": {"E": e_wrong, "R": r_wrong, "pass": b},
        "c_e_minus_c_accuracy": c | {"pass": c["low"] > 0},
        "verdict": a["low"] > 0 and b and c["low"] > 0,
        "criteria": "D-109",
    }


def _model() -> tuple[JsonProvider, Embed]:
    from spec_bridge.llm.audit import AuditLog
    from spec_bridge.llm.provider import OllamaProvider
    from spec_bridge.rag.settings import ollama_embeddings

    provider = OllamaProvider(DEFAULT_MODEL, AuditLog(RUNS / "audit.jsonl"))
    return provider, ollama_embeddings(EMBEDDING).embed_documents


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if args[:1] == ["run"] and len(args) == 3:
        provider, embed = _model() if args[2] != "R" else (None, None)
        print(run(args[1], args[2], provider, embed).relative_to(ROOT))
    elif args[:1] == ["compare"] and len(args) == 4:
        print(json.dumps(compare(*(Path(a) for a in args[1:])), indent=2))
    elif args == ["freeze", "write"]:
        provider, _ = _model()
        print(write_freeze(getattr(provider, "digest", None)))
    elif args == ["freeze", "verify"]:
        changed = verify_freeze()
        print("frozen files unchanged" if not changed else f"changed: {changed}")
        if changed:
            raise SystemExit(1)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
