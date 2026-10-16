from pathlib import Path

import pytest

from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.provider import LlmError, OllamaProvider
from tests.llm.fakes import FakeClient


def provider(tmp_path: Path, replies: list[str | Exception], **kwargs: object) -> OllamaProvider:
    audit = AuditLog(tmp_path / "audit.jsonl")
    return OllamaProvider("fake:1b", audit, client=FakeClient(replies), **kwargs)  # type: ignore[arg-type]


def ask(p: OllamaProvider) -> dict[str, object]:
    return p.complete_json(system="sys", user="secret document text", schema=None, task="t")


def test_broken_json_is_retried_once(tmp_path: Path) -> None:
    p = provider(tmp_path, ["{not json", '{"ok": true}'])
    assert ask(p) == {"ok": True}
    assert [r["status"] for r in p.audit.rows()] == ["error", "ok"]


def test_failure_after_retries_is_an_llm_error(tmp_path: Path) -> None:
    p = provider(tmp_path, ["{not json", TimeoutError("slow")])
    with pytest.raises(LlmError, match="TimeoutError"):
        ask(p)
    assert len(p.audit.rows()) == 2


def test_non_object_json_is_rejected(tmp_path: Path) -> None:
    p = provider(tmp_path, ["[1, 2]", "[3]"])
    with pytest.raises(LlmError, match="not a JSON object"):
        ask(p)


def test_audit_keeps_hashes_and_options_not_text(tmp_path: Path) -> None:
    p = provider(tmp_path, ['{"ok": true}'])
    ask(p)
    row = p.audit.rows()[0]
    assert "secret document text" not in (tmp_path / "audit.jsonl").read_text()
    assert len(row["prompt_sha256"]) == 64 and row["model_digest"] == "abc123"
    assert row["options"]["temperature"] == 0 and row["options"]["seed"] == 7
    assert row["prompt_tokens"] == 10


def test_schema_is_sent_as_format(tmp_path: Path) -> None:
    client = FakeClient(['{"ok": true}'])
    p = OllamaProvider("fake:1b", AuditLog(tmp_path / "a.jsonl"), client=client)
    schema = {"type": "object"}
    p.complete_json(system="s", user="u", schema=schema, task="t")
    assert client.calls[0]["format"] == schema and client.calls[0]["options"]["num_ctx"] == 8192


def test_offline_mode_rejects_remote_hosts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFLINE", "1")
    with pytest.raises(LlmError, match="non-loopback"):
        provider(tmp_path, [], host="http://10.0.0.5:11434")


@pytest.mark.parametrize("host", ["http://127.0.0.1:11434", "http://localhost:11434"])
def test_offline_mode_allows_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    monkeypatch.setenv("OFFLINE", "1")
    provider(tmp_path, [], host=host)


def test_audit_says_which_server_answered(tmp_path: Path) -> None:
    """W6-6: every audit row names its server, so a run's hosts can be checked."""
    p = provider(tmp_path, ['{"ok": true}'])
    ask(p)
    row = p.audit.rows()[0]
    assert row["provider"] == "ollama" and row["base_url"] == "http://127.0.0.1:11434"
