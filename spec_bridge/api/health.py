"""Health that names the missing dependency (D-116).

`GET /health` answers 200 when the model server has the configured model and the app
registry can be read, else 503 with the failing check. Nothing heavy is built here (no
service, no embeddings): it only lists the server's models and reads the registry's
schema version read-only.
"""

import json
import os
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any

from spec_bridge.llm.provider import DEFAULT_HOST, DEFAULT_MODEL
from spec_bridge.normalize.dictionary import ROOT
from spec_bridge.registry.store import MIGRATES_FROM, SCHEMA_VERSION, stored_schema

TIMEOUT_S = 2.0


def configured_model() -> str:
    return os.environ.get("SPEC_BRIDGE_MODEL") or DEFAULT_MODEL


def ollama_models(host: str) -> list[str]:
    """Model names the Ollama server has (raises OSError when it cannot be reached)."""
    with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=TIMEOUT_S) as reply:
        data: dict[str, Any] = json.loads(reply.read())
    return [str(m.get("model") or m.get("name")) for m in data.get("models", [])]


def model_server() -> dict[str, Any]:
    if os.environ.get("SPEC_BRIDGE_PROVIDER", "ollama") != "ollama":
        return {"ok": True, "detail": "cloud provider: not checked here"}
    host = os.environ.get("SPEC_BRIDGE_BASE_URL") or DEFAULT_HOST
    model = configured_model()
    try:
        names = ollama_models(host)
    except (OSError, ValueError) as error:
        return {"ok": False, "detail": f"model server {host} cannot be reached: {error}"}
    if model not in names:
        return {"ok": False, "detail": f"{model} is not on {host} (ollama pull {model})"}
    return {"ok": True, "detail": f"{model} on {host}"}


def registry() -> dict[str, Any]:
    folder = Path(os.environ.get("SPEC_BRIDGE_APP_DIR") or ROOT / "var/app")
    path = folder / "registry.sqlite"
    if not path.exists():
        return {"ok": True, "detail": f"{path.name} is created on first use"}
    try:
        version = stored_schema(path)
    except sqlite3.DatabaseError as error:
        return {"ok": False, "detail": f"{path} cannot be read: {error}"}
    if version not in {SCHEMA_VERSION, *MIGRATES_FROM}:
        return {"ok": False, "detail": f"{path} has schema {version}, expected {SCHEMA_VERSION}"}
    return {"ok": True, "detail": f"schema {version}"}


def report() -> tuple[int, dict[str, Any]]:
    checks = {"model_server": model_server(), "registry": registry()}
    healthy = all(c["ok"] for c in checks.values())
    return (200 if healthy else 503), {"status": "ok" if healthy else "degraded", "checks": checks}
