"""Registration graph (W5-2, D-062): the pipeline steps as LangGraph nodes, two human stops.

    START → parse → classify ─(unknown)→ choose_class ⏸ ─┐
                       └──────(leaf)──→ extract ←────────┘
    extract → normalize → check → review ⏸
    review ⏸ ─ edit ─→ apply_edit → check → review ⏸   (deterministic: no model)
             ─ acknowledge / refused command ─→ review ⏸
             ─ register_new / link ─→ register → END (or back to check on a store refusal)
             ─ cancel ─→ END
    a parse / classify / extract failure goes straight to review ⏸ (cancel only)

`interrupt()` pauses a node and saves the state in the checkpointer; `Command(resume=…)`
runs that node again from its start with the answer. So the two paused nodes have no side
effects, and the only writes to the registry happen in `register`, which the store makes
idempotent per job (W5-3). Model calls happen before the first stop and are never
repeated: their results are in the checkpoint.
"""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from spec_bridge.dedup.matcher import Match
from spec_bridge.extract.classifier import UNKNOWN, classify
from spec_bridge.extract.extractor import Extraction
from spec_bridge.graph.state import (
    COMMAND,
    Acknowledge,
    Action,
    Cancel,
    ChooseClass,
    ClassPrompt,
    ContextHint,
    Edit,
    JobState,
    Link,
    RegisterNew,
    ReviewPrompt,
    UnresolvedNote,
)
from spec_bridge.llm.provider import JsonProvider, LlmError
from spec_bridge.normalize.values import Normalizer
from spec_bridge.ontology.definitions import Ontology
from spec_bridge.parse.blocks import ParsedDocument, ParseError
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.pipeline import NOT_VALIDATED, check_step, extract_step, normalize_step
from spec_bridge.rag.pipeline import RagSetup
from spec_bridge.registry.edits import EditRejected, apply_edit
from spec_bridge.registry.explain import (
    duplicate_blocker,
    explain_context_reason,
    explain_finding,
    explain_unresolved,
    place_of,
    shown_value,
    unknown_maker_blocker,
)
from spec_bridge.registry.identity import MakerIndex
from spec_bridge.registry.output import RegistrationResult, decide_status
from spec_bridge.registry.store import RegistryError, canonical
from spec_bridge.registry.terms import Enums, term_notes
from spec_bridge.validate.findings import Finding
from spec_bridge.validate.validator import Validation


class Registrar(Protocol):
    """The registry writes (W5-3); both are idempotent per job."""

    def register(
        self, job_id: str, result: RegistrationResult, edits: list[dict[str, Any]]
    ) -> str: ...

    def link(
        self,
        job_id: str,
        target_id: str,
        result: RegistrationResult,
        edits: list[dict[str, Any]],
    ) -> None: ...


def now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class GraphDeps:
    onto: Ontology
    normalizer: Normalizer
    provider: JsonProvider
    rag: RagSetup | None
    makers: MakerIndex
    registry: Callable[[], list[dict[str, Any]]]  # current records: registrations count too
    registrar: Registrar
    provenance: dict[str, Any] = field(default_factory=dict)
    clock: Callable[[], str] = now


def leaf_classes(onto: Ontology) -> list[str]:
    return sorted(c for c, cls in onto.classes.items() if not cls.abstract)


def finding_key(finding: Finding) -> str:
    """Stable across re-validation: the same problem keeps its key."""
    return f"{finding.code}|{','.join(finding.attribute_ids)}|{finding.rule_ref}"


def _document(state: JobState) -> ParsedDocument:
    return ParsedDocument.model_validate_json(json.dumps(state["document"]))


def result_of(state: JobState, provenance: dict[str, Any]) -> RegistrationResult:
    """The standard JSON for the job as it stands (FR-11)."""
    failure = state.get("failure")
    validation = (
        Validation.model_validate_json(json.dumps(state["validation"]))
        if "validation" in state and failure is None
        else NOT_VALIDATED
    )
    matches = [Match.model_validate_json(json.dumps(m)) for m in state.get("matches", [])]
    info = dict(provenance)
    if "document" in state:
        info["parser"] = state["document"]["parser"]
    return RegistrationResult(
        document_id=state["document_id"],
        file_name=state.get("file_name"),
        class_id=state.get("class_id", UNKNOWN),
        class_candidates=state.get("class_candidates", []),
        facts=state.get("facts", []),
        unresolved=state.get("unresolved", []),
        validation=validation,
        matches=matches,
        status=decide_status(validation, matches, failure),
        failure=failure,
        provenance=info,
    )


def context_hints(state: JobState, onto: Ontology) -> list[ContextHint]:
    """Facts whose context the model proposed but verification rejected (D-069): where the
    reviewer should look first. Nothing is changed; a context the model never proposed
    leaves no record, so no hint is not proof the context is complete."""
    records = [r for r in state.get("qualifier_records", []) if r.get("kind") == "value"]
    hints = []
    for index, fact in enumerate(state.get("facts", [])):
        places = [o["location"] for o in fact["occurrences"]]
        reasons: list[str] = []
        for record in records:
            if record["attribute"] == fact["attribute"] and record.get("location") in places:
                reasons += [r for r in record["rejected"] if r not in reasons]
        messages = [m for r in reasons if (m := explain_context_reason(onto, r)) is not None]
        if messages:  # an axis the ontology lacks was invented by the model: not a hint
            hints.append(
                ContextHint(
                    fact_index=index,
                    attribute=fact["attribute"],
                    reasons=reasons,
                    messages=list(dict.fromkeys(messages)),
                )
            )
    return hints


def edited_facts(state: JobState) -> list[int]:
    """Facts that are a reviewer's edit, by the rule the store uses for `human_edit`."""
    after = {canonical(e["after"]) for e in state.get("edits", []) if e["outcome"] == "fact"}
    return [i for i, fact in enumerate(state.get("facts", [])) if canonical(fact) in after]


def review_prompt(
    state: JobState,
    provenance: dict[str, Any],
    onto: Ontology,
    makers: MakerIndex,
    enums: Enums,
) -> ReviewPrompt:
    """What the reviewer may do now (D-063). The screen shows this; it decides nothing."""
    result = result_of(state, provenance)
    acknowledged = state.get("acknowledged", [])
    allowed: list[Action] = ["cancel"]
    blockers: list[str] = []
    review_keys: list[str] = []
    targets: list[str] = []
    terms = [] if result.failure else term_notes(onto, result.class_id, result.facts, enums)
    notes = [
        explain_finding(onto, result.class_id, f, result.unresolved)
        for f in result.validation.findings
    ]
    if result.failure is not None:
        blockers.append(f"처리 실패 — {result.failure}")
    else:
        for finding, note in zip(result.validation.findings, notes, strict=True):
            key = finding_key(finding)
            if finding.code != "REVIEW":
                blockers.append(note)
                continue
            review_keys.append(key)
            if key not in acknowledged:
                blockers.append(f"{note} (확인 필요)")
        blockers += [f"{t.message} (확인 필요)" for t in terms if t.key not in acknowledged]
        for m in result.matches:
            if m.relation == "duplicate":
                blockers.append(duplicate_blocker(m.registry_id))
        maker = next((f["value"] for f in result.facts if f["attribute"] == "maker"), None)
        if isinstance(maker, str) and makers.resolve(maker) is None:
            blockers.append(unknown_maker_blocker(maker))  # the store would refuse it (D-076)
        # duplicates first: the screen preselects the first target (D-079)
        ordered = sorted(result.matches, key=lambda m: m.relation != "duplicate")
        targets = [m.registry_id for m in ordered]
        allowed = ["edit"]
        if review_keys or terms:
            allowed.append("acknowledge")
        if not blockers:
            allowed.append("register_new")
        if targets:
            allowed.append("link")
        allowed.append("cancel")
    return ReviewPrompt(
        revision=state.get("revision", 0),
        result=result,
        allowed=allowed,
        blockers=blockers,
        link_targets=targets,
        review_keys=review_keys,
        acknowledged=acknowledged,
        context_hints=[] if result.failure else context_hints(state, onto),
        term_notes=terms,
        finding_notes=notes,
        unresolved_notes=[
            UnresolvedNote(
                shown=shown_value(r["value_text"], r["unit_text"]),
                explanation=explain_unresolved(onto, r),
                place=place_of(
                    r["occurrence"].get("location", {}), r["occurrence"].get("label_text")
                ),
            )
            for r in result.unresolved
        ],
        edits=state.get("edits", []),
        edited=edited_facts(state),
        attributes=(onto.attributes_of(result.class_id) if result.class_id in onto.classes else []),
        notice=state.get("notice"),
    )


def build_graph(deps: GraphDeps, checkpointer: BaseCheckpointSaver[Any]) -> CompiledStateGraph[Any]:
    onto = deps.onto

    def parse(state: JobState) -> dict[str, Any]:
        try:
            document = parse_document(Path(state["path"]), state["document_id"])
        except ParseError as error:
            return {"failure": f"parse: {error.reason}"}
        return {"document": document.model_dump(mode="json")}

    def classify_node(state: JobState) -> dict[str, Any]:
        try:
            chosen = classify(onto, _document(state), deps.provider)
        except LlmError as error:
            return {"failure": f"classify: {error.reason}"}
        candidates = [s.class_id for s in chosen.top_k]
        return {"class_id": chosen.chosen, "class_candidates": candidates}

    def choose_class(state: JobState) -> dict[str, Any]:
        prompt = ClassPrompt(
            candidates=state.get("class_candidates", []),
            classes=leaf_classes(onto),
            notice=state.get("notice"),
        )
        answer = interrupt(prompt.model_dump(mode="json"))
        try:
            command = COMMAND.validate_python(answer)
        except ValidationError as error:
            return {"notice": f"not a command: {error.errors()[0]['msg']}"}
        if isinstance(command, Cancel):
            return {"outcome": "cancelled", "notice": None}
        if not isinstance(command, ChooseClass) or command.class_id not in prompt.classes:
            return {"notice": "choose one of the listed classes, or cancel"}
        return {"class_id": command.class_id, "notice": None}

    def extract(state: JobState) -> dict[str, Any]:
        extraction, records = extract_step(
            onto, _document(state), state["class_id"], deps.provider, deps.rag
        )
        if extraction.llm_failed:
            return {"failure": f"extract: {extraction.error}"}
        return {"extraction": extraction.model_dump(mode="json"), "qualifier_records": records}

    def normalize(state: JobState) -> dict[str, Any]:
        extraction = Extraction.model_validate_json(json.dumps(state["extraction"]))
        facts, unresolved = normalize_step(onto, extraction, deps.normalizer)
        return {"facts": facts, "unresolved": unresolved}

    def check(state: JobState) -> dict[str, Any]:
        validation, matches = check_step(
            onto,
            state["class_id"],
            state["facts"],
            state["unresolved"],
            deps.registry(),
            deps.makers,
        )
        return {
            "validation": validation.model_dump(mode="json"),
            "matches": [m.model_dump(mode="json") for m in matches],
        }

    def review(state: JobState) -> dict[str, Any]:
        prompt = review_prompt(state, deps.provenance, onto, deps.makers, deps.normalizer.enums)
        answer = interrupt(prompt.model_dump(mode="json"))
        try:
            command = COMMAND.validate_python(answer)
        except ValidationError as error:
            return {"notice": f"not a command: {error.errors()[0]['msg']}", "pending": None}
        if isinstance(command, Cancel):
            return {"outcome": "cancelled", "notice": None, "pending": None}
        if isinstance(command, ChooseClass) or command.action not in prompt.allowed:
            why = "; ".join(prompt.blockers) or "not offered on this screen"
            return {"notice": f"{command.action} is not allowed now: {why}", "pending": None}
        if command.revision != prompt.revision:
            return {
                "notice": f"this screen is out of date (revision {command.revision}, "
                f"now {prompt.revision}); nothing was changed",
                "pending": None,
            }
        if isinstance(command, Acknowledge):
            keys = {*prompt.review_keys, *(t.key for t in prompt.term_notes)}
            unknown = sorted(set(command.keys) - keys)
            if unknown:
                return {"notice": f"no such REVIEW finding or term: {unknown}", "pending": None}
            return {
                "acknowledged": sorted(set(prompt.acknowledged) | set(command.keys)),
                "revision": prompt.revision + 1,
                "notice": None,
                "pending": None,
            }
        if isinstance(command, Link) and command.target_id not in prompt.link_targets:
            return {"notice": f"{command.target_id} is not a match of this document"}
        return {"pending": command.model_dump(mode="json"), "notice": None}

    def apply_edit_node(state: JobState) -> dict[str, Any]:
        command = Edit.model_validate_json(json.dumps(state["pending"]))
        edits = state.get("edits", [])
        try:
            facts, unresolved, record = apply_edit(
                onto,
                deps.normalizer,
                _document(state),
                state["class_id"],
                state["facts"],
                state["unresolved"],
                command.edit,
                f"{state['job_id']}-E{len(edits) + 1}",
                deps.clock(),
            )
        except EditRejected as error:
            return {"notice": f"edit refused: {error}", "pending": None}
        return {
            "facts": facts,
            "unresolved": unresolved,
            "edits": [*edits, record],
            "revision": state.get("revision", 0) + 1,
            "pending": None,
        }

    def register(state: JobState) -> dict[str, Any]:
        command = COMMAND.validate_python(state["pending"])
        result = result_of(state, deps.provenance)
        try:
            if isinstance(command, RegisterNew):
                product_id = deps.registrar.register(
                    state["job_id"], result, state.get("edits", [])
                )
                return {"product_id": product_id, "outcome": "registered", "pending": None}
            assert isinstance(command, Link)
            deps.registrar.link(state["job_id"], command.target_id, result, state.get("edits", []))
        except RegistryError as error:
            return {"notice": f"등록 저장소가 거부함: {error}", "pending": None}
        return {"product_id": command.target_id, "outcome": "linked", "pending": None}

    def after_parse(state: JobState) -> str:
        return "review" if state.get("failure") else "classify"

    def after_classify(state: JobState) -> str:
        if state.get("failure"):
            return "review"
        return "choose_class" if state["class_id"] == UNKNOWN else "extract"

    def after_choice(state: JobState) -> str:
        if state.get("outcome"):
            return END
        return "extract" if state.get("class_id") in leaf_classes(onto) else "choose_class"

    def after_extract(state: JobState) -> str:
        return "review" if state.get("failure") else "normalize"

    def after_review(state: JobState) -> str:
        if state.get("outcome"):
            return END
        pending = state.get("pending")
        if pending is None:
            return "review"
        return "apply_edit" if pending["action"] == "edit" else "register"

    def after_register(state: JobState) -> str:
        return END if state.get("outcome") else "check"  # refused: judge again, then review

    graph = StateGraph(JobState)
    graph.add_node("parse", parse)
    graph.add_node("classify", classify_node)
    graph.add_node("choose_class", choose_class)
    graph.add_node("extract", extract)
    graph.add_node("normalize", normalize)
    graph.add_node("check", check)
    graph.add_node("review", review)
    graph.add_node("apply_edit", apply_edit_node)
    graph.add_node("register", register)
    graph.add_edge(START, "parse")
    graph.add_conditional_edges("parse", after_parse, ["classify", "review"])
    graph.add_conditional_edges("classify", after_classify, ["choose_class", "extract", "review"])
    graph.add_conditional_edges("choose_class", after_choice, ["choose_class", "extract", END])
    graph.add_conditional_edges("extract", after_extract, ["normalize", "review"])
    graph.add_edge("normalize", "check")
    graph.add_edge("check", "review")
    graph.add_conditional_edges("review", after_review, ["review", "apply_edit", "register", END])
    graph.add_edge("apply_edit", "check")
    graph.add_conditional_edges("register", after_register, ["check", END])
    return graph.compile(checkpointer=checkpointer)


def open_checkpointer(path: Path) -> SqliteSaver:
    """Checkpoints in their own SQLite file (D-064)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))


def _config(job_id: str) -> Any:
    return {"configurable": {"thread_id": job_id}}


def start(
    graph: CompiledStateGraph[Any], job_id: str, path: Path, document_id: str, file_name: str | None
) -> None:
    """Run a new job until its first stop (or its end)."""
    first: JobState = {
        "job_id": job_id,
        "document_id": document_id,
        "file_name": file_name,
        "path": str(path),
        "edits": [],
        "acknowledged": [],
        "revision": 0,
        "pending": None,
        "notice": None,
        "failure": None,
        "product_id": None,
        "outcome": None,
    }
    graph.invoke(first, _config(job_id))


def resume(graph: CompiledStateGraph[Any], job_id: str, command: dict[str, Any]) -> None:
    """Answer the job's current stop; the graph runs until the next stop (or its end)."""
    graph.invoke(Command(resume=command), _config(job_id))


def prompt_of(graph: CompiledStateGraph[Any], job_id: str) -> dict[str, Any] | None:
    """The waiting prompt, or None when the job is running, finished or unknown."""
    snapshot = graph.get_state(_config(job_id))
    if not snapshot.interrupts:
        return None
    value: dict[str, Any] = snapshot.interrupts[0].value
    return value


def state_of(graph: CompiledStateGraph[Any], job_id: str) -> JobState:
    return cast(JobState, graph.get_state(_config(job_id)).values)
