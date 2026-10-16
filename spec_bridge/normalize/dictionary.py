"""Development dictionary (W3-5): enum display forms -> ontology tokens, per attribute,
and row labels -> attribute ids for the rule baseline R (W3-7).

Built only from dev-split gold observations (answer contract `variation_aliases`:
development dictionaries fixed before test). Run:
    uv run python -m spec_bridge.normalize.dictionary
"""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/synth/dataset-manifest.yaml"
OUTPUT = ROOT / "ontology/dev-dictionary.yaml"
IDENTITY = {"maker", "model_designation"}  # resolved from registry master data instead


def build_dev_dictionary(answers: Iterable[dict[str, Any]]) -> dict[str, Any]:
    enums: dict[str, dict[str, str]] = {}
    labels: dict[str, str] = {}
    sources: list[str] = []
    for answer in answers:
        sources.append(answer["input_id"])
        for obs in answer["observations"]:
            _add(labels, label_key(obs.get("label_text") or ""), obs["attribute_id"], "label")
            attribute, value = obs["attribute_id"], obs.get("parsed_value")
            if attribute in IDENTITY or attribute is None or obs["interpretation"] != "normalized":
                continue
            if isinstance(value, str):
                pairs = [(obs["raw_text"], value)]
            elif isinstance(value, list):
                pairs = list(zip(obs["raw_text"].split(","), value, strict=True))
            else:
                continue
            table = enums.setdefault(attribute, {})
            for raw, token in pairs:
                _add(table, raw.strip().casefold(), token, attribute)
    return {
        "origin": "synthetic",
        "source": {"split": "dev", "documents": sorted(sources)},
        "enums": {a: dict(sorted(t.items())) for a, t in sorted(enums.items())},
        "labels": dict(sorted(labels.items())),
    }


def label_key(text: str) -> str:
    """'Bore:' and 'bore' are one label."""
    return text.strip().rstrip(":").strip().casefold()


def _add(table: dict[str, str], key: str, value: str | None, where: str) -> None:
    if not key or value is None:
        return
    if table.get(key, value) != value:
        raise ValueError(f"{where}: {key!r} maps to {table[key]!r} and {value!r}")
    table[key] = value


SPLITS = ("dev", "test")


def split_answers(split: str) -> list[dict[str, Any]]:
    """Gold answers of one split. The test split is read only by the W6 evaluation."""
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; use one of {SPLITS}")
    documents = yaml.safe_load(MANIFEST.read_text())["documents"]
    return [
        yaml.safe_load((ROOT / d["answer_path"]).read_text())
        for d in documents
        if d["split"] == split
    ]


def dev_answers() -> list[dict[str, Any]]:
    return split_answers("dev")


def load_dictionary(path: Path = OUTPUT) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return data


def dictionary_sha256(path: Path = OUTPUT) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    dictionary = build_dev_dictionary(dev_answers())
    OUTPUT.write_text(yaml.safe_dump(dictionary, allow_unicode=True, sort_keys=False))
    print(json.dumps({"path": str(OUTPUT.relative_to(ROOT)), "sha256": dictionary_sha256()}))
