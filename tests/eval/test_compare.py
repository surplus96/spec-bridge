"""W4-R R6: the D-048 judge — paired bootstrap and the three checks."""

import json
from pathlib import Path

import pytest

from spec_bridge.eval.compare import judge, micro_f1, paired_bootstrap, split_of
from spec_bridge.eval.scoring import Counts, DocScore


def doc(i: int, tp: int, fp: int, fn: int, ctx_tp: int = 0, ctx_fp: int = 0) -> DocScore:
    return DocScore(
        document_id=f"D{i}",
        expected_class="X",
        predicted_class="X",
        top3_hit=True,
        failed=False,
        facts={"a": Counts(tp=tp, fp=fp, fn=fn)},
        observations_found=0,
        observations_total=0,
        observations_unattributed=0,
        observations_invalid=0,
        context_keys=4,
        context_tp=ctx_tp,
        context_fp=ctx_fp,
    )


def run(tp: int, fp: int, fn: int, ctx_tp: int = 0, ctx_fp: int = 0) -> list[DocScore]:
    return [doc(i, tp, fp, fn, ctx_tp, ctx_fp) for i in range(24)]


def test_identical_runs_have_a_zero_interval() -> None:
    same = run(5, 1, 1)
    result = paired_bootstrap(same, same, micro_f1, n=200)
    assert result == {"diff": 0.0, "low": 0.0, "high": 0.0}


def test_a_uniform_gain_is_clearly_positive() -> None:
    result = paired_bootstrap(run(5, 1, 1), run(7, 0, 0), micro_f1, n=200)
    assert result["diff"] > 0 and result["low"] > 0


def test_judge_passes_only_when_all_three_checks_pass() -> None:
    e1, e0, r = run(9, 0, 1, ctx_tp=3), run(9, 0, 1, ctx_tp=1), run(5, 4, 5)
    verdict = judge(e1, e0, r)
    assert verdict["a_retrieval_adds_context"]["pass"] and verdict["c_beats_rules"]["pass"]
    assert verdict["b_no_more_invention"]["pass"] and verdict["verdict_effect"]
    assert verdict["e1_context_tp"] == 72 and verdict["verdict_target_zone"]  # 24 x 3 >= 50


def test_invented_context_fails_the_judge() -> None:
    e1 = run(9, 0, 1, ctx_tp=3, ctx_fp=1)  # 24 invented contexts > 16
    verdict = judge(e1, run(9, 0, 1, ctx_tp=1), run(5, 4, 5))
    assert not verdict["b_no_more_invention"]["pass"] and not verdict["verdict_effect"]


def test_no_retrieval_gain_fails_the_judge() -> None:
    same = run(9, 0, 1, ctx_tp=2)
    verdict = judge(same, same, run(5, 4, 5))
    assert not verdict["a_retrieval_adds_context"]["pass"] and not verdict["verdict_effect"]


def runs_of(n: int, ctx_tp: int, ctx_fp: int, keys: int) -> list[DocScore]:
    """n documents whose context totals are ctx_tp / ctx_fp over `keys` context keys."""
    docs = []
    for i in range(n):
        d = doc(i, 9, 0, 1, ctx_tp=1 if i < ctx_tp else 0, ctx_fp=1 if i < ctx_fp else 0)
        docs.append(d.model_copy(update={"context_keys": keys // n + (1 if i < keys % n else 0)}))
    return docs


def test_the_test_split_uses_the_registered_limits_not_the_dev_ones() -> None:
    """CP-S4 R6: D-080 for the test split — (b) at most 10, target ceil(51.5% of keys)."""
    e0 = runs_of(72, 0, 0, 72)
    r = [d.model_copy(update={"facts": {"a": Counts(tp=5, fp=4, fn=5)}}) for d in e0]
    eleven = judge(runs_of(72, 38, 11, 72), e0, r, split="test")
    assert eleven["b_no_more_invention"]["limit"] == 10
    assert not eleven["b_no_more_invention"]["pass"]  # 11 > 10, though <= 16 for dev
    assert eleven["target"] == 38 and eleven["verdict_target_zone"] is False  # effect failed
    ten = judge(runs_of(72, 38, 10, 72), e0, r, split="test")
    assert ten["b_no_more_invention"]["pass"] and ten["verdict_effect"]
    assert ten["e1_context_tp"] == 38 and ten["verdict_target_zone"]  # 38 >= 38, < 50 for dev


def test_the_handwritten_set_judges_only_c_and_the_target_zone() -> None:
    """D-080 ③: the handwritten set needs (c) and the target zone; (a) and (b) are shown only."""
    e0 = runs_of(6, 0, 0, 13)
    r = [d.model_copy(update={"facts": {"a": Counts(tp=5, fp=4, fn=5)}}) for d in e0]
    verdict = judge(runs_of(6, 1, 6, 13), e0, r, split="handwritten")
    assert "pass" not in verdict["a_retrieval_adds_context"]
    assert "pass" not in verdict["b_no_more_invention"]
    assert verdict["c_beats_rules"]["pass"] and verdict["target"] == 7
    assert verdict["verdict_handwritten"] is False  # 1 < 7
    assert "verdict_effect" not in verdict


def test_dev_keeps_the_d048_judge() -> None:
    e1, e0, r = run(9, 0, 1, ctx_tp=3), run(9, 0, 1, ctx_tp=1), run(5, 4, 5)
    assert judge(e1, e0, r) == judge(e1, e0, r, split="dev")
    assert judge(e1, e0, r)["target"] == 50


def test_runs_of_different_splits_are_refused(tmp_path: Path) -> None:
    for name, split in (("e1", "test"), ("e0", "test"), ("r", "dev")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "run.json").write_text(json.dumps({"split": split}))
    with pytest.raises(ValueError, match="same split"):
        split_of(tmp_path / "e1", tmp_path / "e0", tmp_path / "r")
