import copy
import errno
import socket
from pathlib import Path
from typing import Any

import pytest
import yaml

from spec_bridge.llm.provider import LOOPBACK
from spec_bridge.ontology.loader import Ontology, load_ontology
from spec_bridge.ontology.schema import build_candidate_model

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology/ontology.yaml"
MANIFEST = ROOT / "data/synth/dataset-manifest.yaml"


@pytest.fixture(scope="session")
def _raw_once() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(ONTOLOGY.read_text())
    return data


@pytest.fixture
def raw(_raw_once: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(_raw_once)


@pytest.fixture
def onto() -> Ontology:
    return load_ontology(ONTOLOGY)


def write_yaml(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "ontology.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    return path


def _documents() -> dict[str, dict[str, Any]]:
    docs = yaml.safe_load(MANIFEST.read_text())["documents"]
    return {d["input_id"]: d for d in docs}


def dev_ids() -> list[str]:
    return sorted(i for i, d in _documents().items() if d["split"] == "dev")


def load_dev_answer(input_id: str) -> dict[str, Any]:
    doc = _documents()[input_id]
    if doc["split"] != "dev":
        raise ValueError(f"{input_id} is not in the dev split (D-020)")
    answer: dict[str, Any] = yaml.safe_load((ROOT / doc["answer_path"]).read_text())
    return answer


def to_location(loc: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"section": loc.get("source_section")}
    if loc.get("pdf_page") is not None:
        out.update(pdf_page=loc["pdf_page"], bbox=loc.get("bbox"))
    if loc.get("sheet") is not None:
        out.update(sheet=loc["sheet"], cell_ref=loc["value_cell"])
    if loc.get("paragraph") is not None:
        out["paragraph"] = loc["paragraph"]
    if loc.get("table") is not None:
        out.update(table=loc["table"], row=loc["row"], column=loc["cell"])
    return {k: v for k, v in out.items() if v is not None}


def to_facts(answer: dict[str, Any], attribute: str) -> list[dict[str, Any]]:
    """Gold facts of one attribute in candidate form (evaluator metadata removed)."""
    observations = {o["observation_id"]: o for o in answer["observations"]}
    facts = []
    for fact in answer["facts"]:
        if fact["attribute_id"] != attribute:
            continue
        occurrences = [
            {
                "source_document_id": answer["input_id"],
                "raw_text": observations[oid]["raw_text"],
                "label_text": observations[oid]["label_text"],
                "unit_text": observations[oid]["unit_text"],
                "location": to_location(observations[oid]["location"]),
            }
            for oid in fact["observation_ids"]
        ]
        facts.append(
            {k: fact[k] for k in ("value", "unit", "basis", "condition", "scope")}
            | {"occurrences": occurrences}
        )
    return facts


def candidate_from_answer(onto: Ontology, answer: dict[str, Any]) -> Any:
    attrs = {f["attribute_id"]: to_facts(answer, f["attribute_id"]) for f in answer["facts"]}
    model = build_candidate_model(onto, answer["expected_class"])
    return model.model_validate({"attributes": attrs})


def first_dev_answer(expected_class: str, attribute: str) -> dict[str, Any]:
    for input_id in dev_ids():
        answer = load_dev_answer(input_id)
        has = any(f["attribute_id"] == attribute for f in answer["facts"])
        if answer["expected_class"] == expected_class and has and not answer["issues"]:
            return answer
    raise LookupError(f"no clean dev {expected_class} with {attribute}")


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
