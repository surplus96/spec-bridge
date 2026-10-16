"""Validation findings (W4-2, FR-09): what the validator reports and why.

Codes follow the answer contract (E1-E5). REVIEW has no contract code: a value the
normalizer could not read without guessing (unknown or missing unit, an unreadable
condition). It blocks registration and goes to a person; it is not scored as E1-E5.
"""

from typing import Any, Literal

from spec_bridge.normalize.values import Reason
from spec_bridge.ontology.facts import StrictModel

Code = Literal["E1", "E2", "E3", "E4", "E5", "REVIEW"]
ONTOLOGY_REF = "ontology/ontology.yaml"

# W4 plan decision 3 (D-038): normalizer reason -> finding code.
UNRESOLVED_CODES: dict[Reason, Code] = {
    "dimension": "E2",
    "not_a_number": "E3",
    "not_integer": "E3",
    "reversed_range": "E3",
    "bad_dimensions": "E3",
    "not_boolean": "E3",
    "unknown_unit": "REVIEW",
    "missing_unit": "REVIEW",
    "condition": "REVIEW",
}
RULE_KINDS: dict[Code, str] = {
    "E2": "dimension",
    "E3": "value_types",
    "REVIEW": "canonical_unit",
}


class Finding(StrictModel):
    code: Code
    attribute_ids: list[str]
    occurrences: list[dict[str, Any]]  # where the problem is; empty for E1 (nothing found)
    rule_ref: str  # "ontology/ontology.yaml#<path>/<rule kind>"
    reason: str


def code_for_unresolved(reason: Reason) -> Code:
    return UNRESOLVED_CODES[reason]
