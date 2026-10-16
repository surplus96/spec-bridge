"""Compare parser blocks with gold observation locations (dev split only, D-020)."""

from pathlib import Path
from typing import Any

import yaml

from spec_bridge.eval.locations import contains_token, same_place
from spec_bridge.parse.blocks import ParsedDocument
from tests.conftest import MANIFEST, ROOT


def dev_documents(file_format: str) -> list[tuple[str, Path, dict[str, Any]]]:
    """(input_id, input path, gold answer) for dev-split documents of one format."""
    rows = []
    for doc in yaml.safe_load(MANIFEST.read_text())["documents"]:
        if doc["split"] == "dev" and doc["file_format"] == file_format:
            answer = yaml.safe_load((ROOT / doc["answer_path"]).read_text())
            rows.append((doc["input_id"], ROOT / doc["input_path"], answer))
    return rows


def recall(parsed: ParsedDocument, answer: dict[str, Any]) -> tuple[int, int, list[str]]:
    """(found, total, missing observation ids): same place and raw_text as a whole token."""
    missing = [
        obs["observation_id"]
        for obs in answer["observations"]
        if not any(
            same_place(obs["location"], block) and contains_token(block.text, obs["raw_text"])
            for block in parsed.blocks
        )
    ]
    total = len(answer["observations"])
    return total - len(missing), total, missing
