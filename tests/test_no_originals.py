"""W6-8 (D-094): no copyrighted original is committed.

The reference documents (manufacturer project guides, data/reference/manifest.yaml) are
read locally for layout and attribute names only; their notices forbid copying. The
repository may hold their manifest (titles, sources, hashes), never the files. Checked on
what git tracks, so it holds in CI's fresh checkout too:

1. no tracked file has the sha256 of a reference document;
2. document files (PDF, Office) are tracked only where synthetic inputs live;
3. the snapshot archives in data/backups hold no document file from data/reference (they
   do hold its folders, manifest and macOS metadata, which are not originals).
"""

import hashlib
import shutil
import subprocess
import tarfile

import pytest
import yaml

from tests.conftest import ROOT

MANIFEST = ROOT / "data/reference/manifest.yaml"
SYNTHETIC_DOCUMENTS = ("data/synth/inputs/",)  # generated sheets, origin: synthetic
DOCUMENT_SUFFIXES = (".pdf", ".docx", ".xlsx", ".doc", ".xls", ".pptx")
HOMES = ("/" + "Users/", "/" + "home/")  # spelled apart so this file does not match itself

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(), reason="needs a git checkout"
)


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [path for path in out.decode().split("\0") if path]


def test_no_tracked_file_is_a_reference_document() -> None:
    references = {d["sha256"] for d in yaml.safe_load(MANIFEST.read_text())["documents"]}
    assert len(references) == 12
    hits = []
    for path in tracked():
        file = ROOT / path
        if file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() in references:
            hits.append(path)
    assert hits == []


def test_document_files_are_tracked_only_as_synthetic_inputs() -> None:
    documents = [p for p in tracked() if p.lower().endswith(DOCUMENT_SUFFIXES)]
    assert documents  # the synthetic inputs are there
    assert [p for p in documents if not p.startswith(SYNTHETIC_DOCUMENTS)] == []


def test_snapshot_archives_hold_no_reference_file() -> None:
    archives = [p for p in tracked() if p.startswith("data/backups/") and p.endswith(".tgz")]
    inside = []
    for path in archives:
        with tarfile.open(ROOT / path) as archive:
            inside += [
                f"{path}: {name}"
                for name in archive.getnames()
                if "data/reference/" in name and name.lower().endswith(DOCUMENT_SUFFIXES)
            ]
    assert inside == []


def test_no_tracked_text_names_a_home_directory() -> None:
    """Paths in documents are written from the project or as ~/…, never a user's home."""
    found = []
    for path in tracked():
        file = ROOT / path
        if not file.is_file() or file.suffix in (".tgz", ".pdf", ".docx", ".xlsx"):
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        if any(home in text for home in HOMES):
            found.append(path)
    assert found == []
