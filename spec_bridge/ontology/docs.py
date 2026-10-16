"""Generate the ontology definition document (O2) from ontology/ontology.yaml.

Run: uv run python -m spec_bridge.ontology.docs
"""

from pathlib import Path

from spec_bridge.ontology.loader import Ontology, load_ontology

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ontology/ontology.yaml"
OUTPUT = ROOT / "docs/ontology/definition.md"


def row(*cells: object) -> str:
    return "| " + " | ".join("—" if c in (None, "", []) else str(c) for c in cells) + " |"


def render_class(onto: Ontology, class_id: str) -> list[str]:
    cls = onto.classes[class_id]
    chain = " → ".join([class_id, *onto.ancestors(class_id)])
    lines = [f"### {class_id}", "", f"상속: {chain}", ""]
    lines.append(row("속성", "자료형", "정규 단위", "차원", "필수"))
    lines.append(row("---", "---", "---", "---", "---"))
    conditional = {a for r in cls.conditional_required for a in r.required_all}
    conditional |= {a for r in cls.conditional_required for g in r.required_any_groups for a in g}
    grouped = {a for g in cls.required_any_groups for a in g}
    for attr_id in onto.attributes_of(class_id):
        attr = onto.attributes[attr_id]
        datatype = attr.datatype if isinstance(attr.datatype, str) else " / ".join(attr.datatype)
        if attr_id in cls.required_all:
            need = "필수"
        elif attr_id in grouped:
            need = "그룹 필수"
        elif attr_id in conditional:
            need = "조건부"
        else:
            need = ""
        lines.append(row(attr_id, datatype, attr.canonical_unit, attr.dimension, need))
    lines.append("")
    for rule in cls.conditional_required:
        when = ", ".join(f"{k} = {v}" for k, v in rule.when.items())
        needs = rule.required_all + [" 또는 ".join(g) for g in rule.required_any_groups]
        lines.append(f"- 조건부: {when}이면 {', '.join(needs)}")
    for group in cls.required_any_groups:
        lines.append(f"- 하나 이상 필수: {' 또는 '.join(group)}")
    for attr_id, values in cls.allowed_values.items():
        lines.append(f"- {attr_id} 허용값(합성 닫힌 목록): {', '.join(values)}")
    lines.append("")
    return lines


def render_definition_markdown(onto: Ontology) -> str:
    leaves = [c for c, d in onto.classes.items() if not d.abstract]
    abstract = [c for c, d in onto.classes.items() if d.abstract]
    lines = [
        "# 온톨로지 정의서",
        "",
        f"자동 생성 문서 — 원본 `ontology/ontology.yaml` (version {onto.version}, "
        f"origin {onto.origin}). 직접 수정하지 말고 YAML을 고친 뒤 "
        "`uv run python -m spec_bridge.ontology.docs`로 다시 만든다.",
        "",
        "클래스 구조와 필수 정책은 프로젝트가 정한 합성 등록 정책이며 업계 표준 분류나 "
        "실제 법적·기술적 필수 요건이 아니다.",
        "",
        "## 클래스",
        "",
        f"상위 클래스: {', '.join(abstract)}",
        "",
    ]
    for class_id in leaves:
        lines += render_class(onto, class_id)
    lines += ["## 라벨 별칭", "", row("라벨", "속성", "구분", "출처", "위치", "검증자")]
    lines.append(row("---", "---", "---", "---", "---", "---"))
    for alias in onto.label_aliases:
        kind = "합성" if alias.origin == "synthetic" else "출처 기반"
        where = ", ".join(f"{k} {v}" for k, v in (alias.location or {}).items())
        verified = alias.verified_by or "미검증"
        lines.append(row(alias.label, alias.attribute, kind, alias.source, where, verified))
    lines += ["", "## 조건·기준 어휘", ""]
    for key, values in onto.vocabularies.basis.items():
        lines.append(f"- basis.{key}: {', '.join(values)}")
    for key, cond in onto.vocabularies.condition.items():
        if cond.kind == "token":
            detail = ", ".join(cond.values)
        else:
            detail = f"{cond.kind} ({cond.dimension})"
        lines.append(f"- condition.{key}: {detail}")
    lines += ["", "## 단위", "", row("표기", "pint"), row("---", "---")]
    lines += [row(unit, spec.pint) for unit, spec in onto.units.items()]
    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_definition_markdown(load_ontology(SOURCE)))
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
