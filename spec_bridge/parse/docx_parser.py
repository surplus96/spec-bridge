"""Word parser (python-docx): body paragraphs and table cells in document order."""

from pathlib import Path

from docx import Document
from docx.shared import Pt
from docx.table import Table
from docx.text.paragraph import Paragraph

from spec_bridge.ontology.facts import Location
from spec_bridge.parse.blocks import Block, BlockKind, ParseError

TITLE_SIZE = Pt(16)


def parse(path: Path, document_id: str) -> list[Block]:
    document = Document(str(path))
    body = document.element.body
    if body.xpath(".//w:ins | .//w:del"):
        # python-docx skips text inside revision marks; never drop it silently.
        raise ParseError(document_id, "tracked changes are not supported; accept or reject them")
    if body.xpath(".//w:tc//w:tbl"):
        # CP-S2 R6: Location has no path for a table inside a table cell.
        raise ParseError(document_id, "nested table is not supported; flatten the table")
    blocks: list[Block] = []
    section: str | None = None
    paragraph_no = table_no = 0
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            paragraph_no += 1
            if not item.text.strip():
                continue
            kind = _paragraph_kind(item)
            if kind == "heading":
                section = item.text
            location = Location(paragraph=paragraph_no, section=section)
            blocks.append(Block(kind=kind, text=item.text, section=section, location=location))
        elif isinstance(item, Table):
            table_no += 1
            blocks += _table_blocks(item, table_no, section)
    return blocks


def _paragraph_kind(paragraph: Paragraph) -> BlockKind:
    runs = [r for r in paragraph.runs if r.text.strip()]
    if not runs or not all(r.bold for r in runs):
        return "paragraph"
    size = runs[0].font.size
    return "title" if size is not None and size >= TITLE_SIZE else "heading"


def _table_blocks(table: Table, table_no: int, section: str | None) -> list[Block]:
    blocks = []
    seen: set[object] = set()  # merged cells repeat the same <w:tc>; emit it once.
    # Keep the elements themselves: lxml proxies are recreated on access, so id() values
    # of discarded proxies can be reused by other cells.
    for row_no, row in enumerate(table.rows, start=1):
        for column_no, cell in enumerate(row.cells, start=1):
            if cell._tc in seen or not cell.text.strip():
                continue
            seen.add(cell._tc)
            location = Location(table=table_no, row=row_no, column=column_no, section=section)
            blocks.append(
                Block(kind="table_cell", text=cell.text, section=section, location=location)
            )
    return blocks
