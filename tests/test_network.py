"""NFR-01 (W3-8): no connection leaves the machine during parsing, rule runs and
LLM runs. Python socket calls to a non-loopback address (connect, connect_ex, sendto,
name lookup) are recorded and refused. Native extensions and child processes that
bypass the socket module are outside this guard (CP-S3 R5)."""

import errno
import json
import os
import socket
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.eval.experiment import run_experiment
from spec_bridge.extract.extractor import extract
from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.provider import DEFAULT_MODEL, LOOPBACK, OllamaProvider
from spec_bridge.ontology.loader import Ontology
from spec_bridge.parse.dispatch import parse_document
from tests.parse.goldmatch import dev_documents


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Records (and refuses) every attempt to reach a non-loopback host."""
    attempts: list[Any] = []
    real = socket.socket
    real_connect, real_connect_ex, real_sendto = real.connect, real.connect_ex, real.sendto
    real_getaddrinfo = socket.getaddrinfo

    def outward(sock: socket.socket, address: Any) -> bool:
        host = address[0] if isinstance(address, tuple) else address
        return sock.family in (socket.AF_INET, socket.AF_INET6) and host not in LOOPBACK

    def connect(self: socket.socket, address: Any) -> None:
        if outward(self, address):
            attempts.append(("connect", address))
            raise OSError(f"NFR-01 test: outbound connection to {address} refused")
        real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        if outward(self, address):
            attempts.append(("connect_ex", address))
            return errno.ECONNREFUSED
        return real_connect_ex(self, address)

    def sendto(self: socket.socket, data: Any, *args: Any) -> int:
        address = args[-1]  # sendto(data, address) or sendto(data, flags, address)
        if outward(self, address):
            attempts.append(("sendto", address))
            raise OSError(f"NFR-01 test: datagram to {address} refused")
        return int(real_sendto(self, data, *args))

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in LOOPBACK and host is not None:
            attempts.append(("resolve", host))
            raise socket.gaierror(f"NFR-01 test: name lookup for {host} refused")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return attempts


def test_guard_sees_every_outbound_path(outbound: list[Any]) -> None:
    target = ("192.0.2.1", 80)  # TEST-NET-1: documentation address, never routed
    with pytest.raises(OSError), socket.socket() as sock:
        sock.connect(target)
    with socket.socket() as sock:
        assert sock.connect_ex(target) == errno.ECONNREFUSED
    with pytest.raises(OSError), socket.socket(type=socket.SOCK_DGRAM) as sock:
        sock.sendto(b"x", target)
    assert outbound == [("connect", target), ("connect_ex", target), ("sendto", target)]


def test_office_parsing_and_rule_run_stay_local(outbound: list[Any], tmp_path: Path) -> None:
    rows = dev_documents("xlsx")[:2] + dev_documents("docx")[:2]
    parsed = tmp_path / "parsed"
    parsed.mkdir()
    for input_id, path, _ in rows:
        document = parse_document(path, input_id)
        (parsed / f"{input_id}.json").write_text(document.model_dump_json())
    summary = {"parsed_ids": [i for i, _, _ in rows], "environment": {}}
    (parsed / "_summary.json").write_text(json.dumps(summary))
    run_experiment("R", "dev", None, tmp_path / "run", parsed)
    assert outbound == []


@pytest.mark.docling
def test_pdf_parsing_stays_local(outbound: list[Any]) -> None:
    input_id, path, _ = dev_documents("pdf")[0]
    assert parse_document(path, input_id).blocks
    assert outbound == []


@pytest.mark.llm
@pytest.mark.skipif(os.environ.get("RUN_LLM") != "1", reason="set RUN_LLM=1 with Ollama up")
def test_real_model_call_stays_local(onto: Ontology, outbound: list[Any], tmp_path: Path) -> None:
    input_id, path, answer = dev_documents("xlsx")[0]
    provider = OllamaProvider(DEFAULT_MODEL, AuditLog(tmp_path / "audit.jsonl"))
    result = extract(onto, parse_document(path, input_id), answer["expected_class"], provider, "C")
    assert not result.llm_failed, result.error
    assert outbound == []
