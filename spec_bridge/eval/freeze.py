"""Freeze record for the W6 evaluation (D-080): what the test split is evaluated with.

    uv run python -m spec_bridge.eval.freeze write    # once, after W6-0/W6-2, before W6-3
    uv run python -m spec_bridge.eval.freeze verify   # any time; the runner checks it too
    uv run python -m spec_bridge.eval.freeze restore  # new checkout: the committed W6 record

`restore` copies docs/reports/w6-freeze.json (the committed copy of the W6 record) to
var/eval/FREEZE.json, so a fresh checkout re-runs the W6 evaluation against the system that
was frozen. Do not `write` there: that would freeze whatever the checkout holds instead.

The record holds the hashes that decide a result: scorer (evaluation modules and answer
set), prompt modules, RAG modules, knowledge base, ontology and development dictionary.
The runner refuses the test split when there is no record or any hash differs, so a test
run can only use the frozen system. The model digest is in every run.json and is compared
there (the record is written without calling the model server).

Records written after CP-S4 also carry the guard set of spec_bridge.eval.manifest (service
wiring, normalizer, parsers, extractor, locked dependencies) and refuse its changes too
(R5). The W6 record (D-086) predates it: it is checked on its own keys, and the guard set
of W6 is shown from git in docs/reports/w6-repro-manifest.json.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_bridge.eval import handwritten, manifest
from spec_bridge.eval.rescore import evaluation_hashes, scorer_id
from spec_bridge.normalize.dictionary import OUTPUT as DICTIONARY
from spec_bridge.normalize.dictionary import ROOT
from spec_bridge.parse import md_parser
from spec_bridge.rag.knowledge import OUTPUT as KB_PATH
from spec_bridge.service import ONTOLOGY, RAG_MODULES, prompt_hashes, sha256_file

FREEZE = ROOT / "var/eval/FREEZE.json"
W6_COPY = ROOT / "docs/reports/w6-freeze.json"  # committed copy of the W6 record (D-086)


class FreezeError(RuntimeError):
    """The test split may not run: no freeze record, or the system changed since."""


def current_hashes() -> dict[str, Any]:
    return {
        "scorer_id": scorer_id(),
        "evaluation": evaluation_hashes(),
        "prompt_modules": prompt_hashes(),
        "rag_modules": {m.__name__: sha256_file(Path(str(m.__file__))) for m in RAG_MODULES},
        "kb_sha256": sha256_file(KB_PATH),
        "ontology_sha256": sha256_file(ONTOLOGY),
        "dev_dictionary_sha256": sha256_file(DICTIONARY),
        "handwritten": {  # inputs and converted answers (D-080 decision 1-B)
            p.name: sha256_file(p)
            for folder in (handwritten.FOLDER / "inputs", handwritten.CONVERTED)
            for p in sorted(folder.glob("*"))
            if p.is_file()
        },
        "handwritten_converter": sha256_file(Path(str(handwritten.__file__))),
        "md_parser": sha256_file(Path(str(md_parser.__file__))),
        "guard": manifest.guard_hashes(),
    }


def write(path: Path = FREEZE) -> dict[str, Any]:
    if path.exists():
        raise FreezeError(f"{path} exists: the system is frozen once (D-080)")
    record = {"frozen_at": datetime.now(UTC).isoformat(), "hashes": current_hashes()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def _differences(frozen: Any, now: Any, prefix: str = "") -> list[str]:
    if isinstance(frozen, dict) and isinstance(now, dict):
        keys = sorted(set(frozen) | set(now))
        return [d for k in keys for d in _differences(frozen.get(k), now.get(k), f"{prefix}{k}.")]
    return [] if frozen == now else [prefix.rstrip(".")]


def verify(path: Path = FREEZE) -> dict[str, Any]:
    """The freeze record, if the system still matches it; FreezeError otherwise."""
    if not path.exists():
        raise FreezeError(f"no freeze record at {path}: write it before the test split (D-080)")
    record: dict[str, Any] = json.loads(path.read_text())
    now = current_hashes()
    if "guard" not in record["hashes"]:  # a W6 record: its guard set is in the manifest
        now.pop("guard")
    changed = _differences(record["hashes"], now)
    if changed:
        raise FreezeError(f"the system changed since the freeze: {', '.join(changed)}")
    return record


def restore(source: Path = W6_COPY, path: Path = FREEZE) -> dict[str, Any]:
    """Put the committed W6 record in place (a fresh checkout); a different record stays."""
    if path.exists():
        if path.read_bytes() != source.read_bytes():
            raise FreezeError(f"{path} exists and differs from {source}: not overwritten")
        return dict(json.loads(path.read_text()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.read_bytes())
    return dict(json.loads(path.read_text()))


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if command == "write":
        print(json.dumps(write(), indent=2))
    elif command == "restore":
        print(f"restored the W6 record ({restore()['frozen_at']}) to {FREEZE}")
    else:
        record = verify()
        print(f"frozen system unchanged ({FREEZE})")
        if "guard" not in record["hashes"]:
            print(
                "the record has no guard set: check it with `python -m spec_bridge.eval.manifest`"
            )
