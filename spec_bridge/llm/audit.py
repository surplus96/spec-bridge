"""Append-only audit log of LLM calls (NFR-02/03): hashes, options, timing, outcome.

The JSONL file stays (experiments read it). The service may add a sink (W5-4, D-064)
that also writes each row to the registry's audit table with the job it belongs to.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.sink: Callable[[dict[str, Any]], None] | None = None

    def record(self, entry: dict[str, Any]) -> None:
        row = {"at": datetime.now(UTC).isoformat(), **entry}
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        if self.sink is not None:
            self.sink(row)

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]
