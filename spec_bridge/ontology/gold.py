"""Convert handwritten gold v2 records into candidate input (W1-5).

Evaluator metadata (expected_status, match tolerances, injections) is dropped.
Mapping follows dataset-contract metadata_contract.gold_v2_aliases.
"""

from typing import Any

BASIS_KEYS = {
    "capacity_basis": "capacity",
    "rating_basis": "rating",
    "pressure_basis": "pressure",
    "weight_basis": "weight",
}
LOCATION_KEYS = ("section", "pdf_page", "paragraph", "table", "row", "line")


def v2_location(location: dict[str, Any]) -> dict[str, Any]:
    return {k: location[k] for k in LOCATION_KEYS if location.get(k) is not None}


def v2_occurrences(doc_id: str, occurrences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_document_id": doc_id,
            "raw_text": o["raw_text"],
            "label_text": o.get("label_text"),
            "unit_text": o.get("unit_text"),
            "location": v2_location(o["location"]),
        }
        for o in occurrences
    ]


def v2_attribute_facts(doc_id: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """One v2 attribute -> facts. conditional_values become sibling facts."""
    basis = {new: entry[old] for old, new in BASIS_KEYS.items() if old in entry}
    condition = dict(entry.get("condition") or {}) | dict(entry.get("reference_conditions") or {})
    scope = entry.get("scope", "unknown")
    facts = [
        {
            "value": entry["value"],
            "unit": entry["unit"],
            "basis": basis,
            "condition": condition,
            "scope": scope,
            "occurrences": v2_occurrences(doc_id, entry["occurrences"]),
        }
    ]
    for extra in entry.get("conditional_values") or []:
        facts.append(
            {
                "value": extra["value"],
                "unit": extra["unit"],
                "basis": basis,
                "condition": dict(extra.get("condition") or {}),
                "scope": scope,
                "occurrences": v2_occurrences(doc_id, extra["occurrences"]),
            }
        )
    return facts


def v2_to_candidate_input(answer: dict[str, Any]) -> dict[str, Any]:
    doc_id = answer["doc_id"]
    return {
        "attributes": {
            attr: v2_attribute_facts(doc_id, entry) for attr, entry in answer["attributes"].items()
        }
    }
