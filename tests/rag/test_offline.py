"""W4-R R0: vector stores and local embeddings make no outbound connection (NFR-01).

The fake-embedding test runs everywhere and catches store-side traffic (Chroma telemetry).
FAISS and PyTorch (Docling) each ship their own OpenMP runtime, and loading both in one
process aborts (OMP Error #15, D-044), so FAISS is checked in a separate process. The Ollama
test also measures each candidate model's dimension; it needs RUN_LLM=1.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from spec_bridge.rag.settings import EMBEDDING_MODELS, chroma_settings, ollama_embeddings

LINES = [
    ("Engine (kWm) | 3746.4 | kW | continuous rating; at R1; engine shaft", "F1"),
    ("Dry weight | 31755.2 | kg | dry; for engine without generator", "F2"),
    ("Rated speed | 720 | rpm | at R1; for engine crankshaft", "F3"),
]
DOCS = [Document(page_content=text, metadata={"family_id": fam}) for text, fam in LINES]
FAISS_PROBE = """
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
docs = [Document(page_content=t) for t in ("dry weight", "rated speed")]
store = FAISS.from_documents(docs, DeterministicFakeEmbedding(size=16))
print(store.similarity_search("dry weight", k=1)[0].page_content)
"""


def search_in_process(embeddings: Embeddings, tmp_path: Path) -> list[str]:
    """Load and query Chroma (persistent, telemetry off, family filter) and BM25."""
    chroma = Chroma.from_documents(
        DOCS,
        embeddings,
        collection_name="r0_probe",
        client_settings=chroma_settings(str(tmp_path / "chroma")),
    )
    bm25 = BM25Retriever.from_documents(DOCS, k=1)
    not_f1: Any = {"family_id": {"$ne": "F1"}}  # Chroma where-filter (operator form)
    hits = [
        chroma.similarity_search("dry weight", k=1, filter=not_f1)[0],
        bm25.invoke("R1 crankshaft")[0],
    ]
    return [hit.page_content for hit in hits]


def test_vector_stores_stay_offline(outbound: list[Any], tmp_path: Path) -> None:
    contents = search_in_process(DeterministicFakeEmbedding(size=16), tmp_path)
    assert contents[0] != LINES[0][0]  # the excluded family never comes back
    assert contents[1] == LINES[2][0]  # BM25 finds the exact tokens
    assert outbound == []


def test_faiss_runs_in_its_own_process() -> None:
    done = subprocess.run(
        [sys.executable, "-c", FAISS_PROBE], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-500:]
    assert done.stdout.strip() == "dry weight"


@pytest.mark.llm
@pytest.mark.skipif(os.environ.get("RUN_LLM") != "1", reason="set RUN_LLM=1 with Ollama up")
@pytest.mark.parametrize("model", EMBEDDING_MODELS)
def test_local_embeddings_stay_offline(outbound: list[Any], tmp_path: Path, model: str) -> None:
    embeddings = ollama_embeddings(model)
    vectors = embeddings.embed_documents([text for text, _ in LINES])
    dims = {len(v) for v in vectors}
    print(f"\n{model}: dimension {dims.pop()}")
    assert not dims  # every vector has the same length
    assert search_in_process(embeddings, tmp_path)[0] == LINES[1][0]
    assert outbound == []
