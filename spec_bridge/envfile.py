"""Minimal .env reader (D-034): KEY=VALUE lines into os.environ, standard library only.

Variables already set in the shell win, blank values stay unset, and errors name the
line number but never the value, so a misplaced secret is not echoed.
"""

import os
from pathlib import Path


def load_env_file(path: Path) -> list[str]:
    """Set variables from `path` that the environment lacks; return the names set."""
    if not path.exists():
        return []
    loaded = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        name, sep, value = text.removeprefix("export ").partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name.isidentifier():
            raise ValueError(f"{path.name} line {number}: expected KEY=VALUE")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if value and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded
