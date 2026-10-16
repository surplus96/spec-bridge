"""W4-R R6: configuration E runs end to end — values from mode C, context from the chain."""

import json
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.eval.experiment import run_experiment
from spec_bridge.normalize.dictionary import load_dictionary
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.rag.pipeline import RagSetup
from spec_bridge.rag.qualifiers import build_chain
from spec_bridge.service import normalizer_for
from tests.conftest import ONTOLOGY
from tests.eval.test_experiment import FAST, classify_reply, write_parsed
from tests.extract.test_extractor import line_of
from tests.llm.fakes import FakeProvider


def scoped_fact(answer: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """A gold fact with a stated scope, and its observation."""
    fact = next(f for f in answer["facts"] if f["scope"] != "main_equipment")
    obs = next(o for o in answer["observations"] if o["observation_id"] in fact["observation_ids"])
    return fact, obs


def chain_for(provider: FakeProvider) -> RagSetup:
    onto = load_ontology(ONTOLOGY)
    chain = build_chain(onto, normalizer_for(onto, "dev", load_dictionary()), provider, [], None)
    return RagSetup(chain=chain, info={"mode": "e0"})


def test_config_e_qualifies_each_value(tmp_path: Path) -> None:
    doc_id = next(
        i for i in FAST if any(f["scope"] != "main_equipment" for f in FAST[i][1]["facts"])
    )
    path, answer = FAST[doc_id]
    fact, obs = scoped_fact(answer)
    phrase = fact["scope"].replace("_", " ")
    item = {
        "attribute": fact["attribute_id"],
        "value_text": obs["raw_text"],
        "unit_text": obs["unit_text"],
        "line": line_of(parse_document(path, doc_id), obs),
    }
    provider = FakeProvider(
        [
            classify_reply(doc_id),
            {"facts": [item]},  # mode-C extraction, no context
            {"scope": {"value": phrase, "evidence": phrase}},  # the qualifier chain
        ]
    )
    parsed = write_parsed(tmp_path / "parsed", [doc_id])
    run = run_experiment("E", "dev", provider, tmp_path / "run", parsed, rag=chain_for(provider))
    saved = json.loads((tmp_path / f"run/predictions/{doc_id}.json").read_text())
    assert saved["qualifiers"][0]["qualifiers"]["scope"] == phrase
    assert [f["scope"] for f in saved["prediction"]["facts"]] == [fact["scope"]]
    assert run["extraction"] == {"context": "optional"}
    assert run["rag"]["qualifiers"] == {"values": 1, "fields_kept": 1, "fields_rejected": {}}
    assert provider.replies == []


def test_config_e_needs_a_chain(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RAG setup"):
        run_experiment("E", "dev", FakeProvider([]), tmp_path / "run", tmp_path)


def conflict_setup(kb: list[Any]) -> RagSetup:
    from spec_bridge.rag.retrieval import KbBM25Retriever

    by_id = {e.example_id: e for e in kb}
    return RagSetup(chain=None, retriever=KbBM25Retriever(kb), kb=by_id, k=3)  # type: ignore[arg-type]


def kb_case(i: str, family: str, attribute: str, text: str) -> Any:
    from spec_bridge.rag.knowledge import KbExample, Qualifiers

    return KbExample(
        example_id=i,
        doc_id=i.split(":")[0],
        family_id=family,
        split="dev",
        attribute=attribute,
        label_text=None,
        line_text=text,
        parent_text=f"Line: {text}",
        qualifiers=Qualifiers(),
        evidence={},
    )


def competing(line: str) -> tuple[list[Any], list[Any]]:
    from spec_bridge.extract.extractor import RawObservation
    from spec_bridge.rag.qualifiers import QualifierItem

    raws, items = [], []
    for attribute in ("dry_weight", "reported_weight"):
        raws.append(
            RawObservation(
                attribute=attribute,
                value_text="31755.2",
                unit_text="kg",
                basis={},
                condition={},
                scope="main_equipment",
                occurrence={"location": {"table": 1, "row": 9, "column": 2}},
            )
        )
        items.append(
            QualifierItem(
                attribute=attribute,
                value_text="31755.2",
                unit_text="kg",
                line_text=line,
                parent_text=f"Line: {line}",
                family_id="FAM-SELF",
            )
        )
    return raws, items


FILLER = [
    kb_case("F:1", "FAM-F1", "bore", "Bore | 240 | mm | —"),
    kb_case("F:2", "FAM-F2", "stroke", "Stroke | 310 | mm | —"),
    kb_case("F:3", "FAM-F3", "rated_speed", "Rated speed | 720 | rpm | at R1"),
]


def test_retrieved_cases_settle_an_attribute_conflict() -> None:
    from spec_bridge.rag.pipeline import resolve_conflicts

    line = "Dry weight | 31755.2 | kg | dry; for engine without generator"
    kb = [
        kb_case("A:1", "FAM-A", "dry_weight", "Dry weight | 5583.15 | kg | dry; for unit"),
        kb_case("B:1", "FAM-B", "dry_weight", "Dry weight | 350.79 | kg | dry condition"),
        kb_case("S:1", "FAM-SELF", "reported_weight", line),  # own family: never votes
        *FILLER,
    ]
    raws, items = competing(line)
    keep, records = resolve_conflicts(conflict_setup(kb), raws, items)
    assert [raws[i].attribute for i in keep] == ["dry_weight"]
    assert records[0]["kept"] == "dry_weight" and "reported_weight" not in records[0]["votes"]


def test_a_tie_or_no_vote_drops_both() -> None:
    from spec_bridge.rag.pipeline import resolve_conflicts

    line = "Weight | 12 | kg | —"
    raws, items = competing(line)
    keep, records = resolve_conflicts(conflict_setup(FILLER), raws, items)
    assert keep == [] and records[0]["kept"] is None


def test_without_a_resolver_nothing_changes() -> None:
    from spec_bridge.rag.pipeline import resolve_conflicts

    raws, items = competing("Dry weight | 1 | kg | dry")
    setup = RagSetup(chain=None)  # type: ignore[arg-type]
    assert resolve_conflicts(setup, raws, items) == ([0, 1], [])
