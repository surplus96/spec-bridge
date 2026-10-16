"""Parse every input of one split into var/parsed/<split>/ (W2-6, CP-S2 R2/P8).

Run: uv run python -m spec_bridge.parse.run dev
Consumers (W3) must read only the documents listed in `_summary.json` `parsed_ids`;
a failed re-parse removes that document's previous JSON so no stale success remains.
Gold answers are not read here; location recall is measured by the dev-split tests.
"""

import hashlib
import json
import subprocess
import sys
import time
from functools import cache
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

from spec_bridge.parse.blocks import ParseError
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.parse.settings import DOCLING_MODELS, PDF_OPTIONS

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/synth/dataset-manifest.yaml"
PACKAGES = ("docling", "docling-core", "docling-ibm-models", "pypdfium2", "openpyxl", "python-docx")


def split_inputs(split: str) -> list[tuple[str, Path]]:
    documents = yaml.safe_load(MANIFEST.read_text())["documents"]
    return [(d["input_id"], ROOT / d["input_path"]) for d in documents if d["split"] == split]


def run_split(split: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    parsed: dict[str, int] = {}
    failures: list[dict[str, str]] = []
    for input_id, path in split_inputs(split):
        target = out_dir / f"{input_id}.json"
        try:
            document = parse_document(path, input_id)
        except ParseError as error:  # reported, never fatal (W3 treats it as unknown)
            target.unlink(missing_ok=True)  # CP-S2 R2: no stale success for a failed document
            failures.append({"input_id": input_id, "reason": error.reason})
            continue
        target.write_text(document.model_dump_json(indent=2) + "\n")
        parsed[input_id] = len(document.blocks)
    summary = {
        "split": split,
        "documents": len(parsed) + len(failures),
        "parsed": len(parsed),
        "parsed_ids": sorted(parsed),
        "blocks": sum(parsed.values()),
        "failures": failures,
        "seconds": round(time.perf_counter() - started, 1),
        "environment": environment(),
    }
    (out_dir / "_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


@cache
def environment() -> dict[str, Any]:
    """What produced this parse (NFR-03): code, lock file, libraries, models, options."""
    return {
        "git_commit": _git(["rev-parse", "HEAD"]),
        "git_dirty": bool(_git(["status", "--porcelain"])),
        "uv_lock_sha256": _sha256(ROOT / "uv.lock"),
        "versions": {package: version(package) for package in PACKAGES},
        "models_sha256": _tree_sha256(DOCLING_MODELS) if DOCLING_MODELS.is_dir() else None,
        "pdf_options": PDF_OPTIONS,
    }


def _git(args: list[str]) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(folder: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(str(file.relative_to(folder)).encode())
        digest.update(_sha256(file).encode())
    return digest.hexdigest()


if __name__ == "__main__":
    split = sys.argv[1]
    result = run_split(split, ROOT / "var/parsed" / split)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("failures", "parsed_ids")}, indent=2
        )
    )
    for failure in result["failures"]:
        print(f"FAILED {failure['input_id']}: {failure['reason']}")
    sys.exit(1 if result["failures"] else 0)
