"""Supplement request (W5-4, D-066): what the sender must add or restate, and why.

The system never fills a missing value itself (no model guess, no lookup elsewhere). It
lists the required attributes the document lacks, with the ontology rule that makes them
required and the form the value must take, and the values it could not read, with where
they are. Deterministic: the same job always gives the same request.
"""

from typing import Any

from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.explain import explain_unresolved, place_of, shown_value
from spec_bridge.registry.output import RegistrationResult
from spec_bridge.validate.findings import code_for_unresolved


class Expected(StrictModel):
    datatype: list[str]
    dimension: str
    unit: str | None  # the canonical unit, or None for unitless values
    allowed_values: list[str] = []


class MissingItem(StrictModel):
    attribute: str
    rule_ref: str  # why it is required
    expected: Expected


class UnreadableItem(StrictModel):
    attribute: str
    code: str  # E2 / E3 / REVIEW
    value_text: str
    unit_text: str | None
    reason: str
    location: dict[str, Any]
    shown: str  # the value as written, unit once
    explanation: str  # why it was not read, in words
    place: str  # where, for a person


class SupplementRequest(StrictModel):
    document_id: str
    file_name: str | None
    class_id: str
    missing: list[MissingItem]
    unreadable: list[UnreadableItem]
    text: str  # the same content as plain text, to send to the document's sender


def _expected(onto: Ontology, class_id: str, attribute: str) -> Expected:
    attr = onto.attributes[attribute]
    allowed: list[str] = []
    for name in [*reversed(onto.ancestors(class_id)), class_id]:
        allowed = onto.classes[name].allowed_values.get(attribute, allowed)
    types = attr.datatype if isinstance(attr.datatype, list) else [attr.datatype]
    return Expected(
        datatype=[str(t) for t in types],
        dimension=attr.dimension,
        unit=attr.canonical_unit,
        allowed_values=allowed,
    )


def _text(request: SupplementRequest) -> str:
    lines = [
        f"보강 요청: {request.file_name or request.document_id} (클래스 {request.class_id})",
        "",
    ]
    if request.missing:
        lines.append("문서에서 찾지 못한 필수 정보:")
        for m in request.missing:
            form = "/".join(m.expected.datatype)
            unit = f", 단위 {m.expected.unit}" if m.expected.unit else ""
            allowed = (
                f", 허용값 {', '.join(m.expected.allowed_values)}"
                if m.expected.allowed_values
                else ""
            )
            lines.append(f"- {m.attribute}: {form}{unit}{allowed} (근거 규칙 {m.rule_ref})")
        lines.append("")
    if request.unreadable:
        lines.append("적힌 그대로는 읽을 수 없는 값:")
        for u in request.unreadable:
            lines.append(f'- {u.attribute}: "{u.shown}" ({u.place}) — {u.explanation}')
        lines.append("")
    if not request.missing and not request.unreadable:
        lines.append("보강할 내용이 없습니다.")
    return "\n".join(lines).rstrip() + "\n"


def supplement_request(onto: Ontology, result: RegistrationResult) -> SupplementRequest:
    known = result.class_id in onto.classes
    missing = [
        MissingItem(
            attribute=f.attribute_ids[0],
            rule_ref=f.rule_ref,
            expected=_expected(onto, result.class_id, f.attribute_ids[0]),
        )
        for f in result.validation.findings
        if f.code == "E1" and known
    ]
    unreadable = []
    for row in result.unresolved:
        unreadable.append(
            UnreadableItem(
                attribute=row["attribute"],
                code=code_for_unresolved(row["reason"]),
                value_text=row["value_text"],
                unit_text=row["unit_text"],
                reason=row["reason"],
                location=row["occurrence"].get("location", {}),
                shown=shown_value(row["value_text"], row["unit_text"]),
                explanation=explain_unresolved(onto, row),
                place=place_of(
                    row["occurrence"].get("location", {}), row["occurrence"].get("label_text")
                ),
            )
        )
    request = SupplementRequest(
        document_id=result.document_id,
        file_name=result.file_name,
        class_id=result.class_id,
        missing=missing,
        unreadable=unreadable,
        text="",
    )
    return request.model_copy(update={"text": _text(request)})
