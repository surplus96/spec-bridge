"""Service wiring shared by the MVP upload API and the job API (W4-7, W5-4).

The service (ontology, normalizer, model, E1SV RAG chain, registry) is built once on the
first request. Tests replace it through FastAPI's dependency override of `get_service`.
"""

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from spec_bridge.envfile import load_env_file
from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.provider import JsonProvider
from spec_bridge.normalize.dictionary import ROOT, load_dictionary
from spec_bridge.normalize.values import Normalizer
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.rag.pipeline import RagSetup
from spec_bridge.registry.identity import MakerIndex
from spec_bridge.service import (
    make_provider,
    make_rag,
    normalizer_for,
    prompt_hashes,
    sha256_file,
)

ALLOWED_SUFFIXES = {".pdf", ".xlsx", ".docx"}
REGISTRY = ROOT / "data/synth/registry"
ONTOLOGY = ROOT / "ontology/ontology.yaml"


@dataclass
class Service:
    onto: Ontology
    normalizer: Normalizer
    provider: JsonProvider
    rag: RagSetup | None
    registry: list[dict[str, Any]]
    makers: MakerIndex
    provenance: dict[str, Any] = field(default_factory=dict)
    audit: AuditLog | None = None  # the model's audit log, so the job API can add a sink


def load_registry(split: str = "dev") -> tuple[list[dict[str, Any]], MakerIndex]:
    records = [json.loads(line) for line in (REGISTRY / f"{split}.jsonl").read_text().splitlines()]
    makers = MakerIndex(json.loads((REGISTRY / "manufacturers.json").read_text()))
    return records, makers


PROVIDERS = ("ollama", "openai")


def service_provider(audit: AuditLog) -> tuple[JsonProvider, dict[str, Any]]:
    """One setting picks the model (NFR-05): SPEC_BRIDGE_PROVIDER=ollama (default) or
    openai; SPEC_BRIDGE_MODEL and SPEC_BRIDGE_BASE_URL are optional overrides."""
    kind = os.environ.get("SPEC_BRIDGE_PROVIDER", "ollama")
    if kind not in PROVIDERS:
        raise ValueError(f"SPEC_BRIDGE_PROVIDER must be one of {PROVIDERS}, not {kind!r}")
    model = os.environ.get("SPEC_BRIDGE_MODEL") or None
    base_url = os.environ.get("SPEC_BRIDGE_BASE_URL") or None
    return make_provider(kind, model, base_url, audit)


def built_once[T](build: Callable[[], T]) -> Callable[[], T]:
    """Build on the first call, behind a lock: a page load sends several requests at once
    and the build embeds the KB on the local model (D-075). A failed build is not kept, so
    the next request tries again (e.g. after the model server is started)."""
    lock = threading.Lock()
    done: list[T] = []

    @wraps(build)
    def get() -> T:
        with lock:
            if not done:
                done.append(build())
            return done[0]

    return get


@built_once
def get_service() -> Service:
    """Production wiring: the chosen model and the E1SV configuration (D-053)."""
    load_env_file(ROOT / ".env")  # API keys for the cloud option; shell variables win
    onto = load_ontology(ONTOLOGY)
    audit = AuditLog(ROOT / "var/api/audit.jsonl")
    provider, model_info = service_provider(audit)
    rag = make_rag(provider, retrieval=True, self_check=True, resolve=True)
    registry, makers = load_registry()
    provenance = {
        "model": model_info,
        "ontology_sha256": sha256_file(ONTOLOGY),
        "prompt_modules": prompt_hashes(),
        "rag": rag.info,
    }
    normalizer = normalizer_for(onto, "dev", load_dictionary())
    return Service(onto, normalizer, provider, rag, registry, makers, provenance, audit)
