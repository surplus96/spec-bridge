"""Class mapping (W3-3, FR-06): keyword candidates, then an LLM choice among them.

The main product is declared in the document head (title, product line); other classes
appear in the body as applicable engines, components or scope words, so head matches
weigh more. The LLM may only pick a candidate or "unknown".
"""

import re
from typing import Literal

from spec_bridge.extract.prompt_input import render_lines
from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.parse.blocks import Block, ParsedDocument

HEAD_WEIGHT = 5.0
HEADING_WEIGHT = 2.0
BODY_WEIGHT = 1.0
UNKNOWN = "unknown"

SYSTEM = (
    "You map a marine equipment specification to the one product class it describes. "
    "Judge the main product declared by the document. Applicable engines, included "
    "components and scope wording are not the product. If unsure, answer unknown."
)


class ClassScore(StrictModel):
    class_id: str
    score: float


class ClassPrediction(StrictModel):
    top_k: list[ClassScore]
    chosen: str  # a leaf class id or "unknown"
    method: Literal["keyword", "llm"]
    reason: str


def _head(document: ParsedDocument) -> list[Block]:
    """Blocks before the first section heading: title and product lines."""
    head = []
    for block in document.blocks:
        if block.kind == "heading" or block.kind == "table_cell":
            break
        head.append(block)
    return head


def keyword_scores(onto: Ontology, document: ParsedDocument) -> list[ClassScore]:
    head = {id(b) for b in _head(document)}
    scores = []
    for class_id, cls in onto.classes.items():
        if cls.abstract:
            continue
        terms = [*cls.keywords, *([cls.label] if cls.label else [])]
        patterns = [re.compile(r"\b" + re.escape(t.lower())) for t in terms]
        score = 0.0
        for block in document.blocks:
            hits = sum(len(p.findall(block.text.lower())) for p in patterns)
            if not hits:
                continue
            weight = (
                HEAD_WEIGHT
                if id(block) in head
                else HEADING_WEIGHT
                if block.kind in ("heading", "title")
                else BODY_WEIGHT
            )
            score += hits * weight
        scores.append(ClassScore(class_id=class_id, score=score))
    return sorted(scores, key=lambda s: (-s.score, s.class_id))


def classify(
    onto: Ontology,
    document: ParsedDocument,
    provider: JsonProvider | None = None,
    *,
    k: int = 3,
) -> ClassPrediction:
    ranked = keyword_scores(onto, document)
    top_k = [s for s in ranked if s.score > 0][:k]
    if provider is None:
        chosen = top_k[0].class_id if top_k else UNKNOWN
        return ClassPrediction(top_k=top_k, chosen=chosen, method="keyword", reason="keyword score")
    candidates = [s.class_id for s in top_k] or [s.class_id for s in ranked]
    options = [*candidates, UNKNOWN]
    schema = {
        "type": "object",
        "properties": {
            "product_class": {"type": "string", "enum": options},
            "reason": {"type": "string"},
        },
        "required": ["product_class", "reason"],
    }
    labels = "\n".join(f"- {c}: {onto.classes[c].label}" for c in candidates)
    text, _ = render_lines(document)
    reply = provider.complete_json(
        system=SYSTEM,
        user=f"Candidate classes:\n{labels}\n\nDocument lines:\n{text}",
        schema=schema,
        task="classify",
    )
    answer = reply.get("product_class")
    if answer not in options:
        raise LlmError("classify", f"answer {answer!r} is not one of {options}")
    return ClassPrediction(
        top_k=top_k, chosen=str(answer), method="llm", reason=str(reply.get("reason", ""))
    )
