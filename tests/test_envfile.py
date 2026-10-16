import os
from pathlib import Path

import pytest

from spec_bridge.envfile import load_env_file


@pytest.fixture(autouse=True)
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SB_A", "SB_B", "SB_C", "SB_EMPTY"):
        monkeypatch.setenv(name, "")  # record the original state so teardown removes
        monkeypatch.delenv(name)  # whatever load_env_file sets during the test


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text)
    return path


def test_pairs_are_loaded_and_their_names_returned(tmp_path: Path) -> None:
    path = write(tmp_path, "SB_A=1\nSB_B=two words\n")
    assert load_env_file(path) == ["SB_A", "SB_B"]
    assert os.environ["SB_A"] == "1" and os.environ["SB_B"] == "two words"


def test_the_shell_environment_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SB_A", "from shell")
    assert load_env_file(write(tmp_path, "SB_A=from file\n")) == []
    assert os.environ["SB_A"] == "from shell"


def test_comments_export_prefix_and_quotes(tmp_path: Path) -> None:
    text = "# comment\n\nexport SB_A='quoted'\nSB_B = \"spaced\"\nSB_C=a=b\n"
    load_env_file(write(tmp_path, text))
    assert (os.environ["SB_A"], os.environ["SB_B"], os.environ["SB_C"]) == (
        "quoted",
        "spaced",
        "a=b",
    )


def test_blank_values_are_left_unset(tmp_path: Path) -> None:
    assert load_env_file(write(tmp_path, "SB_EMPTY=\n")) == []
    assert "SB_EMPTY" not in os.environ


def test_a_missing_file_changes_nothing(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "absent.env") == []


def test_a_malformed_line_names_the_line_not_the_value(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"line 2") as error:
        load_env_file(write(tmp_path, "SB_A=1\nsk-secret-without-name\n"))
    assert "sk-secret" not in str(error.value)
