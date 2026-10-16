"""Qualifier RAG chain (W4-R R4, configuration E): basis, condition and scope of ONE value.

LCEL chain, step by step:

    item ─▶ retrieve solved cases (label + remarks query, own family left out in evaluation)
         ─▶ render prompt (ontology wording + cases with their answers + this line)
         ─▶ model (our provider wrapped as a Runnable: audit, offline guard, seed)
         ─▶ verify in code (evidence quoted from this line, vocabulary, unit dimension)

The model interprets; code verifies (plan 5-1, D-042). A field that fails verification is
dropped and its reason kept: nothing is invented (D-043 decision 6).
"""

import json
from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough

from spec_bridge.extract.prompt_input import has_token
from spec_bridge.extract.schemas import HIDDEN
from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.llm.runnable import as_runnable
from spec_bridge.normalize.values import NUMBER, NormalizationError, Normalizer
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.rag.knowledge import KbExample, Qualifiers
from spec_bridge.rag.retrieval import KbRetriever, examples_of, for_query

EMPTY_CELLS = {"", "—", "-"}
SYSTEM = (
    "You read one line of a marine equipment specification and state the basis, the "
    "conditions and the scope of one value on that line. Use only what the line states. "
    "Every field you give must quote its evidence: the exact words of the line that state "
    "it. Leave a field out when the line does not state it. Solved cases from other "
    "documents show the expected answers."
)


class QualifierItem(StrictModel):
    """One extracted value and where it stands (from the mode-C extraction)."""

    attribute: str
    value_text: str
    unit_text: str | None
    line_text: str
    parent_text: str
    family_id: str | None = None  # set only in evaluation: leave this family out


class QualifierResult(StrictModel):
    qualifiers: Qualifiers
    evidence: dict[str, str]
    rejected: list[str]  # "<field>: <reason>"
    retrieved_ids: list[str]
    before_check: Qualifiers | None = None  # set by the self-check (R5): what it removed from


# the line ------------------------------------------------------------------------------
def line_parts(line: str) -> tuple[str, str]:
    """(label, remarks). Table rows: `label | value | unit | remarks`; text lines:
    `label — value unit (remarks)`."""
    cells = [c.strip() for c in line.split(" | ")]
    if len(cells) >= 2:
        remarks = cells[3] if len(cells) >= 4 and cells[3] not in EMPTY_CELLS else ""
        return cells[0], remarks
    label, _, rest = line.partition(" — ")
    start, end = rest.find("("), rest.rfind(")")  # outer brackets: "1013 mbar(a)" may nest
    return label.strip(), rest[start + 1 : end].strip() if 0 <= start < end else ""


def query_of(item: QualifierItem) -> str:
    """The fixed search query (D-047): label and remarks, without value and unit."""
    label, remarks = line_parts(item.line_text)
    return f"{label} {remarks}".strip()


# output schema --------------------------------------------------------------------------
def _described(texts: dict[str, str], tokens: list[str]) -> str:
    parts = [texts["_"]] if "_" in texts else []
    named = [f"{t}: {texts[t]}" for t in tokens if t in texts]
    return " ".join([*parts, *(["Tokens - " + "; ".join(named)] if named else [])])


def _field(value: dict[str, Any], description: str) -> dict[str, Any]:
    prop: dict[str, Any] = {
        "type": "object",
        "properties": {"value": value, "evidence": {"type": "string"}},
        "required": ["value", "evidence"],
    }
    return prop | {"description": description} if description else prop


def qualifier_schema(onto: Ontology) -> dict[str, Any]:
    """Every axis is optional; each given field pairs a value with its evidence."""
    vocab, described = onto.vocabularies, onto.vocabularies.descriptions
    basis = {}
    for axis, values in vocab.basis.items():
        tokens = [v for v in values if v not in HIDDEN]
        texts = described.basis.get(axis, {}) if described else {}
        basis[axis] = _field({"type": "string", "enum": tokens}, _described(texts, tokens))
    condition = {}
    for key, cond in vocab.condition.items():
        tokens = [v for v in cond.values if v not in HIDDEN]
        value = {"type": "string", "enum": tokens} if cond.kind == "token" else {"type": "string"}
        texts = described.condition.get(key, {}) if described else {}
        condition[key] = _field(value, _described(texts, tokens))
    scope_text = described.scope.get("optional", "") if described else ""
    return {
        "type": "object",
        "properties": {
            "basis": {"type": "object", "properties": basis},
            "condition": {"type": "object", "properties": condition},
            "scope": _field({"type": "string"}, scope_text),
        },
    }


# prompt ---------------------------------------------------------------------------------
def answer_of(example: KbExample) -> dict[str, Any]:
    """A solved case's answer in the output shape (evidence null where code found none)."""
    q, ev = example.qualifiers, example.evidence
    answer: dict[str, Any] = {}
    if q.basis:
        answer["basis"] = {
            k: {"value": v, "evidence": ev.get(f"basis.{k}")} for k, v in q.basis.items()
        }
    if q.condition:
        answer["condition"] = {
            k: {"value": v, "evidence": ev.get(f"condition.{k}")} for k, v in q.condition.items()
        }
    if q.scope:
        answer["scope"] = {"value": q.scope, "evidence": ev.get("scope")}
    return answer


def render(item: QualifierItem, examples: list[KbExample]) -> str:
    unit = f" {item.unit_text}" if item.unit_text else ""
    blocks = [f"Attribute: {item.attribute}\nValue: {item.value_text}{unit}"]
    if examples:
        for n, example in enumerate(examples, start=1):
            answer = json.dumps(answer_of(example), ensure_ascii=False)
            blocks.append(f"Solved case {n}\n{example.parent_text}\nAnswer: {answer}")
    else:
        blocks.append("Solved cases: none")
    blocks.append(f"Now answer for this line\n{item.parent_text}")
    return "\n\n".join(blocks)


# verification ---------------------------------------------------------------------------
def verify(
    onto: Ontology, normalizer: Normalizer, item: QualifierItem, reply: dict[str, Any]
) -> tuple[Qualifiers, dict[str, str], list[str]]:
    """Keep only fields the line itself supports; return reasons for the rest.

    A provider without strict structured output may answer off the schema (a bare string
    where an object with value and evidence belongs); that field is rejected, never a
    crash of the whole document (D-067)."""
    line = item.line_text
    _, remarks = line_parts(line)
    vocab = onto.vocabularies
    kept, evidence, rejected = Qualifiers(), {}, []

    def quoted(field: str, given: Any, where: str) -> str | None:
        text = given.get("evidence") if isinstance(given, dict) else None
        if not isinstance(text, str) or not text.strip():
            rejected.append(f"{field}: no evidence")
            return None
        if text.strip().casefold() not in where.casefold():
            rejected.append(f"{field}: evidence not in the line")
            return None
        return text.strip()

    def fields(name: str) -> dict[str, Any]:
        given = reply.get(name) or {}
        if isinstance(given, dict):
            return given
        rejected.append(f"{name}: not an object")
        return {}

    def proposed(given: Any) -> bool:
        """A field with no value proposes nothing (D-072): not kept, not rejected."""
        value = given.get("value") if isinstance(given, dict) else given
        return not (
            value is None or (isinstance(value, str) and value.strip().casefold() in ("", "none"))
        )

    def shaped(field: str, given: Any) -> bool:
        if given is None or isinstance(given, dict):  # None: judged below, as before
            return True
        rejected.append(f"{field}: not an object")
        return False

    for axis, given in fields("basis").items():
        field = f"basis.{axis}"
        if not proposed(given):
            continue
        if not shaped(field, given):
            continue
        value = (given or {}).get("value")
        if axis not in vocab.basis or value not in vocab.basis[axis] or value in HIDDEN:
            rejected.append(f"{field}: not in the vocabulary")
        elif (span := quoted(field, given, line)) is not None:
            kept.basis[axis], evidence[field] = value, span
    for key, given in fields("condition").items():
        field = f"condition.{key}"
        if not proposed(given):
            continue
        if not shaped(field, given):
            continue
        value = (given or {}).get("value")
        spec = vocab.condition.get(key)
        if spec is None or not isinstance(value, str) or not value.strip():
            rejected.append(f"{field}: not in the vocabulary")
            continue
        if spec.kind == "token" and (value not in spec.values or value in HIDDEN):
            rejected.append(f"{field}: not in the vocabulary")
            continue
        if spec.kind != "token":
            numbers = NUMBER.findall(value)
            if not numbers or not all(has_token(line, n) for n in numbers):
                rejected.append(f"{field}: number not in the line")  # copied from a case
                continue
            try:
                normalizer.condition({key: value})
            except NormalizationError:
                rejected.append(f"{field}: wrong unit or form")
                continue
        if (span := quoted(field, given, line)) is not None:
            kept.condition[key], evidence[field] = value, span
    scope = reply.get("scope")
    if not shaped("scope", scope):
        scope = None
    phrase = scope.get("value") if isinstance(scope, dict) else None
    if isinstance(phrase, str) and phrase.strip() and phrase.strip().casefold() != "none":
        if phrase.strip().casefold() not in remarks.casefold():
            rejected.append("scope: phrase not in the remarks")  # never the label (D-049)
        elif (span := quoted("scope", scope, remarks)) is not None:
            kept.scope, evidence["scope"] = phrase.strip(), span
    return kept, evidence, rejected


# chain ----------------------------------------------------------------------------------
def build_chain(
    onto: Ontology,
    normalizer: Normalizer,
    provider: JsonProvider,
    kb: list[KbExample],
    retriever: KbRetriever | None,
    *,
    k: int = 3,
    self_check: bool = False,
) -> Runnable[QualifierItem, QualifierResult]:
    """retriever=None is configuration E0: the same question without solved cases.
    self_check adds the Self-RAG support check (R5) after code verification."""
    from spec_bridge.rag.selfrag import check_support  # selfrag imports this module

    by_id = {e.example_id: e for e in kb}
    model = as_runnable(provider, system=SYSTEM, schema=qualifier_schema(onto), task="qualify")

    def retrieve(inputs: dict[str, Any]) -> list[KbExample]:
        if retriever is None:
            return []
        item: QualifierItem = inputs["item"]
        search = for_query(retriever, item.family_id).model_copy(update={"k": k})
        return examples_of(search.invoke(query_of(item)), by_id)

    def finish(inputs: dict[str, Any]) -> QualifierResult:
        item, examples = inputs["item"], inputs["examples"]
        ids = [e.example_id for e in examples]
        try:
            reply = model.invoke(inputs["prompt"])
        except LlmError as error:
            return QualifierResult(
                qualifiers=Qualifiers(),
                evidence={},
                rejected=[f"llm: {error.reason}"],
                retrieved_ids=ids,
            )
        kept, evidence, rejected = verify(onto, normalizer, item, reply)
        result = QualifierResult(
            qualifiers=kept, evidence=evidence, rejected=rejected, retrieved_ids=ids
        )
        return check_support(provider, item, result) if self_check else result

    def wrap(item: QualifierItem) -> dict[str, Any]:
        return {"item": item}

    chain: Runnable[QualifierItem, QualifierResult] = (
        RunnableLambda(wrap)
        | RunnablePassthrough.assign(examples=RunnableLambda(retrieve))
        | RunnablePassthrough.assign(
            prompt=RunnableLambda(lambda x: render(x["item"], x["examples"]))
        )
        | RunnableLambda(finish)
    )
    return chain
