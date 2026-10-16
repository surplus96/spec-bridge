"""Knowledge base for RAG semantic mapping (W4-R R1, D-042/D-043).

Each example is a solved case: one development-split line and the qualifiers (basis,
condition, scope) its gold fact carries, written in the shape the model will answer in:
tokens for vocabulary axes, quantities and scope phrases as text. Only dev gold and the
ontology's own definitions go in; any other split is refused (no test leakage).

Run: uv run python -m spec_bridge.rag.knowledge   -> data/rag/kb-dev.jsonl (committed, D-085)
"""

import hashlib
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import yaml

from spec_bridge.eval.locations import same_place
from spec_bridge.eval.scoring import CONTEXT_DEFAULTS, DEFAULT_SCOPE
from spec_bridge.extract.prompt_input import group_lines
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.parse.blocks import Block, ParsedDocument

ROOT = Path(__file__).resolve().parents[2]
CASE_PLAN = ROOT / "data/synth/case-plan.yaml"
OUTPUT = ROOT / "data/rag/kb-dev.jsonl"  # committed: frozen with the system (D-085)


class Qualifiers(StrictModel):
    """Basis tokens, condition tokens or quantities as written, scope as a phrase."""

    basis: dict[str, str] = {}
    condition: dict[str, str] = {}
    scope: str = ""  # "" means the main product itself


class KbExample(StrictModel):
    example_id: str
    doc_id: str
    family_id: str
    split: Literal["dev"]
    attribute: str
    label_text: str | None
    line_text: str  # the chunk that is searched
    parent_text: str  # section, table header and line: what the prompt shows
    qualifiers: Qualifiers
    evidence: dict[str, str]  # "basis.weight" -> the words in the line that state it


class KbDefinition(StrictModel):
    definition_id: str  # e.g. "basis.rating.motor_rated"
    text: str


def documents_by_split() -> dict[str, dict[str, Any]]:
    return {d["input_id"]: d for d in yaml.safe_load(CASE_PLAN.read_text())["documents"]}


# qualifiers as written ------------------------------------------------------------------
def _number(value: Any) -> str:
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def _quantity_forms(value: dict[str, Any]) -> list[str]:
    """How a gold quantity may be written; the first form is the fallback."""
    head = f"{_number(value['value'])} {value['unit']}"
    ref = value.get("reference_temperature")
    if ref is None:
        return [head]
    tail = f"{_number(ref['value'])} {ref['unit']}"
    return [f"{head} at {tail}", f"{head}/{tail}", f"{head} / {tail}"]


def qualifiers_from_fact(fact: dict[str, Any], line: str) -> Qualifiers:
    """Gold basis/condition/scope in the model's answer shape (contract defaults left out)."""
    lowered = line.casefold()
    condition = {}
    for key, value in fact["condition"].items():
        if isinstance(value, dict):
            forms = _quantity_forms(value)
            condition[key] = next((f for f in forms if f.casefold() in lowered), forms[0])
        else:
            condition[key] = str(value)
    scope = "" if fact["scope"] == DEFAULT_SCOPE else fact["scope"].replace("_", " ")
    basis = {k: v for k, v in fact["basis"].items() if CONTEXT_DEFAULTS.get(k) != v}
    return Qualifiers(basis=basis, condition=condition, scope=scope)


def find_evidence(qualifiers: Qualifiers, line: str) -> dict[str, str]:
    """Words of the line that state each qualifier, when code can find them verbatim."""
    lowered = line.casefold()

    def span(*candidates: str) -> str | None:
        for candidate in candidates:
            start = lowered.find(candidate.casefold())
            if candidate and start != -1:
                return line[start : start + len(candidate)]
        return None

    found: dict[str, str | None] = {}
    for axis, token in qualifiers.basis.items():
        found[f"basis.{axis}"] = span(token, token.replace("_", " "))
    for key, value in qualifiers.condition.items():
        head = value.split(" at ")[0].split("/")[0]
        found[f"condition.{key}"] = span(value, value.replace("_", " "), head)
    if qualifiers.scope:
        found["scope"] = span(qualifiers.scope)
    return {k: v for k, v in found.items() if v}


# lines and parents ----------------------------------------------------------------------
def line_text_of(line: list[Block]) -> str:
    return " | ".join(block.text.strip() for block in line)


def parent_of(lines: list[list[Block]], index: int) -> str:
    """Section heading, the table header row (if the line is a table row) and the line."""
    line = lines[index]
    parts = [f"Section: {line[0].section}"] if line[0].section else []
    if line[0].kind == "table_cell":
        start = index
        while start > 0 and lines[start - 1][0].kind == "table_cell":
            start -= 1
        if start != index:
            parts.append(f"Table header: {line_text_of(lines[start])}")
    parts.append(f"Line: {line_text_of(line)}")
    return "\n".join(parts)


# building ---------------------------------------------------------------------------------
def build_kb(
    answers: Iterable[dict[str, Any]], documents: dict[str, ParsedDocument]
) -> list[KbExample]:
    """One example per gold fact occurrence of the development split."""
    plan = documents_by_split()
    examples: list[KbExample] = []
    for answer in answers:
        doc_id = answer["input_id"]
        if plan[doc_id]["split"] != "dev":
            raise ValueError(f"{doc_id} is not in the dev split; the KB is dev-only (D-042)")
        lines = group_lines(documents[doc_id])
        observations = {o["observation_id"]: o for o in answer["observations"]}
        for fact in answer["facts"]:
            for oid in fact["observation_ids"]:
                obs = observations[oid]
                index = next(
                    i
                    for i, line in enumerate(lines)
                    if any(same_place(obs["location"], b) for b in line)
                )
                line = line_text_of(lines[index])
                qualifiers = qualifiers_from_fact(fact, line)
                examples.append(
                    KbExample(
                        example_id=f"{doc_id}:{oid}",
                        doc_id=doc_id,
                        family_id=plan[doc_id]["family_id"],
                        split="dev",
                        attribute=fact["attribute_id"],
                        label_text=obs["label_text"],
                        line_text=line,
                        parent_text=parent_of(lines, index),
                        qualifiers=qualifiers,
                        evidence=find_evidence(qualifiers, line),
                    )
                )
    return examples


def definitions(onto: Ontology) -> list[KbDefinition]:
    """The ontology's own wording for context axes and tokens (D-039)."""
    described = onto.vocabularies.descriptions
    if described is None:
        return []
    rows = [
        KbDefinition(definition_id=f"{kind}.{axis}.{token}".removesuffix("._"), text=text)
        for kind, table in (("basis", described.basis), ("condition", described.condition))
        for axis, texts in table.items()
        for token, text in texts.items()
    ]
    rows += [KbDefinition(definition_id=f"scope.{k}", text=t) for k, t in described.scope.items()]
    return rows


def save_kb(examples: list[KbExample], path: Path = OUTPUT) -> str:
    """Write one JSON object per line in a stable order; return the file's sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(examples, key=lambda e: e.example_id)
    path.write_text("".join(e.model_dump_json() + "\n" for e in rows))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_kb(path: Path = OUTPUT) -> list[KbExample]:
    return [KbExample.model_validate_json(row) for row in path.read_text().splitlines() if row]


def summary(examples: list[KbExample]) -> dict[str, Any]:
    with_context = [e for e in examples if e.qualifiers != Qualifiers()]
    fields = sum(len(e.qualifiers.basis) + len(e.qualifiers.condition) for e in examples)
    fields += sum(bool(e.qualifiers.scope) for e in examples)
    return {
        "examples": len(examples),
        "with_qualifiers": len(with_context),
        "families": len({e.family_id for e in examples}),
        "qualifier_fields": fields,
        "fields_with_evidence": sum(len(e.evidence) for e in examples),
    }


if __name__ == "__main__":
    from spec_bridge.normalize.dictionary import dev_answers

    parsed = ROOT / "var/parsed/dev"
    ids = json.loads((parsed / "_summary.json").read_text())["parsed_ids"]
    docs = {i: ParsedDocument.model_validate_json((parsed / f"{i}.json").read_text()) for i in ids}
    missing = [a["input_id"] for a in dev_answers() if a["input_id"] not in docs]
    if missing:
        sys.exit(f"parse these dev documents first: {missing}")
    kb = build_kb(dev_answers(), docs)
    sha = save_kb(kb)
    print(json.dumps(summary(kb) | {"path": str(OUTPUT.relative_to(ROOT)), "sha256": sha}))
