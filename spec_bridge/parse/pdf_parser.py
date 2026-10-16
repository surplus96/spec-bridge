"""PDF parser: Docling for layout, table structure and positions; the PDF text layer
for characters (D-024 — Docling's own text replaces e.g. '—' with '-')."""

import os
from functools import cache
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"  # NFR-01: never fetch models at parse time (forced)

import pypdfium2 as pdfium  # noqa: E402
from docling.datamodel.base_models import ConversionStatus, InputFormat  # noqa: E402
from docling.datamodel.pipeline_options import PdfPipelineOptions  # noqa: E402
from docling.document_converter import DocumentConverter, PdfFormatOption  # noqa: E402
from docling_core.types.doc import (  # noqa: E402
    BoundingBox,
    DocItem,
    SectionHeaderItem,
    TableItem,
    TitleItem,
)

from spec_bridge.ontology.facts import Location  # noqa: E402
from spec_bridge.parse.blocks import Block, BlockKind, ParseError  # noqa: E402
from spec_bridge.parse.settings import DOCLING_MODELS as MODELS  # noqa: E402
from spec_bridge.parse.settings import PDF_OPTIONS  # noqa: E402


@cache
def converter() -> DocumentConverter:
    options = PdfPipelineOptions(
        artifacts_path=MODELS,
        do_ocr=PDF_OPTIONS["do_ocr"],
        do_table_structure=PDF_OPTIONS["do_table_structure"],
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def parse(path: Path, document_id: str) -> list[Block]:
    if not MODELS.is_dir():
        raise ParseError(
            document_id,
            "Docling models missing: uv run docling-tools models download"
            " layout tableformer -o var/models/docling",
        )
    result = converter().convert(path)
    if result.status != ConversionStatus.SUCCESS:  # CP-S2 R3: partial is not complete
        details = "; ".join(str(e.error_message) for e in result.errors) or "no details"
        raise ParseError(document_id, f"Docling conversion {result.status.value}: {details}")
    document = result.document
    pdf = pdfium.PdfDocument(str(path))
    try:
        blocks: list[Block] = []
        section: str | None = None
        title_seen = False
        for item, _level in document.iterate_items():
            if not isinstance(item, DocItem):
                continue
            for prov in item.prov:
                page = pdf[prov.page_no - 1]
                height = page.get_height()
                textpage = page.get_textpage()
                if isinstance(item, TableItem):
                    for cell in item.data.table_cells:
                        if cell.bbox is None:
                            continue
                        box = _bottom_left(cell.bbox, height)
                        text = _read(textpage, box)
                        if text.strip():
                            location = Location(pdf_page=prov.page_no, bbox=box, section=section)
                            blocks.append(
                                Block(
                                    kind="table_cell", text=text, section=section, location=location
                                )
                            )
                    continue
                box = _bottom_left(prov.bbox, height)
                text = _read(textpage, box)
                if not text.strip():
                    continue
                kind: BlockKind = "paragraph"
                if isinstance(item, TitleItem) or (
                    isinstance(item, SectionHeaderItem) and not title_seen
                ):
                    kind, title_seen = "title", True
                elif isinstance(item, SectionHeaderItem):
                    kind, section = "heading", text
                location = Location(pdf_page=prov.page_no, bbox=box, section=section)
                blocks.append(Block(kind=kind, text=text, section=section, location=location))
        return blocks
    finally:
        pdf.close()


def _bottom_left(bbox: BoundingBox, page_height: float) -> list[float]:
    """[x0, y0, x1, y1] in PDF points with a bottom-left origin, like the gold boxes."""
    box = bbox.to_bottom_left_origin(page_height)
    return [box.l, box.b, box.r, box.t]


def _read(textpage: pdfium.PdfTextPage, box: list[float]) -> str:
    left, bottom, right, top = box
    return str(textpage.get_text_bounded(left=left, bottom=bottom, right=right, top=top))
