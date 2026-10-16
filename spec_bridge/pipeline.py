"""Process one document end to end (W4-7, MVP): file in, registration result out.

parse -> classify -> extract values (mode C, optional context) -> RAG qualifiers (E1SV:
retrieved cases, code checks, Self-RAG support check, attribute conflicts) -> normalize ->
validate (E1-E5) -> duplicate/similar against the registry -> standard JSON.

Failures never raise: a file that cannot be parsed or a model that gives no usable answer
yields a `needs_review` result with the reason (plan 5-1: unknown is not a pass).
"""

from pathlib import Path
from typing import Any

from spec_bridge.dedup.matcher import Match, match
from spec_bridge.extract.classifier import UNKNOWN, classify
from spec_bridge.extract.extractor import Extraction, extract
from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.normalize.values import Normalizer, normalize_extraction
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.parse.blocks import ParsedDocument, ParseError
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.rag.pipeline import RagSetup, qualify_extraction
from spec_bridge.registry.identity import MakerIndex
from spec_bridge.registry.output import RegistrationResult, decide_status
from spec_bridge.validate.validator import Validation, validate

NOT_VALIDATED = Validation(
    findings=[], missing_required=[], presence="unknown_class", status="needs_review"
)


def _failed(
    document_id: str, file_name: str | None, reason: str, **known: Any
) -> RegistrationResult:
    return RegistrationResult(
        document_id=document_id,
        file_name=file_name,
        class_id=known.get("class_id", UNKNOWN),
        class_candidates=known.get("class_candidates", []),
        validation=NOT_VALIDATED,
        status="needs_review",
        failure=reason,
        provenance=known.get("provenance", {}),
    )


# Steps (W5-1): the registration graph runs these as its nodes; parsing and classification
# are `parse_document` and `classify` themselves.


def extract_step(
    onto: Ontology,
    document: ParsedDocument,
    class_id: str,
    provider: JsonProvider,
    rag: RagSetup | None,
) -> tuple[Extraction, list[dict[str, Any]]]:
    """Values (mode C, optional context), then the RAG qualifiers (E1SV), with the chain's
    records (fields kept and rejected per value; the review screen shows the rejected ones,
    D-069). A failed extraction comes back as it is (`llm_failed`), without qualifiers."""
    extraction = extract(onto, document, class_id, provider, "C", "optional")
    if extraction.llm_failed or rag is None:
        return extraction, []
    # production: no family is left out of the knowledge base
    return qualify_extraction(rag, document, extraction, None)


def normalize_step(
    onto: Ontology, extraction: Extraction, normalizer: Normalizer
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic normalization: candidate facts and the unresolved values as rows."""
    facts, unresolved = normalize_extraction(onto, extraction, normalizer)
    return facts, [u.model_dump() for u in unresolved]


def check_step(
    onto: Ontology,
    class_id: str,
    facts: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    registry: list[dict[str, Any]],
    makers: MakerIndex,
) -> tuple[Validation, list[Match]]:
    """Validation (E1-E5, REVIEW) and duplicate/similar judgement; no model. Runs again
    after every human edit."""
    return validate(onto, class_id, facts, unresolved), match(class_id, facts, registry, makers)


def process_document(
    path: Path,
    document_id: str,
    *,
    onto: Ontology,
    normalizer: Normalizer,
    provider: JsonProvider,
    rag: RagSetup | None,
    registry: list[dict[str, Any]],
    makers: MakerIndex,
    provenance: dict[str, Any] | None = None,
    file_name: str | None = None,
) -> RegistrationResult:
    info = dict(provenance or {})
    try:
        document = parse_document(path, document_id)
    except ParseError as error:
        return _failed(document_id, file_name, f"parse: {error.reason}", provenance=info)
    info["parser"] = document.parser
    try:
        chosen = classify(onto, document, provider)
    except LlmError as error:
        return _failed(document_id, file_name, f"classify: {error.reason}", provenance=info)
    candidates = [s.class_id for s in chosen.top_k]
    known: dict[str, Any] = {
        "class_id": chosen.chosen,
        "class_candidates": candidates,
        "provenance": info,
    }
    if chosen.chosen == UNKNOWN:
        return _failed(document_id, file_name, "class unknown", **known)
    extraction, _ = extract_step(onto, document, chosen.chosen, provider, rag)
    if extraction.llm_failed:
        return _failed(document_id, file_name, f"extract: {extraction.error}", **known)
    facts, unresolved = normalize_step(onto, extraction, normalizer)
    validation, matches = check_step(onto, chosen.chosen, facts, unresolved, registry, makers)
    return RegistrationResult(
        document_id=document_id,
        file_name=file_name,
        class_id=chosen.chosen,
        class_candidates=candidates,
        facts=facts,
        unresolved=unresolved,
        validation=validation,
        matches=matches,
        status=decide_status(validation, matches, None),
        provenance=info,
    )
