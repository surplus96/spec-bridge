"""BOM notation data for the G5 follow-up (D-102, D-104): formats and the start conditions.

Three files (docs/dataset-plan.md 4-5):
- data/reference/bom/manifest.yaml        sources (committed; originals beside it are not)
- data/reference/bom/raw-examples.yaml    rows as written in the sources (local only)
- data/reference/bom-notation-patterns.yaml  notation patterns with source refs (committed;
  descriptions only, never the original text)

Only signed entries (`verified_by`) count. Signatures are normally the user's; D-106
authorizes Codex signatures for that BOM review only. Patterns come from collected
sources, never from memory (H3); this module checks shape and counts, not usage rights.

    uv run python -m spec_bridge.bom.notation
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import Field, ValidationError

from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.store import ROOT

FOLDER = ROOT / "data/reference/bom"
MANIFEST = FOLDER / "manifest.yaml"
RAW = FOLDER / "raw-examples.yaml"  # gitignored: original text stays local
CATALOG = ROOT / "data/reference/bom-notation-patterns.yaml"

# Start conditions (docs/dataset-plan.md 4-5), confirmed by the user on 2026-10-16 (D-104)
MIN_SOURCES, MIN_PUBLISHERS, MIN_RAW_ROWS, MIN_PATTERN_TYPES = 3, 2, 30, 5
GENERAL_AT = 2  # a pattern seen in this many sources is "general"

Text = Annotated[str, Field(min_length=1)]


class NotationError(ValueError):
    """A notation file does not have the agreed shape."""


class Source(StrictModel):
    id: Text
    kind: Literal["public_document", "work_material", "user_observed"]
    publisher: Text  # maker or issuing body; "de-identified" for work material
    title: Text
    edition: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    license_note: str | None = None
    file: str | None = None  # the local original's name in data/reference/bom/
    sha256: str | None = None  # of the original; none for a user's own record
    verified_by: str | None = None  # user; scoped Codex exception recorded in D-106


class SourceRef(StrictModel):
    source_id: Text
    location: Text  # page, sheet, row


class Pattern(StrictModel):
    id: Text
    pattern_type: Text  # named from the collected rows, not fixed in advance
    description: Text  # in the project's words; no sentence copied from a source
    source_refs: Annotated[list[SourceRef], Field(min_length=1)]
    verified_by: str | None = None


class RawRow(StrictModel):
    source_id: Text
    location: Text
    raw_text: Text
    pattern_ids: list[str] = []


class Manifest(StrictModel):
    schema_version: Literal[1]
    sources: list[Source]


class Catalog(StrictModel):
    schema_version: Literal[1]
    patterns: list[Pattern]  # strict: a raw_example field here is refused


class RawFile(StrictModel):
    rows: list[RawRow]


Loaded = tuple[list[Source], list[Pattern], list[RawRow]]


def _read[M: StrictModel](path: Path, model: type[M]) -> M:
    try:
        return model.model_validate(yaml.safe_load(path.read_text()) or {})
    except (ValidationError, yaml.YAMLError) as error:
        raise NotationError(f"{path.name}: {error}") from error


def _unique(ids: list[str], what: str) -> None:
    twice = sorted(i for i, n in Counter(ids).items() if n > 1)
    if twice:
        raise NotationError(f"{what} ids used twice: {twice}")


def load(manifest: Path = MANIFEST, catalog: Path = CATALOG, raw: Path = RAW) -> Loaded:
    """Read and cross-check the three files; the raw file may be absent (nothing yet)."""
    sources = _read(manifest, Manifest).sources
    patterns = _read(catalog, Catalog).patterns
    rows = _read(raw, RawFile).rows if raw.is_file() else []
    _unique([s.id for s in sources], "source")
    _unique([p.id for p in patterns], "pattern")
    for s in sources:
        if s.kind != "user_observed" and not s.sha256:
            raise NotationError(f"{s.id}: a {s.kind} needs the original's sha256")
    cited = [r.source_id for p in patterns for r in p.source_refs] + [r.source_id for r in rows]
    unknown = sorted(set(cited) - {s.id for s in sources})
    if unknown:
        raise NotationError(f"sources not in the manifest: {unknown}")
    return sources, patterns, rows


def check(sources: list[Source], patterns: list[Pattern], rows: list[RawRow]) -> dict[str, Any]:
    """Counts of signed entries against the start conditions, and what is still missing."""
    signed = {s.id: s for s in sources if s.verified_by}
    good = [
        p for p in patterns if p.verified_by and all(r.source_id in signed for r in p.source_refs)
    ]
    seen = {p.id: {r.source_id for r in p.source_refs} for p in good}
    counted = [r for r in rows if r.source_id in signed]
    publishers = {s.publisher for s in signed.values() if s.kind != "user_observed"}
    types = {p.pattern_type for p in good}
    missing = [
        message
        for short, message in (
            (len(signed) < MIN_SOURCES, f"signed sources {len(signed)} < {MIN_SOURCES}"),
            (len(publishers) < MIN_PUBLISHERS, f"publishers {len(publishers)} < {MIN_PUBLISHERS}"),
            (len(counted) < MIN_RAW_ROWS, f"raw rows {len(counted)} < {MIN_RAW_ROWS}"),
            (len(types) < MIN_PATTERN_TYPES, f"pattern types {len(types)} < {MIN_PATTERN_TYPES}"),
        )
        if short
    ]
    return {
        "ready": not missing,
        "missing": missing,
        "sources": len(signed),
        "publishers": len(publishers),
        "raw_rows": len(counted),
        "pattern_types": len(types),
        "general_patterns": sorted(p for p, s in seen.items() if len(s) >= GENERAL_AT),
        "single_source_patterns": sorted(p for p, s in seen.items() if len(s) < GENERAL_AT),
        "conditions": "confirmed by the user on 2026-10-16 (D-104)",
    }


def main() -> None:
    try:
        report = check(*load())
    except NotationError as error:
        sys.exit(f"refused: {error}")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
