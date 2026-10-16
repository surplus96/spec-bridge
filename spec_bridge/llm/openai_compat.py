"""OpenAI-compatible Chat Completions adapter (D-034): cloud comparison runs only.

Same contract as OllamaProvider: a JSON object or an LlmError, with retries and an
audit row per attempt. The API key comes from OPENAI_API_KEY and is never logged;
OFFLINE=1 refuses non-loopback servers (NFR-01 applies to the default local path).
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.provider import LlmError, check_offline_host, sha256

OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_OPTIONS: dict[str, Any] = {"temperature": 0, "seed": 7}


class Transport(Protocol):
    def post(
        self, url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> dict[str, Any]: ...


class UrllibTransport:
    """POST a JSON body and return the JSON reply; HTTP errors keep status and body."""

    def post(
        self, url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data: dict[str, Any] = json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            raise RuntimeError(f"HTTP {error.code}: {detail}") from None
        return data


class OpenAIProvider:
    def __init__(
        self,
        model: str,
        audit: AuditLog,
        *,
        base_url: str = OPENAI_BASE_URL,
        options: dict[str, Any] | None = None,
        strict: bool = False,
        timeout_s: float = 300.0,
        retries: int = 1,
        client: Transport | None = None,
    ) -> None:
        check_offline_host(base_url)
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise LlmError("provider", "OPENAI_API_KEY is not set")
        self.model = model
        self.audit = audit
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.options = OPENAI_OPTIONS | (options or {})
        self.strict = strict
        self.timeout_s = timeout_s
        self.retries = retries
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self._client = client if client is not None else UrllibTransport()

    def _response_format(self, schema: dict[str, Any] | None, task: str) -> dict[str, Any]:
        if schema is None:
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {"name": task, "schema": schema, "strict": self.strict},
        }

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any] | None, task: str
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": self._response_format(schema, task),
            **self.options,
        }
        base = {
            "task": task,
            "provider": "openai",
            "model": self.model,
            "base_url": self.url,
            "prompt_sha256": sha256(system + "\n" + user),
            "schema_sha256": sha256(json.dumps(schema, sort_keys=True)) if schema else None,
            "options": self.options,
            "strict": self.strict,
        }
        last = "no attempt"
        for attempt in range(1, self.retries + 2):
            started = time.perf_counter()
            try:
                reply = self._client.post(self.url, self._headers, body, self.timeout_s)
                message = reply["choices"][0]["message"]
                if message.get("refusal"):
                    raise ValueError(f"refusal: {message['refusal']}")
                data = json.loads(message.get("content") or "")
                if not isinstance(data, dict):
                    raise ValueError("reply is not a JSON object")
            except Exception as exc:  # HTTP error, broken JSON, refusal: retry, then report
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
            usage = reply.get("usage") or {}
            self.audit.record(
                base
                | {
                    "attempt": attempt,
                    "status": "ok",
                    "latency_s": round(time.perf_counter() - started, 3),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "model_resolved": reply.get("model"),
                    "system_fingerprint": reply.get("system_fingerprint"),
                }
            )
            return data
        raise LlmError(task, last)
