"""W4-6/7 (MVP): upload a specification, get a schema-valid registration result."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from spec_bridge.api.app import Service, app, get_service, load_registry, service_provider
from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.openai_compat import OpenAIProvider
from spec_bridge.normalize.dictionary import load_dictionary
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.rag.pipeline import RagSetup
from spec_bridge.rag.qualifiers import build_chain
from spec_bridge.registry.output import RegistrationResult, check_result, export_schema
from spec_bridge.service import normalizer_for
from tests.conftest import ONTOLOGY
from tests.eval.test_experiment import FAST, classify_reply
from tests.extract.test_extractor import line_of
from tests.llm.fakes import FakeProvider

DOC_ID = next(i for i in FAST if any(f["scope"] != "main_equipment" for f in FAST[i][1]["facts"]))
PATH, ANSWER = FAST[DOC_ID]


def service_with(replies: list[Any]) -> Service:
    onto = load_ontology(ONTOLOGY)
    normalizer = normalizer_for(onto, "dev", load_dictionary())
    provider = FakeProvider(replies)
    chain = build_chain(onto, normalizer, provider, [], None)  # E0 chain: no retrieval in tests
    registry, makers = load_registry()
    return Service(
        onto, normalizer, provider, RagSetup(chain=chain), registry, makers, {"test": True}
    )


def client_for(service: Service) -> TestClient:
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


def scoped_item() -> tuple[dict[str, Any], dict[str, Any]]:
    fact = next(f for f in ANSWER["facts"] if f["scope"] != "main_equipment")
    obs = next(o for o in ANSWER["observations"] if o["observation_id"] in fact["observation_ids"])
    item = {
        "attribute": fact["attribute_id"],
        "value_text": obs["raw_text"],
        "unit_text": obs["unit_text"],
        "line": line_of(parse_document(PATH, DOC_ID), obs),
    }
    return fact, item


def test_upload_returns_a_valid_registration_result() -> None:
    fact, item = scoped_item()
    phrase = fact["scope"].replace("_", " ")
    replies = [
        classify_reply(DOC_ID),
        {"facts": [item]},
        {"scope": {"value": phrase, "evidence": phrase}},
    ]
    service = service_with(replies)
    response = client_for(service).post(
        "/documents", files={"file": (PATH.name, PATH.read_bytes())}
    )
    assert response.status_code == 200
    result = RegistrationResult.model_validate(response.json())
    check_result(service.onto, result)
    assert result.class_id == ANSWER["expected_class"] and result.file_name == PATH.name
    assert [f["scope"] for f in result.facts] == [fact["scope"]]
    assert result.status == "needs_review"  # one fact only: required attributes are missing
    assert result.validation.findings and result.provenance["test"] is True
    assert result.provenance["parser"].startswith("openpyxl")


def test_unparsable_file_is_needs_review_not_an_error() -> None:
    response = client_for(service_with([])).post(
        "/documents", files={"file": ("broken.xlsx", b"not a workbook")}
    )
    body = response.json()
    assert response.status_code == 200 and body["status"] == "needs_review"
    assert body["failure"].startswith("parse:") and body["class_id"] == "unknown"


def test_unknown_class_is_needs_review() -> None:
    reply = {"product_class": "unknown", "reason": "test"}
    response = client_for(service_with([reply])).post(
        "/documents", files={"file": (PATH.name, PATH.read_bytes())}
    )
    assert response.json()["failure"] == "class unknown"


@pytest.mark.parametrize(
    "name, data, status", [("spec.txt", b"text", 415), ("spec.xlsx", b"", 400)]
)
def test_bad_uploads_are_refused(name: str, data: bytes, status: int) -> None:
    response = client_for(service_with([])).post("/documents", files={"file": (name, data)})
    assert response.status_code == status


def test_health() -> None:
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_result_schema_is_exported(tmp_path: Path) -> None:
    schema = json.loads(export_schema(tmp_path / "registration-result.schema.json").read_text())
    assert {"document_id", "facts", "validation", "matches", "status"} <= set(schema["properties"])


def test_one_setting_switches_the_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OFFLINE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    monkeypatch.setenv("SPEC_BRIDGE_PROVIDER", "openai")
    provider, info = service_provider(AuditLog(tmp_path / "audit.jsonl"))
    assert isinstance(provider, OpenAIProvider) and info["provider"] == "openai"
    monkeypatch.setenv("SPEC_BRIDGE_PROVIDER", "nonsense")
    with pytest.raises(ValueError, match="SPEC_BRIDGE_PROVIDER"):
        service_provider(AuditLog(tmp_path / "audit.jsonl"))
