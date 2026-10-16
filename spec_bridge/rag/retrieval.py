"""Retrievers over the knowledge base (W4-R R2, D-043/D-046).

Three LangChain retrievers share one rule: when `exclude_family` is set, no example of
that product family comes back (leave-family-out evaluation, Review Focus 1). They are
`BaseRetriever` subclasses, so they compose in LCEL chains; per query, set the family with
`for_query(retriever, family)`.

- KbBM25Retriever: lexical, rank_bm25 over the line text; exact symbols such as R1 or cSt.
- KbDenseRetriever: embedding search in Chroma with a family where-filter.
- KbHybridRetriever: reciprocal rank fusion (RRF) of the two lists.

FAISS is not used here: it cannot share a process with Docling (OpenMP clash, D-044); the
search diagnosis compares it in its own process (R3).
"""

import re
import uuid
from typing import Any

from langchain_chroma import Chroma
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, PrivateAttr
from rank_bm25 import BM25Okapi

from spec_bridge.rag.knowledge import KbExample
from spec_bridge.rag.settings import chroma_settings

TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")  # keeps "4-stroke", "r1", "17220.6"
RRF_K = 60  # standard reciprocal-rank-fusion constant; equal weights (D-043 decision 5)


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.casefold())


def to_document(example: KbExample) -> Document:
    """The searched chunk is the line; metadata leads back to the whole example."""
    metadata = {
        "example_id": example.example_id,
        "family_id": example.family_id,
        "attribute": example.attribute,
    }
    return Document(page_content=example.line_text, metadata=metadata)


def examples_of(documents: list[Document], kb: dict[str, KbExample]) -> list[KbExample]:
    return [kb[d.metadata["example_id"]] for d in documents]


class KbRetriever(BaseRetriever):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    k: int = 5
    exclude_family: str | None = None


def for_query(retriever: KbRetriever, family: str | None) -> KbRetriever:
    """A copy that leaves out one family; the shared index is not rebuilt."""
    return retriever.model_copy(update={"exclude_family": family})


class KbBM25Retriever(KbRetriever):
    _docs: list[Document] = PrivateAttr()
    _index: BM25Okapi = PrivateAttr()

    def __init__(self, examples: list[KbExample], **data: Any) -> None:
        super().__init__(**data)
        self._docs = [to_document(e) for e in examples]
        self._index = BM25Okapi([tokens(d.page_content) for d in self._docs])

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        words = tokens(query)
        if not words:
            return []
        scores = self._index.get_scores(words)
        ranked = sorted(
            (
                (float(score), doc.metadata["example_id"], doc)
                for score, doc in zip(scores, self._docs, strict=True)
                if score > 0 and doc.metadata["family_id"] != self.exclude_family
            ),
            key=lambda row: (-row[0], row[1]),  # ties broken by id: deterministic
        )
        return [doc for _, _, doc in ranked[: self.k]]


class KbDenseRetriever(KbRetriever):
    _store: Chroma = PrivateAttr()

    def __init__(self, examples: list[KbExample], embeddings: Embeddings, **data: Any) -> None:
        super().__init__(**data)
        self._store = Chroma.from_documents(
            [to_document(e) for e in examples],
            embeddings,
            collection_name=f"kb-{uuid.uuid4().hex[:12]}",  # in-memory, one per index
            client_settings=chroma_settings(),
        )

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        if not query.strip():
            return []
        where: Any = {"family_id": {"$ne": self.exclude_family}} if self.exclude_family else None
        return self._store.similarity_search(query, k=self.k, filter=where)


class KbHybridRetriever(KbRetriever):
    lexical: KbRetriever
    semantic: KbRetriever
    fetch_k: int = 20  # depth of each list before fusion

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        fused: dict[str, float] = {}
        docs: dict[str, Document] = {}
        for part in (self.lexical, self.semantic):
            ranked = part.model_copy(
                update={"k": self.fetch_k, "exclude_family": self.exclude_family}
            )
            for rank, doc in enumerate(ranked.invoke(query), start=1):
                key = doc.metadata["example_id"]
                fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank)
                docs[key] = doc
        order = sorted(fused, key=lambda key: (-fused[key], key))
        return [docs[key] for key in order[: self.k]]
