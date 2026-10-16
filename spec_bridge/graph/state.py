"""Registration graph state and the reviewer's commands (W5-2, D-062).

The state holds only JSON values (dicts, lists, strings) so that the SQLite checkpoint
does not depend on how a library version pickles Pydantic models. Models are rebuilt at
node boundaries.

A paused graph shows a prompt (what the reviewer may do and why something is blocked);
the reviewer answers with one command. Review commands carry the revision they were made
on: a command made on an older screen is refused, not applied twice.
"""

from typing import Annotated, Any, Literal, TypedDict

from pydantic import Field, TypeAdapter

from spec_bridge.ontology.facts import StrictModel
from spec_bridge.registry.edits import FactEdit
from spec_bridge.registry.output import RegistrationResult
from spec_bridge.registry.terms import TermNote

Outcome = Literal["registered", "linked", "cancelled"]
Action = Literal["choose_class", "edit", "acknowledge", "register_new", "link", "cancel"]


class JobState(TypedDict, total=False):
    job_id: str
    document_id: str
    file_name: str | None
    path: str  # the stored upload
    document: dict[str, Any]  # ParsedDocument
    class_id: str
    class_candidates: list[str]
    extraction: dict[str, Any]  # Extraction
    qualifier_records: list[dict[str, Any]]  # RAG chain records per value (D-069)
    facts: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    validation: dict[str, Any]  # Validation
    matches: list[dict[str, Any]]  # Match
    edits: list[dict[str, Any]]  # HumanEdit rows, in order
    acknowledged: list[str]  # REVIEW finding and TERM keys the reviewer has confirmed
    revision: int  # +1 for every applied edit or acknowledgement
    pending: dict[str, Any] | None  # an accepted command waiting for its node
    notice: str | None  # why the last command was not applied
    failure: str | None  # parse / classify / extract failure
    product_id: str | None
    outcome: Outcome | None


class ChooseClass(StrictModel):
    action: Literal["choose_class"]
    class_id: str


class Edit(StrictModel):
    action: Literal["edit"]
    revision: int
    edit: FactEdit


class Acknowledge(StrictModel):
    action: Literal["acknowledge"]
    revision: int
    keys: list[str]


class RegisterNew(StrictModel):
    action: Literal["register_new"]
    revision: int


class Link(StrictModel):
    action: Literal["link"]
    revision: int
    target_id: str


class Cancel(StrictModel):
    action: Literal["cancel"]
    reason: str = ""


ResumeCommand = Annotated[
    ChooseClass | Edit | Acknowledge | RegisterNew | Link | Cancel,
    Field(discriminator="action"),
]
COMMAND: TypeAdapter[ResumeCommand] = TypeAdapter(ResumeCommand)


class ClassPrompt(StrictModel):
    kind: Literal["choose_class"] = "choose_class"
    candidates: list[str]  # the classifier's ranking
    classes: list[str]  # every leaf class
    notice: str | None = None


class ContextHint(StrictModel):
    """A fact whose basis / condition / scope the reviewer should check (D-069)."""

    fact_index: int
    attribute: str
    reasons: list[str]  # the chain's rejections, e.g. "basis.rating: evidence not in the line"
    messages: list[str] = []  # the same for a person; invented axes left out (D-072)


class UnresolvedNote(StrictModel):
    """One unread value in words (parallel to result.unresolved)."""

    shown: str  # the value as written, unit once
    explanation: str  # why it was not read
    place: str  # where, for a person ("1쪽 · Specifications · 라벨 Throughput")


class ReviewPrompt(StrictModel):
    kind: Literal["review"] = "review"
    revision: int
    result: RegistrationResult  # what would be registered now
    allowed: list[Action]
    blockers: list[str]  # why register_new is not allowed (empty when it is)
    link_targets: list[str]  # duplicate / similar registry ids
    review_keys: list[str]  # REVIEW findings to acknowledge
    acknowledged: list[str]
    context_hints: list[ContextHint] = []
    term_notes: list[TermNote] = []  # values that did not become a dictionary term (D-091)
    finding_notes: list[str] = []  # one explanation per finding, in order
    unresolved_notes: list[UnresolvedNote] = []  # one per unresolved value, in order
    edits: list[dict[str, Any]] = []  # HumanEdit rows so far (history on the screen)
    edited: list[int] = []  # indexes of facts that are a reviewer's edit (✎)
    attributes: list[str] = []  # the class's attributes (the "add" form)
    notice: str | None = None
