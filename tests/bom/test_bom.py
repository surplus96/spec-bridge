"""BOM step 1 (D-101): BOM rows -> existing products -> has_component, deterministic."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openpyxl
import pytest
import yaml

from spec_bridge.bom.__main__ import main
from spec_bridge.bom.linker import Pick, apply, candidates, plan, plan_key
from spec_bridge.bom.reader import BomDocument, BomError, read_bom
from spec_bridge.ontology.loader import Ontology
from spec_bridge.registry.store import RegistryStore
from tests.conftest import ROOT

BOMS = ROOT / "data/synth/boms"
REGISTRY = ROOT / "data/synth/registry"
SPLIT_OF = {"BOM-001": "dev", "BOM-002": "test", "BOM-003": "dev", "BOM-004": "test"}


def answer(bom_id: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((BOMS / f"{bom_id}.yaml").read_text())
    return data


def store_for(tmp_path: Path, onto: Ontology, split: str, relations: bool = True) -> RegistryStore:
    s = RegistryStore(tmp_path / f"{split}.sqlite", onto)
    s.load_manufacturers(REGISTRY / "manufacturers.json")
    s.load_jsonl(REGISTRY / f"{split}.jsonl")
    if not relations:
        with s.conn:
            s.conn.execute("DELETE FROM relations WHERE relation_id = 'has_component'")
    return s


@pytest.fixture
def dev(tmp_path: Path, onto: Ontology) -> Iterator[RegistryStore]:
    s = store_for(tmp_path, onto, "dev", relations=False)
    yield s
    s.close()


def as_xlsx(markdown: Path, out: Path) -> Path:
    """The same BOM as an Excel sheet: header cells, then the table."""
    bom = read_bom(markdown)
    book = openpyxl.Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Root model", bom.root_model])
    sheet.append(["Manufacturer", bom.root_maker])
    sheet.append([])
    sheet.append(["Component", "Model", "Manufacturer", "Quantity"])
    for row in bom.rows:
        sheet.append([row.component, row.model, row.maker, row.quantity])
    book.save(out)
    return out


def shape(b: BomDocument) -> tuple[str, str, list[dict[str, Any]]]:
    return b.root_model, b.root_maker, [r.model_dump(exclude={"line"}) for r in b.rows]


def edited(markdown: Path, tmp_path: Path, old: str, new: str) -> Path:
    out = tmp_path / markdown.name
    out.write_text(markdown.read_text().replace(old, new, 1))
    return out


@pytest.mark.parametrize("bom_id", sorted(SPLIT_OF))
def test_markdown_and_excel_read_the_same_rows(bom_id: str, tmp_path: Path) -> None:
    bom = read_bom(BOMS / f"{bom_id}.md")
    gold = answer(bom_id)
    assert bom.root_model == gold["root_model"]
    assert [(r.component, r.model, r.quantity) for r in bom.rows] == [
        (i["class"], i["model_designation"], i["quantity"]) for i in gold["items"]
    ]
    excel = read_bom(as_xlsx(BOMS / f"{bom_id}.md", tmp_path / f"{bom_id}.xlsx"))
    assert shape(excel) == shape(bom)


@pytest.mark.parametrize("bom_id", sorted(SPLIT_OF))
def test_every_row_is_identified_as_the_answer_and_the_seed_already_has_it(
    bom_id: str, tmp_path: Path, onto: Ontology
) -> None:
    gold = answer(bom_id)
    store = store_for(tmp_path, onto, SPLIT_OF[bom_id])
    try:
        result = plan(store, onto, read_bom(BOMS / f"{bom_id}.md"))
        assert result.root_id == gold["root_product_id"]
        assert [r.product_id for r in result.rows] == [i["product_id"] for i in gold["items"]]
        assert {r.status for r in result.rows} == {"existing"} and result.not_in_bom == []
        assert apply(store, result, "reviewer") == 0  # nothing new: nothing written
    finally:
        store.close()


def test_apply_adds_the_relations_once_and_keeps_the_quantities(
    dev: RegistryStore, onto: Ontology
) -> None:
    gold = answer("BOM-001")
    result = plan(dev, onto, read_bom(BOMS / "BOM-001.md"))
    assert {r.status for r in result.rows} == {"new"}
    assert dev.relations_of(result.root_id, "has_component") == []  # a preview writes nothing
    assert apply(dev, result, "reviewer") == 3
    assert dev.relations_of(result.root_id, "has_component") == sorted(
        i["product_id"] for i in gold["items"]
    )
    again = plan(dev, onto, read_bom(BOMS / "BOM-001.md"))
    assert {r.status for r in again.rows} == {"existing"} and apply(dev, again, "reviewer") == 0
    product = dev.product(result.root_id)
    assert product is not None
    (event,) = [e for e in product["events"] if e["event_type"] == "bom_linked"]
    assert [r["quantity"] for r in event["payload"]["rows"]] == [1, 1, 1]
    assert event["payload"]["bom_file"] == "BOM-001.md"
    audits = dev.conn.execute("SELECT kind FROM audit_events").fetchall()
    assert audits == [("bom_linked",)]


def test_rows_that_are_not_found_wait_for_review_and_the_rest_is_applied(
    dev: RegistryStore, onto: Ontology, tmp_path: Path
) -> None:
    gold = answer("BOM-001")
    tc, pump, sep = gold["items"]
    source = BOMS / "BOM-001.md"
    bad = edited(source, tmp_path, f"| {pump['model_designation']} |", "| VX999-999 |")
    result = plan(dev, onto, read_bom(bad))
    statuses = [(r.status, r.product_id) for r in result.rows]
    assert statuses == [("new", tc["product_id"]), ("pending", None), ("new", sep["product_id"])]
    assert "not in the registry" in (result.rows[1].reason or "")
    assert apply(dev, result, "reviewer") == 2
    assert dev.relations_of(result.root_id, "has_component") == sorted(
        [tc["product_id"], sep["product_id"]]
    )


def test_a_row_whose_component_is_not_the_product_class_waits_for_review(
    dev: RegistryStore, onto: Ontology, tmp_path: Path
) -> None:
    pump = answer("BOM-001")["items"][1]
    line = f"| {pump['class']} | {pump['model_designation']} |"
    bad = edited(
        BOMS / "BOM-001.md", tmp_path, line, f"| Separator | {pump['model_designation']} |"
    )
    row = plan(dev, onto, read_bom(bad)).rows[1]
    assert row.status == "pending" and row.product_id is None
    assert "class" in (row.reason or "")


def test_an_unknown_root_refuses_the_whole_bom(
    dev: RegistryStore, onto: Ontology, tmp_path: Path
) -> None:
    gold = answer("BOM-001")
    bad = edited(
        BOMS / "BOM-001.md", tmp_path, f"Root model: {gold['root_model']}", "Root model: VX999-999"
    )
    with pytest.raises(BomError, match="root"):
        plan(dev, onto, read_bom(bad))


def test_an_existing_relation_missing_from_the_bom_is_reported_not_removed(
    tmp_path: Path, onto: Ontology
) -> None:
    gold = answer("BOM-001")
    sep = gold["items"][2]
    store = store_for(tmp_path, onto, "dev")
    try:
        lines = [
            line
            for line in (BOMS / "BOM-001.md").read_text().splitlines()
            if f"| {sep['model_designation']} |" not in line
        ]
        short = tmp_path / "short.md"
        short.write_text("\n".join(lines))
        result = plan(store, onto, read_bom(short))
        assert result.not_in_bom == [sep["product_id"]]
        apply(store, result, "reviewer")
        assert sep["product_id"] in store.relations_of(result.root_id, "has_component")
    finally:
        store.close()


@pytest.mark.parametrize(
    ("old", "new", "why"),
    [
        ("| Component | Model | Manufacturer | Quantity |", "| Part | Model |", "columns"),
        ("Root model:", "Top model:", "Root model"),
        ("| 1 |", "| one |", "quantity"),
        ("| 1 |", "| 0 |", "quantity"),
    ],
)
def test_a_bom_that_cannot_be_read_is_refused(tmp_path: Path, old: str, new: str, why: str) -> None:
    with pytest.raises(BomError, match=why):
        read_bom(edited(BOMS / "BOM-001.md", tmp_path, old, new))


def test_other_file_types_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_text("a,b\n")
    with pytest.raises(BomError, match="xlsx or .md"):
        read_bom(path)


def test_the_command_previews_unless_asked_to_apply(
    dev: RegistryStore, onto: Ontology, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = Path(dev.conn.execute("PRAGMA database_list").fetchone()[2])
    root = plan(dev, onto, read_bom(BOMS / "BOM-001.md")).root_id
    main([str(BOMS / "BOM-001.md"), "--registry", str(path)])
    shown = json.loads(capsys.readouterr().out)
    assert shown["applied"] is False and [r["status"] for r in shown["rows"]] == ["new"] * 3
    assert dev.relations_of(root, "has_component") == []
    main([str(BOMS / "BOM-001.md"), "--registry", str(path), "--apply"])
    assert json.loads(capsys.readouterr().out)["added"] == 3
    assert len(dev.relations_of(root, "has_component")) == 3


def test_a_bom_document_is_a_plain_model() -> None:
    bom = read_bom(BOMS / "BOM-001.md")
    assert BomDocument.model_validate(bom.model_dump()) == bom


# step 2 (D-103): reviewer picks, candidates, a fingerprint for stale previews ---------
def typo_bom(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    pump = answer("BOM-001")["items"][1]
    return edited(
        BOMS / "BOM-001.md", tmp_path, f"| {pump['model_designation']} |", "| VX999-999 |"
    ), pump


def test_a_pending_row_lists_the_products_of_its_class_as_candidates(
    dev: RegistryStore, onto: Ontology, tmp_path: Path
) -> None:
    path, pump = typo_bom(tmp_path)
    row = plan(dev, onto, read_bom(path)).rows[1]
    found = candidates(dev, onto, row.row)
    assert pump["product_id"] in [c["product_id"] for c in found]
    assert {c["class_id"] for c in found} == {pump["class"]}


def test_a_reviewer_pick_links_a_pending_row_and_is_marked_as_the_reviewers(
    dev: RegistryStore, onto: Ontology, tmp_path: Path
) -> None:
    path, pump = typo_bom(tmp_path)
    line = plan(dev, onto, read_bom(path)).rows[1].row.line
    pick = Pick(line=line, product_id=pump["product_id"], reason="model typo in the BOM")
    result = plan(dev, onto, read_bom(path), [pick])
    row = result.rows[1]
    assert (row.status, row.product_id, row.decided_by) == ("new", pump["product_id"], "reviewer")
    assert row.reason == "model typo in the BOM"
    assert [r.decided_by for r in result.rows] == ["rule", "reviewer", "rule"]
    assert apply(dev, result, "reviewer", {"bom_id": "B1"}) == 3
    product = dev.product(result.root_id)
    assert product is not None
    (event,) = [e for e in product["events"] if e["event_type"] == "bom_linked"]
    assert event["payload"]["bom_id"] == "B1"
    assert event["payload"]["rows"][1]["decided_by"] == "reviewer"


@pytest.mark.parametrize("problem", ["other class", "unknown product", "found row", "no line"])
def test_a_pick_that_does_not_fit_is_refused(
    problem: str, dev: RegistryStore, onto: Ontology, tmp_path: Path
) -> None:
    path, pump = typo_bom(tmp_path)
    rows = plan(dev, onto, read_bom(path)).rows
    sep = answer("BOM-001")["items"][2]
    pick = {
        "other class": Pick(line=rows[1].row.line, product_id=sep["product_id"], reason="x"),
        "unknown product": Pick(line=rows[1].row.line, product_id="REG-NONE", reason="x"),
        "found row": Pick(line=rows[0].row.line, product_id=pump["product_id"], reason="x"),
        "no line": Pick(line=999, product_id=pump["product_id"], reason="x"),
    }[problem]
    with pytest.raises(BomError):
        plan(dev, onto, read_bom(path), [pick])


def test_the_fingerprint_changes_when_the_registry_changes(
    dev: RegistryStore, onto: Ontology
) -> None:
    bom = read_bom(BOMS / "BOM-001.md")
    first = plan(dev, onto, bom)
    assert plan_key(plan(dev, onto, bom)) == plan_key(first)  # same registry, same plan
    apply(dev, first, "reviewer")
    assert plan_key(plan(dev, onto, bom)) != plan_key(first)  # new -> existing
