"""Local RAG settings (W4-R R0, D-043): embedding models and offline vector stores.

Embeddings run on the local Ollama server only (NFR-01). Chroma's anonymous telemetry is
switched off; tests/rag/test_offline.py checks that no store or embedding call leaves
the machine.
"""

from chromadb.config import Settings
from langchain_ollama import OllamaEmbeddings

from spec_bridge.llm.provider import DEFAULT_HOST, check_offline_host

EMBEDDING_MODELS = ("bge-m3", "nomic-embed-text")  # candidates compared in R3


def chroma_settings(persist_directory: str | None = None) -> Settings:
    """In-memory by default; persistent when a directory is given. Never phones home."""
    return Settings(
        anonymized_telemetry=False,
        is_persistent=persist_directory is not None,
        persist_directory=persist_directory or "./chroma",
    )


def ollama_embeddings(model: str, host: str = DEFAULT_HOST) -> OllamaEmbeddings:
    check_offline_host(host)  # OFFLINE=1 refuses non-loopback embedding servers
    return OllamaEmbeddings(model=model, base_url=host)
