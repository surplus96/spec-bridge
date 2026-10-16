"""CP-S4 R5: files that decide a result beyond the W6 freeze record are guarded."""

import json
from pathlib import Path

import pytest

from spec_bridge.eval import freeze, manifest
from spec_bridge.eval.freeze import FreezeError

SERVICE = 'RAG_EMBEDDING = "bge-m3"\nRAG_K = 3\n'


def tree(root: Path) -> Path:
    (root / "spec_bridge/normalize").mkdir(parents=True)
    (root / "spec_bridge/service.py").write_text(SERVICE)
    (root / "spec_bridge/normalize/values.py").write_text("x = 1\n")
    (root / "uv.lock").write_text("lock\n")
    return root


def test_changing_the_number_of_retrieved_cases_changes_the_guard_set(tmp_path: Path) -> None:
    root = tree(tmp_path)
    before = manifest.guard_hashes(root)
    assert "spec_bridge/service.py" in before and "uv.lock" in before
    (root / "spec_bridge/service.py").write_text(SERVICE.replace("RAG_K = 3", "RAG_K = 1"))
    assert manifest.compare(before, manifest.guard_hashes(root)) == ["spec_bridge/service.py"]


def test_a_new_or_removed_guarded_file_counts_as_a_change(tmp_path: Path) -> None:
    root = tree(tmp_path)
    before = manifest.guard_hashes(root)
    (root / "spec_bridge/normalize/units.py").write_text("y = 2\n")
    (root / "uv.lock").unlink()
    changed = manifest.compare(before, manifest.guard_hashes(root))
    assert changed == ["spec_bridge/normalize/units.py", "uv.lock"]


def test_dataset_files_are_checked_against_their_listed_hashes(tmp_path: Path) -> None:
    (tmp_path / "data/synth").mkdir(parents=True)
    good, bad = tmp_path / "data/synth/a.txt", tmp_path / "data/synth/b.txt"
    good.write_text("a")
    bad.write_text("b")
    sums = f"{manifest.sha256(b'a')}  data/synth/a.txt\n{manifest.sha256(b'x')}  data/synth/b.txt\n"
    (tmp_path / manifest.SUMS).write_text(sums)
    report = manifest.dataset_check(tmp_path)
    assert report["files"] == 2 and report["differ"] == ["data/synth/b.txt"]


def test_the_repository_dataset_matches_its_sums() -> None:
    assert manifest.dataset_check()["differ"] == []


def test_a_new_freeze_record_refuses_a_guard_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = freeze.write(tmp_path / "F")
    assert "guard" in record["hashes"]
    changed = dict(record["hashes"]["guard"]) | {"spec_bridge/service.py": "changed"}
    monkeypatch.setattr(manifest, "guard_hashes", lambda root=None: changed)
    with pytest.raises(FreezeError, match="guard.spec_bridge/service.py"):
        freeze.verify(tmp_path / "F")


def test_a_w6_record_without_a_guard_set_is_checked_on_its_own_keys(tmp_path: Path) -> None:
    record = freeze.write(tmp_path / "F")
    del record["hashes"]["guard"]
    (tmp_path / "F").write_text(json.dumps(record))
    assert "guard" not in freeze.verify(tmp_path / "F")["hashes"]


def test_restore_puts_the_committed_w6_record_in_place_once(tmp_path: Path) -> None:
    """CP-S4 R2: a fresh checkout restores the W6 record instead of freezing anew."""
    target = tmp_path / "eval/FREEZE.json"
    record = freeze.restore(freeze.W6_COPY, target)
    assert record["frozen_at"].startswith("2026-10-15T00:48:37")
    assert target.read_bytes() == freeze.W6_COPY.read_bytes()
    assert freeze.restore(freeze.W6_COPY, target) == record  # same record: nothing changes
    target.write_text(json.dumps({"frozen_at": "other", "hashes": {}}))
    with pytest.raises(FreezeError, match="not overwritten"):
        freeze.restore(freeze.W6_COPY, target)


def test_the_committed_w6_record_matches_this_checkout(tmp_path: Path) -> None:
    freeze.restore(freeze.W6_COPY, tmp_path / "F")
    assert "guard" not in freeze.verify(tmp_path / "F")["hashes"]
