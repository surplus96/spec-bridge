"""Deterministic normalization (W3-5, FR-08) of mode-C observations into facts.

Numbers, ranges, dimensions, booleans, lists, enum display forms (dev dictionary),
identity (registry master data) and units (ontology + pint). Nothing is guessed: a value
that cannot be normalized becomes Unresolved with a reason (E2/E3 candidates for W4).
"""

import re
from typing import Any, Literal

import pint

from spec_bridge.extract.extractor import (
    Extraction,
    RawObservation,
    merge_facts,
    validate_facts,
)
from spec_bridge.extract.schemas import units_of_dimension
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.identity import MakerIndex, model_key

NUMBER = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
QUANTITY = re.compile(rf"^(?:at\s+)?({NUMBER.pattern})\s*([^\s/]+?)(?:\s*\(a\)|\s+absolute)?$")
REFERENCED = re.compile(
    rf"^(?:viscosity\s+)?({NUMBER.pattern})\s*(\S+)\s*(?:at|/)\s*({NUMBER.pattern})\s*(\S+)$"
)
DIMENSION_SPLIT = re.compile(r"\s*[×xX]\s*")
EMPTY_UNITS = {"", "—", "-"}

Reason = Literal[
    "not_a_number",
    "not_integer",
    "reversed_range",
    "bad_dimensions",
    "not_boolean",
    "missing_unit",
    "unknown_unit",
    "dimension",
    "condition",
]


class Unresolved(StrictModel):
    attribute: str
    value_text: str
    unit_text: str | None
    reason: Reason
    occurrence: dict[str, Any]


class NormalizationError(ValueError):
    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason: Reason = reason


def unit_symbol(unit_text: str | None) -> str | None:
    """'(mm)' -> 'mm': the unit as copied with its brackets (W3-7 second round)."""
    if unit_text is None:
        return None
    unit = unit_text.strip()
    if len(unit) > 2 and unit[0] == "(" and unit[-1] == ")":
        unit = unit[1:-1].strip()
    return unit


def drop_unit_suffix(text: str, unit: str | None) -> str:
    """'1457.04 kg' with unit 'kg' -> '1457.04': the unit was copied into the value too."""
    text = text.strip()
    if unit and unit not in EMPTY_UNITS and text.endswith(" " + unit):
        return text[: -len(unit)].strip()
    return text


def parse_number(text: str) -> int | float:
    text = text.strip()
    if not NUMBER.fullmatch(text):
        raise NormalizationError("not_a_number")
    plain = text.replace(",", "")
    return float(plain) if "." in plain else int(plain)


class Normalizer:
    def __init__(
        self,
        onto: Ontology,
        dictionary: dict[str, Any],
        makers: list[dict[str, Any]],
        registry_models: list[str],
    ) -> None:
        self.onto = onto
        self.enums: dict[str, dict[str, str]] = dictionary.get("enums", {})
        self.makers = MakerIndex(makers)
        self.maker_names = {m["maker_id"]: m["name"] for m in makers}
        self.models = {model_key(m): m for m in registry_models}
        self.ureg = pint.UnitRegistry()

    def fact(self, raw: RawObservation) -> dict[str, Any] | Unresolved:
        try:
            value, unit = self.value(raw.attribute, raw.value_text, raw.unit_text)
            condition = self.condition(raw.condition)
        except NormalizationError as error:
            return Unresolved(
                attribute=raw.attribute,
                value_text=raw.value_text,
                unit_text=raw.unit_text,
                reason=error.reason,
                occurrence=raw.occurrence,
            )
        return {
            "attribute": raw.attribute,
            "value": value,
            "unit": unit,
            "basis": raw.basis,
            "condition": condition,
            "scope": raw.scope,
            "occurrences": [raw.occurrence],
        }

    # values -----------------------------------------------------------------------------
    def value(self, attribute: str, text: str, unit_text: str | None) -> tuple[Any, str | None]:
        attr = self.onto.attributes[attribute]
        types = attr.datatype if isinstance(attr.datatype, list) else [attr.datatype]
        unit_text = unit_symbol(unit_text)
        text = drop_unit_suffix(text, unit_text)
        if "range" in types and " to " in text:
            low, high = (self._number(p, unit_text, attribute) for p in text.split(" to ", 1))
            if low > high:
                raise NormalizationError("reversed_range")
            return {"min": low, "max": high}, attr.canonical_unit
        kind = types[0]
        if kind in ("number", "integer"):
            number = self._number(text, unit_text, attribute)
            if kind == "integer" and not isinstance(number, int):
                raise NormalizationError("not_integer")
            return number, attr.canonical_unit
        if kind == "dimensions":
            parts = DIMENSION_SPLIT.split(text)
            if len(parts) != 3:
                raise NormalizationError("bad_dimensions")
            axes = [self._number(p, unit_text, attribute) for p in parts]
            return dict(zip(("length", "width", "height"), axes, strict=True)), attr.canonical_unit
        if kind == "boolean":
            word = text.casefold()
            if word not in ("yes", "no", "true", "false"):
                raise NormalizationError("not_boolean")
            return word in ("yes", "true"), None
        if kind == "string_set":
            return [self._token(attribute, part) for part in text.split(",")], None
        return self._string(attribute, text), None

    def _token(self, attribute: str, text: str) -> str:
        return self.enums.get(attribute, {}).get(text.strip().casefold(), text.strip())

    def _string(self, attribute: str, text: str) -> str:
        if attribute == "maker":
            maker_id = self.makers.resolve(text)
            return self.maker_names[maker_id] if maker_id else text
        if attribute == "model_designation":
            return self.models.get(model_key(text), text)
        return self._token(attribute, text)

    def _number(self, text: str, unit_text: str | None, attribute: str) -> int | float:
        number = parse_number(text)
        canonical = self.onto.attributes[attribute].canonical_unit
        if canonical is None:
            return number
        unit = (unit_text or "").strip()
        if unit in EMPTY_UNITS:
            raise NormalizationError("missing_unit")
        return self._convert(number, unit, canonical)

    def _convert(self, number: int | float, unit: str, canonical: str) -> int | float:
        if unit == canonical:
            return number  # no float noise for the common case
        if unit not in self.onto.units:  # e.g. bhp, ton: no memory-based conversion (H3)
            raise NormalizationError("unknown_unit")
        source = self.ureg.parse_units(self.onto.units[unit].pint)
        target = self.ureg.parse_units(self.onto.units[canonical].pint)
        if source.dimensionality != target.dimensionality:
            raise NormalizationError("dimension")
        converted = self.ureg.Quantity(number, source).to(target).magnitude
        return float(converted)

    # conditions -------------------------------------------------------------------------
    def condition(self, condition: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in condition.items():
            spec = self.onto.vocabularies.condition.get(key)
            if spec is None:
                raise NormalizationError("condition")
            if spec.kind == "token":
                if value not in spec.values:
                    raise NormalizationError("condition")
                result[key] = value
                continue
            assert spec.dimension is not None
            text = str(value).strip()
            if spec.kind == "reference_quantity":
                match = REFERENCED.fullmatch(text)
                if not match:
                    raise NormalizationError("condition")
                result[key] = self._quantity(match[1], match[2], spec.dimension) | {
                    "reference_temperature": self._quantity(match[3], match[4], "temperature")
                }
            else:
                match = QUANTITY.fullmatch(text)
                if not match:
                    raise NormalizationError("condition")
                result[key] = self._quantity(match[1], match[2], spec.dimension)
        return result

    def _quantity(self, number: str, unit: str, dimension: str) -> dict[str, Any]:
        if unit not in units_of_dimension(self.onto, dimension):  # Review Focus 5
            raise NormalizationError("condition")
        return {"value": parse_number(number), "unit": unit}


def normalize_extraction(
    onto: Ontology, extraction: Extraction, normalizer: Normalizer
) -> tuple[list[dict[str, Any]], list[Unresolved]]:
    """Mode-C raw observations -> merged, schema-checked facts plus unresolved values."""
    facts: list[dict[str, Any]] = []
    unresolved: list[Unresolved] = []
    for raw in extraction.raw:
        result = normalizer.fact(raw)
        if isinstance(result, Unresolved):
            unresolved.append(result)
        else:
            facts.append(result)
    return validate_facts(onto, extraction.class_id, merge_facts(facts), extraction), unresolved
