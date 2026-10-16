"""Common fact structure (W1-3). Ported from docs/ontology-scope/examples."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Index = Annotated[int, Field(ge=1)]
Text = Annotated[str, Field(min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Location(StrictModel):
    """Where a value was read: PDF page/box, sheet cell, or DOCX paragraph/table cell."""

    section: Text | None = None
    pdf_page: Index | None = None
    bbox: Annotated[list[float], Field(min_length=4, max_length=4)] | None = None
    sheet: Text | None = None
    cell_ref: Text | None = None
    paragraph: Index | None = None
    table: Index | None = None
    row: Index | None = None
    column: Index | None = None
    line: Index | None = None

    @model_validator(mode="after")
    def validate_position(self) -> Self:
        anchors = (self.pdf_page, self.cell_ref, self.paragraph, self.table, self.line)
        if all(anchor is None for anchor in anchors):
            raise ValueError("A page, cell, paragraph, table or line position is required")
        if self.row is not None and self.table is None:
            raise ValueError("A table row must identify its table")
        return self


class Occurrence(StrictModel):
    source_document_id: Text
    raw_text: Text
    label_text: str | None = None
    unit_text: str | None = None
    location: Location


class Quantity(StrictModel):
    value: float
    unit: Text


class ReferenceQuantity(Quantity):
    reference_temperature: Quantity | None = None


class NumericRange(StrictModel):
    min: float
    max: float

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.min > self.max:
            raise ValueError("Range minimum must not exceed maximum")
        return self


class Dimensions(StrictModel):
    length: float | None = None
    width: float | None = None
    height: float | None = None

    @model_validator(mode="after")
    def validate_known_axis(self) -> Self:
        if all(axis is None for axis in (self.length, self.width, self.height)):
            raise ValueError("At least one dimension must be known")
        return self
