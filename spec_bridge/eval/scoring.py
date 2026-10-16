"""Evaluator v1 (W3-6, FR-13) following data/synth/answer-contract.yaml `scoring`.

Channels: class_mapping (top-1/top-3/unknown), normalized_facts (P/R/F1 by fact key,
micro and macro, per attribute and per class) and raw_observation_retrieval (recall).
Every answer stays in the inventory: a failed or missing prediction scores its gold
facts as misses (contract `generation_failures`).
"""

import json
from collections.abc import Iterable
from typing import Any

from spec_bridge.eval.locations import contains_token, same_place
from spec_bridge.ontology.facts import Location, StrictModel

ABS_TOLERANCE = 0.000001  # contract numeric_match default (rel tolerance 0)
INVALID = {"invalid_unit", "invalid_shape"}  # no normalized fact (E2/E3)
# Contract context_defaults: policy values the document does not write; a prediction
# that leaves them out is the same context.
CONTEXT_DEFAULTS = {"pressure": "not_applicable", "weight": "unknown"}
DEFAULT_SCOPE = "main_equipment"


class Prediction(StrictModel):
    document_id: str
    class_id: str  # chosen leaf class or "unknown"
    class_candidates: list[str] = []  # ranked; used for top-3
    facts: list[dict[str, Any]] = []  # candidate facts with "attribute" and "occurrences"
    unresolved: list[dict[str, Any]] = []  # grounded but not normalized (attribute, occurrence)
    failure: str | None = None  # parse or LLM failure: nothing was extracted


class Counts(StrictModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: "Counts") -> None:
        self.tp, self.fp, self.fn = self.tp + other.tp, self.fp + other.fp, self.fn + other.fn


class DocScore(StrictModel):
    document_id: str
    expected_class: str
    predicted_class: str
    top3_hit: bool
    failed: bool
    facts: dict[str, Counts]  # per attribute
    observations_found: int
    observations_total: int
    observations_unattributed: int
    observations_invalid: int
    occurrences_predicted: int = 0
    occurrences_matched: int = 0  # predicted occurrences that land on a gold observation
    context_keys: int = 0  # gold keys with a stated basis, condition or non-default scope
    context_tp: int = 0
    context_fp: int = 0  # predicted keys carrying a context that match no gold key


class Prf(StrictModel):
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


class Metrics(StrictModel):
    documents: int
    failed_documents: list[str]
    class_top1: float
    class_top3: float
    class_unknown: int
    facts_micro: Prf
    facts_macro_f1_attribute: float  # mean over gold attributes only (CP-S3 R1)
    facts_macro_f1_class: float
    facts_fp_outside_gold: int  # facts for attributes no answer has (CP-S3 R1)
    facts_by_attribute: dict[str, Prf]
    facts_by_class: dict[str, Prf]
    observation_recall: float
    observations_found: int
    observations_total: int
    observations_unattributed: int
    observations_invalid: int
    occurrence_precision: float  # CP-S3 L4
    occurrences_predicted: int
    occurrences_matched: int
    context_keys: int  # W4-R: the qualifier channel (D-048 thresholds)
    context_tp: int
    plain_keys: int
    plain_tp: int
    context_fp: int



# matching -------------------------------------------------------------------------------
def _canon(value: Any) -> Any:
    """Key form: integral floats become ints so 50 and 50.0 name the same condition."""
    if isinstance(value, dict):
        return {k: _canon(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canon(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def fact_key(
    attribute: str, basis: dict[str, Any], condition: dict[str, Any], scope: str | None
) -> str:
    stated = {k: v for k, v in basis.items() if CONTEXT_DEFAULTS.get(k) != v}
    scope = scope or DEFAULT_SCOPE  # contract context_defaults, not left to producers (R7)
    return json.dumps([attribute, stated, _canon(condition), scope], sort_keys=True)


def has_context(key: str) -> bool:
    """A fact key whose basis or condition is stated or whose scope is not the default."""
    _, basis, condition, scope = json.loads(key)
    return bool(basis or condition or scope != DEFAULT_SCOPE)


def values_match(gold: Any, predicted: Any) -> bool:
    """Numbers within the absolute tolerance, lists order-free, objects atomic."""
    if isinstance(gold, bool) or isinstance(predicted, bool):
        return gold is predicted
    if isinstance(gold, (int, float)) and isinstance(predicted, (int, float)):
        return abs(gold - predicted) <= ABS_TOLERANCE
    if isinstance(gold, dict) and isinstance(predicted, dict):
        return gold.keys() == predicted.keys() and all(
            values_match(gold[k], predicted[k]) for k in gold
        )
    if isinstance(gold, list) and isinstance(predicted, list):
        rest = list(predicted)
        for item in gold:
            hit = next((i for i, p in enumerate(rest) if values_match(item, p)), None)
            if hit is None:
                return False
            rest.pop(hit)
        return not rest
    return bool(gold == predicted)


def _same_set(gold: list[tuple[Any, Any]], predicted: list[tuple[Any, Any]]) -> bool:
    """E5: the distinct values under one key form an atomic set."""

    def covered(a: list[tuple[Any, Any]], b: list[tuple[Any, Any]]) -> bool:
        return all(any(u == w and values_match(v, x) for x, w in b) for v, u in a)

    return covered(gold, predicted) and covered(predicted, gold)


def _groups(facts: Iterable[dict[str, Any]], attribute_field: str) -> dict[str, list[Any]]:
    groups: dict[str, list[Any]] = {}
    for fact in facts:
        key = fact_key(fact[attribute_field], fact["basis"], fact["condition"], fact["scope"])
        groups.setdefault(key, []).append((fact["value"], fact["unit"]))
    return groups


def _occurrences(prediction: Prediction) -> list[tuple[str, dict[str, Any]]]:
    found = [(f["attribute"], o) for f in prediction.facts for o in f.get("occurrences", [])]
    return found + [(u["attribute"], u["occurrence"]) for u in prediction.unresolved]


def _retrieved(obs: dict[str, Any], occurrences: list[tuple[str, dict[str, Any]]]) -> bool:
    return any(
        attribute == obs["attribute_id"]
        and occurrence.get("location")
        and same_place(obs["location"], Location.model_validate(occurrence["location"]))
        and contains_token(str(occurrence.get("raw_text", "")), obs["raw_text"])
        for attribute, occurrence in occurrences
    )


def _matched(
    attribute: str, occurrence: dict[str, Any], observations: list[dict[str, Any]]
) -> bool:
    if not occurrence.get("location"):
        return False
    location = Location.model_validate(occurrence["location"])
    raw = str(occurrence.get("raw_text", ""))
    return any(
        obs["attribute_id"] == attribute
        and same_place(obs["location"], location)
        and contains_token(raw, obs["raw_text"])
        for obs in observations
    )


def _top3(prediction: Prediction) -> list[str]:
    """The chosen class first, then keyword candidates: exactly three classes (R6)."""
    rest = [c for c in prediction.class_candidates if c != prediction.class_id]
    return [prediction.class_id, *rest][:3]


# scoring ---------------------------------------------------------------------------------
def score_document(answer: dict[str, Any], prediction: Prediction | None) -> DocScore:
    failed = prediction is None or prediction.failure is not None
    gold = _groups(answer["facts"], "attribute_id")
    predicted = {} if failed or prediction is None else _groups(prediction.facts, "attribute")
    counts: dict[str, Counts] = {}
    context_tp = context_fp = 0
    for key in gold.keys() | predicted.keys():
        attribute = json.loads(key)[0]
        count = counts.setdefault(attribute, Counts())
        if key in gold and key in predicted and _same_set(gold[key], predicted[key]):
            count.tp += 1
            context_tp += has_context(key)
            continue
        count.fn += key in gold
        count.fp += key in predicted
        context_fp += key in predicted and has_context(key)

    attributed = [o for o in answer["observations"] if o["attribute_id"] is not None]
    occurrences = [] if failed or prediction is None else _occurrences(prediction)
    return DocScore(
        document_id=answer["input_id"],
        expected_class=answer["expected_class"],
        predicted_class="unknown" if prediction is None else prediction.class_id,
        top3_hit=prediction is not None and answer["expected_class"] in _top3(prediction),
        failed=failed,
        facts=dict(sorted(counts.items())),
        observations_found=sum(_retrieved(o, occurrences) for o in attributed),
        observations_total=len(attributed),
        observations_unattributed=len(answer["observations"]) - len(attributed),
        observations_invalid=sum(o["interpretation"] in INVALID for o in answer["observations"]),
        occurrences_predicted=len(occurrences),
        occurrences_matched=sum(_matched(a, o, attributed) for a, o in occurrences),
        context_keys=sum(has_context(key) for key in gold),
        context_tp=context_tp,
        context_fp=context_fp,    
    )


def prf(counts: Counts) -> Prf:
    precision = counts.tp / (counts.tp + counts.fp) if counts.tp + counts.fp else 0.0
    recall = counts.tp / (counts.tp + counts.fn) if counts.tp + counts.fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Prf(tp=counts.tp, fp=counts.fp, fn=counts.fn, precision=precision, recall=recall, f1=f1)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(scores: list[DocScore]) -> Metrics:
    total = Counts()
    by_attribute: dict[str, Counts] = {}
    by_class: dict[str, Counts] = {}
    for score in scores:
        for attribute, count in score.facts.items():
            total.add(count)
            by_attribute.setdefault(attribute, Counts()).add(count)
            by_class.setdefault(score.expected_class, Counts()).add(count)
    attribute_prf = {a: prf(c) for a, c in sorted(by_attribute.items())}
    gold_attributes = [a for a, c in by_attribute.items() if c.tp + c.fn]
    class_prf = {c: prf(n) for c, n in sorted(by_class.items())}
    found = sum(s.observations_found for s in scores)
    observed = sum(s.observations_total for s in scores)
    predicted = sum(s.occurrences_predicted for s in scores)
    matched = sum(s.occurrences_matched for s in scores)
    return Metrics(
        documents=len(scores),
        failed_documents=[s.document_id for s in scores if s.failed],
        class_top1=_mean([float(s.predicted_class == s.expected_class) for s in scores]),
        class_top3=_mean([float(s.top3_hit) for s in scores]),
        class_unknown=sum(s.predicted_class == "unknown" for s in scores),
        facts_micro=prf(total),
        facts_macro_f1_attribute=_mean([attribute_prf[a].f1 for a in gold_attributes]),
        facts_macro_f1_class=_mean([p.f1 for p in class_prf.values()]),
        facts_fp_outside_gold=sum(
            c.fp for a, c in by_attribute.items() if a not in gold_attributes
        ),
        facts_by_attribute=attribute_prf,
        facts_by_class=class_prf,
        observation_recall=found / observed if observed else 0.0,
        observations_found=found,
        observations_total=observed,
        observations_unattributed=sum(s.observations_unattributed for s in scores),
        observations_invalid=sum(s.observations_invalid for s in scores),
        occurrence_precision=matched / predicted if predicted else 0.0,
        occurrences_predicted=predicted,
        occurrences_matched=matched,
        context_keys=sum(s.context_keys for s in scores),
        context_tp=sum(s.context_tp for s in scores),
        plain_keys=sum(sum(c.tp + c.fn for c in s.facts.values()) - s.context_keys for s in scores),
        plain_tp=sum(sum(c.tp for c in s.facts.values()) - s.context_tp for s in scores),
        context_fp=sum(s.context_fp for s in scores),
    )


def score_split(
    answers: list[dict[str, Any]], predictions: dict[str, Prediction]
) -> tuple[list[DocScore], Metrics]:
    """Score every answer; a document without a prediction is a failure, never dropped."""
    scores = [score_document(a, predictions.get(a["input_id"])) for a in answers]
    return scores, aggregate(scores)
