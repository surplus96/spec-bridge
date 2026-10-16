import json
from pathlib import Path
from typing import Any

import pytest

from spec_bridge.eval import freeze
from spec_bridge.eval.experiment import run_experiment, run_id
from spec_bridge.eval.freeze import FreezeError
from spec_bridge.eval.rescore import rescore, scorer_id
from spec_bridge.extract.extractor import CONTEXT_GUIDE
from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.openai_compat import OpenAIProvider
from spec_bridge.llm.provider import LlmError
from spec_bridge.normalize.dictionary import dev_answers
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.service import make_provider
from tests.llm.fakes import FakeProvider
from tests.parse.goldmatch import dev_documents

FAST = {i: (p, a) for i, p, a in dev_documents("xlsx") + dev_documents("docx")}
ORDER = [a["input_id"] for a in dev_answers() if a["input_id"] in FAST]  # runner order


def write_parsed(folder: Path, ids: list[str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for input_id in ids:
        document = parse_document(FAST[input_id][0], input_id)
        (folder / f"{input_id}.json").write_text(document.model_dump_json())
    summary = {"parsed_ids": sorted(ids), "environment": {"git_commit": None}}
    (folder / "_summary.json").write_text(json.dumps(summary))
    return folder


@pytest.fixture(scope="module")
def fast_parsed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_parsed(tmp_path_factory.mktemp("parsed"), ORDER)


def classify_reply(input_id: str) -> dict[str, Any]:
    return {"product_class": FAST[input_id][1]["expected_class"], "reason": "test"}


def test_rule_run_keeps_unparsed_documents_as_failures(fast_parsed: Path, tmp_path: Path) -> None:
    run = run_experiment("R", "dev", None, tmp_path / "run", fast_parsed)
    metrics = json.loads((tmp_path / "run/metrics.json").read_text())
    unparsed = sorted(a["input_id"] for a in dev_answers() if a["input_id"] not in FAST)
    assert sorted(run["failures"]) == unparsed
    assert set(run["failures"].values()) == {"not_parsed"}
    assert metrics["documents"] == len(dev_answers())
    assert sorted(metrics["failed_documents"]) == unparsed
    assert metrics["facts_micro"]["tp"] > 0
    assert len(list((tmp_path / "run/predictions").glob("*.json"))) == len(ORDER)


def test_llm_failure_does_not_stop_the_run(tmp_path: Path) -> None:
    first, second, third = ORDER[:3]
    parsed = write_parsed(tmp_path / "parsed", [first, second, third])
    provider = FakeProvider(
        [
            LlmError("classify", "timeout"),
            classify_reply(second),
            LlmError("extract-C", "broken json"),
            classify_reply(third),
            {"facts": []},
        ]
    )
    run = run_experiment("C", "dev", provider, tmp_path / "run", parsed)
    assert run["failures"][first] == "timeout" and run["failures"][second] == "broken json"
    assert third not in run["failures"] and provider.replies == []
    scores = {s["document_id"]: s for s in json.loads((tmp_path / "run/scores.json").read_text())}
    gold_first = FAST[first][1]["facts"]
    assert scores[first]["failed"] and sum(c["fn"] for c in scores[first]["facts"].values()) > 0
    assert gold_first and scores[second]["failed"] and not scores[third]["failed"]
    assert scores[first]["predicted_class"] == "unknown"  # classification failed
    assert scores[second]["predicted_class"] == FAST[second][1]["expected_class"]  # D-031
    saved = json.loads((tmp_path / f"run/predictions/{third}.json").read_text())
    assert saved["reply"] == {"facts": []}


def test_run_record_has_hashes_and_latency(tmp_path: Path) -> None:
    parsed = write_parsed(tmp_path / "parsed", ORDER[:2])
    ticks = iter([0.0, 2.0, 10.0, 11.5])
    run = run_experiment("R", "dev", None, tmp_path / "run", parsed, clock=lambda: next(ticks))
    assert run["latency_s"]["first"] == 2.0 and run["latency_s"]["rest_mean"] == 1.5
    assert len(run["hashes"]["dev_dictionary"]) == 64
    assert set(run["hashes"]["prompt_modules"]) >= {"spec_bridge.extract.extractor"}
    evaluation = run["hashes"]["evaluation"]
    assert {"spec_bridge.eval.scoring", "spec_bridge.eval.locations", "SHA256SUMS"} <= set(
        evaluation
    )
    assert run["hashes"]["scorer_id"] == scorer_id()
    assert json.loads((tmp_path / "run/run.json").read_text()) == run


def test_rescore_writes_beside_and_keeps_the_original(tmp_path: Path) -> None:
    parsed = write_parsed(tmp_path / "parsed", ORDER[:2])
    run_experiment("R", "dev", None, tmp_path / "run", parsed)
    original = (tmp_path / "run/metrics.json").read_text()
    path = rescore(tmp_path / "run")
    assert path.name == f"rescored-{scorer_id()}.json"
    assert (tmp_path / "run/metrics.json").read_text() == original
    assert json.loads(path.read_text())["metrics"] == json.loads(original)


@pytest.mark.parametrize(
    "config, split, provider, message",
    [("R", "train", None, "unknown split"), ("B", "dev", None, "needs an LLM provider")],
)
def test_invalid_runs_are_refused(
    tmp_path: Path, config: Any, split: str, provider: Any, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_experiment(config, split, provider, tmp_path / "run", tmp_path)


def test_the_test_split_needs_the_freeze_record(tmp_path: Path) -> None:
    """D-080: no record, or a changed system, and the test split does not run."""
    with pytest.raises(FreezeError, match="no freeze record"):
        run_experiment("R", "test", None, tmp_path / "run", tmp_path, freeze_path=tmp_path / "F")
    record = freeze.write(tmp_path / "F")
    record["hashes"]["prompt_modules"]["spec_bridge.extract.extractor"] = "changed"
    (tmp_path / "F").write_text(json.dumps(record))
    with pytest.raises(FreezeError, match="prompt_modules.spec_bridge.extract.extractor"):
        run_experiment("R", "test", None, tmp_path / "run", tmp_path, freeze_path=tmp_path / "F")


def test_a_freeze_is_written_once_and_matches_the_system(tmp_path: Path) -> None:
    freeze.write(tmp_path / "F")
    assert freeze.verify(tmp_path / "F")["hashes"] == freeze.current_hashes()
    with pytest.raises(FreezeError, match="frozen once"):
        freeze.write(tmp_path / "F")


def test_run_record_lists_the_models_that_served(tmp_path: Path) -> None:
    parsed = write_parsed(tmp_path / "parsed", ORDER[:1])
    audit = AuditLog(tmp_path / "run/audit.jsonl")
    served = {"model_resolved": "gpt-4o-mini-2024-07-18", "system_fingerprint": "fp_a"}
    audit.record({"status": "ok", **served})
    audit.record({"status": "ok", **served})
    audit.record({"status": "error", "model_resolved": None})
    run = run_experiment("R", "dev", None, tmp_path / "run", parsed)
    assert run["served_by"] == [served]


def test_openai_provider_is_built_with_its_default_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OFFLINE", raising=False)
    provider, model = make_provider("openai", None, None, AuditLog(tmp_path / "a.jsonl"))
    assert isinstance(provider, OpenAIProvider)
    assert model["provider"] == "openai" and model["name"] == "gpt-4o-mini"
    assert model["options"] == {"temperature": 0, "seed": 7} and model["strict"] is False


def test_cloud_run_ids_name_the_provider() -> None:
    assert run_id("C", "ollama", "20261012T000000Z") == "C-20261012T000000Z"
    assert run_id("C", "openai", "20261012T000000Z") == "C-openai-20261012T000000Z"


@pytest.mark.parametrize("style", ["optional", "required_none"])
def test_context_style_reaches_the_extractor(tmp_path: Path, style: Any) -> None:
    """W4-1: the --context choice must reach the prompt, not only run.json (D-040)."""
    first = ORDER[0]
    parsed = write_parsed(tmp_path / "parsed", [first])
    provider = FakeProvider([classify_reply(first), {"facts": []}])
    run = run_experiment("C", "dev", provider, tmp_path / "run", parsed, context=style)
    assert run["extraction"] == {"context": style}
    assert CONTEXT_GUIDE[style] in provider.prompts[1]["user"]
