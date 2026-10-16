"""W6-2: the Markdown reader for the handwritten evaluation inputs."""

from pathlib import Path

import pytest

from spec_bridge.parse.blocks import ParseError
from spec_bridge.parse.dispatch import parse_document
from tests.conftest import ROOT

INPUTS = sorted((ROOT / "data/eval/handwritten/inputs").glob("DOC-*.md"))

SAMPLE = """TECHNICAL SPECIFICATION
Issued by: Example Works

1. General
1.1 Maker: Example Works

2. Main Technical Data
| Item | Value | Unit | Remark |
|---|---|---|---|
| Bore | 650 | mm | |
| Stroke | 2,750 | – | |

3. Notes
Free text line.
"""


def test_lines_tables_and_sections(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text(SAMPLE)
    document = parse_document(path, "X")
    assert document.file_format == "md" and document.parser.startswith("spec-bridge")
    title, issued = document.blocks[0], document.blocks[1]
    assert title.kind == "title" and issued.location.paragraph == 2
    maker = next(b for b in document.blocks if b.text.startswith("1.1"))
    assert maker.section == "1. General" and maker.location.paragraph == 5
    bore = next(b for b in document.blocks if b.text == "650")
    assert (bore.location.table, bore.location.row, bore.location.column) == (1, 2, 2)
    assert bore.section == "2. Main Technical Data" and bore.location.line == 10
    assert not any(b.text in ("–", "---") for b in document.blocks)  # dashes are empty cells
    note = next(b for b in document.blocks if b.text == "Free text line.")
    assert note.section == "3. Notes"


@pytest.mark.parametrize("path", INPUTS, ids=lambda p: p.stem)
def test_every_handwritten_input_parses(path: Path) -> None:
    document = parse_document(path, path.stem)
    assert any(b.kind == "table_cell" for b in document.blocks)
    assert any(b.kind == "heading" for b in document.blocks)


def test_a_binary_file_named_md_is_a_parse_error(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ParseError, match="not a valid md"):
        parse_document(path, "X")
