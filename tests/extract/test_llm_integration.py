"""Real-model check of the extraction path (CP-S1 L7). Needs Ollama: RUN_LLM=1."""

import os
from pathlib import Path

import pytest

from spec_bridge.extract.extractor import extract
from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.provider import DEFAULT_MODEL, OllamaProvider
from spec_bridge.ontology.loader import Ontology
from spec_bridge.parse.dispatch import parse_document
from tests.parse.goldmatch import dev_documents

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(os.environ.get("RUN_LLM") != "1", reason="set RUN_LLM=1 with Ollama up"),
]


@pytest.mark.parametrize("mode", ["B", "C"])
def test_real_model_returns_grounded_output(onto: Ontology, tmp_path: Path, mode: str) -> None:
    input_id, path, answer = dev_documents("xlsx")[0]
    provider = OllamaProvider(DEFAULT_MODEL, AuditLog(tmp_path / "audit.jsonl"))
    result = extract(onto, parse_document(path, input_id), answer["expected_class"], provider, mode)  # type: ignore[arg-type]
    grounded = len(result.facts) + len(result.raw)
    print(
        f"\n{mode}: grounded={grounded} rejected={[r.reason for r in result.rejected]}"
        f" gold_facts={len(answer['facts'])}"
    )
    assert not result.llm_failed, result.error
    assert grounded > 0
