"""Test doubles for the LLM layer (no model server needed)."""

from types import SimpleNamespace
from typing import Any


class FakeClient:
    """Mimics ollama.Client.chat/list; replies are JSON strings or exceptions."""

    def __init__(self, replies: list[str | Exception], model: str = "fake:1b") -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.model = model

    def chat(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            message=SimpleNamespace(content=reply), prompt_eval_count=10, eval_count=5
        )

    def list(self) -> Any:
        return SimpleNamespace(models=[SimpleNamespace(model=self.model, digest="abc123")])


class FakeTransport:
    """Mimics the OpenAI-compatible HTTP transport; replies are response dicts or exceptions."""

    def __init__(self, replies: list[dict[str, Any] | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def post(
        self, url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def chat_reply(content: str | None, *, refusal: str | None = None) -> dict[str, Any]:
    """A Chat Completions response body as the API returns it."""
    return {
        "model": "gpt-4o-mini-2024-07-18",
        "system_fingerprint": "fp_test",
        "choices": [
            {
                "message": {"role": "assistant", "content": content, "refusal": refusal},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 6},
    }


class FakeProvider:
    """A JsonProvider that returns prepared objects (or raises prepared errors)."""

    def __init__(self, replies: list[dict[str, Any] | Exception]) -> None:
        self.replies = list(replies)
        self.prompts: list[dict[str, Any]] = []

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any] | None, task: str
    ) -> dict[str, Any]:
        self.prompts.append({"system": system, "user": user, "schema": schema, "task": task})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
