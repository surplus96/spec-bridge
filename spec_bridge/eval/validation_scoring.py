"""Validation scoring G3 (W4-4, FR-13): the validator's findings against the gold issues.

Matching follows the answer contract `issue_match` as fixed in the W4 plan (decision 4,
D-038): code and attribute set exactly; the rule compared by its kind (the gold points at
data/ontology/dataset-contract.yaml, the system at ontology/ontology.yaml); and every gold
occurrence must lie inside the finding's occurrences (E1 has none: nothing was found).
REVIEW findings have no contract code; they are counted apart, never as E1-E5 errors.
A failed or missing prediction scores its gold issues as misses (no document is dropped).
"""

from collections import defaultdict
from typing import Any

from pydantic import ValidationError

from spec_bridge.eval.locations import same_place
from spec_bridge.eval.scoring import Counts, Prediction, Prf, prf
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import Location, StrictModel
from spec_bridge.validate.findings import Finding
from spec_bridge.validate.validator import validate

CODES = ("E1", "E2", "E3", "E4", "E5")


class ValidationScore(StrictModel):
    document_id: str
    clean: bool  # the gold has no issue
    failed: bool
    by_code: dict[str, Counts]
    review: int  # REVIEW findings (no gold code)


class ValidationMetrics(StrictModel):
    documents: int
    clean_documents: int
    failed_documents: list[str]
    micro: Prf  # E1-E5 together
    by_code: dict[str, Prf]
    false_findings_on_clean: int
    false_findings_per_clean_document: float
    review_findings: int


def rule_kind(rule_ref: str) -> str:
    """'…/dataset_allowed_values' and '…/allowed_values' are the same kind of rule."""
    last = rule_ref.rsplit("/", 1)[-1]
    return "allowed_values" if last.endswith("allowed_values") else last


def _covers(
    finding: Finding, issue: dict[str, Any], observations: dict[str, dict[str, Any]]
) -> bool:
    if issue["code"] == "E1":
        return True
    places = [
        Location.model_validate(o["location"]) for o in finding.occurrences if o.get("location")
    ]
    return all(
        any(same_place(observations[oid]["location"], place) for place in places)
        for oid in issue["observation_ids"]
    )


def _matches(
    finding: Finding, issue: dict[str, Any], observations: dict[str, dict[str, Any]]
) -> bool:
    return (
        finding.code == issue["code"]
        and sorted(finding.attribute_ids) == sorted(issue["attribute_ids"])
        and rule_kind(finding.rule_ref) == rule_kind(issue["rule_ref"])
        and _covers(finding, issue, observations)
    )


def score_validation(answer: dict[str, Any], findings: list[Finding] | None) -> ValidationScore:
    """findings=None: the document failed upstream; every gold issue is a miss."""
    observations = {o["observation_id"]: o for o in answer["observations"]}
    counts = {code: Counts() for code in CODES}
    found = [f for f in (findings or []) if f.code != "REVIEW"]
    unmatched = list(found)
    for issue in answer["issues"]:
        hit = next((f for f in unmatched if _matches(f, issue, observations)), None)
        if hit is None:
            counts[issue["code"]].fn += 1
        else:
            counts[issue["code"]].tp += 1
            unmatched.remove(hit)
    for finding in unmatched:
        counts[finding.code].fp += 1
    return ValidationScore(
        document_id=answer["input_id"],
        clean=not answer["issues"],
        failed=findings is None,
        by_code=counts,
        review=sum(f.code == "REVIEW" for f in (findings or [])),
    )


def aggregate_validation(scores: list[ValidationScore]) -> ValidationMetrics:
    total = Counts()
    by_code: dict[str, Counts] = defaultdict(Counts)
    for score in scores:
        for code, count in score.by_code.items():
            total.add(count)
            by_code[code].add(count)
    clean = [s for s in scores if s.clean]
    false_on_clean = sum(c.fp for s in clean for c in s.by_code.values())
    return ValidationMetrics(
        documents=len(scores),
        clean_documents=len(clean),
        failed_documents=[s.document_id for s in scores if s.failed],
        micro=prf(total),
        by_code={code: prf(by_code[code]) for code in CODES},
        false_findings_on_clean=false_on_clean,
        false_findings_per_clean_document=false_on_clean / len(clean) if clean else 0.0,
        review_findings=sum(s.review for s in scores),
    )


def validate_predictions(
    onto: Ontology, answers: list[dict[str, Any]], predictions: dict[str, Prediction]
) -> tuple[list[ValidationScore], ValidationMetrics]:
    """Run the validator on each prediction (as the pipeline would) and score it."""
    scores = []
    for answer in answers:
        prediction = predictions.get(answer["input_id"])
        if prediction is None or prediction.failure is not None:
            scores.append(score_validation(answer, None))
            continue
        try:
            result = validate(onto, prediction.class_id, prediction.facts, prediction.unresolved)
        except ValidationError:  # facts that never passed the schema (config A): no findings
            scores.append(score_validation(answer, None))
            continue
        scores.append(score_validation(answer, result.findings))
    return scores, aggregate_validation(scores)
