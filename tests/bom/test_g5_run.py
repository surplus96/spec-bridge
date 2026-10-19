"""G5 follow-up runner (D-109): R/C/E answers, scores, the pre-registered judge, the freeze."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.bom.g5 import run as g5
from spec_bridge.bom.g5.resolve import NONE, Examples, llm_answer, schema
from spec_bridge.bom.g5.rows import load
from spec_bridge.bom.linker import _spans, search_key


class ModelKeyProvider:
    """Answers the candidate whose model key is in the row, else none (a stand-in)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any] | None, task: str
    ) -> dict[str, Any]:
        self.calls.append({"user": user, "schema": schema})
        row = user.rsplit("Row: ", 1)[1]
        model = row.split("Model: ", 1)[1].split("\n")[0]
        spans = _spans(model)
        assert schema is not None
        for line in user.split("Candidates:\n", 1)[1].splitlines():
            if " | model " in line and search_key(line.rsplit(" | model ", 1)[1]) in spans:
                return {"product_id": line.split(" | ")[0], "reason": "model key"}
        return {"product_id": NONE, "reason": "no candidate"}


def embed(texts: list[str]) -> list[list[float]]:
    return [[b / 255 for b in hashlib.sha256(t.encode()).digest()[:8]] for t in texts]


def test_r_never_links_a_wrong_product_on_dev(tmp_path: Path) -> None:
    folder = g5.run("dev", "R", out=tmp_path)
    scores = json.loads((folder / "scores.json").read_text())
    assert scores["n"] == len(load("dev")) and scores["wrong_link"] == 0
    assert set(scores["by_kind"]) == {"product", "no_model", "driver", "unregistered"}
    meta = json.loads((folder / "run.json").read_text())
    assert meta["config"] == "R" and meta["files"] == g5.file_hashes()


def test_c_asks_with_candidates_only_and_scores_recall(tmp_path: Path) -> None:
    provider = ModelKeyProvider()
    folder = g5.run("dev", "C", provider, out=tmp_path)
    rows = json.loads((folder / "predictions.json").read_text())
    assert len(provider.calls) == len(rows)
    assert all("Solved rows" not in c["user"] for c in provider.calls)  # C has no examples
    enum = provider.calls[0]["schema"]["properties"]["product_id"]["enum"]
    assert len(enum) == 11 and enum[-1] == NONE
    assert json.loads((folder / "scores.json").read_text())["candidates_recall"] > 0.9


def test_e_shows_three_examples_never_of_the_rows_own_product(tmp_path: Path) -> None:
    provider = ModelKeyProvider()
    folder = g5.run("dev", "E", provider, embed, out=tmp_path)
    rows = {r["row_id"]: r for r in json.loads((folder / "predictions.json").read_text())}
    gold = {c.row_id: c.gold for c in load("dev")}
    for row in rows.values():
        assert len(row["examples"]) == 3 and row["row_id"] not in row["examples"]
        if row["gold"]:
            assert all(gold[e] != row["gold"] for e in row["examples"])
    assert "Solved rows" in provider.calls[0]["user"]


def test_an_answer_outside_the_candidates_is_none() -> None:
    class Wild:
        def complete_json(self, **_: Any) -> dict[str, Any]:
            return {"product_id": "REG-NOT-SHOWN", "reason": "x"}

    candidates = [{"product_id": "REG-A"}]
    assert llm_answer(Wild(), "row", candidates) == (None, "x")
    assert schema(candidates)["properties"]["product_id"]["enum"] == ["REG-A", NONE]


def test_examples_leave_out_the_given_product() -> None:
    cases = load("dev")
    examples = Examples(cases, {}, embed)
    target = cases[0]
    assert all(e.gold != target.gold for e in examples.top(target, {target.gold or ""}))
    assert all(e.row_id != target.row_id for e in examples.top(target, None))


def test_the_test_split_is_refused_without_a_matching_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the gate reads the real record through verify_freeze(); stand in a mismatch
    with monkeypatch.context() as patched:
        patched.setattr(g5, "verify_freeze", lambda: ["no freeze record"])
        with pytest.raises(SystemExit, match="refused"):
            g5.run("test", "R", out=tmp_path)
    g5.write_freeze("digest", tmp_path / "G5-FREEZE.json")
    with pytest.raises(SystemExit, match="written once"):
        g5.write_freeze("digest", tmp_path / "G5-FREEZE.json")
    assert g5.verify_freeze(tmp_path / "G5-FREEZE.json") == []
    record = json.loads((tmp_path / "G5-FREEZE.json").read_text())
    record["files"]["spec_bridge/bom/linker.py"] = "0" * 64
    (tmp_path / "G5-FREEZE.json").write_text(json.dumps(record))
    assert g5.verify_freeze(tmp_path / "G5-FREEZE.json") == ["spec_bridge/bom/linker.py"]


def _write(folder: Path, split: str, answers: list[str | None], golds: list[str | None]) -> Path:
    folder.mkdir()
    rows = [
        {"row_id": f"r{i}", "gold": g, "answer": a}
        for i, (a, g) in enumerate(zip(answers, golds, strict=True))
    ]
    (folder / "predictions.json").write_text(json.dumps(rows))
    (folder / "run.json").write_text(json.dumps({"split": split}))
    return folder


def test_the_judge_follows_the_preregistered_criteria(tmp_path: Path) -> None:
    golds: list[str | None] = ["P"] * 40 + [None] * 10
    perfect = list(golds)
    r: list[str | None] = [None] * 50  # R waits on every product row
    c = ["P"] * 20 + [None] * 20 + [None] * 10
    verdict = g5.compare(
        _write(tmp_path / "e", "test", perfect, golds),
        _write(tmp_path / "r", "test", r, golds),
        _write(tmp_path / "c", "test", c, golds),
    )
    assert verdict["verdict"] and verdict["b_wrong_links"]["E"] == 0
    risky = ["Q"] * 4 + ["P"] * 36 + [None] * 10  # 8% wrong links
    failed = g5.compare(
        _write(tmp_path / "e2", "test", risky, golds),
        _write(tmp_path / "r2", "test", r, golds),
        _write(tmp_path / "c2", "test", c, golds),
    )
    assert not failed["b_wrong_links"]["pass"] and not failed["verdict"]
    with pytest.raises(SystemExit, match="same split"):
        g5.compare(tmp_path / "e", tmp_path / "r", _write(tmp_path / "d", "dev", c, golds))


# D-110: code verifies the model's choice; examples never answer with a shown candidate --
def test_a_choice_without_the_model_code_or_of_another_class_becomes_none() -> None:
    from spec_bridge.bom.g5.resolve import verify
    from spec_bridge.ontology.loader import load_ontology
    from tests.conftest import ONTOLOGY

    onto = load_ontology(ONTOLOGY)
    case = next(c for c in load("dev") if c.kind == "product")
    other = next(c for c in load("dev") if c.kind == "product" and c.component != case.component)
    product = {
        "product_id": case.gold,
        "class_id": case.component,
        "model_designation": _model_of(case),
    }
    assert verify(onto, case, product) is None  # the model code is in the row, class fits
    assert verify(onto, case.model_copy(update={"model": "—"}), product) is not None
    wrong_class = case.model_copy(update={"component": other.component})
    assert verify(onto, wrong_class, product) is not None


def _model_of(case: Any) -> str:
    from spec_bridge.bom.g5.rows import registry_records

    return str(
        next(
            r["model_designation"] for r in registry_records("dev") if r["product_id"] == case.gold
        )
    )


def test_c_and_e_keep_the_model_answer_and_the_verified_answer(tmp_path: Path) -> None:
    class Closest:  # answers the first candidate, as the local model did on rows with no model
        def complete_json(
            self, *, user: str, schema: dict[str, Any] | None, **_: Any
        ) -> dict[str, Any]:
            assert schema is not None
            return {
                "product_id": schema["properties"]["product_id"]["enum"][0],
                "reason": "closest",
            }

    folder = g5.run("dev", "C", Closest(), out=tmp_path)
    rows = json.loads((folder / "predictions.json").read_text())
    none_rows = [r for r in rows if r["gold"] is None]
    assert all(r["model_answer"] is not None for r in none_rows)
    assert all(r["answer"] is None and r["rejected"] for r in none_rows)  # verification held
    assert (
        json.loads((folder / "scores.json").read_text())["by_kind"]["no_model"]["wrong_link"] == 0
    )


def test_examples_leave_out_every_shown_candidate() -> None:
    cases = load("dev")
    examples = Examples(cases, {}, embed)
    target = cases[0]
    shown = {c.gold for c in cases[:12] if c.gold}
    assert all(e.gold not in shown for e in examples.top(target, shown))


# D-111: the bundled runs reproduce their scores and the recorded judgment ---------------
BUNDLE = Path(__file__).resolve().parents[2] / "data/eval/g5-runs"


def test_bundled_runs_rescore_to_their_scores() -> None:
    folders = sorted(BUNDLE.iterdir())
    assert len(folders) == 6
    for folder in folders:
        rows = json.loads((folder / "predictions.json").read_text())
        assert g5.score(rows) == json.loads((folder / "scores.json").read_text()), folder.name


def test_the_bundled_test_runs_reproduce_the_judgment() -> None:
    run = {p.name.split("-")[1]: p for p in BUNDLE.glob("test-*")}
    verdict = g5.compare(run["E"], run["R"], run["C"])
    assert verdict["a_e_minus_r_accuracy"]["pass"] and verdict["b_wrong_links"]["pass"]
    assert not verdict["c_e_minus_c_accuracy"]["pass"] and verdict["verdict"] is False
    assert round(verdict["a_e_minus_r_accuracy"]["diff"], 4) == 0.3125
