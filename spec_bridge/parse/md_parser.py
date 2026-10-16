"""Markdown specifications (W6-2, D-080 decision 1-B): the handwritten evaluation inputs.

Same block model as the DOCX parser: every line is a paragraph numbered by its line in
the file; a numbered top-level heading ("2. Main Technical Data") opens a section; a pipe
table is a table whose header row is row 1 (the |---| rule is not a row) and whose cells
are numbered from column 1. Evaluation-only input: the upload API does not accept .md.
"""

import re
from pathlib import Path

from spec_bridge.ontology.facts import Location
from spec_bridge.parse.blocks import Block, BlockKind

HEADING = re.compile(r"^\d+\.\s+\S")  # "2. Main Technical Data", not "2.1 Driver: ..."
RULE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(path: Path, document_id: str) -> list[Block]:
    blocks: list[Block] = []
    section: str | None = None
    table_no = 0
    row_no = 0
    in_table = False
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text.startswith("|"):
            in_table = False
        if not text:
            continue
        if text.startswith("|"):
            if not in_table:
                in_table, table_no, row_no = True, table_no + 1, 0
            if RULE.match(text):
                continue
            row_no += 1
            for column_no, cell in enumerate(_cells(text), start=1):
                if not cell or cell in ("–", "-", "—"):
                    continue
                location = Location(
                    table=table_no, row=row_no, column=column_no, line=line_no, section=section
                )
                blocks.append(
                    Block(kind="table_cell", text=cell, section=section, location=location)
                )
            continue
        kind: BlockKind = "paragraph"
        if not blocks:
            kind = "title"
        elif HEADING.match(text):
            kind, section = "heading", text
        location = Location(paragraph=line_no, line=line_no, section=section)
        blocks.append(Block(kind=kind, text=text, section=section, location=location))
    return blocks
