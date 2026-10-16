"""Self-RAG support check (W4-R R5, D-052): does the quoted evidence state the value?

Code verification (R4) proves the quote is on the line; it cannot tell whether the quote
supports the chosen token. In the E1 run, quotes that exist on the line were attached to
values they do not state (for example a rating point added to overall dimensions). After
verification, the model judges each kept field once more; fields it does not support are
dropped, so the check can only remove context, never add it.
"""

from typing import Any

from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.rag.knowledge import Qualifiers
from spec_bridge.rag.qualifiers import QualifierItem, QualifierResult

SYSTEM = (
    "You check one line of a marine equipment specification. For each numbered field, "
    "answer supported=true only if the quoted words of the line state that value for the "
    "named attribute; otherwise supported=false."
)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"field": {"type": "string"}, "supported": {"type": "boolean"}},
                "required": ["field", "supported"],
            },
        }
    },
    "required": ["checks"],
}


def _value(qualifiers: Qualifiers, field: str) -> str:
    kind, _, name = field.partition(".")
    if kind == "scope":
        return qualifiers.scope
    table = qualifiers.basis if kind == "basis" else qualifiers.condition
    return table[name]


def support_prompt(item: QualifierItem, result: QualifierResult) -> str:
    rows = [
        f'{field} = {_value(result.qualifiers, field)} (quoted: "{quote}")'
        for field, quote in sorted(result.evidence.items())
    ]
    return f"Attribute: {item.attribute}\nLine: {item.line_text}\n\nFields:\n" + "\n".join(rows)


def check_support(
    provider: JsonProvider, item: QualifierItem, result: QualifierResult
) -> QualifierResult:
    """Drop the fields the model says the quote does not support; keep the rest."""
    if not result.evidence:
        return result
    before = result.qualifiers.model_copy(deep=True)
    try:
        reply = provider.complete_json(
            system=SYSTEM, user=support_prompt(item, result), schema=SCHEMA, task="qualify-check"
        )
    except LlmError as error:  # the check failed: keep the verified answer, say so
        return result.model_copy(
            update={"rejected": [*result.rejected, f"self-check: llm {error.reason}"]}
        )
    unsupported = {
        str(c.get("field"))
        for c in reply.get("checks", [])
        if isinstance(c, dict) and c.get("supported") is False
    }
    kept = result.qualifiers.model_copy(deep=True)
    evidence = dict(result.evidence)
    rejected = list(result.rejected)
    for field in sorted(unsupported & evidence.keys()):
        kind, _, name = field.partition(".")
        if kind == "scope":
            kept.scope = ""
        else:
            (kept.basis if kind == "basis" else kept.condition).pop(name, None)
        evidence.pop(field)
        rejected.append(f"{field}: not supported (self-check)")
    return result.model_copy(
        update={
            "qualifiers": kept,
            "evidence": evidence,
            "rejected": rejected,
            "before_check": before,
        }
    )
