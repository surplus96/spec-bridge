"""Production wiring (W5-0): the model, the normalizer and the E1SV RAG chain.

Shared by the API, the registration graph and the experiment runner, so that the
service does not import the experiment runner. Not part of the scorer hash.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from spec_bridge.extract import classifier, extractor, prompt_input, rules, schemas
from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.openai_compat import OPENAI_BASE_URL, OPENAI_DEFAULT_MODEL, OpenAIProvider
from spec_bridge.llm.provider import DEFAULT_MODEL, JsonProvider, OllamaProvider
from spec_bridge.normalize.dictionary import load_dictionary
from spec_bridge.normalize.values import Normalizer
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.rag import knowledge, pipeline, qualifiers, selfrag
from spec_bridge.rag import retrieval as retrieval_module
from spec_bridge.rag.knowledge import OUTPUT as KB_PATH
from spec_bridge.rag.knowledge import load_kb
from spec_bridge.rag.pipeline import RagSetup
from spec_bridge.rag.qualifiers import build_chain
from spec_bridge.rag.retrieval import KbBM25Retriever, KbDenseRetriever, KbHybridRetriever
from spec_bridge.rag.settings import ollama_embeddings

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology/ontology.yaml"
REGISTRY = ROOT / "data/synth/registry"
PROMPT_MODULES = (classifier, extractor, prompt_input, rules, schemas)
RAG_MODULES = (knowledge, qualifiers, retrieval_module, selfrag, pipeline)  # W4-R
RAG_EMBEDDING = "bge-m3"  # D-047
RAG_K = 3  # D-047


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_hashes() -> dict[str, str]:
    """Prompts, schemas and rules live in code: hash those modules (frozen before W3-7)."""
    return {m.__name__: sha256_file(Path(str(m.__file__))) for m in PROMPT_MODULES}


def normalizer_for(onto: Ontology, split: str, dictionary: dict[str, Any]) -> Normalizer:
    """Identity master data of the same split only (CP-S2 W3 input contract)."""
    makers = json.loads((REGISTRY / "manufacturers.json").read_text())
    models = [
        json.loads(line)["model_designation"]
        for line in (REGISTRY / f"{split}.jsonl").read_text().splitlines()
    ]
    return Normalizer(onto, dictionary, makers, models)


def make_provider(
    kind: str, model: str | None, base_url: str | None, audit: AuditLog
) -> tuple[JsonProvider, dict[str, Any]]:
    """The model the run talks to, and how run.json describes it."""
    if kind == "openai":
        cloud = OpenAIProvider(
            model or OPENAI_DEFAULT_MODEL, audit, base_url=base_url or OPENAI_BASE_URL
        )
        info = {"name": cloud.model, "url": cloud.url, "strict": cloud.strict}
        return cloud, {"provider": kind, **info, "options": cloud.options}
    ollama = OllamaProvider(model or DEFAULT_MODEL, audit)
    info = {"name": ollama.model, "digest": ollama.digest, "options": ollama.options}
    return ollama, {"provider": kind, **info}


def make_rag(
    provider: JsonProvider | None,
    *,
    retrieval: bool,
    self_check: bool = False,
    resolve: bool = False,
) -> RagSetup:
    """Config E with the retriever fixed in D-047 (E1), or without retrieval (E0).
    self_check: Self-RAG support check (R5); resolve: attribute conflicts by retrieved
    cases (D-052). Both need the run to say so in its id and run.json."""
    assert provider is not None
    onto = load_ontology(ONTOLOGY)
    normalizer = normalizer_for(onto, "dev", load_dictionary())
    kb = load_kb()
    retriever = None
    if retrieval:
        lexical = KbBM25Retriever(kb)
        semantic = KbDenseRetriever(kb, ollama_embeddings(RAG_EMBEDDING))
        retriever = KbHybridRetriever(lexical=lexical, semantic=semantic)
    chain = build_chain(onto, normalizer, provider, kb, retriever, k=RAG_K, self_check=self_check)
    info = {
        "mode": "e1" if retrieval else "e0",
        "self_check": self_check,
        "resolve_conflicts": resolve and retriever is not None,
        "kb_sha256": sha256_file(KB_PATH),
        "retriever": f"hybrid:bm25+{RAG_EMBEDDING}" if retrieval else None,
        "query": "label_remarks",
        "k": RAG_K if retrieval else 0,
        "modules": {m.__name__: sha256_file(Path(str(m.__file__))) for m in RAG_MODULES},
    }
    by_id = {e.example_id: e for e in kb}
    resolver = retriever if resolve else None
    return RagSetup(chain=chain, info=info, retriever=resolver, kb=by_id, k=RAG_K)
