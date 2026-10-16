"""Synthetic identity policy (D-016, D-021): exact keys only; fuzzy matching is W4."""

import re
from typing import Any


def model_key(text: str) -> str:
    """Uppercase and drop spaces/hyphens: 'vx022 009' -> 'VX022009'."""
    return re.sub(r"[\s\-]", "", text).upper()


def maker_key(text: str) -> str:
    return " ".join(text.split()).casefold()


class MakerIndex:
    def __init__(self, manufacturers: list[dict[str, Any]]) -> None:
        self._ids: dict[str, str] = {}
        for maker in manufacturers:
            for name in [maker["name"], *maker.get("aliases", [])]:
                key = maker_key(name)
                if self._ids.get(key, maker["maker_id"]) != maker["maker_id"]:
                    raise ValueError(f"maker name {name!r} is shared by two makers")
                self._ids[key] = maker["maker_id"]

    def resolve(self, text: str) -> str | None:
        return self._ids.get(maker_key(text))
