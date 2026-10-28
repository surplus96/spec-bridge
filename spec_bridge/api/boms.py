"""BOM API for the review UI (BOM step 2, D-103).

    POST /api/boms                    upload an .xlsx / .md BOM -> its preview (writes nothing)
    GET  /api/boms/{id}               the preview again, against the registry as it is now
    POST /api/boms/{id}/preview       the preview with the reviewer's picks for pending rows
    POST /api/boms/{id}/apply         plan_key + picks -> the new relations are written
    POST /api/boms/{id}/suggest       a pending row's line -> a verified suggestion (D-112)

The uploaded file is kept in <app>/boms/<id>/ and its hash goes with the event (D-103 7).
Apply plans again and refuses (409) when the plan differs from the preview the reviewer
saw (plan_key): another registration may have changed it. A file that cannot be read,
an unknown root and a pick that does not fit are 422 with the reason.
"""

import hashlib
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile

from spec_bridge.api import deps
from spec_bridge.api.jobs import CURRENT_JOB, Jobs, JobsDep
from spec_bridge.bom.linker import BomPlan, Pick, apply, candidates, plan, plan_key
from spec_bridge.bom.reader import BomError, read_bom
from spec_bridge.bom.suggest import Suggestion, suggest_from
from spec_bridge.ontology.facts import StrictModel

ALLOWED = (".xlsx", ".md")
BOM_ID = re.compile(r"BOM-UP-[0-9a-f]{12}")


class BomCandidate(StrictModel):
    product_id: str
    class_id: str
    model_designation: str
    maker_name: str | None = None


class BomRowView(StrictModel):
    component: str
    model: str
    maker: str
    quantity: int
    line: int
    status: Literal["new", "existing", "pending"]
    product_id: str | None = None
    reason: str | None = None
    decided_by: Literal["rule", "reviewer"] = "rule"
    candidates: list[BomCandidate] = []  # for a pending row: products of its class


class BomView(StrictModel):
    bom_id: str
    file_name: str
    sha256: str
    root_id: str
    rows: list[BomRowView]
    not_in_bom: list[str]  # relations the root has that the BOM does not list (kept)
    plan_key: str  # send it back with apply: a changed plan is refused
    added: int | None = None  # set by apply


class PreviewRequest(StrictModel):
    picks: list[Pick] = []


class SuggestRequest(StrictModel):
    line: int
    picks: list[Pick] = []


class ApplyRequest(StrictModel):
    plan_key: str
    picks: list[Pick] = []


def _file(jobs: Jobs, bom_id: str) -> Path:
    folder = jobs.uploads_dir.parent / "boms" / bom_id
    files = sorted(folder.iterdir()) if BOM_ID.fullmatch(bom_id) and folder.is_dir() else []
    if not files:
        raise HTTPException(404, f"no BOM {bom_id}")
    return files[0]


def _plan(jobs: Jobs, path: Path, picks: list[Pick]) -> BomPlan:
    """Call with the registry lock held."""
    try:
        return plan(jobs.registry.store, jobs.service.onto, read_bom(path), picks)
    except BomError as error:
        raise HTTPException(422, str(error)) from error


def _view(jobs: Jobs, bom_id: str, path: Path, result: BomPlan, added: int | None) -> BomView:
    """Call with the registry lock held."""
    store, onto = jobs.registry.store, jobs.service.onto
    rows = [
        BomRowView(
            **r.row.model_dump(),
            status=r.status,
            product_id=r.product_id,
            reason=r.reason,
            decided_by=r.decided_by,
            candidates=[BomCandidate.model_validate(c) for c in candidates(store, onto, r.row)]
            if r.status == "pending"
            else [],
        )
        for r in result.rows
    ]
    return BomView(
        bom_id=bom_id,
        file_name=path.name,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        root_id=result.root_id,
        rows=rows,
        not_in_bom=result.not_in_bom,
        plan_key=plan_key(result),
        added=added,
    )


def _preview(jobs: Jobs, bom_id: str, picks: list[Pick]) -> BomView:
    path = _file(jobs, bom_id)
    with jobs.registry.lock:
        return _view(jobs, bom_id, path, _plan(jobs, path, picks), None)


router = APIRouter(prefix="/api")


@router.post("/boms")
def upload_bom(file: UploadFile, jobs: JobsDep) -> BomView:
    """Unsupported type: 415. Empty: 400. Unreadable or unknown root: 422."""
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(415, f"unsupported BOM type {Path(name).suffix!r}; use .xlsx or .md")
    data = deps.read_upload(file)
    if not data:
        raise HTTPException(400, "empty file")
    digest = hashlib.sha256(data).hexdigest()
    bom_id = f"BOM-UP-{digest[:12]}"
    folder = jobs.uploads_dir.parent / "boms" / bom_id
    folder.mkdir(parents=True, exist_ok=True)
    if not any(folder.iterdir()):  # the same file again keeps its first copy
        partial = folder.parent / f".{bom_id}.part"  # outside the folder _file reads
        partial.write_bytes(data)
        partial.replace(folder / name)  # the copy appears whole or not at all
        jobs.registry.audit(
            bom_id, "bom_uploaded", {"file_name": name, "sha256": digest}, "reviewer"
        )
    return _preview(jobs, bom_id, [])


@router.get("/boms/{bom_id}")
def get_bom(bom_id: str, jobs: JobsDep) -> BomView:
    return _preview(jobs, bom_id, [])


@router.post("/boms/{bom_id}/preview")
def preview_bom(bom_id: str, request: PreviewRequest, jobs: JobsDep) -> BomView:
    return _preview(jobs, bom_id, request.picks)


@router.post("/boms/{bom_id}/apply")
def apply_bom(bom_id: str, request: ApplyRequest, jobs: JobsDep) -> BomView:
    path = _file(jobs, bom_id)
    with jobs.registry.lock:  # plan, compare and write as one step
        result = _plan(jobs, path, request.picks)
        if plan_key(result) != request.plan_key:
            raise HTTPException(
                409, "the preview is out of date (the registry changed); preview again"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        extra = {"bom_id": bom_id, "file_name": path.name, "sha256": digest}
        added = apply(jobs.registry.store, result, "reviewer", extra)
        return _view(jobs, bom_id, path, _plan(jobs, path, request.picks), added)


@router.post("/boms/{bom_id}/suggest")
def suggest_bom_row(bom_id: str, request: SuggestRequest, jobs: JobsDep) -> Suggestion:
    """A product for a pending row: the model chooses, code verifies (D-112). Nothing is
    written but an audit row; the reviewer confirms the suggestion as a pick. 422 for a
    row that is not pending, 503 when the model server cannot be reached."""
    path = _file(jobs, bom_id)
    store = jobs.registry.store
    with jobs.registry.lock:  # copy what the model needs; do not hold the lock while it runs
        result = _plan(jobs, path, request.picks)
        products, aliases = store.identities(), store.maker_aliases()
    found = next((r for r in result.rows if r.row.line == request.line), None)
    if found is None or found.status != "pending":
        raise HTTPException(422, f"line {request.line} is not a row waiting for review")
    token = CURRENT_JOB.set(bom_id)  # the model call is audited under the BOM it serves
    try:
        suggestion = suggest_from(
            products, aliases, jobs.service.onto, jobs.service.provider, found.row, result.root_id
        )
    finally:
        CURRENT_JOB.reset(token)
    jobs.registry.audit(bom_id, "bom_suggestion", suggestion.model_dump(), "system")
    if suggestion.unavailable is not None:
        raise HTTPException(503, f"the model server cannot be reached: {suggestion.unavailable}")
    return suggestion
