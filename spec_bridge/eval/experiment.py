"""Experiment runner (W3-7): one configuration over the dev split, scored and recorded.

Run (R needs no model; A/B/C call the local Ollama model by default):
    uv run python -m spec_bridge.eval.experiment --config R
    uv run python -m spec_bridge.eval.experiment --config C --provider openai  # D-034
Writes var/eval/<run_id>/{predictions/*.json, scores.json, metrics.json, run.json,
audit.jsonl}. Every answer stays in the inventory: an unparsed document or an LLM
failure becomes a failed prediction and its gold facts count as misses.
"""

import argparse
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spec_bridge.envfile import load_env_file
from spec_bridge.eval import handwritten
from spec_bridge.eval.freeze import FREEZE, verify
from spec_bridge.eval.rescore import evaluation_hashes, scorer_id
from spec_bridge.eval.scoring import Prediction, score_split
from spec_bridge.extract.classifier import UNKNOWN, classify
from spec_bridge.extract.extractor import Config, Extraction, extract
from spec_bridge.extract.rules import rule_extract
from spec_bridge.extract.schemas import ContextStyle
from spec_bridge.llm.audit import AuditLog
from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.normalize.dictionary import OUTPUT as DICTIONARY
from spec_bridge.normalize.dictionary import load_dictionary, split_answers
from spec_bridge.normalize.values import Normalizer, normalize_extraction
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.parse.blocks import ParsedDocument
from spec_bridge.parse.run import environment
from spec_bridge.rag.knowledge import documents_by_split
from spec_bridge.rag.pipeline import RagSetup, qualifier_summary, qualify_extraction
from spec_bridge.service import (
    make_provider,
    make_rag,
    normalizer_for,
    prompt_hashes,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "ontology/ontology.yaml"


def predict(
    onto: Ontology,
    document: ParsedDocument,
    config: Config,
    provider: JsonProvider | None,
    normalizer: Normalizer,
    labels: dict[str, str],
    context: ContextStyle = "required_none",
    rag: RagSetup | None = None,
    family_id: str | None = None,
) -> tuple[Prediction, Extraction | None, list[dict[str, Any]]]:
    """One document -> prediction, the raw extraction and (config E) qualifier records."""
    doc_id = document.document_id
    try:
        chosen = classify(onto, document, None if config == "R" else provider)
    except LlmError as error:
        return Prediction(document_id=doc_id, class_id=UNKNOWN, failure=error.reason), None, []
    candidates = [s.class_id for s in chosen.top_k]
    base = Prediction(document_id=doc_id, class_id=chosen.chosen, class_candidates=candidates)
    if chosen.chosen == UNKNOWN:
        return base, None, []
    records: list[dict[str, Any]] = []
    if config == "R":
        extraction = rule_extract(onto, document, chosen.chosen, labels)
    else:
        assert provider is not None
        mode = "C" if config == "E" else config  # E extracts like C, then qualifies
        style: ContextStyle = "optional" if config == "E" else context
        extraction = extract(onto, document, chosen.chosen, provider, mode, style)
        if extraction.llm_failed:
            return base.model_copy(update={"failure": extraction.error}), extraction, []
        if config == "E":
            assert rag is not None
            extraction, records = qualify_extraction(rag, document, extraction, family_id)
    if config in ("R", "C", "E"):
        facts, unresolved = normalize_extraction(onto, extraction, normalizer)
        update = {"facts": facts, "unresolved": [u.model_dump() for u in unresolved]}
        return base.model_copy(update=update), extraction, records
    return base.model_copy(update={"facts": extraction.facts}), extraction, []


def run_experiment(
    config: Config,
    split: str,
    provider: JsonProvider | None,
    out_dir: Path,
    parsed_dir: Path,
    *,
    model: dict[str, Any] | None = None,
    clock: Callable[[], float] = time.perf_counter,
    context: ContextStyle = "required_none",
    rag: RagSetup | None = None,
    freeze_path: Path = FREEZE,
) -> dict[str, Any]:
    if split not in ("dev", "test", "handwritten"):
        raise ValueError(f"unknown split {split!r}")
    # D-080: the test split and the handwritten set run on the frozen system only
    frozen = verify(freeze_path) if split != "dev" else None
    if config != "R" and provider is None:
        raise ValueError(f"config {config} needs an LLM provider")
    if config == "E" and rag is None:
        raise ValueError("config E needs a RAG setup (qualifier chain)")
    families = {i: d["family_id"] for i, d in documents_by_split().items()}
    onto = load_ontology(ONTOLOGY)
    dictionary = load_dictionary()
    # handwritten documents have no registry of their own: the development master data
    normalizer = normalizer_for(onto, "dev" if split == "handwritten" else split, dictionary)
    answers = handwritten.answers() if split == "handwritten" else split_answers(split)
    summary = json.loads((parsed_dir / "_summary.json").read_text())
    parsed_ids = set(summary["parsed_ids"])
    (out_dir / "predictions").mkdir(parents=True, exist_ok=True)
    predictions: dict[str, Prediction] = {}
    latency: dict[str, float] = {}
    qualifier_records: list[dict[str, Any]] = []
    for answer in answers:
        doc_id = answer["input_id"]
        if doc_id not in parsed_ids:  # CP-S2 input contract: unparsed = failure, kept
            predictions[doc_id] = Prediction(
                document_id=doc_id, class_id=UNKNOWN, failure="not_parsed"
            )
            continue
        document = ParsedDocument.model_validate_json((parsed_dir / f"{doc_id}.json").read_text())
        started = clock()
        prediction, extraction, qualified = predict(
            onto,
            document,
            config,
            provider,
            normalizer,
            dictionary["labels"],
            context,
            rag,
            families.get(doc_id),  # leave-family-out: this family's cases are never shown
        )
        qualifier_records += qualified
        latency[doc_id] = round(clock() - started, 3)
        predictions[doc_id] = prediction
        record = {
            "prediction": prediction.model_dump(),
            "rejected": [r.model_dump() for r in extraction.rejected] if extraction else [],
            "reply": extraction.reply if extraction else None,
            "qualifiers": qualified,
        }
        (out_dir / "predictions" / f"{doc_id}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        )
    scores, metrics = score_split(answers, predictions)
    (out_dir / "scores.json").write_text(
        json.dumps([s.model_dump() for s in scores], indent=2) + "\n"
    )
    (out_dir / "metrics.json").write_text(metrics.model_dump_json(indent=2) + "\n")
    times = list(latency.values())
    run = {
        "run_id": out_dir.name,
        "config": config,
        "split": split,
        "finished_at": datetime.now(UTC).isoformat(),
        "model": model,
        "extraction": {"context": "optional" if config == "E" else context},
        "rag": (rag.info | {"qualifiers": qualifier_summary(qualifier_records)}) if rag else None,
        "failures": {d: p.failure for d, p in predictions.items() if p.failure},
        "latency_s": {
            "per_document": latency,
            "first": times[0] if times else None,
            "rest_mean": round(sum(times[1:]) / len(times[1:]), 3) if len(times) > 1 else None,
        },
        "tokens": _token_totals(out_dir / "audit.jsonl"),
        "served_by": _served_by(out_dir / "audit.jsonl"),
        "hashes": {
            "ontology": sha256_file(ONTOLOGY),
            "dev_dictionary": sha256_file(DICTIONARY),
            "prompt_modules": prompt_hashes(),
            "evaluation": evaluation_hashes(),  # CP-S3 R4: scorer and answer set
            "scorer_id": scorer_id(),
        },
        "freeze": frozen["frozen_at"] if frozen else None,
        "parse": {"summary": str(parsed_dir / "_summary.json"), **summary["environment"]},
        "environment": environment(),
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    return run


def _token_totals(audit_path: Path) -> dict[str, int]:
    rows = AuditLog(audit_path).rows()
    ok = [r for r in rows if r.get("status") == "ok"]
    return {
        "calls": len(rows),
        "errors": len(rows) - len(ok),
        "prompt": sum(r.get("prompt_tokens") or 0 for r in ok),
        "completion": sum(r.get("completion_tokens") or 0 for r in ok),
    }


def _served_by(audit_path: Path) -> list[dict[str, Any]]:
    """Distinct (resolved model, backend fingerprint) pairs that answered; cloud only."""
    pairs = {
        (r.get("model_resolved"), r.get("system_fingerprint"))
        for r in AuditLog(audit_path).rows()
        if r.get("status") == "ok" and r.get("model_resolved")
    }
    return [{"model_resolved": m, "system_fingerprint": f} for m, f in sorted(pairs, key=str)]


def run_id(config: str, provider: str, stamp: str) -> str:
    """Local runs keep the W3 naming; cloud runs say where the model ran."""
    return f"{config}-{stamp}" if provider == "ollama" else f"{config}-{provider}-{stamp}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", choices=["R", "A", "B", "C", "E"], required=True)
    parser.add_argument("--split", choices=["dev", "test", "handwritten"], default="dev")
    parser.add_argument("--provider", choices=["ollama", "openai"], default="ollama")
    parser.add_argument("--model", default=None, help="default depends on --provider")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible server (openai)")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="KEY=VALUE secrets")
    parser.add_argument("--context", choices=["optional", "required_none"], default="required_none")
    parser.add_argument(
        "--rag", choices=["e0", "e1"], default="e1", help="config E: e0 = no retrieval"
    )
    parser.add_argument("--self-check", action="store_true", help="config E: Self-RAG (R5)")
    parser.add_argument(
        "--resolve-conflicts", action="store_true", help="config E: attribute conflicts"
    )
    args = parser.parse_args()
    loaded = load_env_file(args.env_file)  # shell variables win; values are never printed
    if loaded:
        print(f"loaded from {args.env_file.name}: {', '.join(loaded)}")
    label = args.config
    if args.config == "E":
        label = (
            args.rag.upper()
            + ("S" if args.self_check else "")
            + ("V" if args.resolve_conflicts else "")
        )
    if args.config in ("A", "B", "C") and args.context == "optional":
        label += "opt"  # D-089: the optional-context row is named apart from the W4-1 design
    name = run_id(label, args.provider, datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    if args.split != "dev":  # W6: test / handwritten runs are named by their split
        name = f"{args.split}-{name}"
    out_dir = ROOT / "var/eval" / name
    provider, model = None, None
    if args.config != "R":
        audit = AuditLog(out_dir / "audit.jsonl")
        provider, model = make_provider(args.provider, args.model, args.base_url, audit)
    rag = None
    if args.config == "E":
        rag = make_rag(
            provider,
            retrieval=args.rag == "e1",
            self_check=args.self_check,
            resolve=args.resolve_conflicts,
        )
    run = run_experiment(
        args.config,
        args.split,
        provider,
        out_dir,
        ROOT / "var/parsed" / args.split,
        model=model,
        context=args.context,
        rag=rag,
    )
    metrics = json.loads((out_dir / "metrics.json").read_text())
    print(json.dumps({"run_id": name, "failures": run["failures"]}, indent=2))
    print(
        json.dumps(
            {
                k: metrics[k]
                for k in (
                    "class_top1",
                    "class_top3",
                    "class_unknown",
                    "facts_micro",
                    "facts_macro_f1_attribute",
                    "observation_recall",
                    "context_keys",
                    "context_tp",
                    "context_fp",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
