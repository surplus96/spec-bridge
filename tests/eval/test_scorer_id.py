"""The scorer is frozen: any byte change in an evaluation module changes its id (D-036).

A formatter run over the whole package once changed the id without changing a rule
(2026-10-14). If you change scoring on purpose, record the new id in docs/decisions.md,
rescore every run and update RECORDED here.
"""

from spec_bridge.eval.rescore import scorer_id

RECORDED = "f9b6e223cb15"  # D-081 (W6-0: split-aware dedup scoring)


def test_the_scorer_is_the_recorded_one() -> None:
    assert scorer_id() == RECORDED
