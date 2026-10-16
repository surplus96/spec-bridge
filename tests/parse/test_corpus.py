"""W2 DoD: all 40 inputs parse with positions. Gold answers are not read here."""

from pathlib import Path

import pytest

from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.parse.run import run_split, split_inputs

ALL_INPUTS = [
    pytest.param(i, p, marks=pytest.mark.docling) if p.suffix == ".pdf" else (i, p)
    for split in ("dev", "test")
    for i, p in split_inputs(split)
]


def test_corpus_has_forty_inputs() -> None:
    assert len(ALL_INPUTS) == 40


@pytest.mark.parametrize("input_id, path", ALL_INPUTS)
def test_every_input_parses_with_positions(input_id: str, path: Path) -> None:
    document = parse_document(path, input_id)
    assert isinstance(document, ParsedDocument) and document.blocks
    kinds = {b.kind for b in document.blocks}
    assert "table_cell" in kinds or "paragraph" in kinds


@pytest.mark.docling
def test_run_split_writes_one_file_per_document(tmp_path: Path) -> None:
    summary = run_split("dev", tmp_path)
    assert summary["failures"] == [] and summary["parsed"] == len(split_inputs("dev"))
    assert len(list(tmp_path.glob("SYN-*.json"))) == summary["parsed"]
    reloaded = ParsedDocument.model_validate_json(next(tmp_path.glob("SYN-*.json")).read_text())
    assert reloaded.blocks
