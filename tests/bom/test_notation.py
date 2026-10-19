"""BOM notation data (D-102, D-104): formats, the start conditions, no original committed.

The fixtures use placeholder text only: notation patterns come from real sources the
user collects, never from memory (H3), so a test must not look like one.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from spec_bridge.bom.notation import NotationError, check, load


def write(
    folder: Path,
    sources: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
    rows: list[dict[str, Any]] | None,
) -> tuple[Path, Path, Path]:
    manifest = folder / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"schema_version": 1, "sources": sources}))
    catalog = folder / "patterns.yaml"
    catalog.write_text(yaml.safe_dump({"schema_version": 1, "patterns": patterns}))
    raw = folder / "raw-examples.yaml"
    if rows is not None:
        raw.write_text(yaml.safe_dump({"rows": rows}))
    return manifest, catalog, raw


def source(i: int, publisher: str, kind: str = "public_document") -> dict[str, Any]:
    return {
        "id": f"BOMSRC-{i:02d}",
        "kind": kind,
        "publisher": publisher,
        "title": f"placeholder title {i}",
        "sha256": None if kind == "user_observed" else f"{i:064x}",
        "verified_by": "user",
    }


def pattern(i: int, kind: str, sources: list[int], verified: bool = True) -> dict[str, Any]:
    return {
        "id": f"PAT-{i:02d}",
        "pattern_type": kind,
        "description": f"placeholder description {i}",
        "source_refs": [{"source_id": f"BOMSRC-{s:02d}", "location": "p.1"} for s in sources],
        "verified_by": "user" if verified else None,
    }


def rows(n: int, sources: int) -> list[dict[str, Any]]:
    return [
        {
            "source_id": f"BOMSRC-{i % sources + 1:02d}",
            "location": f"row {i}",
            "raw_text": f"ROW-{i}",
        }
        for i in range(n)
    ]


def test_empty_templates_report_what_is_missing(tmp_path: Path) -> None:
    report = check(*load(*write(tmp_path, [], [], None)))
    assert report["ready"] is False
    assert report["sources"] == 0 and report["raw_rows"] == 0 and report["pattern_types"] == 0
    assert any("source" in m for m in report["missing"])


def test_the_start_conditions_are_met_with_three_sources_thirty_rows_five_types(
    tmp_path: Path,
) -> None:
    sources = [source(1, "org A"), source(2, "org B"), source(3, "org A", "user_observed")]
    patterns = [pattern(i, f"type_{i}", [1, 2] if i == 1 else [i % 3 + 1]) for i in range(1, 6)]
    report = check(*load(*write(tmp_path, sources, patterns, rows(30, 3))))
    assert report["ready"] is True and report["missing"] == []
    assert report["general_patterns"] == ["PAT-01"]  # seen in two sources
    assert len(report["single_source_patterns"]) == 4


def test_unverified_entries_do_not_count(tmp_path: Path) -> None:
    sources = [source(1, "org A"), source(2, "org B"), source(3, "org C")]
    sources[2]["verified_by"] = None
    patterns = [pattern(i, f"type_{i}", [1], verified=i != 5) for i in range(1, 6)]
    report = check(*load(*write(tmp_path, sources, patterns, rows(30, 2))))
    assert report["sources"] == 2 and report["pattern_types"] == 4
    assert report["ready"] is False


def test_two_publishers_are_needed(tmp_path: Path) -> None:
    sources = [source(i, "org A") for i in (1, 2, 3)]
    patterns = [pattern(i, f"type_{i}", [1]) for i in range(1, 6)]
    report = check(*load(*write(tmp_path, sources, patterns, rows(30, 3))))
    assert report["ready"] is False and any("publisher" in m for m in report["missing"])


@pytest.mark.parametrize(
    "broken",
    [
        "unknown source",  # a pattern cites a source the manifest lacks
        "raw text in the catalog",  # the committed catalog must not carry original text
        "duplicate id",
        "public without hash",
    ],
)
def test_a_broken_file_is_refused(tmp_path: Path, broken: str) -> None:
    sources = [source(1, "org A"), source(2, "org B")]
    patterns = [pattern(1, "type_1", [1])]
    if broken == "unknown source":
        patterns = [pattern(1, "type_1", [9])]
    elif broken == "raw text in the catalog":
        patterns[0]["raw_example"] = "ROW-1"
    elif broken == "duplicate id":
        sources.append(source(1, "org C"))
    else:
        sources[0]["sha256"] = None
    with pytest.raises(NotationError):
        load(*write(tmp_path, sources, patterns, rows(2, 2)))


def test_the_committed_catalog_without_local_rows_is_not_ready(tmp_path: Path) -> None:
    from tests.conftest import ROOT

    report = check(
        *load(
            ROOT / "data/reference/bom/manifest.yaml",
            ROOT / "data/reference/bom-notation-patterns.yaml",
            tmp_path / "raw-examples.yaml",
        )
    )
    # A checkout has metadata, but the original excerpts remain local (D-104, D-106).
    # The test must not depend on whether this developer has those private files.
    assert report["raw_rows"] == 0
    assert report["ready"] is False
    assert any("raw rows" in message for message in report["missing"])
