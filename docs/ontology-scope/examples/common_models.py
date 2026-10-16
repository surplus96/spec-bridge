"""W1-COMMON-MODEL: executable reference models, not a domain ontology.

Read from Location to Fact. Class policies and unit semantics belong to the
future ontology loader; these models only validate the common data structure.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Index = Annotated[int, Field(ge=1)]
Text = Annotated[str, Field(min_length=1)]


class StructuralModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Location(StructuralModel):
    """First reference supports numbered PDF pages and section/table positions."""

    section: Text | None = None
    table: Index | None = None
    row: Index | None = None
    paragraph: Index | None = None
    line: Index | None = None
    pdf_page: Index | None = None
    printed_page: Text | None = None

    @model_validator(mode="after")
    def validate_position(self) -> Self:
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one source position is required")
        if self.row is not None and self.table is None:
            raise ValueError("A table row must identify its table")
        return self


class Occurrence(StructuralModel):
    source_document_id: Text
    raw_text: Text
    label_text: str | None = None
    unit_text: str | None = None
    location: Location


class Quantity(StructuralModel):
    value: float
    unit: Text


class ReferenceQuantity(Quantity):
    reference_temperature: Quantity | None = None


class Conditions(StructuralModel):
    """Closed field names; domain token values are not yet ontology-validated."""

    medium: Text | None = None
    viscosity: ReferenceQuantity | None = None
    viscosity_basis: Literal["fuel_reference", "unknown", "not_applicable"] = "unknown"
    temperature: Quantity | None = None
    absolute_pressure: Quantity | None = None
    frequency: Quantity | None = None
    rating_point: Text | None = None
    engine_type: Text | None = None
    basis: Text | None = None


class Basis(StructuralModel):
    capacity: Text = "unknown"
    rating: Text = "unknown"
    pressure: Literal["gauge", "absolute", "unknown", "not_applicable"] = "unknown"
    weight: Text = "unknown"


class NumericRange(StructuralModel):
    min: float
    max: float

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.min > self.max:
            raise ValueError("Range minimum must not exceed maximum")
        return self


class Dimensions(StructuralModel):
    length: float | None = None
    width: float | None = None
    height: float | None = None

    @model_validator(mode="after")
    def validate_known_axis(self) -> Self:
        if all(value is None for value in (self.length, self.width, self.height)):
            raise ValueError("At least one dimension must be known")
        return self


Value = bool | int | float | str | list[str] | NumericRange | Dimensions


class Fact(StructuralModel):
    """One value/context, with one or more independently located occurrences."""

    value: Value
    unit: Text | None
    basis: Basis = Field(default_factory=Basis)
    condition: Conditions = Field(default_factory=Conditions)
    scope: Text = "unknown"
    occurrences: Annotated[list[Occurrence], Field(min_length=1)]
