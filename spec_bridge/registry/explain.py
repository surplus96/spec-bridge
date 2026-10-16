"""Reviewer-facing explanations (W5-6 review): why a value was not read, why registration is
blocked, and where in the document a value stands — in words, not codes.

Deterministic and built only from the ontology (dimensions, units, allowed values) and the
validator's findings; no domain fact is added here (H3). The dimension names below are the
project's display labels for the ontology's own dimension ids.
"""

from functools import cache
from typing import Any

import pint

from spec_bridge.normalize.values import unit_symbol
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.validate.findings import Finding

DIMENSION_LABELS = {  # display labels for ontology dimension ids (origin: synthetic)
    "dimensionless": "단위 없음",
    "length": "길이",
    "mass": "질량",
    "power": "출력",
    "pressure": "압력",
    "volume_flow": "부피 유량",
    "rotational_frequency": "회전수",
    "frequency": "주파수",
    "temperature": "온도",
    "kinematic_viscosity": "동점도",
}


def dimension_label(dimension: str) -> str:
    return DIMENSION_LABELS.get(dimension, dimension)


@cache
def _registry() -> pint.UnitRegistry:
    return pint.UnitRegistry()


def unit_dimension(onto: Ontology, unit: str) -> str | None:
    """The ontology dimension of a unit the ontology defines, else None."""
    spec = onto.units.get(unit)
    if spec is None:
        return None
    ureg = _registry()
    have = ureg.parse_units(spec.pint).dimensionality
    for dimension, text in onto.dimensions.items():
        if ureg.get_dimensionality(text) == have:
            return dimension
    return None


def shown_value(value_text: str, unit_text: str | None) -> str:
    """The value as written, with its unit once: '5230.4 kg' + 'kg' is '5230.4 kg'."""
    unit = unit_symbol(unit_text)
    text = value_text.strip()
    if not unit or text.endswith(unit):
        return text
    return f"{text} {unit}"


def place_of(location: dict[str, Any], label: str | None = None) -> str:
    """'1쪽 · Specifications · 라벨 Throughput'; boxes stay for the highlight only."""
    parts = []
    if location.get("pdf_page") is not None:
        parts.append(f"{location['pdf_page']}쪽")
    if location.get("sheet"):
        parts.append(f"시트 {location['sheet']}")
    if location.get("cell_ref"):
        parts.append(f"셀 {location['cell_ref']}")
    if location.get("table") is not None:
        cell = f"표 {location['table']}"
        if location.get("row") is not None:
            cell += f" {location['row']}행"
        if location.get("column") is not None:
            cell += f" {location['column']}열"
        parts.append(cell)
    if location.get("paragraph") is not None:
        parts.append(f"{location['paragraph']}번째 단락")
    if location.get("line") is not None:
        parts.append(f"{location['line']}번째 줄")
    if location.get("section"):
        parts.append(str(location["section"]))
    if label:
        parts.append(f"라벨 {label}")
    return " · ".join(parts) or "위치 정보 없음"


def explain_unresolved(onto: Ontology, row: dict[str, Any]) -> str:
    """Why the normalizer did not read this value, in the reviewer's words."""
    attr = onto.attributes.get(row["attribute"])
    canonical = attr.canonical_unit if attr else None
    unit = unit_symbol(row.get("unit_text")) or ""
    reason = row["reason"]
    if reason == "dimension" and attr is not None:
        have = unit_dimension(onto, unit)
        have_text = f"{dimension_label(have)}" if have else "다른 차원"
        return (
            f"단위 차원 불일치: {unit}는 {have_text} 단위인데, 이 속성은 "
            f"{dimension_label(attr.dimension)}({canonical})이어야 함"
        )
    texts = {
        "not_a_number": "숫자로 읽을 수 없음",
        "not_integer": "정수여야 함",
        "reversed_range": "범위의 최솟값이 최댓값보다 큼",
        "bad_dimensions": "치수(길이×폭×높이) 형식으로 읽을 수 없음",
        "not_boolean": "예/아니오 값으로 읽을 수 없음",
        "missing_unit": f"단위가 없음: 이 속성은 단위({canonical})가 필요함",
        "unknown_unit": f"단위 '{unit}'는 온톨로지에 정의되지 않아 환산하지 않음",
        "condition": "조건 표기를 읽을 수 없음",
    }
    return texts.get(reason, str(reason))


def explain_finding(
    onto: Ontology, class_id: str, finding: Finding, unresolved: list[dict[str, Any]]
) -> str:
    """'E2 rated_throughput — 단위 차원 불일치: …': the code stays first for traceability."""
    attributes = ", ".join(finding.attribute_ids)
    head = f"{finding.code} {attributes}"
    if finding.code == "E1":
        return f"{head} — 필수 값이 문서에 없음"
    if finding.code in ("E2", "E3", "REVIEW"):
        rows = [r for r in unresolved if r["attribute"] in finding.attribute_ids]
        reasons = list(dict.fromkeys(explain_unresolved(onto, r) for r in rows))
        return f"{head} — {'; '.join(reasons) or finding.reason}"
    if finding.code == "E4":
        allowed: list[str] = []
        if class_id in onto.classes:
            for name in [*reversed(onto.ancestors(class_id)), class_id]:
                allowed = onto.classes[name].allowed_values.get(finding.attribute_ids[0], allowed)
        return f"{head} — 허용값 밖의 값 (허용: {', '.join(allowed)})"
    if finding.code == "E5":
        count = len(finding.occurrences)
        return f"{head} — 같은 기준·조건·범위에 서로 다른 값이 있음 (출현 {count}곳)"
    return f"{head} — {finding.reason}"


def duplicate_blocker(registry_id: str) -> str:
    return (
        f"동일 제품 {registry_id}이(가) 이미 등록됨 — 기존 제품에 연결하거나, "
        "제조사·모델 값을 고치세요"
    )


CONTEXT_REASONS = {  # the RAG chain's rejection reasons, in the reviewer's words
    "not in the vocabulary": "모델이 제시한 값이 어휘에 없음",
    "no evidence": "모델이 근거 구절을 제시하지 않음",
    "evidence not in the line": "모델의 근거 구절이 원문 줄에 없음",
    "number not in the line": "조건의 숫자가 원문 줄에 없음(사례 값 복사 의심)",
    "wrong unit or form": "조건의 단위·형식이 맞지 않음",
    "phrase not in the remarks": "범위 구절이 비고에 없음",
    "not supported (self-check)": "자기 검토(Self-RAG)에서 원문이 뒷받침하지 않는다고 판정",
    "not an object": "모델 답의 형식이 맞지 않음",
}


def explain_context_reason(onto: Ontology, reason: str) -> str | None:
    """'basis.rating: evidence not in the line' → '기준 rating — 모델의 근거 구절이 원문 줄에
    없음'. None for an axis the ontology does not have (the model invented it; there is
    nothing to check) and for a whole group sent in the wrong shape."""
    if reason.startswith("llm:") or reason.startswith("self-check: llm"):
        return "문맥 확인용 모델 호출이 실패해 문맥을 확인하지 못함"
    field, _, why = reason.partition(": ")
    group, _, axis = field.partition(".")
    vocab = onto.vocabularies
    if group == "basis" and axis in vocab.basis:
        name = f"기준 {axis}"
    elif group == "condition" and axis in vocab.condition:
        name = f"조건 {axis}"
    elif field == "scope":
        name = "범위"
    else:
        return None
    return f"{name} — {CONTEXT_REASONS.get(why, why)}"


def unknown_maker_blocker(maker: str) -> str:
    return (
        f"제조사 '{maker}'이(가) 제조사 목록에 없음 — 새 제조사는 자동으로 추가하지 않음. "
        "원문의 제조사 표기를 확인하세요"
    )
