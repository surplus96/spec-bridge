"""W5-2: the registration graph, its two human stops and the deterministic edit loop."""

from pathlib import Path
from typing import Any

import pytest
from langgraph.graph.state import CompiledStateGraph

from spec_bridge.eval.locations import same_place
from spec_bridge.graph.registration import (
    GraphDeps,
    build_graph,
    open_checkpointer,
    prompt_of,
    resume,
    start,
    state_of,
)
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.pipeline import process_document
from spec_bridge.registry.output import RegistrationResult
from spec_bridge.registry.store import RegistryError
from spec_bridge.validate.validator import _allowed
from tests.api.test_app import DOC_ID, PATH, scoped_item, service_with
from tests.eval.test_experiment import FAST, classify_reply
from tests.test_pipeline import replies

CLEAN = "SYN-011"  # dev: registrable once the reviewer adds the values the sheet holds
DUPLICATE = "SYN-004"  # dev: the registry already holds this product (D-059)


class Recorder:
    def __init__(self, refuse: bool = False) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.refuse = refuse

    def register(self, job_id: str, result: RegistrationResult, edits: list[Any]) -> str:
        if self.refuse:
            raise RegistryError("duplicate identity")
        self.calls.append(("register", job_id))
        return "REG-TEST-1"

    def link(
        self, job_id: str, target_id: str, result: RegistrationResult, edits: list[Any]
    ) -> None:
        self.calls.append(("link", job_id, target_id))


def graph_for(
    tmp_path: Path, answers: list[Any], *, rag: bool = False, registrar: Recorder | None = None
) -> tuple[CompiledStateGraph[Any], Any, Recorder]:
    service = service_with(answers)
    recorder = registrar or Recorder()
    deps = GraphDeps(
        service.onto,
        service.normalizer,
        service.provider,
        service.rag if rag else None,
        service.makers,
        lambda: service.registry,
        recorder,
    )
    return build_graph(deps, open_checkpointer(tmp_path / "checkpoints.sqlite")), service, recorder


def started(
    tmp_path: Path, doc_id: str, **kw: Any
) -> tuple[CompiledStateGraph[Any], Any, Recorder]:
    graph, service, recorder = graph_for(tmp_path, [classify_reply(doc_id), {"facts": []}], **kw)
    path = FAST[doc_id][0]
    start(graph, "J", path, doc_id, path.name)
    return graph, service, recorder


def prompt(graph: CompiledStateGraph[Any], job: str = "J") -> dict[str, Any]:
    value = prompt_of(graph, job)
    assert value is not None
    return value


def edit(
    graph: CompiledStateGraph[Any],
    change: dict[str, Any],
    revision: int | None = None,
    job: str = "J",
) -> None:
    rev = prompt(graph, job)["revision"] if revision is None else revision
    resume(graph, job, {"action": "edit", "revision": rev, "edit": {"reason": "test", **change}})


def add_values_from_the_document(
    graph: CompiledStateGraph[Any], doc_id: str, job: str = "J"
) -> int:
    """What a reviewer does in S1: for each missing attribute the document does state,
    point at the block and type the value."""
    path, answer = FAST[doc_id]
    blocks = parse_document(path, doc_id).blocks
    observations = {o["observation_id"]: o for o in answer["observations"]}
    added = 0
    for attribute in prompt(graph, job)["result"]["validation"]["missing_required"]:
        fact = next((f for f in answer["facts"] if f["attribute_id"] == attribute), None)
        if fact is None:  # really absent (an E1 document)
            continue
        seen = observations[fact["observation_ids"][0]]
        block = next(i for i, b in enumerate(blocks) if same_place(seen["location"], b))
        change = {"op": "add", "attribute": attribute, "block": block}
        value = {"value_text": seen["raw_text"], "unit_text": seen["unit_text"]}
        edit(graph, change | value, job=job)
        added += 1
    return added


def test_review_before_any_edit_equals_process_document(tmp_path: Path) -> None:
    whole = service_with(replies())
    expected = process_document(
        PATH,
        DOC_ID,
        onto=whole.onto,
        normalizer=whole.normalizer,
        provider=whole.provider,
        rag=whole.rag,
        registry=whole.registry,
        makers=whole.makers,
    )
    graph, _, _ = graph_for(tmp_path, replies(), rag=True)
    start(graph, "J", PATH, DOC_ID, PATH.name)
    shown = RegistrationResult.model_validate(prompt(graph)["result"])
    assert shown.class_id == expected.class_id and shown.facts == expected.facts
    assert shown.unresolved == expected.unresolved and shown.validation == expected.validation
    assert shown.matches == expected.matches and shown.status == expected.status


def test_unknown_class_waits_for_a_choice(tmp_path: Path) -> None:
    unknown = {"product_class": "unknown", "reason": "test"}
    graph, _, _ = graph_for(tmp_path, [unknown, {"facts": []}])
    start(graph, "J", PATH, DOC_ID, PATH.name)
    assert prompt(graph)["kind"] == "choose_class"

    resume(graph, "J", {"action": "choose_class", "class_id": "NotAClass"})
    assert prompt(graph)["kind"] == "choose_class" and prompt(graph)["notice"]

    expected = FAST[DOC_ID][1]["expected_class"]
    resume(graph, "J", {"action": "choose_class", "class_id": expected})
    assert prompt(graph)["kind"] == "review"
    assert prompt(graph)["result"]["class_id"] == expected


def test_s1_edits_rerun_checks_without_the_model_then_register(tmp_path: Path) -> None:
    graph, service, recorder = started(tmp_path, CLEAN)
    calls = len(service.provider.prompts)
    assert "register_new" not in prompt(graph)["allowed"]

    added = add_values_from_the_document(graph, CLEAN)

    shown = prompt(graph)
    assert added and len(service.provider.prompts) == calls  # no model after the first stop
    assert shown["revision"] == added and "register_new" in shown["allowed"]
    assert len(state_of(graph, "J")["edits"]) == added
    resume(graph, "J", {"action": "register_new", "revision": shown["revision"]})
    assert prompt_of(graph, "J") is None
    assert state_of(graph, "J")["outcome"] == "registered"
    assert recorder.calls == [("register", "J")]


def test_a_wrong_unit_becomes_a_finding_and_blocks_registration(tmp_path: Path) -> None:
    graph, _, recorder = started(tmp_path, CLEAN)
    add_values_from_the_document(graph, CLEAN)
    facts = prompt(graph)["result"]["facts"]
    index, fact = next((i, f) for i, f in enumerate(facts) if f["unit"] not in (None, "kg"))

    edit(
        graph, {"op": "set", "target": "fact", "index": index, "value_text": "1", "unit_text": "kg"}
    )

    shown = prompt(graph)
    codes = {
        (f["code"], tuple(f["attribute_ids"])) for f in shown["result"]["validation"]["findings"]
    }
    assert ("E2", (fact["attribute"],)) in codes
    assert "register_new" not in shown["allowed"] and shown["blockers"]
    resume(graph, "J", {"action": "register_new", "revision": shown["revision"]})
    assert "not allowed" in prompt(graph)["notice"] and recorder.calls == []


def test_a_restart_resumes_the_same_review_without_the_model(tmp_path: Path) -> None:
    graph, _, _ = started(tmp_path, CLEAN)
    before = prompt(graph)

    again, service, _ = graph_for(tmp_path, [])  # new process: same checkpoint file, no replies
    assert prompt_of(again, "J") == before
    edit(again, {"op": "remove", "target": "fact", "index": 0})
    assert prompt_of(again, "J") is not None and service.provider.prompts == []


def test_a_command_from_an_old_screen_is_not_applied_twice(tmp_path: Path) -> None:
    graph, _, _ = started(tmp_path, CLEAN)
    added = add_values_from_the_document(graph, CLEAN)
    change = {"op": "remove", "target": "fact", "index": 0}
    edit(graph, change, revision=added)
    edit(graph, change, revision=added)  # double submit
    assert "out of date" in prompt(graph)["notice"]
    assert len(state_of(graph, "J")["edits"]) == added + 1


def test_s2_a_duplicate_is_linked_not_registered(tmp_path: Path) -> None:
    graph, _, recorder = started(tmp_path, DUPLICATE)
    add_values_from_the_document(graph, DUPLICATE)
    shown = prompt(graph)
    assert "register_new" not in shown["allowed"] and "link" in shown["allowed"]
    assert any(b.startswith("동일 제품 REG-COMP-009") for b in shown["blockers"])

    resume(graph, "J", {"action": "link", "revision": shown["revision"], "target_id": "NOPE"})
    assert "not a match" in prompt(graph)["notice"]
    resume(
        graph, "J", {"action": "link", "revision": shown["revision"], "target_id": "REG-COMP-009"}
    )
    assert state_of(graph, "J")["outcome"] == "linked"
    assert recorder.calls == [("link", "J", "REG-COMP-009")]


def test_a_store_refusal_returns_to_review(tmp_path: Path) -> None:
    graph, _, _ = started(tmp_path, CLEAN, registrar=Recorder(refuse=True))
    add_values_from_the_document(graph, CLEAN)
    resume(graph, "J", {"action": "register_new", "revision": prompt(graph)["revision"]})
    assert "등록 저장소가 거부함" in prompt(graph)["notice"]
    assert state_of(graph, "J")["outcome"] is None


def test_an_unparsable_file_offers_cancel_only(tmp_path: Path) -> None:
    broken = tmp_path / "broken.xlsx"
    broken.write_bytes(b"not a workbook")
    graph, _, _ = graph_for(tmp_path, [])
    start(graph, "J", broken, "UP-broken", broken.name)
    shown = prompt(graph)
    assert shown["allowed"] == ["cancel"] and shown["blockers"][0].startswith("처리 실패 — parse:")

    edit(graph, {"op": "remove", "target": "fact", "index": 0})
    assert "not allowed" in prompt(graph)["notice"]
    resume(graph, "J", {"action": "cancel", "reason": "wrong file"})
    assert prompt_of(graph, "J") is None and state_of(graph, "J")["outcome"] == "cancelled"


@pytest.mark.parametrize("answer", [{"action": "fly"}, {"no": "action"}, "text"])
def test_a_malformed_answer_is_a_notice_not_a_crash(tmp_path: Path, answer: Any) -> None:
    graph, _, _ = started(tmp_path, CLEAN)
    resume(graph, "J", answer)
    assert prompt(graph)["notice"].startswith("not a command")


def test_acknowledging_a_review_finding_lifts_only_that_blocker(tmp_path: Path) -> None:
    graph, _, _ = started(tmp_path, CLEAN)
    add_values_from_the_document(graph, CLEAN)
    facts = prompt(graph)["result"]["facts"]
    index = next(i for i, f in enumerate(facts) if f["unit"] is not None)
    edit(
        graph,
        {"op": "set", "target": "fact", "index": index, "value_text": "1", "unit_text": "zzz"},
    )
    shown = prompt(graph)
    (key,) = shown["review_keys"]
    assert "acknowledge" in shown["allowed"]
    assert any(b.startswith("REVIEW") for b in shown["blockers"])

    ack = {"action": "acknowledge", "revision": shown["revision"]}
    resume(graph, "J", ack | {"keys": ["REVIEW|nothing"]})
    assert "no such REVIEW finding" in prompt(graph)["notice"]
    resume(graph, "J", ack | {"keys": [key]})
    after = prompt(graph)
    assert after["acknowledged"] == [key] and after["revision"] == shown["revision"] + 1
    assert not any(b.startswith("REVIEW") for b in after["blockers"])
    assert any(b.startswith("E1") for b in after["blockers"])  # the value is still unread


def test_a_rejected_context_field_marks_its_fact_for_checking(tmp_path: Path) -> None:
    """D-069: the review shows where verification refused the model's context."""
    fact, item = scoped_item()
    unsupported = {"scope": {"value": "nowhere", "evidence": "nowhere"}}
    graph, _, _ = graph_for(
        tmp_path, [classify_reply(DOC_ID), {"facts": [item]}, unsupported], rag=True
    )
    start(graph, "J", PATH, DOC_ID, PATH.name)
    (hint,) = prompt(graph)["context_hints"]
    assert hint["fact_index"] == 0 and hint["attribute"] == fact["attribute_id"]
    assert hint["reasons"] == ["scope: phrase not in the remarks"]
    assert hint["messages"] == ["범위 — 범위 구절이 비고에 없음"]


def test_an_accepted_context_gives_no_hint(tmp_path: Path) -> None:
    graph, _, _ = graph_for(tmp_path, replies(), rag=True)
    start(graph, "J", PATH, DOC_ID, PATH.name)
    assert prompt(graph)["context_hints"] == []


def test_the_review_lists_edits_edited_facts_and_the_class_attributes(tmp_path: Path) -> None:
    graph, service, _ = started(tmp_path, CLEAN)
    added = add_values_from_the_document(graph, CLEAN)
    shown = prompt(graph)
    assert len(shown["edits"]) == added == len(shown["edited"])
    facts = shown["result"]["facts"]
    assert {facts[i]["attribute"] for i in shown["edited"]} == {
        e["attribute"] for e in shown["edits"]
    }
    assert shown["attributes"] == service.onto.attributes_of(shown["result"]["class_id"])


def test_an_unregistered_maker_blocks_registration_before_the_click(tmp_path: Path) -> None:
    """D-076: the store refuses unknown makers (no automatic new makers); the review says so
    first, instead of offering a button the store will refuse."""
    graph, _, recorder = started(tmp_path, CLEAN)
    add_values_from_the_document(graph, CLEAN)
    facts = prompt(graph)["result"]["facts"]
    index = next(i for i, f in enumerate(facts) if f["attribute"] == "maker")
    change = {"op": "set", "target": "fact", "index": index, "value_text": "Nobody Works"}
    edit(graph, change)
    shown = prompt(graph)
    assert "register_new" not in shown["allowed"]
    assert any("제조사 목록에 없음" in b for b in shown["blockers"])
    assert recorder.calls == []


def test_a_duplicate_comes_first_among_link_targets(tmp_path: Path) -> None:
    """D-079: the screen preselects the first target; a duplicate must be it, not a similar
    product that happens to come earlier in the registry."""
    graph, service, _ = graph_for(tmp_path, [classify_reply(DUPLICATE), {"facts": []}])
    service.registry.sort(key=lambda r: r["product_id"] == "REG-COMP-009")  # duplicate last
    path = FAST[DUPLICATE][0]
    start(graph, "J", path, DUPLICATE, path.name)
    add_values_from_the_document(graph, DUPLICATE)
    shown = prompt(graph)
    assert shown["result"]["matches"][-1]["registry_id"] == "REG-COMP-009"
    relations = {m["registry_id"]: m["relation"] for m in shown["result"]["matches"]}
    assert relations[shown["link_targets"][0]] == "duplicate"
    assert len(shown["link_targets"]) == len(relations)


def test_a_value_outside_the_dictionary_terms_must_be_checked_before_registering(
    tmp_path: Path,
) -> None:
    """D-091: a written value the dictionary did not turn into a term is shown, blocks
    registration until the reviewer confirms it, and goes away once corrected to a term.
    Attributes with an allowed list are left to E4 (no second warning)."""
    graph, service, _ = started(tmp_path, CLEAN)
    add_values_from_the_document(graph, CLEAN)
    onto, enums = service.onto, service.normalizer.enums
    shown = prompt(graph)
    assert shown["term_notes"] == [] and "register_new" in shown["allowed"]
    class_id = shown["result"]["class_id"]
    attribute = next(
        a for a in onto.attributes_of(class_id) if a in enums and a not in _allowed(onto, class_id)
    )
    add = {"op": "add", "attribute": attribute, "block": 0, "value_text": "Not A Listed Term"}
    edit(graph, add)
    shown = prompt(graph)
    (note,) = shown["term_notes"]
    assert note["attribute"] == attribute and note["value"] == "Not A Listed Term"
    assert "register_new" not in shown["allowed"] and "acknowledge" in shown["allowed"]
    assert any("표준 용어" in b and "(확인 필요)" in b for b in shown["blockers"])

    ack = {"action": "acknowledge", "revision": shown["revision"], "keys": [note["key"]]}
    resume(graph, "J", ack)
    confirmed = prompt(graph)
    assert confirmed["acknowledged"] == [note["key"]] and "register_new" in confirmed["allowed"]

    term = sorted(set(enums[attribute].values()))[0]
    change = {"op": "set", "target": "fact", "index": note["fact_index"], "value_text": term}
    edit(graph, change)
    assert prompt(graph)["term_notes"] == []
