"""Reproduction manifest: what decides a result beyond the freeze record (CP-S4 R5).

The W6 freeze record (freeze.py) hashes the scorer, prompt and RAG modules, knowledge
base, ontology, dictionary and handwritten set. Other files decide results too: the
service wiring (number of retrieved cases, embedding model), the normalizer, parsers and
extractor, and the locked dependencies. They are the *guard* set here.

- guard: changing any of these may change a result. Future freeze records carry their
  hashes and `freeze verify` refuses a change. The W6 record predates this; for W6 the
  manifest shows, from git, that the guard set at the freeze commit equals the current one.
- record only: kept for the reader, not refused (run naming, audit fields of the model
  client, parsed outputs, the model digest that every run.json carries).
- dataset: every line of data/synth/SHA256SUMS checked against the actual file.

Run:
    uv run python -m spec_bridge.eval.manifest w6      # write docs/reports/w6-repro-manifest.json
    uv run python -m spec_bridge.eval.manifest check   # guard set vs that manifest, dataset hashes
"""

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_bridge.normalize.dictionary import ROOT

GUARD = (
    "spec_bridge/service.py",
    "spec_bridge/pipeline.py",
    "spec_bridge/normalize/*.py",
    "spec_bridge/parse/*.py",
    "spec_bridge/extract/*.py",
    "spec_bridge/rag/settings.py",
    "uv.lock",
)
RECORD_ONLY = ("spec_bridge/eval/experiment.py", "spec_bridge/llm/provider.py")
SPLITS_PARSED = ("dev", "test", "handwritten")
SUMS = "data/synth/SHA256SUMS"
W6_FREEZE_COMMIT = "5494f33"  # the commit made right after the W6 freeze record (D-086)
W6_MODEL_DIGEST = "c7c4e3d1ca22fe9225f18b35eb719f67e2ca96a42e7fd17294a45b83ba8fbf03"
OUTPUT = ROOT / "docs/reports/w6-repro-manifest.json"

Reader = Callable[[str], bytes | None]  # repo-relative path -> content, None if absent


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expand(patterns: tuple[str, ...], root: Path = ROOT) -> list[str]:
    """Repo-relative files matching the patterns in the working tree, sorted."""
    found = {p.relative_to(root).as_posix() for pat in patterns for p in root.glob(pat)}
    return sorted(f for f in found if "__pycache__" not in f)


def hashes(paths: list[str], read: Reader) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for path in paths:
        data = read(path)
        out[path] = None if data is None else sha256(data)
    return out


def working_tree(root: Path = ROOT) -> Reader:
    def read(path: str) -> bytes | None:
        file = root / path
        return file.read_bytes() if file.is_file() else None

    return read


def at_commit(commit: str, root: Path = ROOT) -> Reader:
    def read(path: str) -> bytes | None:
        done = subprocess.run(
            ["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True, check=False
        )
        return done.stdout if done.returncode == 0 else None

    return read


def guard_hashes(root: Path = ROOT) -> dict[str, str | None]:
    """The guard set as it is now (what a freeze record carries from now on)."""
    return hashes(expand(GUARD, root), working_tree(root))


def dataset_check(root: Path = ROOT) -> dict[str, Any]:
    """Each SHA256SUMS line against the actual file: counts and the files that differ."""
    lines = [line.split(None, 1) for line in (root / SUMS).read_text().splitlines() if line]
    bad = [
        path.strip()
        for digest, path in lines
        if not (root / path.strip()).is_file()
        or sha256((root / path.strip()).read_bytes()) != digest
    ]
    return {"sums_file": sha256((root / SUMS).read_bytes()), "files": len(lines), "differ": bad}


def parsed_hashes(root: Path = ROOT) -> dict[str, str | None]:
    """One digest per parsed split folder (file names and contents), None if not parsed."""
    out: dict[str, str | None] = {}
    for split in SPLITS_PARSED:
        folder = root / "var/parsed" / split
        files = sorted(folder.glob("*.json")) if folder.is_dir() else []
        digest = hashlib.sha256()
        for file in files:
            digest.update(file.name.encode() + b"\0" + file.read_bytes())
        out[split] = digest.hexdigest() if files else None
    return out


def compare(then: dict[str, str | None], now: dict[str, str | None]) -> list[str]:
    """Paths whose hash differs (added, removed or changed)."""
    return sorted(p for p in set(then) | set(now) if then.get(p) != now.get(p))


def w6_manifest(root: Path = ROOT, commit: str = W6_FREEZE_COMMIT) -> dict[str, Any]:
    paths = expand(GUARD, root)
    then, now = hashes(paths, at_commit(commit, root)), hashes(paths, working_tree(root))
    record_paths = list(RECORD_ONLY)
    record_then = hashes(record_paths, at_commit(commit, root))
    record_now = hashes(record_paths, working_tree(root))
    return {
        "written_at": datetime.now(UTC).isoformat(),
        "freeze_commit": commit,
        "guard": {"hashes": now, "changed_since_freeze": compare(then, now)},
        "record_only": {
            "hashes": record_now,
            "changed_since_freeze": compare(record_then, record_now),
        },
        "dataset": dataset_check(root),
        "parsed": parsed_hashes(root),
        "model_digest": W6_MODEL_DIGEST,
    }


def check(path: Path = OUTPUT, root: Path = ROOT) -> list[str]:
    """Problems against a written manifest: guard changes and dataset files that differ."""
    manifest = json.loads(path.read_text())
    problems = [
        f"guard changed: {p}" for p in compare(manifest["guard"]["hashes"], guard_hashes(root))
    ]
    return problems + [f"dataset file differs: {p}" for p in dataset_check(root)["differ"]]


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "check"
    if command == "w6":
        manifest = w6_manifest()
        OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(json.dumps({k: manifest[k] for k in ("guard", "record_only")}, indent=2)[:2000])
        return
    problems = check()
    print("\n".join(problems) if problems else f"guard set and dataset match {OUTPUT.name}")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
