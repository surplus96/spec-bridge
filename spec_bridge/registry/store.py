"""SQLite registry of existing products (FR-03, D-021) and new registrations (W5-3).

Build: uv run python -m spec_bridge.registry.store dev

Schema 2 (D-064) adds the reviewer's edits and an audit table. A schema-1 file is
migrated in place: the new tables are created and nothing else changes.
Schema 3 (D-100) lets the edit table hold context edits (op 'context'). SQLite cannot
change a CHECK in place, so a schema-2 file gets its edit table rebuilt, rows kept.
Before any migration the file is copied as it was, next to it
(`<name>.schema<old>-backup-<UTC time>`, D-116): registrations and edits made in the app
are not in the seed and could not be rebuilt otherwise.
"""

import hashlib
import json
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from spec_bridge.ontology.loader import Ontology, load_ontology
from spec_bridge.ontology.schema import build_candidate_model
from spec_bridge.registry.identity import MakerIndex, maker_key, model_key
from spec_bridge.registry.output import RegistrationResult

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "3"
MIGRATES_FROM = {"1", "2"}  # schema versions opened in place (new tables, rebuilt edit table)

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manufacturers (
    maker_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, origin TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manufacturer_aliases (
    alias_key TEXT PRIMARY KEY,
    maker_id TEXT NOT NULL REFERENCES manufacturers(maker_id),
    alias_text TEXT NOT NULL, origin TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY, class_id TEXT NOT NULL,
    maker_id TEXT NOT NULL REFERENCES manufacturers(maker_id),
    model_designation TEXT NOT NULL, model_key TEXT NOT NULL,
    origin TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE (maker_id, model_key));
CREATE TABLE IF NOT EXISTS product_facts (
    fact_pk INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    attribute_id TEXT NOT NULL, value_json TEXT NOT NULL, unit TEXT,
    basis_json TEXT NOT NULL, condition_json TEXT NOT NULL, scope TEXT NOT NULL,
    evidence_kind TEXT NOT NULL
        CHECK (evidence_kind IN ('registry_seed', 'observed', 'human_edit')),
    evidence_ref TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relations (
    product_id TEXT NOT NULL REFERENCES products(product_id),
    relation_id TEXT NOT NULL CHECK (relation_id IN ('has_component', 'variant_of')),
    target_product_id TEXT NOT NULL
        REFERENCES products(product_id) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY (product_id, relation_id, target_product_id));
CREATE TABLE IF NOT EXISTS registration_events (
    event_id INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    event_type TEXT NOT NULL, actor TEXT NOT NULL, occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS human_edits (
    edit_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
    product_id TEXT REFERENCES products(product_id),
    attribute_id TEXT NOT NULL, op TEXT NOT NULL CHECK (op IN ('set', 'add', 'remove', 'context')),
    before_json TEXT NOT NULL, after_json TEXT NOT NULL, outcome TEXT NOT NULL,
    reason TEXT NOT NULL, actor TEXT NOT NULL, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_events (
    audit_pk INTEGER PRIMARY KEY, job_id TEXT NOT NULL, kind TEXT NOT NULL,
    actor TEXT NOT NULL, occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL);
"""


class RegistryError(ValueError):
    """A registry record conflicts with the store or the ontology."""


def canonical(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stored_schema(path: Path) -> str | None:
    """The schema version a registry file was written with, without changing the file."""
    if not path.is_file():
        return None
    uri = f"{path.resolve().as_uri()}?mode=ro"  # as_uri escapes '#', '?' and '%'
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        has_meta = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
        ).fetchone()
        row = (
            conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
            if has_meta
            else None
        )
    return None if row is None else str(row[0])


def backup_before_migration(path: Path) -> Path | None:
    """A consistent copy of a file about to be migrated (D-116); None when nothing migrates."""
    old = stored_schema(path)
    if old is None or old not in MIGRATES_FROM:
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.schema{old}-backup-{stamp}")
    with sqlite3.connect(path) as source, sqlite3.connect(target) as copy:
        source.backup(copy)
    source.close()
    copy.close()
    return target


class RegistryStore:
    def __init__(self, path: Path, onto: Ontology) -> None:
        self.onto = onto
        self.backup = backup_before_migration(path)  # before anything touches the file
        # The job API calls from request and worker threads, one at a time (a lock in
        # spec_bridge.api.jobs); sqlite3 only needs to be told it may.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        expected = {"schema_version": SCHEMA_VERSION, "ontology_version": str(onto.version)}
        stored = dict(self.conn.execute("SELECT key, value FROM schema_meta").fetchall())
        if not stored:
            with self.conn:
                for key, value in expected.items():
                    self._meta(key, value)
            return
        if stored.get("schema_version") in MIGRATES_FROM:
            with self.conn:  # the CREATE IF NOT EXISTS above added the new tables
                # sqlite3 opens no transaction before DDL: begin one, so a failed copy also
                # undoes the rename and the new table (the edits stay where they were)
                self.conn.execute("BEGIN")
                self._rebuild_edit_table()
                self._meta("schema_version", SCHEMA_VERSION)
            stored["schema_version"] = SCHEMA_VERSION
        stale = {k: stored.get(k) for k, v in expected.items() if stored.get(k) != v}
        if stale:
            self.conn.close()
            raise RegistryError(
                f"{path}: built with {stale}, expected {expected}; rebuild the registry "
                "(uv run python -m spec_bridge.registry.store <split>)"
            )

    def close(self) -> None:
        self.conn.close()

    def _rebuild_edit_table(self) -> None:
        """Schema 2 → 3: the edit table with the current CHECK, every row kept."""
        (old,) = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'human_edits'"
        ).fetchone()
        if "'context'" in old:
            return
        start = SCHEMA.index("CREATE TABLE IF NOT EXISTS human_edits")
        create = SCHEMA[start : SCHEMA.index(";", start)]
        self.conn.execute("ALTER TABLE human_edits RENAME TO human_edits_schema2")
        self.conn.execute(create)
        self.conn.execute("INSERT INTO human_edits SELECT * FROM human_edits_schema2")
        self.conn.execute("DROP TABLE human_edits_schema2")

    def _meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO schema_meta VALUES (?, ?)", (key, value))

    def count(self, table: str) -> int:
        row = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0])

    def load_manufacturers(self, path: Path) -> int:
        """Load makers in one transaction; returns how many were new.

        Rejects a name/alias owned by another maker (in the file or already in the DB)
        and a changed definition of an existing maker; identical reloads are no-ops.
        """
        makers: list[dict[str, Any]] = json.loads(path.read_text())
        MakerIndex(makers)  # rejects a name shared by two makers within the file
        owners = dict(self.conn.execute("SELECT alias_key, maker_id FROM manufacturer_aliases"))
        added = 0
        with self.conn:
            for m in makers:
                names = {maker_key(t): t for t in [m["name"], *m.get("aliases", [])]}
                for key, text in names.items():
                    if owners.get(key, m["maker_id"]) != m["maker_id"]:
                        raise RegistryError(f"maker name {text!r} is shared with {owners[key]}")
                if self._maker_exists(m["maker_id"]):
                    wanted = (m["name"], m["origin"], set(names))
                    if self._maker_content(m["maker_id"]) != wanted:
                        raise RegistryError(
                            f"{m['maker_id']}: already loaded with different content"
                        )
                    continue
                self.conn.execute(
                    "INSERT INTO manufacturers VALUES (?, ?, ?)",
                    (m["maker_id"], m["name"], m["origin"]),
                )
                for key, text in names.items():
                    self.conn.execute(
                        "INSERT INTO manufacturer_aliases VALUES (?, ?, ?, ?)",
                        (key, m["maker_id"], text, m["origin"]),
                    )
                    owners[key] = m["maker_id"]
                added += 1
        return added

    def _maker_exists(self, maker_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM manufacturers WHERE maker_id = ?", (maker_id,))
        return row.fetchone() is not None

    def _maker_content(self, maker_id: str) -> tuple[str, str, set[str]]:
        name, origin = self.conn.execute(
            "SELECT name, origin FROM manufacturers WHERE maker_id = ?", (maker_id,)
        ).fetchone()
        keys = self.conn.execute(
            "SELECT alias_key FROM manufacturer_aliases WHERE maker_id = ?", (maker_id,)
        )
        return str(name), str(origin), {str(k) for (k,) in keys}

    def resolve_maker(self, text: str) -> str | None:
        row = self.conn.execute(
            "SELECT maker_id FROM manufacturer_aliases WHERE alias_key = ?", (maker_key(text),)
        ).fetchone()
        return None if row is None else str(row[0])

    def load_jsonl(self, path: Path) -> int:
        """Load seed products in one transaction; returns how many were new."""
        records = [json.loads(line) for line in path.read_text().splitlines() if line]
        added = 0
        with self.conn:  # commits on success, rolls back everything on error
            for record in records:
                added += self._load_record(record, path.name)
            self._meta(f"source_sha256:{path.name}", hashlib.sha256(path.read_bytes()).hexdigest())
        return added

    def _load_record(self, record: dict[str, Any], source: str) -> int:
        product_id = record["product_id"]
        key = f"seed:{product_id}:{hashlib.sha256(canonical(record).encode()).hexdigest()}"
        if self.conn.execute(
            "SELECT 1 FROM registration_events WHERE idempotency_key = ?", (key,)
        ).fetchone():
            return 0
        if self.conn.execute(
            "SELECT 1 FROM products WHERE product_id = ?", (product_id,)
        ).fetchone():
            raise RegistryError(f"{product_id}: already registered with different content")
        model = build_candidate_model(self.onto, record["class"], registered=True)
        try:
            validated = model.model_validate({"attributes": record["attributes"]})
        except ValidationError as exc:
            raise RegistryError(f"{product_id}: {exc}") from exc
        self._check_identity(record, validated.model_dump()["attributes"])
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                product_id,
                record["class"],
                record["maker_id"],
                record["model_designation"],
                model_key(record["model_designation"]),
                record["origin"],
                now,
            ),
        )
        for attr_id, facts in validated.model_dump()["attributes"].items():
            for fact in facts:
                self.conn.execute(
                    "INSERT INTO product_facts (product_id, attribute_id, value_json, unit,"
                    " basis_json, condition_json, scope, evidence_kind, evidence_ref)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 'registry_seed', ?)",
                    (
                        product_id,
                        attr_id,
                        canonical(fact["value"]),
                        fact["unit"],
                        canonical(fact["basis"]),
                        canonical(fact["condition"]),
                        fact["scope"],
                        source,
                    ),
                )
        for relation_id in ("has_component", "variant_of"):
            targets = record["relations"].get(relation_id) or []
            for target in [targets] if isinstance(targets, str) else targets:
                self.conn.execute(
                    "INSERT INTO relations VALUES (?, ?, ?)", (product_id, relation_id, target)
                )
        self.conn.execute(
            "INSERT INTO registration_events (product_id, event_type, actor, occurred_at,"
            " payload_json, idempotency_key) VALUES (?, 'seed_import', 'loader', ?, ?, ?)",
            (product_id, now, canonical({"source": source}), key),
        )
        return 1

    def _check_identity(self, record: dict[str, Any], facts: dict[str, Any]) -> None:
        """The product's natural key must agree with its maker/model facts (R2)."""
        product_id, key = record["product_id"], model_key(record["model_designation"])
        for fact in facts.get("model_designation", []):
            if model_key(fact["value"]) != key:
                raise RegistryError(
                    f"{product_id}: identity mismatch, model {record['model_designation']!r}"
                    f" vs fact {fact['value']!r}"
                )
        for fact in facts.get("maker", []):
            if self.resolve_maker(fact["value"]) != record["maker_id"]:
                raise RegistryError(
                    f"{product_id}: identity mismatch, maker {record['maker_id']!r}"
                    f" vs fact {fact['value']!r}"
                )

    def find_by_identity(self, maker_text: str, model_text: str) -> str | None:
        row = self.conn.execute(
            "SELECT p.product_id FROM products p"
            " JOIN manufacturer_aliases a ON a.maker_id = p.maker_id"
            " WHERE a.alias_key = ? AND p.model_key = ?",
            (maker_key(maker_text), model_key(model_text)),
        ).fetchone()
        return None if row is None else str(row[0])

    # BOM relations (D-101) -----------------------------------------------------------------
    def product_class(self, product_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT class_id FROM products WHERE product_id = ?", (product_id,)
        ).fetchone()
        return None if row is None else str(row[0])

    def relations_of(self, product_id: str, relation_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT target_product_id FROM relations WHERE product_id = ? AND relation_id = ?"
            " ORDER BY target_product_id",
            (product_id, relation_id),
        )
        return [str(r[0]) for r in rows]

    def parents_of(self, product_id: str, relation_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT product_id FROM relations WHERE target_product_id = ? AND relation_id = ?"
            " ORDER BY product_id",
            (product_id, relation_id),
        )
        return [str(r[0]) for r in rows]

    def identities(self) -> list[dict[str, Any]]:
        """Every product's identity (id, class, maker, model) for searching a BOM row (D-108)."""
        rows = self.conn.execute(
            "SELECT p.product_id, p.class_id, p.maker_id, m.name, p.model_designation"
            " FROM products p JOIN manufacturers m ON m.maker_id = p.maker_id"
            " ORDER BY p.product_id"
        )
        keys = ("product_id", "class_id", "maker_id", "maker_name", "model_designation")
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def maker_aliases(self) -> dict[str, list[str]]:
        """Other names of each maker (its registered name left out), for BOM suggestions."""
        out: dict[str, list[str]] = {}
        for maker_id, alias, name in self.conn.execute(
            "SELECT a.maker_id, a.alias_text, m.name FROM manufacturer_aliases a"
            " JOIN manufacturers m ON m.maker_id = a.maker_id ORDER BY a.maker_id, a.alias_text"
        ):
            names = out.setdefault(str(maker_id), [])
            if alias != name:
                names.append(str(alias))
        return out

    def products_in_classes(self, classes: list[str]) -> list[dict[str, Any]]:
        """Products of the given classes with their maker's name, by product id."""
        marks = ", ".join("?" for _ in classes) or "NULL"
        rows = self.conn.execute(
            "SELECT p.product_id, p.class_id, p.model_designation, m.name FROM products p"
            f" JOIN manufacturers m ON m.maker_id = p.maker_id WHERE p.class_id IN ({marks})"
            " ORDER BY p.product_id",
            classes,
        )
        keys = ("product_id", "class_id", "model_designation", "maker_name")
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def add_components(
        self, product_id: str, targets: list[str], actor: str, payload: dict[str, Any]
    ) -> int:
        """Add has_component relations in one transaction; returns how many were new.
        Existing relations are kept and never removed; when something was added, the
        product gets a `bom_linked` event and the audit a row, both with the payload."""
        with self.conn:
            added = 0
            for target in sorted(set(targets)):
                cursor = self.conn.execute(
                    "INSERT INTO relations VALUES (?, 'has_component', ?) ON CONFLICT DO NOTHING",
                    (product_id, target),
                )
                added += cursor.rowcount
            if added:
                key = f"bom:{product_id}:{uuid.uuid4().hex}"  # relations dedupe repeats
                self._event(product_id, "bom_linked", actor, payload, key)
                self._audit(f"bom:{product_id}", "bom_linked", actor, payload)
        return added

    # Registrations (W5-3, D-063) ---------------------------------------------------------
    def records(self) -> list[dict[str, Any]]:
        """Every product in the seed JSONL shape, for duplicate/similar matching."""
        records: dict[str, dict[str, Any]] = {}
        for product_id, class_id, maker_id, model, origin in self.conn.execute(
            "SELECT product_id, class_id, maker_id, model_designation, origin FROM products"
            " ORDER BY product_id"
        ):
            records[product_id] = {
                "product_id": product_id,
                "origin": origin,
                "class": class_id,
                "maker_id": maker_id,
                "model_designation": model,
                "attributes": {},
                "relations": {},
            }
        for product_id, attribute, value, unit, basis, condition, scope in self.conn.execute(
            "SELECT product_id, attribute_id, value_json, unit, basis_json, condition_json,"
            " scope FROM product_facts ORDER BY fact_pk"
        ):
            fact = {
                "value": json.loads(value),
                "unit": unit,
                "basis": json.loads(basis),
                "condition": json.loads(condition),
                "scope": scope,
            }
            records[product_id]["attributes"].setdefault(attribute, []).append(fact)
        for product_id, relation, target in self.conn.execute(
            "SELECT product_id, relation_id, target_product_id FROM relations"
        ):
            records[product_id]["relations"].setdefault(relation, []).append(target)
        return list(records.values())

    def _done(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT product_id FROM registration_events WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return None if row is None else str(row[0])

    def _identity(self, result: RegistrationResult) -> tuple[str, str]:
        """(maker_id, model designation) from the facts, or a refusal the reviewer can act on."""
        maker = next((f["value"] for f in result.facts if f["attribute"] == "maker"), None)
        model = next(
            (f["value"] for f in result.facts if f["attribute"] == "model_designation"), None
        )
        if not isinstance(maker, str) or not isinstance(model, str):
            raise RegistryError("제조사나 모델명이 없어 제품을 식별할 수 없음")
        maker_id = self.resolve_maker(maker)
        if maker_id is None:
            raise RegistryError(
                f"제조사 {maker!r}이(가) 제조사 목록에 없음 (새 제조사는 자동으로 추가하지 않음)"
            )
        return maker_id, model

    def _edit_rows(
        self, job_id: str, product_id: str | None, edits: list[dict[str, Any]], actor: str
    ) -> None:
        for e in edits:
            self.conn.execute(
                "INSERT INTO human_edits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(edit_id) DO NOTHING",  # a repeat is skipped, a bad row is not
                (
                    e["edit_id"],
                    job_id,
                    product_id,
                    e["attribute"],
                    e["op"],
                    canonical(e["before"]),
                    canonical(e["after"]),
                    e["outcome"],
                    e["reason"],
                    actor,
                    e["at"],
                ),
            )

    def _event(
        self, product_id: str, event_type: str, actor: str, payload: dict[str, Any], key: str
    ) -> None:
        self.conn.execute(
            "INSERT INTO registration_events (product_id, event_type, actor, occurred_at,"
            " payload_json, idempotency_key) VALUES (?, ?, ?, ?, ?, ?)",
            (product_id, event_type, actor, datetime.now(UTC).isoformat(), canonical(payload), key),
        )

    def register(
        self,
        job_id: str,
        result: RegistrationResult,
        edits: list[dict[str, Any]],
        actor: str = "reviewer",
    ) -> str:
        """A new product from a reviewed job, in one transaction. Idempotent per job: a
        repeated call returns the product made the first time."""
        key = f"{job_id}:register"
        if (done := self._done(key)) is not None:
            return done
        if result.class_id not in self.onto.classes or self.onto.classes[result.class_id].abstract:
            raise RegistryError(f"{result.class_id!r}는 등록할 수 있는 말단 클래스가 아님")
        maker_id, model = self._identity(result)
        if (existing := self._find(maker_id, model)) is not None:
            raise RegistryError(f"동일 식별: {existing}와(과) 제조사·모델이 같음")
        by_attribute: dict[str, list[dict[str, Any]]] = {}
        for fact in result.facts:
            if not fact.get("occurrences"):  # D-063: every value keeps its place in the document
                raise RegistryError(f"{fact['attribute']}: 원문 위치가 없는 값")
            body = {k: v for k, v in fact.items() if k not in ("attribute", "occurrences")}
            by_attribute.setdefault(fact["attribute"], []).append(body)
        model_cls = build_candidate_model(self.onto, result.class_id, registered=True)
        try:
            model_cls.model_validate({"attributes": by_attribute})
        except ValidationError as exc:
            raise RegistryError(f"값이 {result.class_id} 정의에 맞지 않음: {exc}") from exc
        edited = {
            canonical(e["after"]): e["edit_id"] for e in edits if e["outcome"] == "fact"
        }  # a later edit of the same value wins
        product_id = f"REG-UP-{hashlib.sha256(job_id.encode()).hexdigest()[:10].upper()}"
        now = datetime.now(UTC).isoformat()
        with self.conn:
            self.conn.execute(
                "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    product_id,
                    result.class_id,
                    maker_id,
                    model,
                    model_key(model),
                    "user_registered",
                    now,
                ),
            )
            for fact in result.facts:
                edit_id = edited.get(canonical(fact))
                ref = edit_id or canonical(
                    {"document_id": result.document_id, "occurrences": fact["occurrences"]}
                )
                self.conn.execute(
                    "INSERT INTO product_facts (product_id, attribute_id, value_json, unit,"
                    " basis_json, condition_json, scope, evidence_kind, evidence_ref)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        product_id,
                        fact["attribute"],
                        canonical(fact["value"]),
                        fact["unit"],
                        canonical(fact["basis"]),
                        canonical(fact["condition"]),
                        fact["scope"],
                        "human_edit" if edit_id else "observed",
                        ref,
                    ),
                )
            self._edit_rows(job_id, product_id, edits, actor)
            payload = {"job_id": job_id, "result": result.model_dump(mode="json")}
            self._event(product_id, "registered", actor, payload, key)
            self._audit(job_id, "registered", actor, {"product_id": product_id})
        return product_id

    def link(
        self,
        job_id: str,
        target_id: str,
        result: RegistrationResult,
        edits: list[dict[str, Any]],
        actor: str = "reviewer",
    ) -> None:
        """Record that the document belongs to an existing product. Its facts are not
        changed (S2: no automatic merge). Idempotent per job and target."""
        key = f"{job_id}:link:{target_id}"
        if self._done(key) is not None:
            return
        if not self.conn.execute(
            "SELECT 1 FROM products WHERE product_id = ?", (target_id,)
        ).fetchone():
            raise RegistryError(f"{target_id}는 등록된 제품이 아님")
        match = next((m for m in result.matches if m.registry_id == target_id), None)
        with self.conn:
            self._edit_rows(job_id, None, edits, actor)
            payload = {
                "job_id": job_id,
                "document_id": result.document_id,
                "file_name": result.file_name,
                "relation": match.relation if match else None,
                "differing_attributes": (match.evidence if match else {}).get(
                    "differing_attributes", []
                ),
                "result": result.model_dump(mode="json"),
            }
            self._event(target_id, "linked_document", actor, payload, key)
            self._audit(job_id, "linked", actor, {"product_id": target_id})

    def _find(self, maker_id: str, model: str) -> str | None:
        row = self.conn.execute(
            "SELECT product_id FROM products WHERE maker_id = ? AND model_key = ?",
            (maker_id, model_key(model)),
        ).fetchone()
        return None if row is None else str(row[0])

    def _audit(self, job_id: str, kind: str, actor: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO audit_events (job_id, kind, actor, occurred_at, payload_json)"
            " VALUES (?, ?, ?, ?, ?)",
            (job_id, kind, actor, datetime.now(UTC).isoformat(), canonical(payload)),
        )

    def audit(self, job_id: str, kind: str, actor: str, payload: dict[str, Any]) -> None:
        """A decision or step worth keeping (NFR-02): upload, cancel, model call, ..."""
        with self.conn:
            self._audit(job_id, kind, actor, payload)

    def product(self, product_id: str) -> dict[str, Any] | None:
        """A product with every fact's evidence, its edits and its events."""
        row = self.conn.execute(
            "SELECT class_id, maker_id, model_designation, origin, created_at FROM products"
            " WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if row is None:
            return None
        facts = [
            {
                "attribute": a,
                "value": json.loads(v),
                "unit": u,
                "basis": json.loads(b),
                "condition": json.loads(c),
                "scope": s,
                "evidence_kind": k,
                "evidence_ref": r,
            }
            for a, v, u, b, c, s, k, r in self.conn.execute(
                "SELECT attribute_id, value_json, unit, basis_json, condition_json, scope,"
                " evidence_kind, evidence_ref FROM product_facts WHERE product_id = ?"
                " ORDER BY fact_pk",
                (product_id,),
            )
        ]
        edits = [
            {
                "edit_id": e,
                "job_id": j,
                "attribute": a,
                "op": o,
                "before": json.loads(b),
                "after": json.loads(f),
                "outcome": oc,
                "reason": r,
                "actor": ac,
                "at": at,
            }
            for e, j, a, o, b, f, oc, r, ac, at in self.conn.execute(
                "SELECT edit_id, job_id, attribute_id, op, before_json, after_json, outcome,"
                " reason, actor, occurred_at FROM human_edits WHERE product_id = ?"
                " ORDER BY occurred_at, edit_id",
                (product_id,),
            )
        ]
        events = [
            {"event_type": t, "actor": a, "at": at, "payload": json.loads(p)}
            for t, a, at, p in self.conn.execute(
                "SELECT event_type, actor, occurred_at, payload_json FROM registration_events"
                " WHERE product_id = ? ORDER BY event_id",
                (product_id,),
            )
        ]
        class_id, maker_id, model, origin, created_at = row
        name = self.conn.execute(
            "SELECT name FROM manufacturers WHERE maker_id = ?", (maker_id,)
        ).fetchone()
        return {
            "product_id": product_id,
            "class_id": class_id,
            "maker_id": maker_id,
            "maker_name": None if name is None else str(name[0]),
            "model_designation": model,
            "origin": origin,
            "created_at": created_at,
            "facts": facts,
            "edits": edits,
            "events": events,
        }


def build(split: str) -> Path:
    registry = ROOT / "data/synth/registry"
    out = ROOT / f"var/registry/{split}.sqlite"
    out.parent.mkdir(parents=True, exist_ok=True)
    store = RegistryStore(out, load_ontology(ROOT / "ontology/ontology.yaml"))
    try:
        store.load_manufacturers(registry / "manufacturers.json")
        store.load_jsonl(registry / f"{split}.jsonl")
    finally:
        store.close()
    return out


if __name__ == "__main__":
    print(build(sys.argv[1]).relative_to(ROOT))
