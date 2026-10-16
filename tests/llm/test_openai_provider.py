from pathlib import Path
from typing import Any

import pytest

from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.openai_compat import OpenAIProvider
from spec_bridge.llm.provider import LlmError
from tests.llm.fakes import FakeTransport, chat_reply

KEY = "sk-test-not-a-real-key"


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.delenv("OFFLINE", raising=False)


def provider(
    tmp_path: Path, replies: list[dict[str, Any] | Exception], **kwargs: Any
) -> tuple[OpenAIProvider, FakeTransport]:
    transport = FakeTransport(replies)
    audit = AuditLog(tmp_path / "audit.jsonl")
    return OpenAIProvider("gpt-4o-mini", audit, client=transport, **kwargs), transport


def ask(p: OpenAIProvider, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    return p.complete_json(system="sys", user="secret document text", schema=schema, task="t")


def test_request_carries_model_messages_options_and_schema(tmp_path: Path) -> None:
    p, transport = provider(tmp_path, [chat_reply('{"ok": true}')])
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    assert p.complete_json(system="s", user="u", schema=schema, task="extract-C") == {"ok": True}
    call = transport.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    body = call["body"]
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    assert body["temperature"] == 0 and body["seed"] == 7
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "extract-C", "schema": schema, "strict": False},
    }


def test_strict_schema_is_opt_in(tmp_path: Path) -> None:
    p, transport = provider(tmp_path, [chat_reply("{}")], strict=True)
    ask(p, schema={"type": "object"})
    assert transport.calls[0]["body"]["response_format"]["json_schema"]["strict"] is True


def test_no_schema_uses_json_object_mode(tmp_path: Path) -> None:
    p, transport = provider(tmp_path, [chat_reply('{"a": 1}')])
    assert ask(p) == {"a": 1}
    assert transport.calls[0]["body"]["response_format"] == {"type": "json_object"}


def test_base_url_reaches_any_compatible_server(tmp_path: Path) -> None:
    p, transport = provider(tmp_path, [chat_reply("{}")], base_url="http://127.0.0.1:11434/v1/")
    ask(p)
    assert transport.calls[0]["url"] == "http://127.0.0.1:11434/v1/chat/completions"


def test_broken_json_is_retried_once(tmp_path: Path) -> None:
    p, _ = provider(tmp_path, [chat_reply("{not json"), chat_reply('{"ok": true}')])
    assert ask(p) == {"ok": True}
    assert [r["status"] for r in p.audit.rows()] == ["error", "ok"]


def test_failure_after_retries_is_an_llm_error(tmp_path: Path) -> None:
    p, _ = provider(tmp_path, [RuntimeError("HTTP 429: rate limited"), chat_reply("[1]")])
    with pytest.raises(LlmError, match="not a JSON object"):
        ask(p)
    assert [r["status"] for r in p.audit.rows()] == ["error", "error"]


def test_refusal_is_an_error_not_an_empty_reply(tmp_path: Path) -> None:
    p, _ = provider(tmp_path, [chat_reply(None, refusal="no"), chat_reply(None, refusal="no")])
    with pytest.raises(LlmError, match="refusal"):
        ask(p)


def test_audit_keeps_served_model_and_tokens_not_text_or_key(tmp_path: Path) -> None:
    p, _ = provider(tmp_path, [chat_reply('{"ok": true}')])
    ask(p)
    row = p.audit.rows()[0]
    text = (tmp_path / "audit.jsonl").read_text()
    assert "secret document text" not in text and KEY not in text
    assert row["provider"] == "openai" and row["model"] == "gpt-4o-mini"
    assert row["model_resolved"] == "gpt-4o-mini-2024-07-18"
    assert row["system_fingerprint"] == "fp_test"
    assert row["prompt_tokens"] == 12 and row["completion_tokens"] == 6
    assert len(row["prompt_sha256"]) == 64


def test_missing_api_key_is_an_llm_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(LlmError, match="OPENAI_API_KEY"):
        provider(tmp_path, [])


def test_offline_mode_rejects_the_cloud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFLINE", "1")
    with pytest.raises(LlmError, match="non-loopback"):
        provider(tmp_path, [])


def test_offline_mode_allows_a_loopback_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFLINE", "1")
    provider(tmp_path, [], base_url="http://localhost:11434/v1")
