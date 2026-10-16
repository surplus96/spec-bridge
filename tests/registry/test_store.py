import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.ontology.loader import Ontology
from spec_bridge.registry.store import RegistryError, RegistryStore
from tests.conftest import ROOT

REGISTRY = ROOT / "data/synth/registry"


@pytest.fixture
def store(tmp_path: Path, onto: Ontology) -> Iterator[RegistryStore]:
    s = RegistryStore(tmp_path / "registry.sqlite", onto)
    s.load_manufacturers(REGISTRY / "manufacturers.json")
    yield s
    s.close()


def dev_records() -> list[dict[str, Any]]:
    lines = (REGISTRY / "dev.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def standalone_record() -> dict[str, Any]:
    """A record without relations, so it can be loaded alone."""
    return next(r for r in dev_records() if not r["relations"].get("has_component"))


def write_jsonl(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    path = tmp_path / "records.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def test_loads_dev_registry(store: RegistryStore) -> None:
    assert store.load_jsonl(REGISTRY / "dev.jsonl") == len(dev_records())
    assert store.count("products") == len(dev_records())


def test_reload_is_idempotent(store: RegistryStore) -> None:
    store.load_jsonl(REGISTRY / "dev.jsonl")
    before = store.count("registration_events")
    assert store.load_jsonl(REGISTRY / "dev.jsonl") == 0
    assert store.count("registration_events") == before


def test_changed_record_is_not_overwritten(store: RegistryStore, tmp_path: Path) -> None:
    record = standalone_record()
    store.load_jsonl(write_jsonl(tmp_path, [record]))
    record["model_designation"] += "-X"
    with pytest.raises(RegistryError, match="different content"):
        store.load_jsonl(write_jsonl(tmp_path, [record]))


def test_invalid_fact_rolls_back_whole_file(store: RegistryStore, tmp_path: Path) -> None:
    good, bad = standalone_record(), dict(standalone_record())
    first_attr = next(iter(bad["attributes"]))
    bad["product_id"] += "-BAD"
    bad["attributes"][first_attr][0]["unit"] = "not-a-unit"
    with pytest.raises(RegistryError):
        store.load_jsonl(write_jsonl(tmp_path, [good, bad]))
    assert store.count("products") == 0


def test_identity_lookup_tolerates_notation(store: RegistryStore) -> None:
    store.load_jsonl(REGISTRY / "dev.jsonl")
    record = dev_records()[0]
    makers = json.loads((REGISTRY / "manufacturers.json").read_text())
    alias = next(m["aliases"][0] for m in makers if m["maker_id"] == record["maker_id"])
    model = record["model_designation"].replace("-", " ").lower()
    assert store.find_by_identity(alias, model) == record["product_id"]


def test_every_relation_target_is_registered(store: RegistryStore) -> None:
    store.load_jsonl(REGISTRY / "dev.jsonl")
    dangling = store.conn.execute(
        "SELECT COUNT(*) FROM relations r LEFT JOIN products p"
        " ON p.product_id = r.target_product_id WHERE p.product_id IS NULL"
    ).fetchone()[0]
    assert store.count("relations") > 0 and dangling == 0


def test_seed_facts_are_marked_as_seed_evidence(store: RegistryStore) -> None:
    store.load_jsonl(REGISTRY / "dev.jsonl")
    kinds = store.conn.execute("SELECT DISTINCT evidence_kind FROM product_facts").fetchall()
    assert kinds == [("registry_seed",)]


def test_relation_to_unloaded_product_is_rejected(store: RegistryStore, tmp_path: Path) -> None:
    record = next(r for r in dev_records() if r["relations"].get("has_component"))
    with pytest.raises(Exception, match="FOREIGN KEY"):
        store.load_jsonl(write_jsonl(tmp_path, [record]))
    assert store.count("products") == 0


def makers() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((REGISTRY / "manufacturers.json").read_text())
    return data


def write_makers(tmp_path: Path, name: str, data: list[dict[str, Any]]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return path


def test_maker_name_conflict_across_loads_is_rejected(tmp_path: Path, onto: Ontology) -> None:
    """R1: the second load claims the first maker's name as another maker's alias."""
    first, second = makers()[:2]
    s = RegistryStore(tmp_path / "r1.sqlite", onto)
    s.load_manufacturers(write_makers(tmp_path, "a.json", [first]))
    aliases_before = s.count("manufacturer_aliases")
    clash = dict(second, aliases=[first["name"]])
    with pytest.raises(RegistryError, match="shared"):
        s.load_manufacturers(write_makers(tmp_path, "b.json", [clash]))
    assert s.count("manufacturer_aliases") == aliases_before
    assert s.count("manufacturers") == 1
    s.close()


def test_changed_maker_content_is_rejected(tmp_path: Path, onto: Ontology) -> None:
    first = makers()[0]
    s = RegistryStore(tmp_path / "r1b.sqlite", onto)
    s.load_manufacturers(write_makers(tmp_path, "a.json", [first]))
    changed = dict(first, aliases=[*first["aliases"], "Another Synthetic Alias"])
    with pytest.raises(RegistryError, match="different content"):
        s.load_manufacturers(write_makers(tmp_path, "a2.json", [changed]))
    s.close()


def test_identical_maker_reload_is_idempotent(tmp_path: Path, onto: Ontology) -> None:
    path = write_makers(tmp_path, "all.json", makers())
    s = RegistryStore(tmp_path / "r1c.sqlite", onto)
    assert s.load_manufacturers(path) == len(makers())
    assert s.load_manufacturers(path) == 0
    s.close()


def test_top_level_model_must_match_fact(store: RegistryStore, tmp_path: Path) -> None:
    """R2: product identity and its model_designation fact must agree."""
    record = standalone_record()
    record["model_designation"] += "-CHANGED"
    with pytest.raises(RegistryError, match="identity"):
        store.load_jsonl(write_jsonl(tmp_path, [record]))


def test_top_level_model_notation_variant_is_accepted(store: RegistryStore, tmp_path: Path) -> None:
    record = standalone_record()
    record["model_designation"] = record["model_designation"].replace("-", " ").lower()
    assert store.load_jsonl(write_jsonl(tmp_path, [record])) == 1


def test_maker_fact_must_belong_to_maker(store: RegistryStore, tmp_path: Path) -> None:
    record = standalone_record()
    other = next(m for m in makers() if m["maker_id"] != record["maker_id"])
    record["attributes"]["maker"][0]["value"] = other["name"]
    with pytest.raises(RegistryError, match="identity"):
        store.load_jsonl(write_jsonl(tmp_path, [record]))


def test_maker_fact_may_use_registered_alias(store: RegistryStore, tmp_path: Path) -> None:
    record = standalone_record()
    own = next(m for m in makers() if m["maker_id"] == record["maker_id"])
    record["attributes"]["maker"][0]["value"] = own["aliases"][0]
    assert store.load_jsonl(write_jsonl(tmp_path, [record])) == 1


def test_reopen_with_other_ontology_version_is_rejected(tmp_path: Path, onto: Ontology) -> None:
    """R4: an existing DB is checked, not silently relabelled."""
    path = tmp_path / "r4.sqlite"
    RegistryStore(path, onto).close()
    newer = onto.model_copy(update={"version": onto.version + 1})
    with pytest.raises(RegistryError, match="rebuild"):
        RegistryStore(path, newer)


def test_reopen_with_same_version_is_allowed(tmp_path: Path, onto: Ontology) -> None:
    path = tmp_path / "r4b.sqlite"
    RegistryStore(path, onto).close()
    RegistryStore(path, onto).close()
