"""W5-3: registrations, links, edits and audit in the registry store (D-063, D-064)."""

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.dedup.matcher import match
from spec_bridge.graph.registration import (
    GraphDeps,
    build_graph,
    open_checkpointer,
    prompt_of,
    result_of,
    resume,
    start,
    state_of,
)
from spec_bridge.ontology.loader import Ontology
from spec_bridge.registry.identity import MakerIndex
from spec_bridge.registry.output import RegistrationResult
from spec_bridge.registry.store import SCHEMA_VERSION, RegistryError, RegistryStore
from tests.api.test_app import service_with
from tests.conftest import ROOT
from tests.eval.test_experiment import FAST, classify_reply
from tests.graph.test_registration import CLEAN, DUPLICATE, add_values_from_the_document

REGISTRY = ROOT / "data/synth/registry"
MAKERS = json.loads((REGISTRY / "manufacturers.json").read_text())


@pytest.fixture
def store(tmp_path: Path, onto: Ontology) -> Iterator[RegistryStore]:
    s = RegistryStore(tmp_path / "registry.sqlite", onto)
    s.load_manufacturers(REGISTRY / "manufacturers.json")
    s.load_jsonl(REGISTRY / "dev.jsonl")
    yield s
    s.close()


def reviewed(
    tmp_path: Path, store: RegistryStore, doc_id: str, job_id: str
) -> tuple[Any, list[dict[str, Any]]]:
    """A job on the graph with the store as registrar, values added as in S1."""
    service = service_with([classify_reply(doc_id), {"facts": []}])
    deps = GraphDeps(
        service.onto,
        service.normalizer,
        service.provider,
        None,
        service.makers,
        store.records,
        store,
    )
    graph = build_graph(deps, open_checkpointer(tmp_path / "checkpoints.sqlite"))
    path = FAST[doc_id][0]
    start(graph, job_id, path, doc_id, path.name)
    add_values_from_the_document(graph, doc_id, job_id)
    return graph, state_of(graph, job_id).get("edits", [])


def register_clean(tmp_path: Path, store: RegistryStore) -> tuple[Any, str]:
    graph, _ = reviewed(tmp_path, store, CLEAN, "J")
    shown = prompt_of(graph, "J")
    assert shown is not None and "register_new" in shown["allowed"]
    resume(graph, "J", {"action": "register_new", "revision": shown["revision"]})
    product_id = state_of(graph, "J")["product_id"]
    assert product_id is not None
    return graph, product_id


def test_s1_registration_keeps_evidence_edits_and_the_standard_json(
    tmp_path: Path, store: RegistryStore
) -> None:
    before = store.count("products")
    graph, product_id = register_clean(tmp_path, store)
    state = state_of(graph, "J")
    product = store.product(product_id)
    assert product is not None and store.count("products") == before + 1
    assert product["origin"] == "user_registered" and product["class_id"] == state["class_id"]
    assert product["maker_name"]  # the registered name, not only its id
    edit_ids = {e["edit_id"] for e in state["edits"]}
    assert {e["edit_id"] for e in product["edits"]} == edit_ids
    kinds = {f["attribute"]: f["evidence_kind"] for f in product["facts"]}
    assert set(kinds.values()) <= {"observed", "human_edit"}
    for fact in product["facts"]:  # NFR-07: every value points at a place or an edit
        if fact["evidence_kind"] == "human_edit":
            assert fact["evidence_ref"] in edit_ids
        else:
            ref = json.loads(fact["evidence_ref"])
            assert ref["document_id"] == CLEAN and ref["occurrences"]
    added = {e["attribute"] for e in state["edits"]}
    assert all(kinds[a] == "human_edit" for a in added)
    (event,) = product["events"]
    assert event["event_type"] == "registered"
    RegistrationResult.model_validate(event["payload"]["result"])  # the standard JSON


def test_registering_twice_makes_one_product(tmp_path: Path, store: RegistryStore) -> None:
    graph, product_id = register_clean(tmp_path, store)
    count = store.count("products")
    result = result_of(state_of(graph, "J"), {})
    assert store.register("J", result, state_of(graph, "J")["edits"]) == product_id
    assert store.count("products") == count


def test_s2_the_registered_product_is_now_a_duplicate_and_is_linked(
    tmp_path: Path, store: RegistryStore
) -> None:
    graph, product_id = register_clean(tmp_path, store)
    facts_before = store.product(product_id)["facts"]  # type: ignore[index]

    again, _ = reviewed(tmp_path / "second", store, CLEAN, "J2")
    shown = prompt_of(again, "J2")
    assert shown is not None and "register_new" not in shown["allowed"]
    assert any(b.startswith(f"동일 제품 {product_id}") for b in shown["blockers"])
    command = {"action": "link", "revision": shown["revision"], "target_id": product_id}
    resume(again, "J2", command)

    product = store.product(product_id)
    assert product is not None and product["facts"] == facts_before  # no automatic merge
    assert [e["event_type"] for e in product["events"]] == ["registered", "linked_document"]
    assert product["events"][1]["payload"]["relation"] == "duplicate"


def test_a_duplicate_identity_is_refused_and_nothing_is_written(
    tmp_path: Path, store: RegistryStore
) -> None:
    graph, _ = reviewed(tmp_path, store, DUPLICATE, "J")
    result = result_of(state_of(graph, "J"), {})
    counts = [store.count(t) for t in ("products", "product_facts", "human_edits")]
    with pytest.raises(RegistryError, match="동일 식별: REG-COMP-009"):
        store.register("J", result, state_of(graph, "J")["edits"])
    assert [store.count(t) for t in ("products", "product_facts", "human_edits")] == counts


def test_a_value_without_a_document_place_is_refused(tmp_path: Path, store: RegistryStore) -> None:
    graph, _ = reviewed(tmp_path, store, CLEAN, "J")
    result = result_of(state_of(graph, "J"), {})
    stripped = result.model_copy(update={"facts": [{**f, "occurrences": []} for f in result.facts]})
    with pytest.raises(RegistryError, match="원문 위치가 없는 값"):
        store.register("J", stripped, [])


def _without(facts: list[dict[str, Any]], attribute: str) -> list[dict[str, Any]]:
    return [f for f in facts if f["attribute"] != attribute]


def _replaced(facts: list[dict[str, Any]], attribute: str, value: Any) -> list[dict[str, Any]]:
    return [{**f, "value": value} if f["attribute"] == attribute else f for f in facts]


@pytest.mark.parametrize(
    ("change", "refusal"),
    [
        (lambda r, o: {"facts": _without(r.facts, "maker")}, "식별할 수 없음"),
        (lambda r, o: {"facts": _without(r.facts, "model_designation")}, "식별할 수 없음"),
        (
            lambda r, o: {"facts": _replaced(r.facts, "maker", "No Such Maker")},
            "제조사 목록에 없음",
        ),
        (
            lambda r, o: {"class_id": next(c for c, v in o.classes.items() if v.abstract)},
            "말단 클래스가 아님",
        ),
        (lambda r, o: {"class_id": "NoSuchClass"}, "말단 클래스가 아님"),
        (
            lambda r, o: {"facts": _replaced(r.facts, "number_of_cylinders", "six")},
            "정의에 맞지 않음",
        ),
    ],
    ids=["no-maker", "no-model", "unknown-maker", "abstract-class", "unknown-class", "bad-value"],
)
def test_register_itself_refuses_what_review_should_have_blocked(
    tmp_path: Path, store: RegistryStore, onto: Ontology, change: Any, refusal: str
) -> None:
    """The store is the last guard: a result that slipped past the review is still refused
    and nothing is written."""
    graph, _ = reviewed(tmp_path, store, CLEAN, "J")
    result = result_of(state_of(graph, "J"), {})
    broken = result.model_copy(update=change(result, onto))
    counts = [store.count(t) for t in ("products", "product_facts", "registration_events")]
    with pytest.raises(RegistryError, match=refusal):
        store.register("J", broken, [])
    assert [store.count(t) for t in ("products", "product_facts", "registration_events")] == counts


def test_link_is_idempotent_and_needs_a_registered_target(
    tmp_path: Path, store: RegistryStore
) -> None:
    graph, _ = reviewed(tmp_path, store, DUPLICATE, "J")
    result = result_of(state_of(graph, "J"), {})
    store.link("J", "REG-COMP-009", result, [])
    store.link("J", "REG-COMP-009", result, [])
    events = store.product("REG-COMP-009")["events"]  # type: ignore[index]
    assert [e["event_type"] for e in events] == ["seed_import", "linked_document"]
    with pytest.raises(RegistryError, match="등록된 제품이 아님"):
        store.link("J", "REG-NOPE", result, [])


def test_records_match_like_the_seed_file(store: RegistryStore) -> None:
    """Matching against the store gives the judgements matching against dev.jsonl gives."""
    seed = [json.loads(line) for line in (REGISTRY / "dev.jsonl").read_text().splitlines()]
    makers = MakerIndex(MAKERS)
    names = {m["maker_id"]: m["name"] for m in MAKERS}
    stored = store.records()
    for record in seed:
        facts = [{"attribute": a, **f} for a, fs in record["attributes"].items() for f in fs] + [
            {"attribute": "maker", "value": names[record["maker_id"]]}
        ]
        expected = match(record["class"], facts, seed, makers)
        got = match(record["class"], facts, stored, makers)
        key = lambda m: m.registry_id  # noqa: E731
        assert sorted(got, key=key) == sorted(expected, key=key)


def test_a_schema_1_file_is_migrated_without_touching_the_seed(
    tmp_path: Path, onto: Ontology
) -> None:
    path = tmp_path / "old.sqlite"
    s = RegistryStore(path, onto)
    s.load_manufacturers(REGISTRY / "manufacturers.json")
    s.load_jsonl(REGISTRY / "dev.jsonl")
    s.close()
    with sqlite3.connect(path) as conn:  # make it look like a W1 file
        conn.execute("DROP TABLE human_edits")
        conn.execute("DROP TABLE audit_events")
        conn.execute("UPDATE schema_meta SET value = '1' WHERE key = 'schema_version'")
    conn.close()

    s = RegistryStore(path, onto)
    try:
        seed = (REGISTRY / "dev.jsonl").read_text().splitlines()
        assert s.count("products") == len(s.records()) == len(seed)
        assert s.count("human_edits") == 0 and s.count("audit_events") == 0
        version = s.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert version == (SCHEMA_VERSION,)
    finally:
        s.close()


def test_audit_rows_are_kept(store: RegistryStore) -> None:
    store.audit("J", "uploaded", "reviewer", {"file_name": "a.xlsx"})
    assert store.count("audit_events") == 1


SCHEMA_2_EDITS = """CREATE TABLE human_edits (
    edit_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
    product_id TEXT REFERENCES products(product_id),
    attribute_id TEXT NOT NULL, op TEXT NOT NULL CHECK (op IN ('set', 'add', 'remove')),
    before_json TEXT NOT NULL, after_json TEXT NOT NULL, outcome TEXT NOT NULL,
    reason TEXT NOT NULL, actor TEXT NOT NULL, occurred_at TEXT NOT NULL)"""


def edit_row(edit_id: str, op: str) -> dict[str, Any]:
    return {
        "edit_id": edit_id,
        "attribute": "rated_power",
        "op": op,
        "before": None,
        "after": None,
        "outcome": "removed",
        "reason": "test",
        "at": "t",
    }


def test_a_schema_2_file_is_migrated_and_keeps_its_edits(tmp_path: Path, onto: Ontology) -> None:
    """D-100: schema 3 lets the edit table hold context edits; old rows are kept."""
    path = tmp_path / "old.sqlite"
    RegistryStore(path, onto).close()
    with sqlite3.connect(path) as conn:  # make it look like a W5 file
        conn.execute("DROP TABLE human_edits")
        conn.execute(SCHEMA_2_EDITS)
        conn.execute(
            "INSERT INTO human_edits VALUES ('J-E1', 'J', NULL, 'rated_power', 'set',"
            " 'null', 'null', 'fact', 'old', 'reviewer', 't')"
        )
        conn.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")
    conn.close()

    s = RegistryStore(path, onto)
    try:
        assert s.conn.execute("SELECT edit_id, reason FROM human_edits").fetchall() == [
            ("J-E1", "old")
        ]
        with s.conn:
            s._edit_rows("J", None, [edit_row("J-E2", "context")], "reviewer")
        assert s.count("human_edits") == 2
        version = s.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert version == (SCHEMA_VERSION,)
    finally:
        s.close()


def test_an_edit_row_the_table_refuses_is_an_error_not_skipped(store: RegistryStore) -> None:
    """A refused row used to vanish under INSERT OR IGNORE; only a repeat is skipped now."""
    with store.conn:
        store._edit_rows("J", None, [edit_row("J-E1", "set")], "reviewer")
        store._edit_rows("J", None, [edit_row("J-E1", "set")], "reviewer")  # idempotent
    assert store.count("human_edits") == 1
    with pytest.raises(sqlite3.IntegrityError), store.conn:
        store._edit_rows("J", None, [edit_row("J-E2", "not an op")], "reviewer")


# production audit 1 (D-116): a copy of the file is kept before a schema migration -------
def schema_2_file(tmp_path: Path, onto: Ontology) -> Path:
    path = tmp_path / "old.sqlite"
    RegistryStore(path, onto).close()
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE human_edits")
        conn.execute(SCHEMA_2_EDITS)
        conn.execute(
            "INSERT INTO human_edits VALUES ('J-E1', 'J', NULL, 'rated_power', 'set',"
            " 'null', 'null', 'fact', 'old', 'reviewer', 't')"
        )
        conn.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")
    conn.close()
    return path


def test_a_migration_keeps_a_backup_of_the_file_as_it_was(tmp_path: Path, onto: Ontology) -> None:
    path = schema_2_file(tmp_path, onto)
    RegistryStore(path, onto).close()
    (backup,) = list(tmp_path.glob("old.sqlite.schema2-backup-*"))
    with sqlite3.connect(backup) as conn:
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        rows = conn.execute("SELECT edit_id, reason FROM human_edits").fetchall()
        (create,) = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'human_edits'"
        ).fetchone()
    conn.close()
    assert version == ("2",) and rows == [("J-E1", "old")]
    assert "'context'" not in create  # the copy is from before the migration


def test_no_backup_without_a_migration(tmp_path: Path, onto: Ontology) -> None:
    path = tmp_path / "new.sqlite"
    RegistryStore(path, onto).close()  # a new file
    RegistryStore(path, onto).close()  # the current schema
    assert list(tmp_path.glob("*backup*")) == []
