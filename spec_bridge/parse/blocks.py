"""Parser output (W2): source text blocks with their original positions."""

from typing import Literal

from pydantic import Field

from spec_bridge.ontology.facts import Location, StrictModel, Text

BlockKind = Literal["title", "heading", "paragraph", "table_cell"]
FileFormat = Literal["pdf", "xlsx", "docx", "md"]


class Block(StrictModel):
    kind: BlockKind
    text: Text  # original characters, never normalized (W3 normalizes)
    section: str | None = None
    location: Location
    cell_type: str | None = None  # XLSX only: openpyxl data type (s, n, b, d)
    number_format: str | None = None  # XLSX only: display format, e.g. "0.0%" (W3 renders)


class ParsedDocument(StrictModel):
    document_id: Text
    file_format: FileFormat
    sha256: Text
    parser: Text  # library name and version
    blocks: list[Block] = Field(min_length=1)


class ParseError(Exception):
    """A document could not be parsed; reported as unknown, never a crash."""

    def __init__(self, document_id: str, reason: str) -> None:
        super().__init__(f"{document_id}: {reason}")
        self.document_id = document_id
        self.reason = reason
