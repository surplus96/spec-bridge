"""CP-S4 R1 (D-097): the public set and its scan, archives included."""

import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from spec_bridge import release
from spec_bridge.eval.rescore import rescore
from tests.conftest import ROOT

HOME = "/" + "Users/someone/project"  # spelled apart so this file does not match a scan


def tgz(path: Path, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_a_clean_folder_scans_clean(tmp_path: Path) -> None:
    (tmp_path / "data/synth/inputs").mkdir(parents=True)
    (tmp_path / "data/synth/inputs/SYN-001.pdf").write_bytes(b"%PDF synthetic")
    (tmp_path / "README.md").write_text("relative paths only: docs/run-guide.md\n")
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\n")
    assert release.scan(tmp_path) == []


def test_problems_are_found_in_files_and_inside_archives(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(f"see {HOME}/x\n")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=x\n")
    (tmp_path / "guide.pdf").write_bytes(b"%PDF not synthetic")
    tgz(tmp_path / "old.tgz", {"docs/decisions.md": HOME.encode(), "pkg/__pycache__/a.pyc": b""})
    found = release.scan(tmp_path)
    assert "home path: notes.md" in found
    assert "env file: .env" in found
    assert "document outside synthetic inputs: guide.pdf" in found
    assert "home path: old.tgz (old.tgz:docs/decisions.md)" in found
    assert "cache or OS metadata: old.tgz (old.tgz:pkg/__pycache__/a.pyc)" in found


def test_a_secret_key_pattern_is_found(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text('KEY = "sk-' + "a" * 24 + '"\n')
    found = release.scan(tmp_path)
    assert found == ["secret pattern: config.py"]


def test_the_public_set_leaves_out_the_backups() -> None:
    files = release.public_files()
    assert files and not [f for f in files if f.startswith("data/backups/")]
    assert "README.md" in files and "data/reference/manifest.yaml" in files


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="needs a git checkout")
def test_the_exported_public_set_scans_clean(tmp_path: Path) -> None:
    files = release.export(tmp_path / "repo")
    assert len(files) > 600
    assert release.scan(tmp_path / "repo") == []


def test_absolute_paths_in_a_run_record_become_relative() -> None:
    root = str(ROOT) + "/"
    record = {"parse": {"summary": root + "var/parsed/test/_summary.json"}, "n": 1}
    assert release._relative(record, root) == {
        "parse": {"summary": "var/parsed/test/_summary.json"},
        "n": 1,
    }


def test_the_committed_runs_re_score_to_their_recorded_metrics(tmp_path: Path) -> None:
    """A fresh checkout can re-score the W6 test result without the model (R2, decision 4)."""
    run = tmp_path / "test-E1SV"
    shutil.copytree(release.BUNDLE / "test-E1SV-20261015T060851Z", run)
    rescored = json.loads(rescore(run).read_text())["metrics"]
    recorded = json.loads((run / "metrics.json").read_text())
    assert rescored["facts_micro"] == recorded["facts_micro"]
    assert (rescored["context_tp"], rescored["context_fp"]) == (62, 8)
    assert release.scan(release.BUNDLE) == []
