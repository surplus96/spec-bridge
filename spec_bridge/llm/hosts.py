"""Which model servers answered (W6-6, NFR-01): read from the audit log, not assumed.

Every provider writes `base_url` into its audit rows. A run is local when every row
names a loopback host. Rows written before W6-6 have no host and are counted apart, never
taken as local. Reads a JSONL audit file or the registry's `audit_events` table.

The audit sees the calls the code makes. The OS sees the rest (native libraries, child
processes, the model server itself): `scripts/w6_offline_watch.sh` records `lsof -nP
-iTCP` once a second and `connection_report` reads the app's and Ollama's peers from it.

Run:
    uv run python -m spec_bridge.llm.hosts var/w6-6/app/registry.sqlite
    uv run python -m spec_bridge.llm.hosts var/w6-6/connections-<time>.log
"""

import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from spec_bridge.llm.provider import LOOPBACK


@dataclass(frozen=True)
class HostReport:
    hosts: dict[str, int]  # base_url -> rows
    outside: list[str]  # hosts that are not loopback
    unrecorded: int  # rows without a host

    @property
    def all_loopback(self) -> bool:
        return bool(self.hosts) and not self.outside and self.unrecorded == 0


def audit_hosts(rows: list[dict[str, Any]]) -> HostReport:
    hosts = Counter(str(r["base_url"]) for r in rows if r.get("base_url"))
    outside = sorted(h for h in hosts if urlparse(h).hostname not in LOOPBACK)
    return HostReport(dict(hosts), outside, sum(1 for r in rows if not r.get("base_url")))


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Model-call rows of a JSONL audit file or of a registry database."""
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text().splitlines() if line]
    uri = f"{path.resolve().as_uri()}?mode=ro"  # as_uri escapes '#', '?' and '%'
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        query = "SELECT payload_json FROM audit_events WHERE kind = 'llm_call'"
        return [json.loads(payload) for (payload,) in conn.execute(query)]


WATCHED = ("python", "uvicorn", "ollama")  # lsof COMMAND prefixes: the app, the model server


@dataclass(frozen=True)
class ConnectionReport:
    samples: int
    peers: dict[str, list[str]]  # "command[pid]" -> remote endpoints seen
    outside: list[str]  # "command[pid] -> endpoint" for non-loopback peers
    seen: dict[str, tuple[str, str]]  # "command[pid]" -> first and last sample time


def _host(endpoint: str) -> str:
    host = endpoint.rsplit(":", 1)[0]
    return host.strip("[]")


def connection_report(lines: list[str]) -> ConnectionReport:
    """Remote endpoints of the watched processes in an lsof recording, per process: a
    name is not enough (other Python programs and the Ollama desktop app share them), so
    each process carries its pid and the time it was seen, to match with the server's."""
    peers: dict[str, set[str]] = {}
    seen: dict[str, tuple[str, str]] = {}
    now = ""
    for line in lines:
        if line.startswith("=== "):
            now = line[4:].strip()
            continue
        fields = line.split()
        if len(fields) < 2 or not fields[0].lower().startswith(WATCHED):
            continue
        process = f"{fields[0]}[{fields[1]}]"
        seen[process] = (seen.get(process, (now, now))[0], now)
        if "->" in line:
            peers.setdefault(process, set()).add(line.split("->", 1)[1].split()[0])
    outside = sorted(
        f"{command} -> {remote}"
        for command, remotes in peers.items()
        for remote in remotes
        if _host(remote) not in LOOPBACK
    )
    return ConnectionReport(
        samples=sum(1 for line in lines if line.startswith("=== ")),
        peers={command: sorted(remotes) for command, remotes in peers.items()},
        outside=outside,
        seen=seen,
    )


def _print_connections(path: Path) -> None:
    report = connection_report(path.read_text().splitlines())
    out = {"source": str(path), "samples": report.samples, "outside": report.outside}
    print(json.dumps(out | {"seen": report.seen}))


def main() -> None:
    for arg in sys.argv[1:]:
        if arg.endswith(".log"):
            _print_connections(Path(arg))
            continue
        report = audit_hosts(read_rows(Path(arg)))
        print(
            json.dumps(
                {
                    "source": arg,
                    "hosts": report.hosts,
                    "outside": report.outside,
                    "unrecorded": report.unrecorded,
                    "all_loopback": report.all_loopback,
                }
            )
        )


if __name__ == "__main__":
    main()
