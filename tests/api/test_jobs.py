"""W5-4: the job API drives the registration graph for the review UI (S1, S2)."""

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from spec_bridge.api.app import app
from spec_bridge.api.jobs import CURRENT_JOB, Jobs, get_jobs
from spec_bridge.api.openapi import export
from spec_bridge.eval.locations import same_place
from spec_bridge.llm.audit import AuditLog
from spec_bridge.ontology.facts import Location
from spec_bridge.parse.dispatch import parse_document
from tests.api.test_app import service_with
from tests.eval.test_experiment import FAST, classify_reply
from tests.graph.test_registration import CLEAN, DUPLICATE


def jobs_for(tmp_path: Path, answers: list[Any]) -> Jobs:
    service = service_with(answers)
    service.rag = None  # the graph's RAG node is covered in tests/graph
    service.audit = AuditLog(tmp_path / "audit.jsonl")
    return Jobs(service, tmp_path / "app", run=lambda task: task())  # inline worker


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(jobs: Jobs) -> Jobs:
    app.dependency_overrides[get_jobs] = lambda: jobs
    return jobs


def upload(client: TestClient, doc_id: str) -> dict[str, Any]:
    path = FAST[doc_id][0]
    response = client.post("/api/jobs", files={"file": (path.name, path.read_bytes())})
    assert response.status_code == 202
    body: dict[str, Any] = response.json()
    return body


def send(
    client: TestClient, job_id: str, command: dict[str, Any], request_id: str | None = None
) -> Any:
    body = {"request_id": request_id or uuid.uuid4().hex, "command": command}
    return client.post(f"/api/jobs/{job_id}/resume", json=body)


def view(client: TestClient, job_id: str) -> dict[str, Any]:
    body: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
    return body


def add_values(client: TestClient, job_id: str, doc_id: str) -> int:
    """S1 through the API: missing values the document states, pointed at by block."""
    answer = FAST[doc_id][1]
    blocks = client.get(f"/api/jobs/{job_id}/blocks").json()
    observations = {o["observation_id"]: o for o in answer["observations"]}
    added = 0
    missing = view(client, job_id)["prompt"]["result"]["validation"]["missing_required"]
    for attribute in missing:
        fact = next((f for f in answer["facts"] if f["attribute_id"] == attribute), None)
        if fact is None:
            continue
        seen = observations[fact["observation_ids"][0]]
        block = next(
            b["index"]
            for b in blocks
            if same_place(seen["location"], Location.model_validate(b["location"]))
        )
        edit = {
            "op": "add",
            "attribute": attribute,
            "block": block,
            "value_text": seen["raw_text"],
            "unit_text": seen["unit_text"],
            "reason": "read from the document",
        }
        revision = view(client, job_id)["prompt"]["revision"]
        response = send(client, job_id, {"action": "edit", "revision": revision, "edit": edit})
        assert response.status_code == 202, response.json()
        added += 1
    return added


def started(tmp_path: Path, client: TestClient, doc_id: str) -> tuple[Jobs, str]:
    jobs = use(jobs_for(tmp_path, [classify_reply(doc_id), {"facts": []}]))
    return jobs, upload(client, doc_id)["job_id"]


def test_upload_runs_to_the_review_and_serves_the_viewer(
    tmp_path: Path, client: TestClient
) -> None:
    _, job_id = started(tmp_path, client, CLEAN)
    shown = view(client, job_id)
    assert shown["status"] == "awaiting_review" and shown["prompt"]["kind"] == "review"
    assert [j["job_id"] for j in client.get("/api/jobs").json()] == [job_id]
    path = FAST[CLEAN][0]
    assert client.get(f"/api/jobs/{job_id}/source").content == path.read_bytes()
    blocks = client.get(f"/api/jobs/{job_id}/blocks").json()
    assert len(blocks) == len(parse_document(path, CLEAN).blocks)


def test_s1_then_s2_through_the_api(tmp_path: Path, client: TestClient) -> None:
    _, job_id = started(tmp_path, client, CLEAN)
    added = add_values(client, job_id, CLEAN)
    revision = view(client, job_id)["prompt"]["revision"]
    assert send(client, job_id, {"action": "register_new", "revision": revision}).status_code == 202
    done = view(client, job_id)
    assert done["status"] == "registered" and done["prompt"] is None
    product_id = done["product_id"]
    product = client.get(f"/api/products/{product_id}").json()
    # every value was added by the reviewer here: the evidence names the edit and its reason
    assert all(f["evidence_text"].endswith("read from the document") for f in product["facts"])
    assert len(product["edits"]) == added and product["events"][0]["event_type"] == "registered"

    use(jobs_for(tmp_path, [classify_reply(CLEAN), {"facts": []}]))  # same app folder
    second = upload(client, CLEAN)["job_id"]
    add_values(client, second, CLEAN)
    shown = view(client, second)["prompt"]
    assert "register_new" not in shown["allowed"] and product_id in shown["link_targets"]
    command = {"action": "link", "revision": shown["revision"], "target_id": product_id}
    assert send(client, second, command).status_code == 202
    assert view(client, second)["status"] == "linked"
    after = client.get(f"/api/products/{product_id}").json()
    assert after["facts"] == product["facts"]  # S2: no automatic merge
    assert [e["event_type"] for e in after["events"]] == ["registered", "linked_document"]


def test_a_repeated_request_id_is_applied_once(tmp_path: Path, client: TestClient) -> None:
    jobs, job_id = started(tmp_path, client, CLEAN)
    add_values(client, job_id, CLEAN)
    facts = view(client, job_id)["prompt"]["result"]["facts"]
    revision = view(client, job_id)["prompt"]["revision"]
    command = {
        "action": "edit",
        "revision": revision,
        "edit": {"op": "remove", "target": "fact", "index": 0, "reason": "test"},
    }
    first = send(client, job_id, command, request_id="same")
    again = send(client, job_id, command, request_id="same")
    assert first.status_code == again.status_code == 202
    assert len(view(client, job_id)["prompt"]["result"]["facts"]) == len(facts) - 1


@pytest.mark.parametrize(
    "command, needle",
    [
        ({"action": "register_new", "revision": 0}, "not allowed"),
        ({"action": "choose_class", "class_id": "Pump"}, "not allowed"),
        ({"action": "acknowledge", "revision": 0, "keys": []}, "not allowed"),
        ({"action": "cancel"}, None),
    ],
)
def test_commands_the_prompt_does_not_offer_are_409(
    tmp_path: Path, client: TestClient, command: dict[str, Any], needle: str | None
) -> None:
    _, job_id = started(tmp_path, client, CLEAN)
    response = send(client, job_id, command)
    if needle is None:
        assert response.status_code == 202 and view(client, job_id)["status"] == "cancelled"
        finished = send(client, job_id, {"action": "cancel"})
        assert finished.status_code == 409 and "not waiting" in finished.json()["detail"]
    else:
        assert response.status_code == 409 and needle in response.json()["detail"]


def test_an_old_screen_is_409(tmp_path: Path, client: TestClient) -> None:
    _, job_id = started(tmp_path, client, CLEAN)
    add_values(client, job_id, CLEAN)
    edit = {"op": "remove", "target": "fact", "index": 0, "reason": "test"}
    response = send(client, job_id, {"action": "edit", "revision": 0, "edit": edit})
    assert response.status_code == 409 and "out of date" in response.json()["detail"]


def test_a_duplicate_offers_link_and_refuses_register(tmp_path: Path, client: TestClient) -> None:
    _, job_id = started(tmp_path, client, DUPLICATE)
    add_values(client, job_id, DUPLICATE)
    shown = view(client, job_id)["prompt"]
    response = send(client, job_id, {"action": "register_new", "revision": shown["revision"]})
    assert response.status_code == 409 and "동일 제품 REG-COMP-009" in response.json()["detail"]


def test_the_supplement_request_lists_what_the_document_lacks(
    tmp_path: Path, client: TestClient
) -> None:
    _, job_id = started(tmp_path, client, CLEAN)
    missing = view(client, job_id)["prompt"]["result"]["validation"]["missing_required"]
    request = client.get(f"/api/jobs/{job_id}/supplement").json()
    assert [m["attribute"] for m in request["missing"]] == missing
    assert all(m["rule_ref"] and m["expected"]["dimension"] for m in request["missing"])
    assert all(a in request["text"] for a in missing)
    assert client.get(f"/api/jobs/{job_id}/supplement").json() == request  # deterministic


def test_a_crash_in_the_worker_fails_the_job_not_the_server(
    tmp_path: Path, client: TestClient
) -> None:
    jobs = use(jobs_for(tmp_path, [RuntimeError("boom")]))
    job_id = upload(client, CLEAN)["job_id"]
    shown = view(client, job_id)
    assert shown["status"] == "failed" and "boom" in shown["error"]
    kinds = [k for (k,) in jobs.registry.store.conn.execute("SELECT kind FROM audit_events")]
    assert kinds == ["uploaded", "failed"]


def test_model_calls_are_audited_with_their_job(tmp_path: Path) -> None:
    jobs = jobs_for(tmp_path, [])
    token = CURRENT_JOB.set("JOB-x")
    try:
        assert jobs.service.audit is not None
        jobs.service.audit.record({"task": "classify", "ok": True})
    finally:
        CURRENT_JOB.reset(token)
    jobs.service.audit.record({"task": "outside a job"})  # no job: JSONL only
    rows = jobs.registry.store.conn.execute("SELECT job_id, kind FROM audit_events").fetchall()
    assert rows == [("JOB-x", "llm_call")]


@pytest.mark.parametrize(
    "path", ["/api/jobs/JOB-none", "/api/jobs/JOB-none/blocks", "/api/products/NOPE"]
)
def test_unknown_ids_are_404(tmp_path: Path, client: TestClient, path: str) -> None:
    use(jobs_for(tmp_path, []))
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "name, data, status", [("spec.txt", b"text", 415), ("spec.xlsx", b"", 400)]
)
def test_bad_uploads_are_refused(
    tmp_path: Path, client: TestClient, name: str, data: bytes, status: int
) -> None:
    use(jobs_for(tmp_path, []))
    assert client.post("/api/jobs", files={"file": (name, data)}).status_code == status


def test_the_api_contract_is_exported(tmp_path: Path) -> None:
    spec = json.loads(export(tmp_path / "openapi.json").read_text())
    paths = set(spec["paths"])
    assert {"/api/jobs", "/api/jobs/{job_id}", "/api/jobs/{job_id}/resume"} <= paths
    assert {"/api/jobs/{job_id}/supplement", "/api/products/{product_id}"} <= paths
    schemas = spec["components"]["schemas"]
    assert {"JobView", "ReviewPrompt", "ClassPrompt", "ResumeRequest", "ProductView"} <= set(
        schemas
    )


def test_the_review_is_computed_now_not_frozen_at_the_pause(
    tmp_path: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job paused before a change (here: of the explanations) shows the current review."""
    _, job_id = started(tmp_path, client, CLEAN)
    import spec_bridge.graph.registration as registration

    monkeypatch.setattr(registration, "explain_finding", lambda *a: "E1 — 새 설명")
    shown = view(client, job_id)["prompt"]
    assert shown["finding_notes"] and set(shown["finding_notes"]) == {"E1 — 새 설명"}
    assert "E1 — 새 설명" in shown["blockers"]


def test_display_labels_are_served(tmp_path: Path, client: TestClient) -> None:
    use(jobs_for(tmp_path, []))
    body = client.get("/api/display").json()
    assert body["attributes"]["rated_throughput"] == "정격 처리량"


def test_document_evidence_reads_as_places() -> None:
    from spec_bridge.api.jobs import evidence_text

    ref = json.dumps(
        {
            "document_id": "UP-1",
            "occurrences": [
                {"location": {"pdf_page": 1, "section": "Specs"}, "label_text": "Bore"}
            ],
        }
    )
    fact = {"evidence_kind": "observed", "evidence_ref": ref}
    assert evidence_text(fact, {}) == "UP-1 · 1쪽 · Specs · 라벨 Bore"


def test_the_service_is_built_once_under_concurrent_first_requests() -> None:
    """Browser loads fire several requests at once; building the service (KB embeddings on
    the local model) three times in parallel crashed Ollama's embedder (D-075)."""
    import threading
    import time

    from spec_bridge.api.deps import built_once

    calls: list[int] = []

    @built_once
    def slow() -> int:
        calls.append(1)
        time.sleep(0.05)
        return 42

    results: list[int] = []
    threads = [threading.Thread(target=lambda: results.append(slow())) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [42] * 5 and len(calls) == 1


def test_a_failed_build_is_retried_on_the_next_request() -> None:
    from spec_bridge.api.deps import built_once

    attempts: list[int] = []

    @built_once
    def flaky() -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("model server not ready")
        return "ok"

    with pytest.raises(RuntimeError):
        flaky()
    assert flaky() == "ok" and len(attempts) == 2
