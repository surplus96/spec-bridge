"""Shape of ontology/ontology.yaml. Cross-references are checked in loader.py."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Datatype = Literal["string", "number", "integer", "boolean", "string_set", "range", "dimensions"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UnitDef(Strict):
    pint: str


class AttributeDef(Strict):
    datatype: Datatype | list[Datatype]
    dimension: str
    canonical_unit: str | None


class ConditionalRule(Strict):
    when: dict[str, str]
    required_all: list[str] = Field(default_factory=list)
    required_any_groups: list[list[str]] = Field(default_factory=list)


class ClassDef(Strict):
    abstract: bool
    parent: str | None
    label: str | None = None
    keywords: list[str] = Field(default_factory=list)
    attributes: list[str]
    required_all: list[str] = Field(default_factory=list)
    required_any_groups: list[list[str]] = Field(default_factory=list)
    conditional_required: list[ConditionalRule] = Field(default_factory=list)
    allowed_values: dict[str, list[str]] = Field(default_factory=dict)


class LabelAlias(Strict):
    """Label notation for an attribute.

    sourced: observed in a reference document; needs source/location, and the user's
    verified_by before it counts as a verified fact (H3).
    synthetic: project choice; source/location may record where it was observed.
    """

    label: str
    attribute: str
    origin: Literal["sourced", "synthetic"] = "sourced"
    source: str | None = None
    location: dict[str, int | str] | None = None
    verified_by: str | None = None  # 사용자만 채운다


class ConditionDef(Strict):
    kind: Literal["token", "quantity", "reference_quantity"]
    values: list[str] = Field(default_factory=list)
    dimension: str | None = None


class VocabularyDescriptions(Strict):
    """Plain meanings of context tokens for the extraction prompt (W4-1, D-039).

    Project wording from the token names only, never from development documents. "_" is
    the axis itself; a token without an entry is unverified (H3) and left undescribed.
    """

    origin: Literal["synthetic"]
    verified_by: str | None = None  # 사용자만 채운다
    basis: dict[str, dict[str, str]] = Field(default_factory=dict)
    condition: dict[str, dict[str, str]] = Field(default_factory=dict)
    scope: dict[Literal["optional", "required_none"], str] = Field(default_factory=dict)


class Vocabularies(Strict):
    basis: dict[str, list[str]]
    condition: dict[str, ConditionDef]
    descriptions: VocabularyDescriptions | None = None


class Ontology(Strict):
    version: int
    origin: str
    dimensions: dict[str, str]
    units: dict[str, UnitDef]
    attributes: dict[str, AttributeDef]
    classes: dict[str, ClassDef]
    label_aliases: list[LabelAlias] = Field(default_factory=list)
    vocabularies: Vocabularies

    def ancestors(self, class_id: str) -> list[str]:
        result: list[str] = []
        parent = self.classes[class_id].parent
        while parent is not None:
            result.append(parent)
            parent = self.classes[parent].parent
        return result

    def attributes_of(self, class_id: str) -> list[str]:
        chain = [*reversed(self.ancestors(class_id)), class_id]
        return [a for c in chain for a in self.classes[c].attributes]
