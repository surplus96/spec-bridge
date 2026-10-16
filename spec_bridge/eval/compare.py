"""Judge configuration E against the thresholds registered before the runs.

Paired bootstrap over documents: resample the documents with replacement, recompute each
metric for both runs on the same sample, and read the 95% percentile interval of the
difference. "Clearly better" means the interval stays above zero.

Each split has its own registered criteria (CP-S4 R6): the dev split D-048, the test
split and the handwritten set D-080. The split is read from the runs' run.json; runs of
different splits are refused.

Run (after the runs exist; scores are re-made with the current scorer first):
    uv run python -m spec_bridge.eval.compare --e1 var/eval/E1-... --e0 var/eval/E0-... \
        --r var/eval/R-...
"""

import argparse
import json
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spec_bridge.eval.rescore import rescore
from spec_bridge.eval.scoring import DocScore

# D-048, fixed before any E run.
C2_CONTEXT_FP = 16  # second-round C: keys with an invented context (W3 report §8)
TARGET_CONTEXT_TP = 50  # user-set target zone
# D-080, fixed before the test and handwritten runs.
TEST_CONTEXT_FP = 10  # 16 per 24 documents carried to 16 documents
TARGET_SHARE = 0.515  # target zone: context TP at least 51.5% of the context keys
SAMPLES = 10_000
SEED = 7


@dataclass(frozen=True)
class Criteria:
    reference: str
    judged: tuple[str, ...]  # checks that carry a pass; the others are shown only
    context_fp_limit: int | None
    target_tp: int | None = None  # a fixed target, else TARGET_SHARE of the context keys

    def target(self, context_keys: int) -> int:
        if self.target_tp is not None:
            return self.target_tp
        return math.ceil(TARGET_SHARE * context_keys)  # TP is a count: "at least 51.5%"


CRITERIA = {
    "dev": Criteria("D-048", ("a", "b", "c"), C2_CONTEXT_FP, TARGET_CONTEXT_TP),
    "test": Criteria("D-080", ("a", "b", "c"), TEST_CONTEXT_FP),
    "handwritten": Criteria("D-080 ③", ("c",), None),
}

Metric = Callable[[list[DocScore]], float]


def micro_f1(scores: list[DocScore]) -> float:
    tp = sum(c.tp for s in scores for c in s.facts.values())
    fp = sum(c.fp for s in scores for c in s.facts.values())
    fn = sum(c.fn for s in scores for c in s.facts.values())
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def context_tp(scores: list[DocScore]) -> float:
    return float(sum(s.context_tp for s in scores))


def context_fp(scores: list[DocScore]) -> float:
    return float(sum(s.context_fp for s in scores))


def paired_bootstrap(
    a: list[DocScore], b: list[DocScore], metric: Metric, *, n: int = SAMPLES, seed: int = SEED
) -> dict[str, float]:
    """b - a on the full set and its 95% percentile interval over document resamples."""
    by_doc = {s.document_id: s for s in a}
    pairs = [(by_doc[s.document_id], s) for s in b]
    if len(pairs) != len(a):
        raise ValueError("the two runs must score the same documents")
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        sample = rng.choices(pairs, k=len(pairs))
        diffs.append(metric([y for _, y in sample]) - metric([x for x, _ in sample]))
    diffs.sort()
    return {
        "diff": metric(b) - metric(a),
        "low": diffs[int(0.025 * n)],
        "high": diffs[int(0.975 * n) - 1],
    }


def judge(
    e1: list[DocScore], e0: list[DocScore], r: list[DocScore], split: str = "dev"
) -> dict[str, Any]:
    """The registered checks of the split, each with the numbers it rests on."""
    criteria = CRITERIA[split]
    retrieval = paired_bootstrap(e0, e1, context_tp)
    over_rules = paired_bootstrap(r, e1, micro_f1)
    invention: dict[str, Any] = {"e1_context_fp": context_fp(e1)}
    if criteria.context_fp_limit is not None:
        invention["limit"] = criteria.context_fp_limit
    shown = {
        "a": ("a_retrieval_adds_context", retrieval, retrieval["low"] > 0),
        "b": ("b_no_more_invention", invention, context_fp(e1) <= (criteria.context_fp_limit or 0)),
        "c": ("c_beats_rules", over_rules, over_rules["low"] > 0),
    }
    checks = {
        name: numbers | ({"pass": passed} if key in criteria.judged else {})
        for key, (name, numbers, passed) in shown.items()
    }
    effect = all(checks[shown[key][0]]["pass"] for key in criteria.judged)
    target = criteria.target(sum(s.context_keys for s in e1))
    reached = context_tp(e1) >= target
    verdicts = (
        {"verdict_handwritten": effect and reached}  # ③'s handwritten condition
        if split == "handwritten"
        else {"verdict_effect": effect, "verdict_target_zone": effect and reached}
    )
    return checks | {
        "criteria": criteria.reference,
        "e1_context_tp": context_tp(e1),
        "target": target,
        **verdicts,
    }


def split_of(*run_dirs: Path) -> str:
    """The one split the runs were made on (run.json); runs of different splits refused."""
    splits = {str(json.loads((d / "run.json").read_text()).get("split", "dev")) for d in run_dirs}
    if len(splits) != 1:
        raise ValueError(f"the runs must be of the same split, got {sorted(splits)}")
    return splits.pop()


def load_scores(run_dir: Path) -> list[DocScore]:
    """Scores of a run under the current scorer (written next to the run, never over it)."""
    record = json.loads(rescore(run_dir).read_text())
    return [DocScore.model_validate(row) for row in record["scores"]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e1", type=Path, required=True)
    parser.add_argument("--e0", type=Path, required=True)
    parser.add_argument("--r", type=Path, required=True)
    args = parser.parse_args()
    split = split_of(args.e1, args.e0, args.r)
    verdict = judge(load_scores(args.e1), load_scores(args.e0), load_scores(args.r), split)
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
