"""Error analysis of a scored run (W6-5): every missed or extra fact key gets one cause.

A missed gold key and an extra predicted key that describe the same fact are paired, so
one wrong fact counts once. Causes, checked in this order:

- value: same key, different value (a near miss in normalization)
- context: same attribute and value, different basis, condition or scope
- attribute: same value under another attribute
- value_and_context: same attribute, but both the key and the value differ
- unresolved: missed, but the run grounded a value of the attribute it could not normalize
- parse: missed, and no gold observation of the attribute is in the parsed text
- not_extracted: missed although the parsed text holds an observation of it
- extra: a predicted key nothing in the answer explains

A wrong class is reported per document apart from the fact causes. Read-only over run
folders, parsed documents and answers; scoring.py stays the judge of the numbers.

Run:
    uv run python -m spec_bridge.eval.errors var/eval/test-E1SV-... [--list]
"""

import argparse
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spec_bridge.eval import handwritten
from spec_bridge.eval.locations import contains_token
from spec_bridge.eval.scoring import Prediction, _groups, _same_set
from spec_bridge.normalize.dictionary import ROOT, split_answers

PAIRED = ("value", "context", "attribute", "value_and_context")
CAUSES = (*PAIRED, "unresolved", "parse", "not_extracted", "extra")

Facts = dict[str, list[Any]]


@dataclass(frozen=True)
class FactError:
    document_id: str
    cause: str
    gold_key: str | None  # the missed key (None for an extra)
    predicted_key: str | None  # the extra key (None for a plain miss)
    gold: list[Any] | None = None
    predicted: list[Any] | None = None


@dataclass(frozen=True)
class DocumentErrors:
    document_id: str
    wrong_class: bool
    facts: list[FactError]


def _attribute(key: str) -> str:
    return str(json.loads(key)[0])


def _unmatched(gold: Facts, predicted: Facts) -> tuple[list[str], list[str]]:
    hit = {k for k in gold.keys() & predicted.keys() if _same_set(gold[k], predicted[k])}
    return sorted(gold.keys() - hit), sorted(predicted.keys() - hit)


def _rules(gold: Facts, predicted: Facts) -> dict[str, Callable[[str, str], bool]]:
    def same_attribute(g: str, p: str) -> bool:
        return _attribute(g) == _attribute(p)

    def same_values(g: str, p: str) -> bool:
        return _same_set(gold[g], predicted[p])

    return {
        "value": lambda g, p: g == p,
        "context": lambda g, p: same_attribute(g, p) and same_values(g, p),
        "attribute": lambda g, p: not same_attribute(g, p) and same_values(g, p),
        "value_and_context": same_attribute,
    }


def _pair(
    misses: list[str], extras: list[str], gold: Facts, predicted: Facts
) -> list[tuple[str, str, str]]:
    """(cause, gold key, predicted key) for misses an extra explains, each key used once."""
    pairs: list[tuple[str, str, str]] = []
    for cause, fits in _rules(gold, predicted).items():
        for g in misses:
            used_gold = {pg for _, pg, _ in pairs}
            used_pred = {pp for _, _, pp in pairs}
            if g in used_gold:
                continue
            match = next((p for p in extras if p not in used_pred and fits(g, p)), None)
            if match is not None:
                pairs = [*pairs, (cause, g, match)]
    return pairs


def _miss_cause(answer: dict[str, Any], attribute: str, unresolved: set[str], text: str) -> str:
    if attribute in unresolved:
        return "unresolved"
    raws = [o["raw_text"] for o in answer["observations"] if o["attribute_id"] == attribute]
    return "not_extracted" if any(contains_token(text, raw) for raw in raws) else "parse"


def document_errors(
    answer: dict[str, Any], prediction: Prediction | None, parsed_text: str
) -> DocumentErrors:
    doc = answer["input_id"]
    failed = prediction is None or prediction.failure is not None
    gold = _groups(answer["facts"], "attribute_id")
    predicted = {} if failed or prediction is None else _groups(prediction.facts, "attribute")
    misses, extras = _unmatched(gold, predicted)
    pairs = _pair(misses, extras, gold, predicted)
    paired_gold = {g for _, g, _ in pairs}
    paired_pred = {p for _, _, p in pairs}
    unresolved = (
        set() if failed or prediction is None else {u["attribute"] for u in prediction.unresolved}
    )
    found = [FactError(doc, c, g, p, gold[g], predicted[p]) for c, g, p in pairs]
    missed = [
        FactError(
            doc,
            _miss_cause(answer, _attribute(g), unresolved, parsed_text),
            g,
            None,
            gold[g],
        )
        for g in misses
        if g not in paired_gold
    ]
    extra = [
        FactError(doc, "extra", None, p, None, predicted[p]) for p in extras if p not in paired_pred
    ]
    wrong_class = prediction is not None and prediction.class_id != answer["expected_class"]
    return DocumentErrors(doc, wrong_class, [*found, *missed, *extra])


def parsed_text(path: Path) -> str:
    """All block texts of one parsed document, a line each ("" when the file is missing)."""
    if not path.exists():
        return ""
    blocks = json.loads(path.read_text())["blocks"]
    return "\n".join(str(block.get("text") or "") for block in blocks)


def _prediction(path: Path) -> Prediction | None:
    if not path.exists():
        return None
    return Prediction.model_validate(json.loads(path.read_text())["prediction"])


def _unexplained_gaps(run_dir: Path, ids: list[str], failures: dict[str, str]) -> list[str]:
    """Documents without a prediction file that the run did not record as unparsed: the run
    writes a file for every parsed document, so these mean an incomplete folder."""
    return [
        doc
        for doc in ids
        if failures.get(doc) != "not_parsed"
        and not (run_dir / "predictions" / f"{doc}.json").exists()
    ]


def run_errors(run_dir: Path) -> list[DocumentErrors]:
    """Refuses (ValueError) a folder missing a prediction its run.json does not explain:
    counting it as a parse failure would make the analysis disagree with scores.json."""
    run = json.loads((run_dir / "run.json").read_text())
    split = run.get("split", "dev")
    answers = handwritten.answers() if split == "handwritten" else split_answers(split)
    gaps = _unexplained_gaps(run_dir, [a["input_id"] for a in answers], run.get("failures", {}))
    if gaps:
        raise ValueError(f"{run_dir} is incomplete: no prediction file for {', '.join(gaps)}")
    return [
        document_errors(
            answer,
            _prediction(run_dir / "predictions" / f"{answer['input_id']}.json"),
            parsed_text(ROOT / "var/parsed" / split / f"{answer['input_id']}.json"),
        )
        for answer in answers
    ]


def summary(documents: list[DocumentErrors]) -> dict[str, Any]:
    """Per cause, the missed gold keys (fn) and extra predicted keys (fp) it accounts for."""
    errors = [e for d in documents for e in d.facts]
    fn = Counter(e.cause for e in errors if e.gold_key is not None)
    fp = Counter(e.cause for e in errors if e.predicted_key is not None)
    return {
        "causes": {c: {"fn": fn[c], "fp": fp[c]} for c in CAUSES if fn[c] or fp[c]},
        "fn": sum(fn.values()),
        "fp": sum(fp.values()),
        "wrong_class": [d.document_id for d in documents if d.wrong_class],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--list", action="store_true", help="print every error, not only counts")
    args = parser.parse_args()
    for run_dir in args.runs:
        documents = run_errors(run_dir)
        print(json.dumps({"run": run_dir.name} | summary(documents), ensure_ascii=False))
        if not args.list:
            continue
        for e in (e for d in documents for e in d.facts):
            print(f"  {e.document_id} {e.cause}")
            print(f"    gold {e.gold_key} {e.gold}")
            print(f"    pred {e.predicted_key} {e.predicted}")


if __name__ == "__main__":
    main()
