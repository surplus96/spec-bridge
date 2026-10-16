"""LLM provider adapter (W3-1): one way out to a model, with retries, audit and an
offline guard (NFR-01/05). Callers get a JSON object or an LlmError, never a crash."""

import hashlib
import json
import os
import time
from typing import Any, Protocol
from urllib.parse import urlparse

from ollama import Client

from spec_bridge.llm.audit import AuditLog

DEFAULT_MODEL = "exaone3.5:7.8b"
DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_OPTIONS: dict[str, Any] = {"temperature": 0, "seed": 7, "num_ctx": 8192}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class LlmError(Exception):
    """The model gave no usable JSON object after the allowed retries."""

    def __init__(self, task: str, reason: str) -> None:
        super().__init__(f"{task}: {reason}")
        self.task = task
        self.reason = reason


class JsonProvider(Protocol):
    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any] | None, task: str
    ) -> dict[str, Any]: ...


def check_offline_host(host: str) -> None:
    """With OFFLINE=1 only loopback model servers are allowed (NFR-01)."""
    if os.environ.get("OFFLINE") == "1" and urlparse(host).hostname not in LOOPBACK:
        raise LlmError("provider", f"OFFLINE=1 forbids non-loopback host {host}")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class OllamaProvider:
    def __init__(
        self,
        model: str,
        audit: AuditLog,
        *,
        host: str = DEFAULT_HOST,
        options: dict[str, Any] | None = None,
        timeout_s: float = 300.0,
        retries: int = 1,
        client: Any = None,
    ) -> None:
        check_offline_host(host)
        self.host = host
        self.model = model
        self.audit = audit
        self.options = DEFAULT_OPTIONS | (options or {})
        self.retries = retries
        self._client = client if client is not None else Client(host=host, timeout=timeout_s)
        self._digest: str | None = None

    @property
    def digest(self) -> str | None:
        """Model identity for reproducibility; looked up once from the server."""
        if self._digest is None:
            for item in self._client.list().models:
                if item.model == self.model:
                    self._digest = item.digest
        return self._digest

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any] | None, task: str
    ) -> dict[str, Any]:
        base = {
            "task": task,
            "provider": "ollama",
            "base_url": self.host,  # W6-6: which server answered (spec_bridge.llm.hosts)
            "model": self.model,
            "model_digest": self.digest,
            "prompt_sha256": sha256(system + "\n" + user),
            "schema_sha256": sha256(json.dumps(schema, sort_keys=True)) if schema else None,
            "options": self.options,
        }
        last = "no attempt"
        for attempt in range(1, self.retries + 2):
            started = time.perf_counter()
            try:
                reply = self._client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    format=schema if schema is not None else "json",
                    options=self.options,
                    keep_alive="5m",
                )
                data = json.loads(reply.message.content or "")
                if not isinstance(data, dict):
                    raise ValueError("reply is not a JSON object")
            except Exception as exc:  # broken JSON, timeout, server error: retry, then report
                last = f"{type(exc).__name__}: {exc}"
                self.audit.record(
                    base
                    | {
                        "attempt": attempt,
                        "status": "error",
                        "error": last,
                        "latency_s": round(time.perf_counter() - started, 3),
                    }
                )
                continue
            self.audit.record(
                base
                | {
                    "attempt": attempt,
                    "status": "ok",
                    "latency_s": round(time.perf_counter() - started, 3),
                    "prompt_tokens": reply.prompt_eval_count,
                    "completion_tokens": reply.eval_count,
                }
            )
            return data
        raise LlmError(task, last)
