from functools import cache
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from tests.parse.goldmatch import dev_documents, recall

DEV_PDF = dev_documents("pdf")
pytestmark = pytest.mark.docling


@cache
def parsed(input_id: str, path: Path) -> ParsedDocument:
    return parse_document(path, input_id)  # Docling is slow: parse each file once


@pytest.mark.parametrize("input_id, path, answer", DEV_PDF)
def test_every_gold_observation_is_located(input_id: str, path: Path, answer: Any) -> None:
    found, total, missing = recall(parsed(input_id, path), answer)
    assert found == total, missing


def test_original_dash_is_preserved() -> None:
    input_id, path, _ = DEV_PDF[0]
    blocks = parsed(input_id, path).blocks
    maker = next(b for b in blocks if b.text.startswith(("Maker", "Manufacturer")))
    assert "\u2014" in maker.text  # Docling's own text would show '-'


def test_boxes_use_bottom_left_origin() -> None:
    input_id, path, _ = DEV_PDF[0]
    blocks = parsed(input_id, path).blocks
    first = next(b for b in blocks if b.text.startswith("Technical specification"))
    assert first.location.bbox is not None
    assert all(first.location.bbox[1] >= b.location.bbox[1] for b in blocks if b.location.bbox)


def test_table_cells_are_inside_the_page() -> None:
    input_id, path, _ = DEV_PDF[0]
    cells = [b for b in parsed(input_id, path).blocks if b.kind == "table_cell"]
    boxes = [b.location.bbox for b in cells if b.location.bbox is not None]
    assert cells and len(boxes) == len(cells)
    assert all(0 <= y0 < y1 <= 600 for _x0, y0, _x1, y1 in boxes)  # A4 landscape height
