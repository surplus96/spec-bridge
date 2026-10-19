"""G5 follow-up rows (D-109): synthetic BOM rows from the signed notation patterns only."""

import json

import pytest

from spec_bridge.bom.g5.rows import (
    NONE_ROWS,
    PATTERNS_BY_SOURCE_SPLIT,
    RowCase,
    allowed_patterns,
    generate,
    registry_records,
)
from spec_bridge.bom.linker import _spans, search_key
from tests.conftest import ROOT


@pytest.fixture(scope="module")
def rows() -> dict[str, list[RowCase]]:
    return {split: generate(split) for split in ("dev", "test")}


def test_generation_is_deterministic(rows: dict[str, list[RowCase]]) -> None:
    assert generate("dev") == rows["dev"]


def test_sizes_follow_the_preregistration(rows: dict[str, list[RowCase]]) -> None:
    for split, cases in rows.items():
        products = len(registry_records(split))
        assert sum(c.gold is not None for c in cases) == products
        assert sum(c.gold is None for c in cases) == NONE_ROWS[split]


def test_each_split_uses_only_patterns_seen_in_its_sources(
    rows: dict[str, list[RowCase]],
) -> None:
    for split, cases in rows.items():
        used = {p for c in cases for p in c.patterns}
        assert used <= allowed_patterns(split)
    dev = {p for c in rows["dev"] for p in c.patterns}
    test = {p for c in rows["test"] for p in c.patterns}
    assert {"PAT-09", "PAT-10"} <= test and not {"PAT-09", "PAT-10"} & dev
    assert {"PAT-03", "PAT-06"} <= dev and not {"PAT-03", "PAT-06"} & test
    assert set(PATTERNS_BY_SOURCE_SPLIT) == {"dev", "test"}


def test_gold_is_consistent_with_the_row_text(rows: dict[str, list[RowCase]]) -> None:
    for split, cases in rows.items():
        models = {
            r["product_id"]: search_key(r["model_designation"]) for r in registry_records(split)
        }
        for case in cases:
            spans = _spans(case.model)
            if case.kind == "product":
                assert case.gold is not None and models[case.gold] in spans, case
            elif case.kind in ("no_model", "unregistered"):
                assert not set(models.values()) & spans, case


def test_rows_name_only_synthetic_makers(rows: dict[str, list[RowCase]]) -> None:
    for cases in rows.values():
        assert all(c.maker.casefold().startswith("sgdw") for c in cases)


def test_the_written_files_match_a_fresh_generation() -> None:
    for split in ("dev", "test"):
        data = json.loads((ROOT / f"data/synth/bom-rows/{split}.json").read_text())
        assert data["origin"] == "synthetic"
        assert [RowCase.model_validate(r) for r in data["rows"]] == generate(split)
