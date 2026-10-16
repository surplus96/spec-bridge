"""Upload API (W4-7, MVP) and the job API for the review UI (W5-4).

Run on loopback only (local-first, NFR-01):
    OFFLINE=1 uv run uvicorn spec_bridge.api.app:app --host 127.0.0.1 --port 8000
Switch the model with one setting (NFR-05); embeddings for retrieval stay local:
    SPEC_BRIDGE_PROVIDER=openai uv run uvicorn spec_bridge.api.app:app --host 127.0.0.1
    curl -F file=@data/synth/inputs/<a dev document> http://127.0.0.1:8000/documents

The job API (/api/...) is in `spec_bridge.api.jobs`; the service wiring in `deps`.
"""

import hashlib
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from spec_bridge.api.boms import router as boms_router
from spec_bridge.api.deps import (
    ALLOWED_SUFFIXES,
    Service,
    get_service,
    load_registry,
    service_provider,
)
from spec_bridge.api.jobs import router as jobs_router
from spec_bridge.normalize.dictionary import ROOT
from spec_bridge.pipeline import process_document

__all__ = ["Service", "app", "get_service", "load_registry", "service_provider"]


app = FastAPI(title="spec-bridge", version="0.1.0")
app.include_router(jobs_router)
app.include_router(boms_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/documents")
def upload(file: UploadFile, service: Annotated[Service, Depends(get_service)]) -> dict[str, Any]:
    """Unsupported type: 415. Empty file: 400. Anything else: 200 with the result JSON,
    whose status is needs_review when the file could not be parsed or understood."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"unsupported file type {suffix!r}; use .pdf, .xlsx or .docx")
    data = file.file.read()
    if not data:
        raise HTTPException(400, "empty file")
    document_id = f"UP-{hashlib.sha256(data).hexdigest()[:12]}"
    with tempfile.TemporaryDirectory() as folder:  # the upload never outlives the request
        path = Path(folder) / f"{document_id}{suffix}"
        path.write_bytes(data)
        result = process_document(
            path,
            document_id,
            onto=service.onto,
            normalizer=service.normalizer,
            provider=service.provider,
            rag=service.rag,
            registry=service.registry,
            makers=service.makers,
            provenance=service.provenance,
            file_name=file.filename,
        )
    return result.model_dump(mode="json")


# The review UI (W5-5, D-061): the built React app on the same origin as the API, so the
# browser needs no CORS and nothing is fetched from outside (NFR-01). Mounted last: the
# API routes above take precedence. Without a build (tests, MVP), nothing is mounted.
UI = ROOT / "web/dist"
if UI.is_dir():
    app.mount("/", StaticFiles(directory=UI, html=True), name="ui")
