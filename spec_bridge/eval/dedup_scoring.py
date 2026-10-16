"""Duplicate/similar scoring G4 (W4-5, FR-13) against the complete comparison labels.

`data/synth/comparison-candidates.yaml` lists, for every document, the duplicate and
similar registry products of its split; any other registry product of the same class is
new (contract `complete_comparison_labels`). Every (document, product) pair of the gold
class is scored as a three-way confusion: duplicate / similar / new. A failed or missing
prediction predicts "new" for every pair, so its labelled pairs count as misses.
"""

import json
from typing import Any

import yaml

from spec_bridge.dedup.matcher import match
from spec_bridge.eval.scoring import Counts, Prediction, Prf, prf
from spec_bridge.normalize.dictionary import ROOT
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.identity import MakerIndex

LABELS = ROOT / "data/synth/comparison-candidates.yaml"
REGISTRY = ROOT / "data/synth/registry"
RELATIONS = ("duplicate", "similar", "new")


class DedupMetrics(StrictModel):
    documents: int
    pairs: int
    confusion: dict[str, dict[str, int]]  # gold relation -> predicted relation -> pairs
    duplicate: Prf
    similar: Prf
    labelled: Prf  # duplicate and similar together: the G4 view


def split_labels(split: str) -> dict[str, dict[str, list[str]]]:
    queries = yaml.safe_load(LABELS.read_text())["queries"]
    return {q["input_id"]: q for q in queries if q["split"] == split}


def split_registry(split: str) -> tuple[list[dict[str, Any]], MakerIndex]:
    """The registry of one split only: a test document is judged against test products."""
    path = REGISTRY / f"{split}.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    makers = MakerIndex(json.loads((REGISTRY / "manufacturers.json").read_text()))
    return records, makers


def confusion_of(
    answer: dict[str, Any],
    predicted: dict[str, str],
    registry: list[dict[str, Any]],
    labels: dict[str, list[str]],
) -> dict[str, dict[str, int]]:
    """Pairs of the gold class plus any product the prediction named outside it."""
    gold_class = answer["expected_class"]
    pairs = {r["product_id"] for r in registry if r["class"] == gold_class} | set(predicted)
    table: dict[str, dict[str, int]] = {g: dict.fromkeys(RELATIONS, 0) for g in RELATIONS}
    for product in pairs:
        gold = (
            "duplicate"
            if product in labels.get("duplicate", [])
            else "similar"
            if product in labels.get("similar", [])
            else "new"
        )
        table[gold][predicted.get(product, "new")] += 1
    return table


def aggregate_dedup(tables: list[dict[str, dict[str, int]]]) -> DedupMetrics:
    total: dict[str, dict[str, int]] = {g: dict.fromkeys(RELATIONS, 0) for g in RELATIONS}
    for table in tables:
        for gold, row in table.items():
            for pred, n in row.items():
                total[gold][pred] += n

    def counts(relations: tuple[str, ...]) -> Counts:
        tp = sum(total[r][r] for r in relations)
        predicted = sum(total[g][p] for g in RELATIONS for p in relations)
        gold = sum(total[g][p] for g in relations for p in RELATIONS)
        return Counts(tp=tp, fp=predicted - tp, fn=gold - tp)

    return DedupMetrics(
        documents=len(tables),
        pairs=sum(sum(row.values()) for row in total.values()),
        confusion=total,
        duplicate=prf(counts(("duplicate",))),
        similar=prf(counts(("similar",))),
        labelled=prf(counts(("duplicate", "similar"))),
    )


def dev_labels() -> dict[str, dict[str, list[str]]]:
    return split_labels("dev")


def dev_registry() -> tuple[list[dict[str, Any]], MakerIndex]:
    return split_registry("dev")


def evaluate_dedup(
    answers: list[dict[str, Any]], predictions: dict[str, Prediction], split: str = "dev"
) -> DedupMetrics:
    registry, makers = split_registry(split)
    labels = split_labels(split)
    tables = []
    for answer in answers:
        prediction = predictions.get(answer["input_id"])
        predicted: dict[str, str] = {}
        if prediction is not None and prediction.failure is None:
            for m in match(prediction.class_id, prediction.facts, registry, makers):
                predicted[m.registry_id] = m.relation
        tables.append(confusion_of(answer, predicted, registry, labels[answer["input_id"]]))
    return aggregate_dedup(tables)
