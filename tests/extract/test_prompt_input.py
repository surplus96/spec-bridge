from pathlib import Path
from typing import Any

import pytest

from spec_bridge.eval.locations import same_place
from spec_bridge.extract.prompt_input import has_token, locate, render_lines
from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from tests.parse.goldmatch import dev_documents

DEV = [
    pytest.param(*row, marks=pytest.mark.docling) if row[1].suffix == ".pdf" else row
    for fmt in ("xlsx", "docx", "pdf")
    for row in dev_documents(fmt)
]
_cache: dict[str, ParsedDocument] = {}


def parsed(input_id: str, path: Path) -> ParsedDocument:
    if input_id not in _cache:
        _cache[input_id] = parse_document(path, input_id)
    return _cache[input_id]


@pytest.mark.parametrize("input_id, path, answer", DEV)
def test_cited_line_recovers_every_gold_block(input_id: str, path: Path, answer: Any) -> None:
    """If the model cites the right line, code finds the exact gold cell (D-026)."""
    _, lines = render_lines(parsed(input_id, path))
    lost = []
    for obs in answer["observations"]:
        line = next((ln for ln in lines if any(same_place(obs["location"], b) for b in ln)), None)
        found = locate(line, obs["raw_text"]) if line else None
        if found is None or not same_place(obs["location"], found):
            lost.append(obs["observation_id"])
    assert lost == []


@pytest.mark.parametrize("input_id, path, answer", DEV)
def test_every_block_is_on_exactly_one_line(input_id: str, path: Path, answer: Any) -> None:
    document = parsed(input_id, path)
    _, lines = render_lines(document)
    assert [b for line in lines for b in line] == document.blocks


@pytest.mark.parametrize("input_id, path, answer", DEV)
def test_rendering_is_deterministic_and_clean(input_id: str, path: Path, answer: Any) -> None:
    text, lines = render_lines(parsed(input_id, path))
    assert text == render_lines(parsed(input_id, path))[0]
    assert len(text.splitlines()) == len(lines)
    assert input_id not in text and "answer" not in text.lower()  # no evaluator data


def test_table_rows_become_one_line() -> None:
    input_id, path, _ = dev_documents("docx")[0]
    _, lines = render_lines(parsed(input_id, path))
    assert any(len(line) >= 3 and line[0].kind == "table_cell" for line in lines)


@pytest.mark.parametrize(
    "text, value, expected",
    [
        ("6 ", "6", True),
        ("17220.6", "6", False),
        ("16", "6", False),
        ("1400 × 795 × 1005 mm", "1400 × 795 × 1005", True),
        ("VX002 009", "VX002 009", True),
        ("Model — VX002-0091", "VX002-009", False),
        ("abc", "", False),
    ],
)
def test_has_token(text: str, value: str, expected: bool) -> None:
    assert has_token(text, value) is expected
