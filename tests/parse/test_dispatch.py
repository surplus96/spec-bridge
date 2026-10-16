from pathlib import Path

import pytest
from pydantic import ValidationError

from spec_bridge.parse.blocks import Block, ParseError
from spec_bridge.parse.dispatch import parse_document
from tests.conftest import load_dev_answer

INPUTS = Path(__file__).resolve().parents[2] / "data/synth/inputs"


def test_unknown_extension_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "spec.txt"
    path.write_text("Capacity 10")
    with pytest.raises(ParseError, match="unsupported"):
        parse_document(path, "X-1")


def test_truncated_file_is_reported_not_crashed(tmp_path: Path) -> None:
    load_dev_answer("SYN-004")  # guard: SYN-004 is a dev-split document
    broken = tmp_path / "broken.docx"
    broken.write_bytes((INPUTS / "SYN-004.docx").read_bytes()[:200])
    with pytest.raises(ParseError) as info:
        parse_document(broken, "SYN-004")
    assert info.value.document_id == "SYN-004"


def test_wrong_content_for_extension_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_text("not a pdf")
    with pytest.raises(ParseError, match="not a valid pdf"):
        parse_document(path, "X-2")


def test_block_requires_a_position() -> None:
    with pytest.raises(ValidationError):
        Block.model_validate({"kind": "paragraph", "text": "x", "location": {"section": "A"}})


def test_block_text_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        Block.model_validate({"kind": "paragraph", "text": "", "location": {"paragraph": 1}})
