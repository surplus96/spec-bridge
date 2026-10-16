"""Model input (W3-2, D-026): one numbered line per paragraph or table row.

The model only cites a line id; `locate()` finds the exact block inside that line,
so positions always come from the parser, never from the model.
"""

import re

from spec_bridge.parse.blocks import Block, ParsedDocument

PDF_ROW_TOLERANCE_PT = 3.0


def has_token(text: str, value: str) -> bool:
    """value occurs whole: not glued to letters/digits, and '6' is not inside '17220.6'."""
    if not value:
        return False
    for match in re.finditer(re.escape(value), text):
        before = text[match.start() - 1] if match.start() else ""
        after = text[match.end()] if match.end() < len(text) else ""
        decimal_after = after == "." and text[match.end() + 1 : match.end() + 2].isdigit()
        glued_before = value[0].isalnum() and (before.isalnum() or before == ".")
        glued_after = value[-1].isalnum() and (after.isalnum() or decimal_after)
        if not glued_before and not glued_after:
            return True
    return False


def _same_row(first: Block, block: Block) -> bool:
    a, b = first.location, block.location
    if a.table is not None:  # DOCX table
        return (a.table, a.row) == (b.table, b.row)
    if a.cell_ref is not None and b.cell_ref is not None:  # XLSX
        return (a.sheet, re.sub(r"\D", "", a.cell_ref)) == (b.sheet, re.sub(r"\D", "", b.cell_ref))
    if a.bbox is not None and b.bbox is not None:  # PDF: same page, similar vertical centre
        ya, yb = (a.bbox[1] + a.bbox[3]) / 2, (b.bbox[1] + b.bbox[3]) / 2
        return a.pdf_page == b.pdf_page and abs(ya - yb) <= PDF_ROW_TOLERANCE_PT
    return False


def group_lines(document: ParsedDocument) -> list[list[Block]]:
    """Blocks in document order, grouped into visual lines."""
    lines: list[list[Block]] = []
    for block in document.blocks:
        current = lines[-1] if lines else None
        if (
            block.kind == "table_cell"
            and current
            and current[0].kind == "table_cell"
            and _same_row(current[0], block)
        ):
            current.append(block)
        else:
            lines.append([block])
    return lines


def render_lines(document: ParsedDocument) -> tuple[str, list[list[Block]]]:
    lines = group_lines(document)
    text = "\n".join(
        f"[L{n}] " + " | ".join(" ".join(b.text.split()) for b in line)
        for n, line in enumerate(lines, start=1)
    )
    return text, lines


def locate(line: list[Block], value_text: str) -> Block | None:
    """The single block of a cited line that holds the value; None if absent or ambiguous."""
    hits = [block for block in line if has_token(block.text, value_text.strip())]
    return hits[0] if len(hits) == 1 else None
