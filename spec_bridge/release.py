"""Public release (CP-S4 R1, D-097): what goes into the new public repository, and a scan of
the result, archives included.

    uv run python -m spec_bridge.release bundle            # W6 runs -> data/eval/w6-runs/
    uv run python -m spec_bridge.release export <folder>   # copy the public set, then scan it
    uv run python -m spec_bridge.release scan <folder>     # scan any folder

- bundle: the 13 W6 runs as a re-scoring set (run.json, predictions, scores, metrics; no
  audit log). Absolute paths in run.json become project-relative.
- export: the files git would commit (tracked and unignored), minus EXCLUDED, copied to an
  empty folder. The existing repository, its history and data/backups stay as they are.
- scan: in every file, and inside every .tgz/.zip member: a home directory path, a
  reference document (manifest sha256), an environment file, a secret key pattern, Python
  caches, macOS metadata, and document files outside the synthetic inputs.
"""

import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from spec_bridge.normalize.dictionary import ROOT

W6_RUNS = (  # D-087 dev reproduction, W6-4 test and handwritten runs, D-089 Copt
    "R-20261015T005831Z",
    "E0-20261015T005833Z",
    "E1SV-20261015T013156Z",
    "test-R-20261015T051146Z",
    "test-A-20261015T051147Z",
    "test-B-20261015T051835Z",
    "test-C-20261015T053143Z",
    "test-E0-20261015T054216Z",
    "test-E1SV-20261015T060851Z",
    "test-Copt-20261015T063748Z",
    "handwritten-R-20261015T065900Z",
    "handwritten-E0-20261015T065901Z",
    "handwritten-E1SV-20261015T070633Z",
)
RUN_FILES = ("run.json", "scores.json", "metrics.json")
BUNDLE = ROOT / "data/eval/w6-runs"

EXCLUDED = ("data/backups/",)  # restore snapshots and the authoring archive (D-097 1, 2)
SYNTHETIC_DOCUMENTS = ("data/synth/inputs/",)
DOCUMENT_SUFFIXES = (".pdf", ".docx", ".xlsx", ".doc", ".xls", ".pptx")
HOMES = (b"/" + b"Users/", b"/" + b"home/")  # spelled apart so this file does not match itself
SECRETS = re.compile(rb"sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
MANIFEST = ROOT / "data/reference/manifest.yaml"


# bundle ------------------------------------------------------------------------------------
def _relative(value: Any, root: str) -> Any:
    if isinstance(value, dict):
        return {k: _relative(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [_relative(v, root) for v in value]
    if isinstance(value, str) and value.startswith(root):
        return value[len(root) :]
    return value


def bundle(
    runs: tuple[str, ...] = W6_RUNS, source: Path = ROOT / "var/eval", out: Path = BUNDLE
) -> int:
    """Copy the runs' re-scoring files; returns the number of files written."""
    root = str(ROOT) + "/"
    written = 0
    for run in runs:
        src, dst = source / run, out / run
        (dst / "predictions").mkdir(parents=True, exist_ok=True)
        for name in RUN_FILES:
            data = json.loads((src / name).read_text())
            text = json.dumps(_relative(data, root), indent=2, sort_keys=True, ensure_ascii=False)
            (dst / name).write_text(text + "\n")
            written += 1
        for prediction in sorted((src / "predictions").glob("*.json")):
            shutil.copyfile(prediction, dst / "predictions" / prediction.name)
            written += 1
    return written


# export ------------------------------------------------------------------------------------
def public_files(root: Path = ROOT) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode()
    files = [p for p in out.split("\0") if p and (root / p).is_file()]
    return sorted(p for p in files if not p.startswith(EXCLUDED))


def export(dest: Path, root: Path = ROOT) -> list[str]:
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    files = public_files(root)
    for path in files:
        (dest / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, dest / path)
    return files


# scan --------------------------------------------------------------------------------------
def _members(path: Path) -> Iterator[tuple[str, bytes]]:
    """(name, content) of a file, and of each member of a .tgz/.zip inside it."""
    data = path.read_bytes()
    yield path.name, data
    if path.suffix in (".tgz", ".gz"):
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            for member in archive.getmembers():
                extracted = archive.extractfile(member) if member.isfile() else None
                if extracted is not None:
                    yield f"{path.name}:{member.name}", extracted.read()
    elif path.suffix == ".zip" and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                yield f"{path.name}:{name}", archive.read(name)


def _problems(rel: str, name: str, data: bytes, references: set[str]) -> list[str]:
    where = rel if name == Path(rel).name else f"{rel} ({name})"
    base = name.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    checks = (
        (any(home in data for home in HOMES), "home path"),
        (hashlib.sha256(data).hexdigest() in references, "reference document"),
        (SECRETS.search(data) is not None, "secret pattern"),
        (base == ".env" or (base.startswith(".env.") and base != ".env.example"), "env file"),
        (
            "__pycache__" in name
            or base.endswith(".pyc")
            or base in (".DS_Store",)
            or base.startswith("._"),
            "cache or OS metadata",
        ),
        (
            base.lower().endswith(DOCUMENT_SUFFIXES) and not rel.startswith(SYNTHETIC_DOCUMENTS),
            "document outside synthetic inputs",
        ),
    )
    return [f"{label}: {where}" for hit, label in checks if hit]


def scan(folder: Path) -> list[str]:
    references = {d["sha256"] for d in yaml.safe_load(MANIFEST.read_text())["documents"]}
    found: list[str] = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        for name, data in _members(path):
            found += _problems(rel, name, data, references)
    return found


def main() -> None:
    command, *rest = sys.argv[1:] or ["scan"]
    if command == "bundle":
        print(f"{bundle()} files -> {BUNDLE}")
        return
    folder = Path(rest[0]) if rest else ROOT
    if command == "export":
        print(f"{len(export(folder))} files -> {folder}")
    problems = scan(folder)
    print("\n".join(problems) if problems else f"scan clean: {folder}")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
