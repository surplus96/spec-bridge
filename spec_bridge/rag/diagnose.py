"""Search-quality diagnosis (W4-R R3): which retriever finds the right solved case?

For every KB example used as a query, the retrievers search the KB with the query's own
family left out (leave-family-out). A hit is a returned example whose qualifiers equal the
query's: exactly the example a few-shot prompt would need. No LLM generation is involved,
so the retriever is chosen here, once, before any generation run (D-043 decision 4).

Run (needs the local Ollama embeddings; FAISS forbids importing Docling, D-044):
    uv run python -m spec_bridge.rag.diagnose
    uv run python -m spec_bridge.rag.diagnose --rewrite   # also the LLM query rewriting
"""

import argparse
import json
import re
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from pydantic import PrivateAttr

from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.ontology.facts import StrictModel
from spec_bridge.rag.knowledge import OUTPUT as KB_PATH
from spec_bridge.rag.knowledge import KbExample, Qualifiers, load_kb
from spec_bridge.rag.retrieval import (
    RRF_K,
    KbBM25Retriever,
    KbDenseRetriever,
    KbHybridRetriever,
    KbRetriever,
    examples_of,
    for_query,
    to_document,
)
from spec_bridge.rag.settings import EMBEDDING_MODELS, ollama_embeddings

ROOT = Path(__file__).resolve().parents[2]
EMPTY_CELLS = {"", "—", "-"}
SEGMENT = re.compile(r"\s*[;,]\s*")
REWRITE_SYSTEM = (
    "You rewrite one line of a technical specification into short search queries. "
    "Return up to three queries: one for how the value is defined (basis), one for the "
    "conditions it holds under, one for the part of the equipment it refers to. "
    "Use only words from the line."
)
REWRITE_SCHEMA = {
    "type": "object",
    "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
    "required": ["queries"],
}

QueryMaker = Callable[[KbExample], list[str]]


# query variants ---------------------------------------------------------------------------
def label_and_remarks(line: str) -> str:
    """The label and the remarks of a line; the value and unit are noise for retrieval.

    Table rows read `label | value | unit | remarks`; text lines `label — value (remarks)`.
    """
    cells = [c.strip() for c in line.split(" | ")]
    if len(cells) >= 2:
        remarks = cells[3] if len(cells) >= 4 and cells[3] not in EMPTY_CELLS else ""
        return f"{cells[0]} {remarks}".strip()
    label, _, rest = line.partition(" — ")
    found = re.search(r"\(([^()]*)\)\s*$", rest)
    return f"{label} {found.group(1) if found else ''}".strip()


def segments(line: str) -> list[str]:
    """Rule-based multi-query: the label, then each remark piece separately."""
    text = label_and_remarks(line)
    return [part for part in SEGMENT.split(text) if part]


def llm_rewrite(provider: JsonProvider) -> QueryMaker:
    """LLM-based multi-query rewriting; falls back to the line if the model fails."""

    def make(example: KbExample) -> list[str]:
        try:
            reply = provider.complete_json(
                system=REWRITE_SYSTEM,
                user=f"Line: {example.line_text}",
                schema=REWRITE_SCHEMA,
                task="rag-rewrite",
            )
        except LlmError:  # the model gave no usable JSON: keep the plain line
            return [example.line_text]
        queries = [q for q in reply.get("queries", []) if isinstance(q, str) and q.strip()]
        return queries[:3] or [example.line_text]

    return make


VARIANTS: dict[str, QueryMaker] = {
    "line": lambda e: [e.line_text],
    "label_remarks": lambda e: [label_and_remarks(e.line_text)],
    "segments": lambda e: segments(e.line_text),
}


def multi_search(
    retriever: KbRetriever, queries: Sequence[str], family: str, k: int
) -> list[Document]:
    """One query: plain search. Several: search each, then reciprocal rank fusion."""
    one = for_query(retriever, family)
    if len(queries) == 1:
        return one.model_copy(update={"k": k}).invoke(queries[0])
    fused: dict[str, float] = {}
    docs: dict[str, Document] = {}
    for query in queries:
        for rank, doc in enumerate(one.model_copy(update={"k": 20}).invoke(query), start=1):
            key = doc.metadata["example_id"]
            fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank)
            docs[key] = doc
    return [docs[key] for key in sorted(fused, key=lambda key: (-fused[key], key))[:k]]


# FAISS (separate process only) ----------------------------------------------------------
class KbFaissRetriever(KbRetriever):
    """Exact L2 search in FAISS; never import this where Docling runs (D-044)."""

    _store: Any = PrivateAttr()
    _size: int = PrivateAttr()

    def __init__(self, examples: list[KbExample], embeddings: Embeddings, **data: Any) -> None:
        super().__init__(**data)
        from langchain_community.vectorstores import FAISS

        self._store = FAISS.from_documents([to_document(e) for e in examples], embeddings)
        self._size = len(examples)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        if not query.strip():
            return []
        family = self.exclude_family
        keep = (lambda meta: meta["family_id"] != family) if family else None
        found: list[Document] = self._store.similarity_search(
            query, k=self.k, filter=keep, fetch_k=self._size
        )
        return found


class CachedEmbeddings(Embeddings):
    """Embeds each distinct text once; Chroma, FAISS and the queries share the vectors."""

    def __init__(self, inner: Embeddings) -> None:
        self.inner = inner
        self.cache: dict[str, list[float]] = {}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if missing:
            self.cache.update(zip(missing, self.inner.embed_documents(missing), strict=True))
        return [self.cache[t] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


# scoring ----------------------------------------------------------------------------------
class DiagnosisRow(StrictModel):
    retriever: str
    variant: str
    queries: int  # examples with qualifiers
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float  # first exact match within the top 10
    empty_top1: float  # examples without qualifiers whose first result is also empty
    ms_per_query: float


def diagnose_one(
    name: str, variant: str, retriever: KbRetriever, kb: list[KbExample], make: QueryMaker
) -> DiagnosisRow:
    by_id = {e.example_id: e for e in kb}
    with_q = [e for e in kb if e.qualifiers != Qualifiers()]
    without = [e for e in kb if e.qualifiers == Qualifiers()]
    hits = {1: 0, 3: 0, 5: 0}
    reciprocal = 0.0
    started = time.perf_counter()
    for example in with_q:
        found = examples_of(multi_search(retriever, make(example), example.family_id, 10), by_id)
        ranks = [i for i, f in enumerate(found, 1) if f.qualifiers == example.qualifiers]
        for k in hits:
            hits[k] += bool(ranks and ranks[0] <= k)
        reciprocal += 1 / ranks[0] if ranks else 0.0
    empty = 0
    for example in without:
        found = examples_of(multi_search(retriever, make(example), example.family_id, 1), by_id)
        empty += bool(found) and found[0].qualifiers == Qualifiers()
    elapsed = (time.perf_counter() - started) * 1000 / max(1, len(kb))
    n = max(1, len(with_q))
    return DiagnosisRow(
        retriever=name,
        variant=variant,
        queries=len(with_q),
        hit_at_1=hits[1] / n,
        hit_at_3=hits[3] / n,
        hit_at_5=hits[5] / n,
        mrr=reciprocal / n,
        empty_top1=empty / max(1, len(without)),
        ms_per_query=round(elapsed, 2),
    )


def retrievers(kb: list[KbExample], embeddings: dict[str, Embeddings]) -> dict[str, KbRetriever]:
    """BM25, each embedding in Chroma and FAISS, and BM25 + Chroma hybrids."""
    lexical = KbBM25Retriever(kb)
    found: dict[str, KbRetriever] = {"bm25": lexical}
    for model, embedding in embeddings.items():
        chroma = KbDenseRetriever(kb, embedding)
        found[f"dense:{model}:chroma"] = chroma
        found[f"dense:{model}:faiss"] = KbFaissRetriever(kb, embedding)
        found[f"hybrid:bm25+{model}"] = KbHybridRetriever(lexical=lexical, semantic=chroma)
    return found


def run(
    kb: list[KbExample],
    embeddings: dict[str, Embeddings],
    variants: dict[str, QueryMaker],
) -> list[DiagnosisRow]:
    rows = []
    for name, retriever in retrievers(kb, embeddings).items():
        for variant, make in variants.items():
            if variant == "llm_rewrite" and not name.startswith("hybrid"):
                continue  # rewriting costs one LLM call per query: hybrids only
            rows.append(diagnose_one(name, variant, retriever, kb, make))
    return rows


def table(rows: list[DiagnosisRow]) -> str:
    head = "| retriever | variant | hit@1 | hit@3 | hit@5 | MRR | empty top-1 | ms/query |"
    lines = [head, "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (-r.hit_at_3, -r.mrr, r.ms_per_query)):
        lines.append(
            f"| {r.retriever} | {r.variant} | {r.hit_at_1:.3f} | {r.hit_at_3:.3f} | "
            f"{r.hit_at_5:.3f} | {r.mrr:.3f} | {r.empty_top1:.3f} | {r.ms_per_query} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", type=Path, default=KB_PATH)
    parser.add_argument("--fake-embeddings", action="store_true", help="tests only")
    parser.add_argument("--rewrite", action="store_true", help="add LLM query rewriting")
    parser.add_argument("--out", type=Path, default=ROOT / "var/rag")
    args = parser.parse_args()
    kb = load_kb(args.kb)
    if args.fake_embeddings:
        embeddings: dict[str, Embeddings] = {"fake": DeterministicFakeEmbedding(size=16)}
    else:
        embeddings = {m: CachedEmbeddings(ollama_embeddings(m)) for m in EMBEDDING_MODELS}
    variants = dict(VARIANTS)
    if args.rewrite:
        from spec_bridge.llm.audit import AuditLog
        from spec_bridge.llm.provider import DEFAULT_MODEL, OllamaProvider

        audit = AuditLog(args.out / "diagnosis-rewrite-audit.jsonl")
        variants["llm_rewrite"] = llm_rewrite(OllamaProvider(DEFAULT_MODEL, audit))
    rows = run(kb, embeddings, variants)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"diagnosis-{stamp}.json"
    record = {
        "kb": str(args.kb),
        "embeddings": {m: len(e.embed_query("probe")) for m, e in embeddings.items()},
        "rows": [r.model_dump() for r in rows],
    }
    out.write_text(json.dumps(record, indent=2) + "\n")
    print(table(rows))
    print(f"\nwritten {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
