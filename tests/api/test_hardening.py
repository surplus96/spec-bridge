"""Production audit follow-ups (D-116): loopback only, honest health, bounded uploads."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spec_bridge.api.app import app


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "::ffff:127.0.0.1", "127.0.0.2"])
def test_loopback_clients_are_served(peer: str) -> None:
    assert TestClient(app, client=(peer, 50000)).get("/health").status_code in (200, 503)


@pytest.mark.parametrize("peer", ["192.168.0.10", "10.0.0.5", "2001:db8::1"])
def test_a_client_from_another_machine_is_refused(peer: str) -> None:
    """No login exists (single local user); serving another machine would hand it the
    registry. A forged Host header does not help: the peer address decides."""
    client = TestClient(app, client=(peer, 50000))
    response = client.get("/api/jobs", headers={"host": "127.0.0.1:8010"})
    assert response.status_code == 403 and "127.0.0.1" in response.json()["detail"]


@pytest.mark.parametrize("peer", [None, "", "localhost", "/run/spec-bridge.sock"])
def test_a_peer_that_is_not_an_address_is_not_local(peer: str | None) -> None:
    """A Unix socket path or a missing peer gives no address to trust: refused, not served."""
    from spec_bridge.api.app import is_local

    assert not is_local(peer)


# health (D-116): say which dependency is missing instead of always "ok" ------------------
def fresh_client() -> TestClient:
    return TestClient(app, client=("127.0.0.1", 50000))


def test_health_is_ok_when_the_model_server_has_the_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import health

    monkeypatch.setenv("SPEC_BRIDGE_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setattr(health, "ollama_models", lambda host: [health.configured_model()])
    response = fresh_client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["checks"]["model_server"]["ok"]
    assert body["checks"]["registry"]["ok"]  # not created yet is fine


def test_health_says_the_model_server_is_down(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import health

    def down(host: str) -> list[str]:
        raise OSError("connection refused")

    monkeypatch.setenv("SPEC_BRIDGE_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setattr(health, "ollama_models", down)
    response = fresh_client().get("/health")
    assert response.status_code == 503
    check = response.json()["checks"]["model_server"]
    assert not check["ok"] and "connection refused" in check["detail"]


def test_health_says_the_model_is_not_pulled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import health

    monkeypatch.setenv("SPEC_BRIDGE_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setattr(health, "ollama_models", lambda host: ["other:1b"])
    response = fresh_client().get("/health")
    assert response.status_code == 503
    assert "ollama pull" in response.json()["checks"]["model_server"]["detail"]


def test_health_says_the_registry_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import health

    folder = tmp_path / "app"
    folder.mkdir()
    (folder / "registry.sqlite").write_text("not a database")
    monkeypatch.setenv("SPEC_BRIDGE_APP_DIR", str(folder))
    monkeypatch.setattr(health, "ollama_models", lambda host: [health.configured_model()])
    response = fresh_client().get("/health")
    assert response.status_code == 503 and not response.json()["checks"]["registry"]["ok"]


def test_health_does_not_probe_ollama_for_a_cloud_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import health

    def probed(host: str) -> list[str]:
        raise AssertionError("the cloud option must not be checked against Ollama")

    monkeypatch.setenv("SPEC_BRIDGE_PROVIDER", "openai")
    monkeypatch.setenv("SPEC_BRIDGE_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setattr(health, "ollama_models", probed)
    response = fresh_client().get("/health")
    assert response.status_code == 200
    assert "not checked" in response.json()["checks"]["model_server"]["detail"]


@pytest.mark.parametrize("version", ["99", None])
def test_health_says_the_registry_schema_is_unknown(
    version: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A registry from a newer build (or not a registry at all) is reported, not opened."""
    import sqlite3

    from spec_bridge.api import health
    from spec_bridge.registry.store import SCHEMA_VERSION

    folder = tmp_path / "app"
    folder.mkdir()
    with sqlite3.connect(folder / "registry.sqlite") as conn:
        conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        if version is not None:
            conn.execute("INSERT INTO schema_meta VALUES ('schema_version', ?)", (version,))
    conn.close()
    monkeypatch.setenv("SPEC_BRIDGE_APP_DIR", str(folder))
    monkeypatch.setattr(health, "ollama_models", lambda host: [health.configured_model()])
    response = fresh_client().get("/health")
    assert response.status_code == 503
    check = response.json()["checks"]["registry"]
    assert not check["ok"] and f"expected {SCHEMA_VERSION}" in check["detail"]


# uploads (D-116): a file over the limit is refused before it is kept ---------------------
@pytest.mark.parametrize(
    ("url", "name"),
    [("/documents", "big.pdf"), ("/api/jobs", "big.pdf"), ("/api/boms", "big.md")],
)
def test_an_upload_over_the_limit_is_refused(
    url: str, name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import deps
    from spec_bridge.api.jobs import get_jobs
    from tests.api.test_app import service_with
    from tests.api.test_jobs import jobs_for

    monkeypatch.setattr(deps, "MAX_UPLOAD_BYTES", 10)
    app.dependency_overrides[deps.get_service] = lambda: service_with([])
    app.dependency_overrides[get_jobs] = lambda: jobs_for(tmp_path, [])
    try:
        response = fresh_client().post(url, files={"file": (name, b"x" * 11)})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 413 and "10" in response.json()["detail"]
    assert not [p for p in tmp_path.rglob("*") if p.is_file() and p.read_bytes() == b"x" * 11]


def test_read_upload_returns_a_file_within_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from spec_bridge.api import deps

    monkeypatch.setattr(deps, "MAX_UPLOAD_BYTES", 10)

    class Upload:
        file = io.BytesIO(b"x" * 10)

    assert deps.read_upload(Upload()) == b"x" * 10  # type: ignore[arg-type]


def test_health_accepts_an_untagged_model_name_as_latest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from spec_bridge.api import health

    monkeypatch.setenv("SPEC_BRIDGE_MODEL", "some-model")
    monkeypatch.setattr(health, "ollama_models", lambda host: ["some-model:latest"])
    assert health.model_server()["ok"]


def test_health_reports_a_reply_it_cannot_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model server that answers something unexpected is a named failure, not a 500."""
    import http.client

    from spec_bridge.api import health

    def odd(host: str) -> list[str]:
        raise http.client.IncompleteRead(b"")

    monkeypatch.setattr(health, "ollama_models", odd)
    check = health.model_server()
    assert not check["ok"] and "cannot be read" in check["detail"]
