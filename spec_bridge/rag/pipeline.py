"""Configuration E in the pipeline (W4-R R6): qualify every extracted value with RAG.

Mode-C extraction (optional context, the W4-1 baseline) finds the values; then, value by
value, the qualifier chain (R4) states basis, condition and scope from the value's own line
and the retrieved solved cases. The chain's verified answer replaces whatever context the
extraction carried, so E and E0 differ from C only in this step.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import Runnable

from spec_bridge.extract.extractor import Extraction, RawObservation, scope_token
from spec_bridge.extract.prompt_input import group_lines
from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.rag.knowledge import KbExample, line_text_of, parent_of
from spec_bridge.rag.qualifiers import QualifierItem, QualifierResult, query_of
from spec_bridge.rag.retrieval import KbRetriever, examples_of, for_query


@dataclass
class RagSetup:
    """The built chain (with or without retrieval) and how run.json describes it."""

    chain: Runnable[QualifierItem, QualifierResult]
    info: dict[str, Any] = field(default_factory=dict)
    # Attribute conflicts (D-052): one value cell given to two attributes is settled by the
    # attributes of the retrieved solved cases for that line. Needs a retriever.
    retriever: KbRetriever | None = None
    kb: dict[str, KbExample] = field(default_factory=dict)
    k: int = 3


def _location_key(location: dict[str, Any]) -> str:
    return json.dumps(location, sort_keys=True)


def resolve_conflicts(
    setup: RagSetup,
    raws: list[RawObservation],
    items: list[QualifierItem],
) -> tuple[list[int], list[dict[str, Any]]]:
    """Indexes of the observations to keep, and one record per settled conflict.

    Observations of different attributes on the same location and value text compete.
    The retrieved cases for that line vote with their attribute; a clear winner stays,
    a tie or no vote drops all of them (nothing is guessed, D-043 decision 6).
    """
    groups: dict[str, list[int]] = {}
    for i, raw in enumerate(raws):
        key = _location_key(raw.occurrence["location"]) + "|" + raw.value_text.strip()
        groups.setdefault(key, []).append(i)
    keep, records = set(range(len(raws))), []
    for members in groups.values():
        candidates = {raws[i].attribute for i in members}
        if len(candidates) < 2 or setup.retriever is None:
            continue
        item = items[members[0]]
        search = for_query(setup.retriever, item.family_id).model_copy(update={"k": setup.k})
        cases = examples_of(search.invoke(query_of(item)), setup.kb)
        votes = Counter(c.attribute for c in cases if c.attribute in candidates)
        ranked = votes.most_common()
        winner = (
            ranked[0][0] if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]) else None
        )
        keep -= {i for i in members if raws[i].attribute != winner}
        records.append(
            {
                "kind": "conflict",
                "line": item.line_text,
                "candidates": sorted(candidates),
                "votes": dict(votes),
                "kept": winner,
                "retrieved_ids": [c.example_id for c in cases],
            }
        )
    return sorted(keep), records


def qualify_extraction(
    setup: RagSetup, document: ParsedDocument, extraction: Extraction, family_id: str | None
) -> tuple[Extraction, list[dict[str, Any]]]:
    """Replace each raw observation's context with the chain's verified answer."""
    lines = group_lines(document)
    where = {
        _location_key(block.location.model_dump(exclude_none=True)): index
        for index, line in enumerate(lines)
        for block in line
    }
    items = []
    for raw in extraction.raw:
        index = where[_location_key(raw.occurrence["location"])]
        items.append(
            QualifierItem(
                attribute=raw.attribute,
                value_text=raw.value_text,
                unit_text=raw.unit_text,
                line_text=line_text_of(lines[index]),
                parent_text=parent_of(lines, index),
                family_id=family_id,
            )
        )
    keep, records = resolve_conflicts(setup, extraction.raw, items)
    raws = []
    for i in keep:
        raw, item = extraction.raw[i], items[i]
        result = setup.chain.invoke(item)
        q = result.qualifiers
        raws.append(
            raw.model_copy(
                update={"basis": q.basis, "condition": q.condition, "scope": scope_token(q.scope)}
            )
        )
        records.append(
            {
                "kind": "value",
                "attribute": raw.attribute,
                "value_text": raw.value_text,
                "location": raw.occurrence["location"],  # which fact it became (W5 hints)
            }
            | result.model_dump()
        )
    return extraction.model_copy(update={"raw": raws}), records


def qualifier_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Fields kept and dropped (by reason) over a run: the harness view of channel E."""
    conflicts = [r for r in records if r.get("kind") == "conflict"]
    records = [r for r in records if r.get("kind", "value") == "value"]
    kept = sum(len(r["evidence"]) for r in records)
    reasons: dict[str, int] = {}
    for record in records:
        for reason in record["rejected"]:
            key = reason.split(": ", 1)[-1] if not reason.startswith("llm:") else "llm failure"
            reasons[key] = reasons.get(key, 0) + 1
    summary = {"values": len(records), "fields_kept": kept, "fields_rejected": reasons}
    if conflicts:
        unresolved = sum(c["kept"] is None for c in conflicts)
        summary["conflicts"] = {"settled": len(conflicts) - unresolved, "dropped": unresolved}
    return summary
