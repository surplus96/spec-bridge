"""W6-2 (D-080 decision 1-B): the converted handwritten answers keep every v2 scoring unit
and every occurrence, and each occurrence is a real place in the parsed document."""

import json

import pytest
import yaml

from spec_bridge.eval import handwritten
from spec_bridge.eval.locations import same_place
from spec_bridge.eval.scoring import Prediction, score_split
from spec_bridge.parse.dispatch import parse_document
from tests.conftest import ROOT

ANSWERS = handwritten.answers()


def test_the_56_v2_scoring_units_are_the_facts() -> None:
    """SCORING-POLICY v2: 55 attributes + the second SEP condition = 56 units."""
    assert sum(len(a["facts"]) for a in ANSWERS) == 56
    assert all(a["issues"] == [] and a["status"].startswith("converted") for a in ANSWERS)


@pytest.mark.parametrize("answer", ANSWERS, ids=lambda a: a["input_id"])
def test_every_v2_occurrence_is_a_place_in_the_document(answer: dict) -> None:  # type: ignore[type-arg]
    v2 = yaml.safe_load((ROOT / answer["conversion"]["source"]).read_text())
    expected = sum(
        len(b["occurrences"])
        + sum(len(x["occurrences"]) for x in b.get("conditional_values") or [])
        for b in v2["attributes"].values()
    )
    assert len(answer["observations"]) == expected
    entry = next(e for e in handwritten.manifest() if e["input_id"] == answer["input_id"])
    document = parse_document(ROOT / entry["input_text"], answer["input_id"])
    for obs in answer["observations"]:
        places = [b for b in document.blocks if same_place(obs["location"], b)]
        assert len(places) == 1, obs
        assert obs["raw_text"].casefold() in " ".join(places[0].text.split()).casefold()


def test_the_gold_as_a_prediction_scores_one() -> None:
    """The converted facts are consistent with the scorer (keys, values, contexts)."""
    predictions = {
        a["input_id"]: Prediction(
            document_id=a["input_id"],
            class_id=a["expected_class"],
            facts=[
                {"attribute": f["attribute_id"]}
                | {k: f[k] for k in ("value", "unit", "basis", "condition", "scope")}
                for f in a["facts"]
            ],
        )
        for a in ANSWERS
    }
    _, metrics = score_split(ANSWERS, predictions)
    assert metrics.facts_micro.f1 == 1.0 and metrics.class_top1 == 1.0


def test_the_build_is_reproducible(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Rebuilding gives the committed answers byte for byte (they are frozen, D-080)."""
    before = {p.name: p.read_text() for p in handwritten.CONVERTED.glob("*.yaml")}
    handwritten.build()
    after = {p.name: p.read_text() for p in handwritten.CONVERTED.glob("*.yaml")}
    assert after == before
    summary = json.loads((handwritten.PARSED / "_summary.json").read_text())
    assert summary["parsed"] == 6 and summary["failures"] == []


def test_a_scope_phrase_must_be_in_its_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(handwritten.SCOPE_PHRASES, ("HW-TC-001", "dimensions"), "not in the text")
    with pytest.raises(handwritten.ConversionError, match="scope phrase"):
        handwritten.build()
