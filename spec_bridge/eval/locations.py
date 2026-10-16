"""Gold location matching (moved from tests/parse/goldmatch.py for the W3-6 evaluator)."""

from typing import Any

from spec_bridge.extract.prompt_input import has_token
from spec_bridge.ontology.facts import Location
from spec_bridge.parse.blocks import Block

PDF_TOLERANCE_PT = 2.0


def same_place(gold: dict[str, Any], place: Block | Location) -> bool:
    loc = place.location if isinstance(place, Block) else place
    if gold.get("pdf_page") is not None:
        # PDF: gold boxes are layout areas (whole cell / paragraph frame) while parser
        # boxes are tight text boxes, so the block's centre must lie in the gold area.
        if loc.bbox is None or loc.pdf_page != gold["pdf_page"]:
            return False
        gx0, gy0, gx1, gy1 = gold["bbox"]
        bx0, by0, bx1, by1 = loc.bbox
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        tol = PDF_TOLERANCE_PT
        return bool(gx0 - tol <= cx <= gx1 + tol and gy0 - tol <= cy <= gy1 + tol)
    if gold.get("sheet") is not None:  # XLSX
        return bool(loc.sheet == gold["sheet"] and loc.cell_ref == gold["value_cell"])
    if gold.get("table") is not None:  # DOCX table cell
        return bool((loc.table, loc.row, loc.column) == (gold["table"], gold["row"], gold["cell"]))
    return bool(loc.paragraph is not None and loc.paragraph == gold.get("paragraph"))  # DOCX


def contains_token(text: str, raw: str) -> bool:
    """raw occurs in text as a whole token: '6' is not in '16' nor in '17220.6' (W3-6)."""
    return has_token(text, raw)
