"""The API contract names the refusals each route gives (OpenAPI error responses).

The UI's types are generated from web/openapi.json, so the committed file must be what the
app exports, and each route must document the codes it refuses with.
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from spec_bridge.api.app import app
from spec_bridge.api.openapi import OUTPUT, export

UPLOAD = {"400", "413", "415"}
# what each route raises (HTTPException in app.py, jobs.py, boms.py, deps.read_upload)
REFUSALS: dict[tuple[str, str], set[str]] = {
    ("/documents", "post"): UPLOAD,
    ("/api/jobs", "post"): UPLOAD,
    ("/api/jobs/{job_id}", "get"): {"404"},
    ("/api/jobs/{job_id}/resume", "post"): {"404", "409"},
    ("/api/jobs/{job_id}/source", "get"): {"404"},
    ("/api/jobs/{job_id}/blocks", "get"): {"404"},
    ("/api/jobs/{job_id}/supplement", "get"): {"404"},
    ("/api/products/{product_id}", "get"): {"404"},
    ("/api/boms", "post"): UPLOAD | {"422"},
    ("/api/boms/{bom_id}", "get"): {"404", "422"},
    ("/api/boms/{bom_id}/preview", "post"): {"404", "422"},
    ("/api/boms/{bom_id}/apply", "post"): {"404", "409", "422"},
    ("/api/boms/{bom_id}/suggest", "post"): {"404", "422", "503"},
}
ERROR_DETAIL = {"$ref": "#/components/schemas/ErrorDetail"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return app.openapi()


def schema_of(response: dict[str, Any]) -> dict[str, Any]:
    schema: dict[str, Any] = response["content"]["application/json"]["schema"]
    return schema


def test_the_committed_contract_is_what_the_app_exports(tmp_path: Path) -> None:
    """Otherwise `npm run gen:api` builds the UI's types from a stale contract."""
    fresh = export(tmp_path / "openapi.json").read_text()
    assert OUTPUT.read_text() == fresh, "run: uv run python -m spec_bridge.api.openapi"


@pytest.mark.parametrize(("path", "method"), sorted(REFUSALS))
def test_each_route_documents_its_refusals(spec: dict[str, Any], path: str, method: str) -> None:
    responses = spec["paths"][path][method]["responses"]
    assert REFUSALS[path, method] <= set(responses)
    for code in REFUSALS[path, method] - {"422"}:
        assert schema_of(responses[code]) == ERROR_DETAIL, code
        assert responses[code]["description"] != "Successful Response"


def test_a_bom_422_is_a_reason_or_a_malformed_request(spec: dict[str, Any]) -> None:
    """A BOM that cannot be read gives a string detail; a malformed body FastAPI's list."""
    schema = schema_of(spec["paths"]["/api/boms/{bom_id}/apply"]["post"]["responses"]["422"])
    assert ERROR_DETAIL in schema["anyOf"] and len(schema["anyOf"]) == 2


def test_health_documents_one_report_for_200_and_503(spec: dict[str, Any]) -> None:
    responses = spec["paths"]["/health"]["get"]["responses"]
    report = {"$ref": "#/components/schemas/HealthReport"}
    assert schema_of(responses["200"]) == report and schema_of(responses["503"]) == report


def test_the_health_body_has_the_documented_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import health

    monkeypatch.setenv("SPEC_BRIDGE_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setattr(health, "ollama_models", lambda host: [])  # model missing: 503
    response = TestClient(app).get("/health")
    assert response.status_code == 503
    assert health.HealthReport.model_validate(response.json()).status == "degraded"
