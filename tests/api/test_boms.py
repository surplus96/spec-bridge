"""BOM step 2 (D-103): upload a BOM, preview, resolve pending rows, apply; product links."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from spec_bridge.api.jobs import Jobs
from tests.api.test_jobs import client, jobs_for, use  # noqa: F401  (fixture)
from tests.bom.test_bom import BOMS, answer
from tests.eval.test_experiment import classify_reply
from tests.graph.test_registration import CLEAN

__all__ = ["client"]


def fresh(tmp_path: Path) -> Jobs:
    """The app registry without the seed BOM relations, so a BOM adds them."""
    jobs = use(jobs_for(tmp_path, [classify_reply(CLEAN), {"facts": []}]))
    with jobs.registry.store.conn as conn:
        conn.execute("DELETE FROM relations WHERE relation_id = 'has_component'")
    return jobs


def upload(client: TestClient, path: Path, name: str | None = None) -> Any:  # noqa: F811
    return client.post("/api/boms", files={"file": (name or path.name, path.read_bytes())})


def test_upload_previews_without_writing_then_apply_adds_the_relations(
    tmp_path: Path,
    client: TestClient,  # noqa: F811
) -> None:
    jobs = fresh(tmp_path)
    gold = answer("BOM-001")
    response = upload(client, BOMS / "BOM-001.md")
    assert response.status_code == 200, response.json()
    view = response.json()
    assert view["root_id"] == gold["root_product_id"] and view["added"] is None
    assert [r["status"] for r in view["rows"]] == ["new"] * 3
    assert jobs.registry.store.relations_of(view["root_id"], "has_component") == []
    assert (tmp_path / "app/boms" / view["bom_id"] / "BOM-001.md").is_file()  # the file is kept

    body = {"plan_key": view["plan_key"], "picks": []}
    applied = client.post(f"/api/boms/{view['bom_id']}/apply", json=body).json()
    assert applied["added"] == 3 and [r["status"] for r in applied["rows"]] == ["existing"] * 3
    product = client.get(f"/api/products/{view['root_id']}").json()
    components = {c["product_id"]: c for c in product["components"]}
    assert set(components) == {i["product_id"] for i in gold["items"]}
    assert all(c["quantity"] == 1 for c in components.values())
    event = next(e for e in product["events"] if e["event_type"] == "bom_linked")
    assert event["payload"]["bom_id"] == view["bom_id"] and event["payload"]["sha256"]
    child = client.get(f"/api/products/{gold['items'][0]['product_id']}").json()
    assert [p["product_id"] for p in child["parents"]] == [view["root_id"]]


def test_an_out_of_date_preview_is_refused(tmp_path: Path, client: TestClient) -> None:  # noqa: F811
    fresh(tmp_path)
    view = upload(client, BOMS / "BOM-001.md").json()
    body = {"plan_key": view["plan_key"], "picks": []}
    assert client.post(f"/api/boms/{view['bom_id']}/apply", json=body).status_code == 200
    again = client.post(f"/api/boms/{view['bom_id']}/apply", json=body)
    assert again.status_code == 409 and "out of date" in again.json()["detail"]


def test_a_pending_row_shows_candidates_and_a_pick_resolves_it(
    tmp_path: Path,
    client: TestClient,  # noqa: F811
) -> None:
    fresh(tmp_path)
    pump = answer("BOM-001")["items"][1]
    text = (BOMS / "BOM-001.md").read_text()
    path = tmp_path / "typo.md"
    path.write_text(text.replace(f"| {pump['model_designation']} |", "| VX999-999 |", 1))
    view = upload(client, path).json()
    row = view["rows"][1]
    assert row["status"] == "pending" and row["reason"]
    assert pump["product_id"] in [c["product_id"] for c in row["candidates"]]
    pick = {"line": row["line"], "product_id": pump["product_id"], "reason": "BOM 오타"}
    preview = client.post(f"/api/boms/{view['bom_id']}/preview", json={"picks": [pick]}).json()
    assert preview["rows"][1]["decided_by"] == "reviewer" and preview["rows"][1]["status"] == "new"
    body = {"plan_key": preview["plan_key"], "picks": [pick]}
    assert client.post(f"/api/boms/{view['bom_id']}/apply", json=body).json()["added"] == 3
    wrong = {**pick, "product_id": answer("BOM-001")["items"][2]["product_id"]}
    bad = client.post(f"/api/boms/{view['bom_id']}/preview", json={"picks": [wrong]})
    assert bad.status_code == 422


def test_a_bom_that_cannot_be_read_or_linked_is_refused(
    tmp_path: Path,
    client: TestClient,  # noqa: F811
) -> None:
    fresh(tmp_path)
    path = tmp_path / "bad.md"
    path.write_text("Root model: VX999-999\nManufacturer: nobody\n\n| Component | Model |\n")
    assert upload(client, path).status_code == 422
    other = tmp_path / "bom.csv"
    other.write_text("a,b\n")
    assert upload(client, other).status_code == 415
    assert client.get("/api/boms/BOM-UP-none").status_code == 404


# D-112: a suggestion for a pending row, confirmed by the reviewer as a pick ---------------
def typo_upload(tmp_path: Path, client: TestClient, replies: list[Any]) -> tuple[Jobs, Any]:  # noqa: F811
    jobs = use(jobs_for(tmp_path, replies))
    with jobs.registry.store.conn as conn:
        conn.execute("DELETE FROM relations WHERE relation_id = 'has_component'")
    pump = answer("BOM-001")["items"][1]
    text = (BOMS / "BOM-001.md").read_text()
    line = next(r for r in text.splitlines() if f"| {pump['model_designation']} |" in r)
    maker = line.split("|")[3].strip()
    typo = line.replace(maker, f"{maker[:-2]}{maker[-1]}{maker[-2]}")
    path = tmp_path / "maker.md"
    path.write_text(text.replace(line, typo))
    return jobs, upload(client, path).json()


def test_a_pending_row_gets_a_verified_suggestion_and_the_reviewer_confirms_it(
    tmp_path: Path,
    client: TestClient,  # noqa: F811
) -> None:
    pump = answer("BOM-001")["items"][1]
    jobs, view = typo_upload(
        tmp_path, client, [{"product_id": pump["product_id"], "reason": "same maker"}]
    )
    pending = [r for r in view["rows"] if r["status"] == "pending"]
    assert pending, view["rows"]
    line = next(r["line"] for r in pending if r["component"] == pump["class"])
    response = client.post(f"/api/boms/{view['bom_id']}/suggest", json={"line": line, "picks": []})
    assert response.status_code == 200, response.json()
    suggestion = response.json()
    assert suggestion["product_id"] == pump["product_id"] and suggestion["rejected"] is None
    audits = jobs.registry.store.conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE kind = 'bom_suggestion'"
    ).fetchone()
    assert audits == (1,)
    pick = {"line": line, "product_id": pump["product_id"], "reason": "모델 제안 확인"}
    preview = client.post(f"/api/boms/{view['bom_id']}/preview", json={"picks": [pick]}).json()
    row = next(r for r in preview["rows"] if r["line"] == line)
    assert row["decided_by"] == "reviewer" and row["status"] == "new"


def test_a_suggestion_is_only_for_a_pending_row(tmp_path: Path, client: TestClient) -> None:  # noqa: F811
    _, view = typo_upload(tmp_path, client, [])
    found = next(r["line"] for r in view["rows"] if r["status"] != "pending")
    response = client.post(f"/api/boms/{view['bom_id']}/suggest", json={"line": found})
    assert response.status_code == 422


def test_without_the_model_server_the_suggestion_says_so(
    tmp_path: Path,
    client: TestClient,  # noqa: F811
) -> None:
    _, view = typo_upload(tmp_path, client, [ConnectionError("Failed to connect to Ollama")])
    line = next(r["line"] for r in view["rows"] if r["status"] == "pending")
    response = client.post(f"/api/boms/{view['bom_id']}/suggest", json={"line": line})
    assert response.status_code == 503 and "model server" in response.json()["detail"]


def test_an_empty_folder_left_by_a_failed_write_does_not_block_the_bom(
    tmp_path: Path,
    client: TestClient,  # noqa: F811
) -> None:
    """The kept copy decides "already uploaded", not the folder: a write that failed after
    the folder was made must not leave the BOM unreadable for good."""
    import hashlib

    fresh(tmp_path)
    data = (BOMS / "BOM-001.md").read_bytes()
    bom_id = f"BOM-UP-{hashlib.sha256(data).hexdigest()[:12]}"
    (tmp_path / "app/boms" / bom_id).mkdir(parents=True)
    response = upload(client, BOMS / "BOM-001.md")
    assert response.status_code == 200, response.json()
    assert (tmp_path / "app/boms" / bom_id / "BOM-001.md").read_bytes() == data


def test_a_suggestion_s_model_call_is_audited_under_its_bom(
    tmp_path: Path,
    client: TestClient,  # noqa: F811
) -> None:
    """A model call outside a job is still written to the audit under the BOM it serves."""
    from spec_bridge.api.jobs import CURRENT_JOB

    pump = answer("BOM-001")["items"][1]
    jobs, view = typo_upload(tmp_path, client, [])
    seen: list[str | None] = []

    class Recording:
        def complete_json(self, **_: Any) -> dict[str, Any]:
            seen.append(CURRENT_JOB.get())
            return {"product_id": pump["product_id"], "reason": "same maker"}

    jobs.service.provider = Recording()
    line = next(r["line"] for r in view["rows"] if r["status"] == "pending")
    client.post(f"/api/boms/{view['bom_id']}/suggest", json={"line": line, "picks": []})
    assert seen == [view["bom_id"]]
    assert CURRENT_JOB.get() is None  # reset after the call
