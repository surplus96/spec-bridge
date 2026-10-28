"""W6-6: the servers that answered a run, read from its audit log (JSONL or registry)."""

import json
import sqlite3
from pathlib import Path

from spec_bridge.llm.hosts import audit_hosts, connection_report, read_rows

LOCAL = "http://127.0.0.1:11434"
REMOTE = "https://api.example.invalid/v1/chat/completions"


def test_hosts_are_counted_and_only_loopback_is_local() -> None:
    rows = [{"base_url": LOCAL}, {"base_url": LOCAL}, {"base_url": REMOTE}, {"task": "old row"}]
    report = audit_hosts(rows)
    assert report.hosts == {LOCAL: 2, REMOTE: 1}
    assert report.outside == [REMOTE]
    assert report.unrecorded == 1  # rows written before the host was recorded
    assert not report.all_loopback


def test_a_local_run_is_all_loopback() -> None:
    report = audit_hosts([{"base_url": LOCAL}, {"base_url": "http://localhost:11434"}])
    assert report.all_loopback and report.outside == [] and report.unrecorded == 0


def test_an_empty_log_is_not_called_local() -> None:
    assert not audit_hosts([]).all_loopback


def test_rows_come_from_jsonl_or_the_registry_audit_table(tmp_path: Path) -> None:
    jsonl = tmp_path / "audit.jsonl"
    jsonl.write_text(json.dumps({"base_url": LOCAL}) + "\n")
    assert read_rows(jsonl) == [{"base_url": LOCAL}]

    db = tmp_path / "registry.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE audit_events (kind TEXT, payload_json TEXT)")
        row = json.dumps({"base_url": LOCAL})
        conn.execute("INSERT INTO audit_events VALUES ('llm_call', ?)", (row,))
        conn.execute("INSERT INTO audit_events VALUES ('upload', '{}')")
    assert read_rows(db) == [{"base_url": LOCAL}]


SAMPLE = """=== 2026-10-16T01:00:00Z
COMMAND     PID      USER   FD   TYPE  DEVICE SIZE/OFF NODE NAME
python3.1  4100 user   7u  IPv4 0x1      0t0  TCP 127.0.0.1:8000 (LISTEN)
python3.1  4100 user   9u  IPv4 0x2      0t0  TCP 127.0.0.1:61000->127.0.0.1:11434 (ESTABLISHED)
ollama     4200 user   5u  IPv4 0x3      0t0  TCP 127.0.0.1:11434->127.0.0.1:61000 (ESTABLISHED)
ollama     4200 user   6u  IPv6 0x4      0t0  TCP [::1]:11434->[::1]:61001 (ESTABLISHED)
Google     4300 user   8u  IPv4 0x5      0t0  TCP 10.0.0.2:62000->142.250.1.1:443 (ESTABLISHED)
=== 2026-10-16T01:00:01Z
COMMAND     PID      USER   FD   TYPE  DEVICE SIZE/OFF NODE NAME
ollama     4200 user   7u  IPv4 0x6      0t0  TCP 10.0.0.2:62001->34.1.2.3:443 (SYN_SENT)
"""


def test_connections_are_read_per_process_with_the_time_it_was_seen() -> None:
    report = connection_report(SAMPLE.splitlines())
    assert report.samples == 2
    assert report.peers == {
        "python3.1[4100]": ["127.0.0.1:11434"],
        "ollama[4200]": ["127.0.0.1:61000", "34.1.2.3:443", "[::1]:61001"],
    }
    assert report.outside == ["ollama[4200] -> 34.1.2.3:443"]  # the browser is not watched
    assert report.seen["python3.1[4100]"] == ("2026-10-16T01:00:00Z", "2026-10-16T01:00:00Z")
    assert report.seen["ollama[4200]"] == ("2026-10-16T01:00:00Z", "2026-10-16T01:00:01Z")


def test_a_recording_with_only_loopback_is_clean() -> None:
    lines = [line for line in SAMPLE.splitlines() if "34.1.2.3" not in line]
    assert connection_report(lines).outside == []


def test_a_registry_path_with_uri_characters_is_read(tmp_path: Path) -> None:
    """The read-only URI is built from the path, so '#' or '?' in a folder name is kept."""
    db = tmp_path / "run #2?" / "registry.sqlite"
    db.parent.mkdir()
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE audit_events (kind TEXT, payload_json TEXT)")
        conn.execute("INSERT INTO audit_events VALUES ('llm_call', ?)", (json.dumps({}),))
    conn.close()
    assert read_rows(db) == [{}]
