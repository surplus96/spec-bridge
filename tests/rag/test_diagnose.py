"""W4-R R3: the search diagnosis counts the right hits, honours leave-family-out, and runs
FAISS only in a process without Docling (D-044)."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from spec_bridge.llm.provider import LlmError
from spec_bridge.rag.diagnose import (
    diagnose_one,
    label_and_remarks,
    llm_rewrite,
    multi_search,
    segments,
)
from spec_bridge.rag.knowledge import KbExample, Qualifiers, save_kb
from spec_bridge.rag.retrieval import KbBM25Retriever
from tests.llm.fakes import FakeProvider

R1 = Qualifiers(condition={"rating_point": "R1"}, scope="engine shaft")
DRY = Qualifiers(basis={"weight": "dry"})


def example(i: str, family: str, text: str, q: Qualifiers) -> KbExample:
    return KbExample(
        example_id=i,
        doc_id=i.split(":")[0],
        family_id=family,
        split="dev",
        attribute="x",
        label_text=None,
        line_text=text,
        parent_text=f"Line: {text}",
        qualifiers=q,
        evidence={},
    )


KB = [
    example("A:1", "FA", "Power | 1 | kW | at R1; engine shaft", R1),
    example("B:1", "FB", "Output | 2 | kW | rating point R1; for engine shaft", R1),
    example("A:2", "FA", "Dry weight | 3 | kg | dry", DRY),  # its only twin is in FA
    example("A:3", "FA", "Dry weight | 4 | kg | dry", DRY),
    example("C:1", "FC", "Bore | 5 | mm | —", Qualifiers()),
    example("D:1", "FD", "Stroke | 6 | mm | —", Qualifiers()),
]


def test_label_and_remarks_drop_value_and_unit() -> None:
    assert label_and_remarks("Power | 1 | kW | at R1; engine shaft") == "Power at R1; engine shaft"
    assert label_and_remarks("Bore | 5 | mm | —") == "Bore"
    assert (
        label_and_remarks("Dry mass — 552.76 kg (dry; complete unit)")
        == "Dry mass dry; complete unit"
    )
    assert label_and_remarks("Maker — X Works") == "Maker"


def test_segments_split_the_remarks() -> None:
    assert segments("Power | 1 | kW | at R1; engine shaft, per TC") == [
        "Power at R1",
        "engine shaft",
        "per TC",
    ]


def test_hits_count_only_other_families() -> None:
    row = diagnose_one("bm25", "line", KbBM25Retriever(KB), KB, lambda e: [e.line_text])
    # A:1 and B:1 find each other; A:2 and A:3 only have a twin in their own family.
    assert row.queries == 4 and row.hit_at_1 == 0.5 and row.hit_at_5 == 0.5
    assert row.empty_top1 == 1.0  # Bore and Stroke both find an empty example first


def test_multi_search_fuses_and_excludes() -> None:
    found = multi_search(KbBM25Retriever(KB), ["at R1", "engine shaft"], "FA", 5)
    ids = [d.metadata["example_id"] for d in found]
    assert ids[0] == "B:1" and len(ids) == len(set(ids))
    assert all(not i.startswith("A:") for i in ids)


def test_llm_rewrite_uses_the_reply_or_falls_back() -> None:
    make = llm_rewrite(FakeProvider([{"queries": ["at R1", "engine shaft", "", 3]}]))
    assert make(KB[0]) == ["at R1", "engine shaft"]
    broken = llm_rewrite(FakeProvider([LlmError("rag-rewrite", "timeout")]))
    assert broken(KB[0]) == [KB[0].line_text]


def run_module(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "spec_bridge.rag.diagnose", *args],
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_diagnosis_runs_faiss_in_its_own_process(tmp_path: Path) -> None:
    save_kb(KB, tmp_path / "kb.jsonl")
    done = run_module(
        "--fake-embeddings", "--kb", str(tmp_path / "kb.jsonl"), "--out", str(tmp_path)
    )
    assert done.returncode == 0, done.stderr[-800:]
    record: dict[str, Any] = json.loads(next(tmp_path.glob("diagnosis-*.json")).read_text())
    names = {row["retriever"] for row in record["rows"]}
    assert {"bm25", "dense:fake:chroma", "dense:fake:faiss", "hybrid:bm25+fake"} == names
    assert record["embeddings"] == {"fake": 16}


def test_diagnosis_never_imports_docling() -> None:
    probe = (
        "import sys, spec_bridge.rag.diagnose; "
        "print('docling' in sys.modules, 'torch' in sys.modules)"
    )
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert done.stdout.split() == ["False", "False"], done.stderr[-500:]
