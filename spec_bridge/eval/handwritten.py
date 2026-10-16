"""Handwritten evaluation set (W6-2, D-080 decision 1-B): six Markdown specifications whose
answers (schema v2, written before the ontology) are converted to the answer contract.

    uv run python -m spec_bridge.eval.handwritten build

writes data/eval/handwritten/converted/DOC-00N.answer.yaml (committed, frozen with the
system) and var/parsed/handwritten/ (the parsed inputs, like var/parsed/<split>/).

Conversion rules (recorded in each converted answer under `conversion`):
- v2 `rating_basis` / `capacity_basis` / `pressure_basis` / `weight_basis` → basis axes;
  v2 `condition` and `reference_conditions` → condition keys (viscosity text through the
  project normalizer); v2 `conditional_values` → one more fact each.
- scope: the contract defines a scope as the phrase the document states (synthetic
  answers tokenize that phrase). v2 used author tokens that differ from the documents'
  phrases, so the scope is taken from SCOPE_PHRASES, each checked to be in its document.
- every v2 occurrence is located in the parsed document by its text and its v2 place
  (table row, or numbered paragraph); zero or several candidates stop the build.
- v2 `match_tolerance_rel` has no counterpart (the scorer compares normalized values).
- issues and missing_required are not labelled (v2 left them null): G3 and G4 are not
  reported on this set; facts, classes and occurrences are.

Limits (D-080): the six documents and their v2 answers were drafted by the helper and read
while the ontology was built; they are not independent of the system.
"""

import json
import re
import sys
from typing import Any

import yaml

from spec_bridge.extract.extractor import scope_token
from spec_bridge.normalize.dictionary import ROOT, load_dictionary
from spec_bridge.normalize.values import Normalizer
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.ontology.schema import build_candidate_model
from spec_bridge.parse.blocks import Block, ParsedDocument
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.parse.run import environment
from spec_bridge.service import ONTOLOGY, normalizer_for

FOLDER = ROOT / "data/eval/handwritten"
CONVERTED = FOLDER / "converted"
PARSED = ROOT / "var/parsed/handwritten"
BASIS_FIELDS = {
    "rating_basis": "rating",
    "capacity_basis": "capacity",
    "pressure_basis": "pressure",
    "weight_basis": "weight",
}
SCOPE_PHRASES = {  # (document, attribute) -> the scope phrase as the document writes it
    ("HW-COMP-001", "dimensions"): "complete compressor unit including electric motor and "
    "flexible mountings",
    ("HW-COMP-001", "dry_weight"): "complete compressor unit including electric motor and "
    "flexible mountings",
    ("HW-SEP-001", "dimensions"): "complete separator module",
    ("HW-SEP-001", "dry_weight"): "complete separator module including feed pump, heater and "
    "control unit",
    ("HW-TC-001", "dimensions"): "complete turbocharger including air inlet silencer and gas "
    "outlet diffuser",
    ("HW-TC-001", "dry_weight"): "complete turbocharger including air inlet silencer and gas "
    "outlet diffuser",
}


class ConversionError(ValueError):
    """A v2 answer cannot be converted without a judgement the rules do not cover."""


def manifest() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = yaml.safe_load(
        (FOLDER / "dataset-manifest.yaml").read_text()
    )["documents"]
    return documents


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def locate(document: ParsedDocument, occurrence: dict[str, Any], where: str) -> dict[str, Any]:
    """The contract location of one v2 occurrence: its block in the parsed document."""
    raw = _norm(str(occurrence["raw_text"]))
    v2 = occurrence.get("location", {})
    blocks: list[Block] = [b for b in document.blocks if raw in _norm(b.text)]
    if v2.get("table") is not None:
        row = v2["row"] + 1  # v2 counts data rows; the parser's row 1 is the header
        found = [b for b in blocks if (b.location.table, b.location.row) == (v2["table"], row)]
        found = found[:1]  # the first cell of the row that states it (value before remark)
    else:
        section = str(v2.get("section", ""))
        if section == "header":
            first_heading = next(
                (b.location.paragraph or 0 for b in document.blocks if b.kind == "heading"),
                10**9,
            )
            found = [
                b
                for b in blocks
                if b.kind != "table_cell" and (b.location.paragraph or 0) < first_heading
            ]
        else:
            lines = [b for b in blocks if b.kind != "table_cell"]
            # "1.2" names the numbered line; "5" with a paragraph names a paragraph of § 5
            found = [b for b in lines if re.match(rf"{re.escape(section)}[ .]", b.text)]
            if not found:
                body = [b for b in lines if re.match(rf"{re.escape(section)}\.\s", b.section or "")]
                index = int(v2.get("paragraph") or 1) - 1
                found = body[index : index + 1] if len(body) > 1 else body
    if len(found) != 1:
        raise ConversionError(f"{where}: {len(found)} places for {occurrence['raw_text']!r}")
    loc = found[0].location
    if loc.table is not None:
        return {"table": loc.table, "row": loc.row, "cell": loc.column, "line": loc.line}
    return {"paragraph": loc.paragraph, "line": loc.line, "section": loc.section}


def _condition(
    normalizer: Normalizer, raw: dict[str, Any], attribute: str, notes: list[str]
) -> dict[str, Any]:
    """v2 condition text in the ontology's unit symbols: '°C' is written 'degC' (the
    meaning is the same; the system's own normalizer does not read '°C', see D-082)."""
    fixed = {k: v.replace("°C", "degC") if isinstance(v, str) else v for k, v in raw.items()}
    if fixed != raw:
        notes.append(f"{attribute}: condition '°C' written as 'degC'")
    return normalizer.condition(fixed) if fixed else {}


def convert(
    onto: Ontology,
    normalizer: Normalizer,
    v2: dict[str, Any],
    input_id: str,
    document: ParsedDocument,
) -> dict[str, Any]:
    doc_id = v2["doc_id"]
    text = _norm(" ".join(b.text for b in document.blocks))
    facts: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    notes: list[str] = []

    def add(attribute: str, body: dict[str, Any], context: dict[str, Any]) -> None:
        ids = []
        for occurrence in body.get("occurrences", []):
            oid = f"O{len(observations) + 1:03d}"
            observations.append(
                {
                    "observation_id": oid,
                    "attribute_id": attribute,
                    "raw_text": occurrence["raw_text"],
                    "label_text": occurrence.get("label_text"),
                    "unit_text": occurrence.get("unit_text"),
                    "location": locate(document, occurrence, f"{doc_id}.{attribute}"),
                    "interpretation": "normalized",
                }
            )
            ids.append(oid)
        fact = {
            "fact_id": f"F{len(facts) + 1:03d}",
            "attribute_id": attribute,
            "value": body["value"],
            "unit": body["unit"],
            **context,
            "observation_ids": ids,
            "admissibility": "supported",
        }
        model = build_candidate_model(onto, v2["expected_class"], registered=True)
        check = {k: fact[k] for k in ("value", "unit", "basis", "condition", "scope")}
        model.model_validate({"attributes": {attribute: [check]}})  # fails loudly
        facts.append(fact)

    for attribute, body in v2["attributes"].items():
        basis = {axis: body[field] for field, axis in BASIS_FIELDS.items() if field in body}
        raw_condition = dict(body.get("condition") or {})
        for key, quantity in (body.get("reference_conditions") or {}).items():
            raw_condition[key] = f"{quantity['value']} {quantity['unit']}"
        condition = _condition(normalizer, raw_condition, attribute, notes)
        scope = "main_equipment"
        if (doc_id, attribute) in SCOPE_PHRASES:
            phrase = SCOPE_PHRASES[(doc_id, attribute)]
            if _norm(phrase) not in text:
                raise ConversionError(f"{doc_id}.{attribute}: scope phrase not in the document")
            scope = scope_token(phrase)
            notes.append(f"{attribute}: scope {body.get('scope')!r} -> {scope!r} (document phrase)")
        if "match_tolerance_rel" in body:
            notes.append(f"{attribute}: match_tolerance_rel dropped (scorer compares exactly)")
        context = {"basis": basis, "condition": condition, "scope": scope}
        add(attribute, body, context)
        for extra in body.get("conditional_values") or []:
            extra_condition = _condition(normalizer, dict(extra["condition"]), attribute, notes)
            add(attribute, extra, context | {"condition": extra_condition})
            notes.append(
                f"{attribute}: conditional value {extra['value']} {extra['unit']} as a fact"
            )

    return {
        "schema_version": 3,
        "input_id": input_id,
        "origin": "synthetic",
        "status": "converted_from_v2_helper_draft",
        "expected_class": v2["expected_class"],
        "facts": facts,
        "observations": observations,
        "issues": [],  # not labelled in v2: G3 is not reported on this set
        "missing_required": [],
        "conversion": {
            "source": f"data/eval/handwritten/{doc_id}.answer.yaml",
            "doc_id": doc_id,
            "author": v2.get("author"),
            "reviewed_by": v2.get("reviewed_by"),
            "notes": notes,
        },
    }


def build() -> dict[str, Any]:
    onto = load_ontology(ONTOLOGY)
    normalizer = normalizer_for(onto, "dev", load_dictionary())  # never the test registry
    CONVERTED.mkdir(parents=True, exist_ok=True)
    PARSED.mkdir(parents=True, exist_ok=True)
    parsed: dict[str, int] = {}
    for entry in manifest():
        input_id = entry["input_id"]
        document = parse_document(ROOT / entry["input_text"], input_id)
        (PARSED / f"{input_id}.json").write_text(document.model_dump_json(indent=2) + "\n")
        parsed[input_id] = len(document.blocks)
        v2 = yaml.safe_load((ROOT / entry["answer"]).read_text())
        answer = convert(onto, normalizer, v2, input_id, document)
        (CONVERTED / f"{input_id}.answer.yaml").write_text(
            yaml.safe_dump(answer, allow_unicode=True, sort_keys=False)
        )
    summary = {
        "split": "handwritten",
        "documents": len(parsed),
        "parsed": len(parsed),
        "parsed_ids": sorted(parsed),
        "blocks": sum(parsed.values()),
        "failures": [],
        "environment": environment(),
    }
    (PARSED / "_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def answers() -> list[dict[str, Any]]:
    """The converted answers, in manifest order."""
    return [
        yaml.safe_load((CONVERTED / f"{e['input_id']}.answer.yaml").read_text()) for e in manifest()
    ]


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        print(json.dumps(build(), indent=2, default=str)[:400])
