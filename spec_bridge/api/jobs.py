"""Job API for the review UI (W5-4, D-062~D-064, D-066).

    POST /api/jobs                    upload → 202, the graph runs in the background
    GET  /api/jobs                    jobs, newest first
    GET  /api/jobs/{id}               status and the waiting prompt (choose class / review)
    POST /api/jobs/{id}/resume        the reviewer's command + request_id → 202
    GET  /api/jobs/{id}/source        the uploaded file (PDF viewer)
    GET  /api/jobs/{id}/blocks        parsed blocks with their places (highlights)
    GET  /api/jobs/{id}/supplement    what the sender must add (D-066)
    GET  /api/products/{id}           a registered product: facts, evidence, edits, events,
                                      its components and parents (has_component, D-103)

One worker runs graph work (the local model serves one request at a time). A command is
checked here against the waiting prompt first (409 with the reason), so the screen hears
at once why a button does nothing; the graph checks again. A repeated request_id is
answered with the current state and never applied twice. Every upload, command, failure
and model call is written to the registry's audit table (NFR-02).
"""

import hashlib
import json
import os
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field, TypeAdapter

from spec_bridge.api.deps import ALLOWED_SUFFIXES, Service, built_once, get_service
from spec_bridge.graph.registration import (
    GraphDeps,
    build_graph,
    open_checkpointer,
    prompt_of,
    result_of,
    resume,
    review_prompt,
    start,
    state_of,
)
from spec_bridge.graph.state import ClassPrompt, ResumeCommand, ReviewPrompt
from spec_bridge.normalize.dictionary import ROOT
from spec_bridge.ontology.display import DisplayLabels, load_display_labels
from spec_bridge.ontology.facts import Location, StrictModel
from spec_bridge.registry.explain import place_of
from spec_bridge.registry.output import RegistrationResult
from spec_bridge.registry.store import RegistryStore
from spec_bridge.registry.supplement import SupplementRequest, supplement_request

REGISTRY = ROOT / "data/synth/registry"
CURRENT_JOB: ContextVar[str | None] = ContextVar("current_job", default=None)

Status = Literal[
    "running",
    "awaiting_class",
    "awaiting_review",
    "registered",
    "linked",
    "cancelled",
    "failed",
    "stalled",  # stopped between two stops (the server ended mid-run)
]
Prompt = Annotated[ClassPrompt | ReviewPrompt, Field(discriminator="kind")]
PROMPT: TypeAdapter[Prompt] = TypeAdapter(Prompt)


class JobSummary(StrictModel):
    job_id: str
    file_name: str | None
    document_id: str
    uploaded_at: str
    status: Status
    class_id: str | None = None
    product_id: str | None = None


class JobView(JobSummary):
    prompt: Prompt | None = None
    error: str | None = None


class ResumeRequest(StrictModel):
    request_id: Annotated[str, Field(min_length=1, max_length=100)]
    command: ResumeCommand


class BlockView(StrictModel):
    index: int
    kind: str
    text: str
    section: str | None
    location: Location


class ProductFact(StrictModel):
    attribute: str
    value: Any
    unit: str | None
    basis: dict[str, Any]
    condition: dict[str, Any]
    scope: str
    evidence_kind: Literal["registry_seed", "observed", "human_edit"]
    evidence_ref: str
    evidence_text: str = ""  # the evidence for a person (where it was read, or why it was edited)


class ProductEdit(StrictModel):
    edit_id: str
    job_id: str
    attribute: str
    op: Literal["set", "add", "remove", "context"]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    outcome: str
    reason: str
    actor: str
    at: str


class ProductEvent(StrictModel):
    event_type: str
    actor: str
    at: str
    payload: dict[str, Any]


class ProductLink(StrictModel):
    """A has_component neighbour; quantity from the last BOM that listed it, if any."""

    product_id: str
    class_id: str
    model_designation: str
    quantity: int | None = None


class ProductView(StrictModel):
    product_id: str
    class_id: str
    maker_id: str
    maker_name: str | None = None
    model_designation: str
    origin: str
    created_at: str
    facts: list[ProductFact]
    edits: list[ProductEdit]
    events: list[ProductEvent]
    components: list[ProductLink] = []
    parents: list[ProductLink] = []


class JobConflict(Exception):
    """The command does not fit the job's current state (HTTP 409)."""


class LockedRegistry:
    """The registry store behind one lock: request threads and the worker share it."""

    def __init__(self, store: RegistryStore) -> None:
        self.store = store
        self.lock = threading.RLock()

    def records(self) -> list[dict[str, Any]]:
        with self.lock:
            return self.store.records()

    def register(self, job_id: str, result: RegistrationResult, edits: list[Any]) -> str:
        with self.lock:
            return self.store.register(job_id, result, edits)

    def link(
        self, job_id: str, target_id: str, result: RegistrationResult, edits: list[Any]
    ) -> None:
        with self.lock:
            self.store.link(job_id, target_id, result, edits)

    def audit(self, job_id: str, kind: str, payload: dict[str, Any], actor: str = "system") -> None:
        with self.lock:
            self.store.audit(job_id, kind, actor, payload)

    def product(self, product_id: str) -> dict[str, Any] | None:
        with self.lock:
            return self.store.product(product_id)

    def uploads(self) -> list[dict[str, Any]]:
        """Upload rows, newest first: the job list."""
        with self.lock:
            rows = self.store.conn.execute(
                "SELECT job_id, occurred_at, payload_json FROM audit_events"
                " WHERE kind = 'uploaded' ORDER BY audit_pk DESC"
            ).fetchall()
        return [{"job_id": j, "at": at, **_json(p)} for j, at, p in rows]

    def applied(self, job_id: str, request_id: str) -> bool:
        with self.lock:
            row = self.store.conn.execute(
                "SELECT 1 FROM audit_events WHERE job_id = ? AND kind = 'command'"
                " AND json_extract(payload_json, '$.request_id') = ?",
                (job_id, request_id),
            ).fetchone()
        return row is not None


def _json(text: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(text)
    return value


class Jobs:
    def __init__(
        self,
        service: Service,
        folder: Path,
        run: Callable[[Callable[[], None]], Any] | None = None,
    ) -> None:
        self.service = service
        self.uploads_dir = folder / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        store = RegistryStore(folder / "registry.sqlite", service.onto)
        store.load_manufacturers(REGISTRY / "manufacturers.json")  # both idempotent
        store.load_jsonl(REGISTRY / "dev.jsonl")
        self.registry = LockedRegistry(store)
        deps = GraphDeps(
            service.onto,
            service.normalizer,
            service.provider,
            service.rag,
            service.makers,
            self.registry.records,  # registrations become duplicate candidates (S2)
            self.registry,
            service.provenance,
        )
        self.graph = build_graph(deps, open_checkpointer(folder / "checkpoints.sqlite"))
        self.running: set[str] = set()
        self.errors: dict[str, str] = {}
        self.lock = threading.Lock()
        self.run = run or ThreadPoolExecutor(max_workers=1, thread_name_prefix="job").submit
        if service.audit is not None:
            service.audit.sink = self._model_call

    def _model_call(self, row: dict[str, Any]) -> None:
        job_id = CURRENT_JOB.get()
        if job_id is not None:
            self.registry.audit(job_id, "llm_call", row)

    def _submit(self, job_id: str, work: Callable[[], None]) -> None:
        self.running.add(job_id)

        def task() -> None:
            token = CURRENT_JOB.set(job_id)
            try:
                work()
            except Exception as error:  # the job fails, the server does not
                self.errors[job_id] = f"{type(error).__name__}: {error}"
                self.registry.audit(job_id, "failed", {"error": self.errors[job_id]})
            finally:
                CURRENT_JOB.reset(token)
                self.running.discard(job_id)

        self.run(task)

    # -- reading ---------------------------------------------------------------------------
    def _upload(self, job_id: str) -> dict[str, Any] | None:
        return next((u for u in self.registry.uploads() if u["job_id"] == job_id), None)

    def _summary(self, upload: dict[str, Any]) -> tuple[JobSummary, Prompt | None]:
        job_id = upload["job_id"]
        state = state_of(self.graph, job_id)
        prompt = None
        status: Status
        if job_id in self.running:
            status = "running"
        elif job_id in self.errors:
            status = "failed"
        elif (value := prompt_of(self.graph, job_id)) is not None:
            prompt = PROMPT.validate_python(value)
            if prompt.kind == "review":
                # The saved pause payload is a snapshot of the code that paused the job. The
                # review node computes its prompt afresh when resumed, so show that one now.
                prompt = review_prompt(
                    state,
                    self.service.provenance,
                    self.service.onto,
                    self.service.makers,
                    self.service.normalizer.enums,
                )
            status = "awaiting_class" if prompt.kind == "choose_class" else "awaiting_review"
        elif (outcome := state.get("outcome")) is not None:
            status = outcome
        else:
            status = "stalled"
        summary = JobSummary(
            job_id=job_id,
            file_name=upload.get("file_name"),
            document_id=upload["document_id"],
            uploaded_at=upload["at"],
            status=status,
            class_id=state.get("class_id"),
            product_id=state.get("product_id"),
        )
        return summary, prompt

    def view(self, job_id: str) -> JobView | None:
        upload = self._upload(job_id)
        if upload is None:
            return None
        summary, prompt = self._summary(upload)
        return JobView(**summary.model_dump(), prompt=prompt, error=self.errors.get(job_id))

    def summaries(self) -> list[JobSummary]:
        return [self._summary(u)[0] for u in self.registry.uploads()]

    # -- writing ---------------------------------------------------------------------------
    def upload(self, file_name: str, data: bytes) -> str:
        suffix = Path(file_name).suffix.lower()
        job_id = f"JOB-{uuid.uuid4().hex[:12]}"
        digest = hashlib.sha256(data).hexdigest()
        document_id = f"UP-{digest[:12]}"
        path = self.uploads_dir / f"{job_id}{suffix}"
        path.write_bytes(data)
        payload = {"file_name": file_name, "document_id": document_id, "sha256": digest}
        self.registry.audit(job_id, "uploaded", payload | {"path": path.name}, "reviewer")
        self._submit(job_id, lambda: start(self.graph, job_id, path, document_id, file_name))
        return job_id

    def resume(self, job_id: str, request: ResumeRequest) -> JobView:
        with self.lock:  # check + record + submit as one step: a double click is seen
            view = self.view(job_id)
            if view is None:
                raise KeyError(job_id)
            if self.registry.applied(job_id, request.request_id):
                return view
            command = request.command
            prompt = view.prompt
            if prompt is None:
                raise JobConflict(f"the job is {view.status}, not waiting for a reviewer")
            if isinstance(prompt, ClassPrompt):
                if command.action not in ("choose_class", "cancel"):
                    raise JobConflict("the job is waiting for a class choice")
            else:
                if command.action not in prompt.allowed:
                    why = "; ".join(prompt.blockers) or "not offered for this job"
                    raise JobConflict(f"{command.action} is not allowed now: {why}")
                revision = getattr(command, "revision", prompt.revision)
                if revision != prompt.revision:
                    raise JobConflict(
                        f"the screen is out of date (revision {revision}, now {prompt.revision})"
                    )
            body = command.model_dump(mode="json")
            entry = {"request_id": request.request_id, "command": body}
            self.registry.audit(job_id, "command", entry, "reviewer")
            self._submit(job_id, lambda: resume(self.graph, job_id, body))
        view = self.view(job_id)
        assert view is not None
        return view

    # -- files and products ----------------------------------------------------------------
    def source(self, job_id: str) -> Path | None:
        upload = self._upload(job_id)
        return None if upload is None else self.uploads_dir / upload["path"]

    def blocks(self, job_id: str) -> list[BlockView] | None:
        document = state_of(self.graph, job_id).get("document")
        if document is None:
            return None
        return [
            BlockView(
                index=i,
                kind=b["kind"],
                text=b["text"],
                section=b.get("section"),
                location=Location.model_validate(b["location"]),
            )
            for i, b in enumerate(document["blocks"])
        ]

    def supplement(self, job_id: str) -> SupplementRequest | None:
        state = state_of(self.graph, job_id)
        if "document_id" not in state:
            return None
        result = result_of(state, self.service.provenance)
        return supplement_request(self.service.onto, result)


@built_once
def get_jobs() -> Jobs:
    folder = Path(os.environ.get("SPEC_BRIDGE_APP_DIR") or ROOT / "var/app")
    return Jobs(get_service(), folder)


router = APIRouter(prefix="/api")
JobsDep = Annotated[Jobs, Depends(get_jobs)]


def _view(jobs: Jobs, job_id: str) -> JobView:
    view = jobs.view(job_id)
    if view is None:
        raise HTTPException(404, f"no job {job_id}")
    return view


@router.post("/jobs", status_code=202)
def create_job(file: UploadFile, jobs: JobsDep) -> JobView:
    """Unsupported type: 415. Empty file: 400. Otherwise the job starts in the background."""
    name = file.filename or ""
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"unsupported file type {suffix!r}; use .pdf, .xlsx or .docx")
    data = file.file.read()
    if not data:
        raise HTTPException(400, "empty file")
    return _view(jobs, jobs.upload(name, data))


@router.get("/jobs")
def list_jobs(jobs: JobsDep) -> list[JobSummary]:
    return jobs.summaries()


@router.get("/jobs/{job_id}")
def get_job(job_id: str, jobs: JobsDep) -> JobView:
    return _view(jobs, job_id)


@router.post("/jobs/{job_id}/resume", status_code=202)
def resume_job(job_id: str, request: ResumeRequest, jobs: JobsDep) -> JobView:
    try:
        return jobs.resume(job_id, request)
    except KeyError as error:
        raise HTTPException(404, f"no job {job_id}") from error
    except JobConflict as error:
        raise HTTPException(409, str(error)) from error


@router.get("/jobs/{job_id}/source")
def job_source(job_id: str, jobs: JobsDep) -> FileResponse:
    path = jobs.source(job_id)
    if path is None or not path.is_file():
        raise HTTPException(404, f"no file for job {job_id}")
    return FileResponse(path)


@router.get("/jobs/{job_id}/blocks")
def job_blocks(job_id: str, jobs: JobsDep) -> list[BlockView]:
    blocks = jobs.blocks(job_id)
    if blocks is None:
        raise HTTPException(404, f"job {job_id} has no parsed document")
    return blocks


@router.get("/jobs/{job_id}/supplement")
def job_supplement(job_id: str, jobs: JobsDep) -> SupplementRequest:
    request = jobs.supplement(job_id)
    if request is None:
        raise HTTPException(404, f"no job {job_id}")
    return request


@router.get("/products/{product_id}")
def get_product(product_id: str, jobs: JobsDep) -> ProductView:
    product = jobs.registry.product(product_id)
    if product is None:
        raise HTTPException(404, f"no product {product_id}")
    edits = {e["edit_id"]: e for e in product["edits"]}
    for fact in product["facts"]:
        fact["evidence_text"] = evidence_text(fact, edits)
    with jobs.registry.lock:
        components, parents = product_links(jobs.registry.store, product_id, product["events"])
    return ProductView.model_validate(product | {"components": components, "parents": parents})


def product_links(
    store: RegistryStore, product_id: str, events: list[dict[str, Any]]
) -> tuple[list[ProductLink], list[ProductLink]]:
    """Components (with the quantity of the last BOM applied to this product) and parents."""
    quantities: dict[str, int] = {}
    for event in events:  # oldest first: a later BOM wins
        if event["event_type"] == "bom_linked":
            for row in event["payload"].get("rows", []):
                if row.get("product_id"):
                    quantities[row["product_id"]] = row["quantity"]

    def link(other: str, quantity: int | None) -> ProductLink:
        record = store.product(other) or {}
        return ProductLink(
            product_id=other,
            class_id=record.get("class_id", ""),
            model_designation=record.get("model_designation", ""),
            quantity=quantity,
        )

    components = [
        link(c, quantities.get(c)) for c in store.relations_of(product_id, "has_component")
    ]
    parents = [link(p, None) for p in store.parents_of(product_id, "has_component")]
    return components, parents


def evidence_text(fact: dict[str, Any], edits: dict[str, dict[str, Any]]) -> str:
    """NFR-07 in words: the document place(s), the edit and its reason, or the seed file."""
    kind, ref = fact["evidence_kind"], fact["evidence_ref"]
    if kind == "human_edit":
        edit = edits.get(ref)
        return f"사람 수정 {ref}: {edit['reason']}" if edit else f"사람 수정 {ref}"
    if kind == "observed":
        data = json.loads(ref)
        places = [place_of(o.get("location", {}), o.get("label_text")) for o in data["occurrences"]]
        return f"{data['document_id']} · " + " / ".join(dict.fromkeys(places))
    return f"기존 등록 목록 적재 ({ref})"


@router.get("/display")
def display_labels(jobs: JobsDep) -> DisplayLabels:
    """Screen names for ontology ids (D-074); the UI falls back to the id."""
    return load_display_labels(ROOT / "ontology/display-labels.yaml", jobs.service.onto)
