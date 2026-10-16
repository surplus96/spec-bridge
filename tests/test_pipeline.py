"""W5-1: the pipeline steps the registration graph runs give the MVP result."""

from typing import Any

from spec_bridge.extract.classifier import classify
from spec_bridge.parse.dispatch import parse_document
from spec_bridge.pipeline import check_step, extract_step, normalize_step, process_document
from spec_bridge.registry.output import decide_status
from tests.api.test_app import ANSWER, DOC_ID, PATH, scoped_item, service_with
from tests.eval.test_experiment import classify_reply


def replies() -> list[Any]:
    fact, item = scoped_item()
    phrase = fact["scope"].replace("_", " ")
    return [
        classify_reply(DOC_ID),
        {"facts": [item]},
        {"scope": {"value": phrase, "evidence": phrase}},
    ]


def test_steps_in_order_equal_process_document() -> None:
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

    s = service_with(replies())
    document = parse_document(PATH, DOC_ID)
    class_id = classify(s.onto, document, s.provider).chosen
    extraction, records = extract_step(s.onto, document, class_id, s.provider, s.rag)
    facts, unresolved = normalize_step(s.onto, extraction, s.normalizer)
    validation, matches = check_step(s.onto, class_id, facts, unresolved, s.registry, s.makers)

    assert class_id == expected.class_id == ANSWER["expected_class"]
    assert facts == expected.facts and unresolved == expected.unresolved
    assert validation == expected.validation and matches == expected.matches
    assert decide_status(validation, matches, None) == expected.status
    assert [r["attribute"] for r in records] == [f["attribute"] for f in facts]
    assert records[0]["location"] == facts[0]["occurrences"][0]["location"]
