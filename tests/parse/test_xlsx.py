from pathlib import Path
from typing import Any

import pytest

from spec_bridge.parse.dispatch import parse_document
from tests.parse.goldmatch import dev_documents, recall

DEV_XLSX = dev_documents("xlsx")


@pytest.mark.parametrize("input_id, path, answer", DEV_XLSX)
def test_every_gold_observation_is_located(input_id: str, path: Path, answer: Any) -> None:
    found, total, missing = recall(parse_document(path, input_id), answer)
    assert found == total, missing


def test_empty_cells_make_no_blocks() -> None:
    input_id, path, _ = DEV_XLSX[0]
    assert all(b.text.strip() for b in parse_document(path, input_id).blocks)


def test_headings_and_dash_cells_are_kept() -> None:
    input_id, path, _ = DEV_XLSX[0]
    blocks = parse_document(path, input_id).blocks
    assert {"title", "heading", "table_cell", "paragraph"} <= {b.kind for b in blocks}
    assert any(b.text == "—" for b in blocks)  # a dash cell is content, not empty


def test_blocks_after_a_heading_carry_its_section() -> None:
    input_id, path, _ = DEV_XLSX[0]
    blocks = parse_document(path, input_id).blocks
    first_heading = next(i for i, b in enumerate(blocks) if b.kind == "heading")
    after = blocks[first_heading + 1]
    assert after.section == blocks[first_heading].text
    assert after.location.section == after.section
